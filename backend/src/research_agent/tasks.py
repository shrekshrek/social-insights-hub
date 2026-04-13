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
    if node_name == "plan":
        plan = node_output.get("search_plan", {})
        keywords = plan.get("keywords", [])
        kw_preview = "、".join(keywords[:3])
        if len(keywords) > 3:
            kw_preview += f" 等 {len(keywords)} 个"
        return f"关键词：{kw_preview}" if kw_preview else "研究计划已生成"
    if node_name == "search":
        candidates = node_output.get("candidates", [])
        return f"找到 {len(candidates)} 条候选内容"
    if node_name == "filter":
        selected = node_output.get("selected", [])
        return f"筛选保留 {len(selected)} 条高相关内容"
    if node_name == "fetch":
        docs = node_output.get("documents", [])
        return f"成功抓取 {len(docs)} 篇全文"
    if node_name == "analyze":
        findings = node_output.get("findings", [])
        return f"分析 {len(findings)} 篇文档"
    if node_name == "evaluate":
        evaluation = node_output.get("evaluation", {})
        covered = len(evaluation.get("questions_covered", []))
        gaps = len(evaluation.get("gap_questions", []))
        if evaluation.get("should_continue"):
            return f"覆盖 {covered} 个问题，{gaps} 个问题数据不足，继续补充搜索"
        return f"覆盖 {covered} 个问题，研究充分，准备综合分析"
    if node_name == "synthesize":
        synthesis = node_output.get("synthesis", "")
        return f"生成 {len(synthesis)} 字综合分析报告"
    return ""


@celery_app.task(
    name="research_agent.run_research",
    bind=True,
    max_retries=0,
    time_limit=600,
    soft_time_limit=570,
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

        initial_state = {
            "query": task.analysis_goal,
            "context": (task.search_config or {}).get("context", ""),
            "title": task.title or "",
            "research_questions": task.research_questions or [],
            "round": 0,
            "max_rounds": MAX_ROUNDS,
        }

        # 累积最终 state（stream 只返回每节点的 delta）
        accumulated: dict = {**initial_state, "documents": [], "findings": []}
        progress: list[dict] = []
        current_round = 1

        for step in research_graph.stream(initial_state):
            node_name = list(step.keys())[0]
            node_output = step[node_name]

            # 累积 state（reducer 字段追加，其余覆盖）
            for k, v in node_output.items():
                if k in ("documents", "findings"):
                    accumulated[k] = accumulated.get(k, []) + (v or [])
                else:
                    accumulated[k] = v

            if node_name == "plan":
                current_round = accumulated.get("round", current_round)

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
        sources = [
            {
                "id": f"src_{i}",
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "source": s.get("source", ""),
                "source_tier": s.get("source_tier", "tier3"),
                "content_type": s.get("content_type", "html"),
                "relevance_score": s.get("relevance_score", 0.0),
            }
            for i, s in enumerate(selected)
        ]

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
            "candidates_total": len(result_state.get("candidates", [])),
            "documents_analyzed": len(selected),
            "synthesis_length": len(result_state.get("synthesis", "")),
        }
        task.status = "completed"

        complete_analysis_job_sync(db=db, job=job, analyzed_count=len(selected))
        db.commit()

        logger.info(
            "ResearchTask %d 完成: %d 条来源, %d 字综合分析",
            research_task_id,
            len(selected),
            len(result_state.get("synthesis", "")),
        )

    except Exception as exc:
        logger.error("ResearchTask %d 失败: %s", research_task_id, exc, exc_info=True)
        db.rollback()
        try:
            task = db.get(ResearchTask, research_task_id)
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:500]
                if task.job_id:
                    job = db.get(AnalysisJob, task.job_id)
                    if job:
                        complete_analysis_job_sync(db=db, job=job, error_message=str(exc)[:500])
                db.commit()
        except Exception as inner_exc:
            logger.error("更新失败状态时出错: %s", inner_exc)
            db.rollback()
    finally:
        db.close()
