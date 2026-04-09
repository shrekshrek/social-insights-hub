"""新闻任务服务层

Phase A 架构（probe/collect 分家）:
- probe 任务：仅做搜索 + 落库 NewsArticle（无 LLM、无全文抓取），秒级返回
- collect 任务：全量抓取 + 逐篇标注 + 整体洞察，由 celery 执行
- probe → collect 通过 approve_probe_task 显式转换（产生新 task，原 probe 保留）
- probe → probe 通过 refine_probe_task 换关键词（probe_round+1）

collect 阶段的执行流水线位于 src/news_media/tasks/celery_tasks.py，
本模块内的辅助函数（_tag_articles_batch / _run_insight_analysis）供 celery
_async_run_collect 直接引用。
"""

import json
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.tasks import crud
from src.news_media.tasks.models import NewsTask
from src.news_media.tasks.schemas import NewsTaskCreate

logger = logging.getLogger(__name__)

# 逐篇标注的批次大小
_TAGGING_BATCH_SIZE = 5

# probe 搜索返回的最大条数（仅 baidu 渠道）
_PROBE_MAX_RESULTS = 10


async def create_news_task(
    db: AsyncSession,
    monitor_id: int,
    data: NewsTaskCreate,
    user_id: int,
    strategy_id: int | None = None,
    phase: str | None = None,
    parent_probe_id: int | None = None,
    probe_round: int = 1,
) -> NewsTask:
    """创建新闻任务"""
    from src.news_media.monitors.crud import get_monitor_by_id

    monitor = await get_monitor_by_id(db, monitor_id, load_relations=False)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"监测项目 {monitor_id} 不存在",
        )
    task_data = {
        "name": data.name,
        "monitor_id": monitor_id,
        "strategy_id": strategy_id,
        "keywords": data.keywords,
        "phase": phase,
        "search_params": data.search_params,
        "auto_analyze": data.auto_analyze,
        "created_by": user_id,
        "probe_round": probe_round,
        "parent_probe_id": parent_probe_id,
    }
    task = await crud.create_task(db, task_data)
    await db.commit()
    await db.refresh(task, ["monitor", "creator"])
    return task


async def get_news_tasks(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    monitor_id: int | None = None,
    status_filter: str | None = None,
    phase: str | None = None,
    search: str | None = None,
) -> tuple[list[NewsTask], int]:
    """获取新闻任务列表"""
    skip = (page - 1) * page_size
    return await crud.get_tasks(
        db, skip=skip, limit=page_size,
        monitor_id=monitor_id, status=status_filter,
        phase=phase, search=search,
    )


async def get_news_task(db: AsyncSession, task_id: int) -> NewsTask | None:
    """获取单个新闻任务"""
    return await crud.get_task_by_id(db, task_id, load_relations=True)


async def get_news_tasks_by_strategy(
    db: AsyncSession, strategy_id: int, phase: str | None = None
) -> list[NewsTask]:
    """查询策略的新闻任务"""
    return await crud.get_tasks_by_strategy(db, strategy_id, phase=phase)


async def delete_news_task(db: AsyncSession, task: NewsTask) -> None:
    """删除新闻任务"""
    await crud.delete_task(db, task)
    await db.commit()


# ==================== Internal Helpers (shared with celery collect) ====================


def _parse_llm_json(content: str) -> list | dict:
    """从 LLM 响应中提取 JSON（兼容 markdown code block 包裹）"""
    text = content.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass

    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        return json.loads(array_match.group())

    return json.loads(content)


async def _search_and_store_articles(
    db: AsyncSession,
    task: NewsTask,
    max_results: int = 10,
    channels: tuple = ("baidu",),
) -> list:
    """搜索 + 创建 NewsArticle（绑定 task_id），返回本次创建的文章列表"""
    from src.news_media.tasks.news_search.aggregator import search_news

    search_results = await search_news(
        query=task.keywords,
        max_results=max_results,
        channels=list(channels),
    )
    if not search_results:
        return []

    articles_data = [
        {
            "task_id": task.id,
            "url": r["url"],
            "title": r["title"],
            "snippet": r.get("snippet"),
            "source_name": r["source_name"],
            "source_tier": r["source_tier"],
            "search_source": r.get("search_source", "baidu"),
            "published_at": r.get("published_at"),
            "image_url": r.get("image_url"),
            "raw_data": r.get("raw_data"),
        }
        for r in search_results
    ]

    return await crud.bulk_create_articles(db, articles_data)


