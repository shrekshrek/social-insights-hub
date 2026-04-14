"""Research Agent Celery 任务

使用 LangGraph stream() 逐节点执行，每步完成后写一条 progress 记录。
Celery gevent worker 中必须使用 sync invoke，不用 asyncio.run。
"""

import logging
from datetime import datetime, timezone

from src.celery_app import celery_app
from src.database import SyncSessionLocal
from src.jobs.factory import (
    create_analysis_job_sync,
    start_analysis_job_sync,
    complete_analysis_job_sync,
)
from src.jobs.models import AnalysisJob
from src.research_agent.models import ResearchTask

logger = logging.getLogger(__name__)

# 节点名称 → 中文标签
_NODE_LABELS: dict[str, str] = {
    "plan": "生成研究计划",
    "search": "搜索报告资料",
    "filter": "筛选相关内容",
    "fetch": "抓取全文",
    "analyze": "分析文档",
    "evaluate": "评估覆盖度",
    "synthesize": "综合分析报告",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_detail(node_name: str, node_output: dict) -> str:
    """从节点输出提取人可读的进度描述"""
    from urllib.parse import urlparse

    if node_name == "plan":
        plan = node_output.get("search_plan", {})
        keywords = plan.get("keywords", [])
        kw_str = "、".join(keywords[:4])
        if len(keywords) > 4:
            kw_str += f" 等 {len(keywords)} 个"
        return f"关键词：{kw_str}" if kw_str else "研究计划已生成"

    if node_name == "search":
        candidates = node_output.get("candidates", [])
        if not candidates:
            return "未找到候选内容"
        # 统计各域名出现次数
        from collections import Counter
        domains = [urlparse(c.get("url", "")).netloc.lstrip("www.") for c in candidates if c.get("url")]
        top = Counter(domains).most_common(5)
        domain_str = "、".join(f"{d}×{n}" if n > 1 else d for d, n in top)
        extra = f"，另 {len(domains) - 5} 个域名" if len(set(domains)) > 5 else ""
        return f"找到 {len(candidates)} 条：{domain_str}{extra}"

    if node_name == "fetch":
        docs = node_output.get("documents", [])
        if not docs:
            return "未能抓取到全文"
        titles = [d.get("title") or urlparse(d.get("url", "")).netloc for d in docs[:4]]
        title_str = "\n".join(f"· {t[:40]}" for t in titles if t)
        suffix = f"\n· 共 {len(docs)} 篇" if len(docs) > 4 else ""
        return title_str + suffix

    if node_name == "filter":
        selected = node_output.get("selected", [])
        if not selected:
            return "无内容通过相关性筛选"
        domains = [urlparse(s.get("url", "")).netloc.lstrip("www.") for s in selected if s.get("url")]
        domain_str = "、".join(list(dict.fromkeys(domains))[:5])
        return f"保留 {len(selected)} 条：{domain_str}"

    if node_name == "analyze":
        findings = node_output.get("findings", [])
        return f"完成 {len(findings)} 篇文档分析"

    if node_name == "evaluate":
        evaluation = node_output.get("evaluation", {})
        covered = evaluation.get("questions_covered", [])
        gaps = evaluation.get("gap_questions", [])
        if evaluation.get("should_continue"):
            gap_str = "、".join(gaps[:3])
            if len(gaps) > 3:
                gap_str += f" 等 {len(gaps)} 个"
            return f"覆盖 {len(covered)} 个问题，待补充：{gap_str}"
        return f"全部 {len(covered)} 个问题覆盖充分，进入综合分析"

    if node_name == "synthesize":
        synthesis = node_output.get("synthesis", "")
        return f"生成 {len(synthesis)} 字综合报告"

    return ""


@celery_app.task(
    name="research_agent.run_research",
    bind=True,
    max_retries=0,
    time_limit=1800,      # 4轮×~160s + synthesize(120s) + 余量 ≈ 900s；1800s 留足缓冲
    soft_time_limit=1700,
)
def run_research_task(self, research_task_id: int) -> None:
    """执行研究任务，逐节点写入 progress"""
    db = SyncSessionLocal()
    try:
        task = db.get(ResearchTask, research_task_id)
        if not task:
            logger.error("ResearchTask %d not found", research_task_id)
            return

        job = create_analysis_job_sync(
            db=db,
            user_id=task.user_id,
            analysis_type="research",
            source_count=0,
            celery_task_id=self.request.id or "",
            analysis_config=task.search_config,
        )
        task.job_id = job.id
        task.status = "running"
        task.progress = []
        db.commit()

        start_analysis_job_sync(db, job)
        db.commit()

        from src.research_agent.config import MAX_ROUNDS
        from src.research_agent.graph import research_graph

        # 从 search_config 构建 Planner 上下文：
        # - "context"：独立任务传入的 Brief 背景文本
        # - "research_scope"：策略任务的行业/地域/时间范围约束
        # - "focus_domains"：策略 research_design_chain 推荐的权威域名
        search_config = task.search_config or {}
        context_parts: list[str] = []
        if search_config.get("context"):
            context_parts.append(search_config["context"])
        scope = search_config.get("research_scope", {})
        if scope and isinstance(scope, dict):
            scope_desc = "，".join(
                f"{k}：{v}"
                for k, v in [
                    ("行业", scope.get("industry")),
                    ("地域", scope.get("geography")),
                    ("时间范围", scope.get("time_range")),
                ]
                if v
            )
            if scope_desc:
                context_parts.append(f"研究范围——{scope_desc}")
        focus_domains = search_config.get("focus_domains", [])
        if focus_domains:
            context_parts.append(f"建议优先搜索域名：{', '.join(focus_domains)}")

        initial_state = {
            "query": task.analysis_goal,
            "context": "\n".join(context_parts),
            "title": task.title or "",
            "research_questions": task.research_questions or [],
            "round": 0,
            "max_rounds": MAX_ROUNDS,
        }

        # 累积最终 state（stream 只返回每节点的 delta）
        accumulated: dict = {**initial_state, "documents": [], "findings": []}
        progress: list[dict] = []
        current_round = 1
        total_candidates = 0  # 跨轮次累计候选数

        # recursion_limit：每轮 6 节点（plan/search/filter/fetch/analyze/evaluate）
        # + 1 synthesize，留 2 倍余量避免 MAX_ROUNDS 调整时再次触顶
        recursion_limit = (MAX_ROUNDS + 1) * 6 * 2
        for step in research_graph.stream(
            initial_state,
            config={"recursion_limit": recursion_limit},
        ):
            # 每步开始前确认任务未被删除
            if not db.get(ResearchTask, research_task_id):
                logger.info("ResearchTask %d was deleted, aborting stream", research_task_id)
                return

            node_name = list(step.keys())[0]
            node_output = step[node_name]

            # 累积 state（reducer 字段追加，其余覆盖）
            # selected 跨轮累积用于构建 url_meta（LangGraph state 中每轮覆盖，但此处需要全量）
            for k, v in node_output.items():
                if k in ("documents", "findings", "selected"):
                    accumulated[k] = accumulated.get(k, []) + (v or [])
                else:
                    accumulated[k] = v

            if node_name == "plan":
                current_round = accumulated.get("round", current_round)
            if node_name == "search":
                total_candidates += len(node_output.get("candidates", []))

            entry = {
                "step": node_name,
                "label": _NODE_LABELS.get(node_name, node_name),
                "round": current_round,
                "status": "completed",
                "ts": _utcnow(),
                "detail": _extract_detail(node_name, node_output),
            }
            progress.append(entry)

            # 增量写入 DB，前端轮询可实时看到进度
            task.progress = list(progress)
            db.commit()

            logger.info(
                "ResearchTask %d [%s] round=%d: %s",
                research_task_id,
                node_name,
                current_round,
                entry["detail"],
            )

        result_state = accumulated
        selected = result_state.get("selected", [])
        findings = result_state.get("findings", [])

        # 用 selected 构建 URL → 元数据映射（补充 relevance_score / content_type 等字段）
        url_meta: dict[str, dict] = {
            s["url"]: s for s in selected if s.get("url")
        }

        # sources 按 findings 顺序枚举（与 synthesize 节点 src_N 索引一致），URL 去重
        seen_urls: set[str] = set()
        sources: list[dict] = []
        for i, f in enumerate(findings):
            url = f.get("source_url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            meta = url_meta.get(url, {})
            sources.append({
                "id": f"src_{i}",
                "title": f.get("source_title", "") or meta.get("title", ""),
                "url": url,
                "source": meta.get("source", ""),
                "source_tier": f.get("source_tier", "tier3"),
                "content_type": meta.get("content_type", "html"),
                "relevance_score": meta.get("relevance_score", 0.0),
                "published_date": f.get("published_date", ""),
            })

        if not task.title:
            generated_title = result_state.get("title", "")
            if generated_title:
                task.title = generated_title

        task.result_data = {
            "findings_by_question": result_state.get("findings_by_question", {}),
            "synthesis": result_state.get("synthesis", ""),
            "sources": sources,
            "coverage": result_state.get("coverage", {}),
            "information_gaps": result_state.get("information_gaps", []),
            "findings": result_state.get("findings", []),
        }
        task.stats = {
            "rounds": result_state.get("round", 1),
            "candidates_total": total_candidates,  # 跨轮次累计，非最后一轮
            "documents_analyzed": len(sources),
            "synthesis_length": len(result_state.get("synthesis", "")),
        }
        task.status = "completed"

        complete_analysis_job_sync(db=db, job=job, analyzed_count=len(sources))
        db.commit()

        logger.info(
            "ResearchTask %d 完成: %d 条来源, %d 字综合分析",
            research_task_id,
            len(sources),
            len(result_state.get("synthesis", "")),
        )

    except Exception as exc:
        # SoftTimeLimitExceeded 需要快速处理，hard limit (SIGKILL) 即将到来
        from billiard.exceptions import SoftTimeLimitExceeded
        is_timeout = isinstance(exc, SoftTimeLimitExceeded)
        error_msg = "任务超时（执行时间超过限制）" if is_timeout else str(exc)[:500]
        log_level = logger.warning if is_timeout else logger.error
        log_level("ResearchTask %d 失败: %s", research_task_id, exc, exc_info=not is_timeout)
        db.rollback()
        try:
            task = db.get(ResearchTask, research_task_id)
            if task:
                task.status = "failed"
                task.error_message = error_msg
                if task.job_id:
                    job = db.get(AnalysisJob, task.job_id)
                    if job:
                        complete_analysis_job_sync(db=db, job=job, error_message=error_msg)
                db.commit()
        except Exception as inner_exc:
            logger.error("更新失败状态时出错: %s", inner_exc)
            db.rollback()
    finally:
        db.close()