async def _tag_articles_batch(
    articles: list,
    analysis_goal: str,
    use_full_text: bool = False,
) -> list[dict]:
    """逐篇轻量标注（批量，_TAGGING_BATCH_SIZE 篇一组）—— 仅 collect 阶段调用"""
    from src.langchain.chains.news_tagging_chain import (
        create_news_tagging_chain,
        format_articles_for_tagging,
    )

    chain = create_news_tagging_chain()
    all_tags: list[dict] = []

    for i in range(0, len(articles), _TAGGING_BATCH_SIZE):
        batch = articles[i:i + _TAGGING_BATCH_SIZE]
        batch_dicts = [
            {
                "title": a.title,
                "source_name": a.source_name,
                "snippet": a.snippet,
                "full_text": a.full_text if use_full_text else None,
            }
            for a in batch
        ]

        articles_content = format_articles_for_tagging(batch_dicts, use_full_text=use_full_text)
        response = await chain.ainvoke({
            "analysis_goal": analysis_goal,
            "article_count": len(batch),
            "articles_content": articles_content,
        })

        try:
            tags = _parse_llm_json(response.content)
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, dict) and "article_index" in tag:
                        tag["article_index"] = i + tag["article_index"]
                all_tags.extend(tags)
            else:
                logger.warning("news_tagging_chain returned non-list: %s", type(tags))
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse tagging response: %s", e)

    return all_tags


async def _apply_tags_to_articles(
    db: AsyncSession,
    articles: list,
    tags: list[dict],
) -> None:
    """将标注结果写回 NewsArticle —— 仅 collect 阶段调用"""
    for tag in tags:
        idx = tag.get("article_index")
        if idx is None or idx >= len(articles):
            continue
        article = articles[idx]
        update_data = {}
        if "relevance" in tag:
            update_data["relevance"] = tag["relevance"]
        if "sentiment" in tag:
            update_data["sentiment"] = tag["sentiment"]
        if "article_type" in tag:
            update_data["article_type"] = tag["article_type"]
        if "mentioned_entities" in tag:
            update_data["mentioned_entities"] = tag["mentioned_entities"]
        if "key_quotes" in tag:
            update_data["key_quotes"] = tag["key_quotes"]
        if "summary" in tag:
            update_data["summary"] = tag["summary"]
        if update_data:
            await crud.update_article(db, article, update_data)
    await db.flush()


async def _run_insight_analysis(
    articles: list,
    analysis_goal: str,
    subject: str,
) -> dict:
    """整体分析（一次 LLM 调用），返回结构化洞察 —— 仅 collect 阶段调用"""
    from src.langchain.chains.news_insight_chain import (
        create_news_insight_chain,
        format_tagged_articles_for_insight,
    )

    relevant = [
        a for a in articles
        if a.relevance in ("high", "medium") or a.relevance is None
    ]

    article_dicts = [
        {
            "title": a.title,
            "source_name": a.source_name,
            "source_tier": a.source_tier,
            "published_at": str(a.published_at) if a.published_at else "未知",
            "relevance": a.relevance,
            "sentiment": a.sentiment,
            "article_type": a.article_type,
            "mentioned_entities": a.mentioned_entities,
            "key_quotes": a.key_quotes,
            "summary": a.summary,
        }
        for a in relevant
    ]

    tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
    for a in relevant:
        tier = a.source_tier or "tier3"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    tagged_content = format_tagged_articles_for_insight(article_dicts)

    chain = create_news_insight_chain()
    response = await chain.ainvoke({
        "analysis_goal": analysis_goal,
        "subject": subject,
        "article_count": len(relevant),
        "tagged_articles": tagged_content,
        "tier1_count": tier_counts["tier1"],
        "tier2_count": tier_counts["tier2"],
        "tier3_count": tier_counts["tier3"],
    })

    try:
        return _parse_llm_json(response.content)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse insight response: %s", e)
        return {"error": str(e)}


# ==================== Task Execution ====================


async def execute_news_probe(
    db: AsyncSession,
    task: NewsTask,
) -> None:
    """执行新闻探测：仅搜索 + 落库，不抓全文、不打标。

    语义：让用户/策略快速判断关键词是否合理。用户在前端看 NewsArticle 卡片
    （title / source_name / source_tier / snippet）决定 approve 或 refine。

    调用者负责 commit。
    """
    try:
        task.status = "running"
        await db.flush()

        articles = await _search_and_store_articles(
            db, task, max_results=_PROBE_MAX_RESULTS, channels=("baidu",)
        )

        tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
        source_samples: list[str] = []
        seen_sources: set[str] = set()
        for a in articles:
            tier = a.source_tier or "tier3"
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            if a.source_name and a.source_name not in seen_sources:
                seen_sources.add(a.source_name)
                if len(source_samples) < 8:
                    source_samples.append(a.source_name)

        task.status = "completed"
        task.articles_count = len(articles)
        task.analysis_result = {
            "meta": {
                "keywords": task.keywords,
                "articles_total": len(articles),
                "source_tier_distribution": tier_counts,
                "source_samples": source_samples,
                "probe_round": task.probe_round,
            },
        }
        await db.flush()
        logger.info(
            "NewsTask %d: probe completed, %d articles, round=%d",
            task.id, task.articles_count, task.probe_round,
        )

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await db.flush()
        logger.error("NewsTask %d: probe failed: %s", task.id, e, exc_info=True)
        raise


# ==================== Approve / Refine ====================


async def approve_probe_task(
    db: AsyncSession,
    probe_task: NewsTask,
    user_id: int,
) -> NewsTask:
    """基于 approved probe task 创建 collect task 并 dispatch celery。

    规则：
    - probe_task 必须 phase=="probe" 且 status=="completed"
    - 继承 keywords / monitor_id / strategy_id / search_params
    - collect_task.parent_probe_id = probe_task.id
    - auto_analyze 默认 True（collect 阶段有意义）
    - 立即 dispatch celery 执行全量流水线

    返回新创建的 collect task。
    """
    if probe_task.phase != "probe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能对 probe 任务执行 approve",
        )
    if probe_task.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"probe 任务当前状态为 {probe_task.status}，无法 approve",
        )

    from src.news_media.tasks.celery_tasks import run_news_collect_task

    collect_task_data = {
        "name": f"{probe_task.name} - 全量",
        "monitor_id": probe_task.monitor_id,
        "strategy_id": probe_task.strategy_id,
        "keywords": probe_task.keywords,
        "phase": "collect",
        "search_params": probe_task.search_params,
        "auto_analyze": True,
        "created_by": user_id,
        "parent_probe_id": probe_task.id,
        "probe_round": 1,
    }
    collect_task = await crud.create_task(db, collect_task_data)
    collect_task.status = "running"
    await db.commit()
    await db.refresh(collect_task, ["monitor", "creator"])

    tagging_job_id: int | None = None
    insight_job_id: int | None = None
    from src.analysis.sources.news import create_news_analysis_jobs

    tagging_job, insight_job = await create_news_analysis_jobs(
        db=db, task=collect_task, user_id=user_id
    )
    tagging_job_id = tagging_job.id
    insight_job_id = insight_job.id

    celery_result = run_news_collect_task.delay(
        task_id=collect_task.id,
        tagging_job_id=tagging_job_id,
        insight_job_id=insight_job_id,
    )

    if tagging_job_id is not None:
        from src.analysis.jobs import crud as jobs_crud
        await jobs_crud.set_celery_task_id(db, tagging_job_id, celery_result.id)
        await db.commit()

    return collect_task


async def refine_probe_task(
    db: AsyncSession,
    probe_task: NewsTask,
    new_keywords: str,
    user_id: int,
) -> NewsTask:
    """基于某个 probe task 产生一个新的 probe task（关键词替换，probe_round+1）。

    原 probe task 保留以供审计与对比。新任务立即 dispatch celery 执行。
    """
    if probe_task.phase != "probe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能对 probe 任务执行 refine",
        )
    keywords = (new_keywords or "").strip()
    if not keywords:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refine 必须提供新的关键词",
        )

    from src.news_media.tasks.celery_tasks import run_news_probe_task

    new_task_data = {
        "name": f"{probe_task.name} #{probe_task.probe_round + 1}",
        "monitor_id": probe_task.monitor_id,
        "strategy_id": probe_task.strategy_id,
        "keywords": keywords,
        "phase": "probe",
        "search_params": probe_task.search_params,
        "auto_analyze": False,
        "created_by": user_id,
        "parent_probe_id": probe_task.id,
        "probe_round": probe_task.probe_round + 1,
    }
    new_task = await crud.create_task(db, new_task_data)
    new_task.status = "running"
    await db.commit()
    await db.refresh(new_task, ["monitor", "creator"])

    run_news_probe_task.delay(task_id=new_task.id)
    return new_task
