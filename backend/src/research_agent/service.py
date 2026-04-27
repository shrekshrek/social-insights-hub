"""Research Agent 服务层

提供异步接口供 FastAPI router 调用。
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.research_agent.models import ResearchTask
from src.research_agent.tasks import run_research_task

logger = logging.getLogger(__name__)


async def parse_brief_from_file(
    content: bytes, filename: str, profile_name: str | None
) -> dict:
    """文件入口 → 抽文本 → brief_parser_chain 一次完成摄入+诊断+方案"""
    from src.knowledge_base.service import parse_text
    from src.llm.chains.research_agent.brief_parser_chain import parse_brief
    from src.utils import run_cpu_bound_task

    try:
        raw_text = await run_cpu_bound_task(parse_text, content, filename)
    except Exception as exc:
        logger.error("Brief 文本提取失败 (%s): %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无法从文档提取文本，请检查文件是否损坏: {exc}",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文档内容为空，无法解析",
        )

    try:
        parsed = await parse_brief(raw_text, profile_name)
        return {**parsed, "brief_text": raw_text[:10000]}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Brief 解析 LLM 调用失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 解析失败，请稍后重试",
        ) from exc


async def parse_brief_from_text(text: str, profile_name: str | None) -> dict:
    """文本入口 → brief_parser_chain 一次完成摄入+诊断+方案"""
    from src.llm.chains.research_agent.brief_parser_chain import parse_brief

    if not text or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文本内容为空，无法解析",
        )

    try:
        parsed = await parse_brief(text, profile_name)
        return {**parsed, "brief_text": text[:10000]}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Brief 解析 LLM 调用失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 解析失败，请稍后重试",
        ) from exc


async def create_research_task(
    db: AsyncSession,
    user_id: int,
    analysis_goal: str,
    title: str | None = None,
    research_questions: list[str] | None = None,
    search_config: dict | None = None,
    strategy_id: int | None = None,
    profile_name: str = "industry",
) -> ResearchTask:
    """创建研究任务并派发 Celery 执行"""
    task = ResearchTask(
        analysis_goal=analysis_goal,
        title=title,
        research_questions=research_questions,
        search_config=search_config,
        strategy_id=strategy_id,
        user_id=user_id,
        profile_name=profile_name,
        status="pending",
    )
    db.add(task)
    await db.flush()

    # 派发 Celery 任务
    run_research_task.delay(task.id)

    await db.commit()
    await db.refresh(task)

    logger.info(
        "创建研究任务 %d: profile=%s, analysis_goal=%s, strategy_id=%s",
        task.id, profile_name, analysis_goal, strategy_id,
    )
    return task


async def get_research_task(db: AsyncSession, task_id: int) -> ResearchTask | None:
    """获取研究任务"""
    return await db.get(ResearchTask, task_id)


async def rerun_research_task(db: AsyncSession, task: ResearchTask) -> ResearchTask:
    """原地重置研究任务并重新派发 Celery 执行（覆盖原有结果）"""
    task.status = "pending"
    task.result_data = None
    task.progress = []
    task.stats = None
    task.error_message = None
    task.job_id = None
    await db.commit()
    await db.refresh(task)

    run_research_task.delay(task.id)

    logger.info("重新派发研究任务 %d", task.id)
    return task


async def list_research_tasks(
    db: AsyncSession,
    user_id: int | None = None,
    strategy_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    profile_name: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ResearchTask], int]:
    """列出研究任务，返回 (items, total)"""
    base = select(ResearchTask)

    if user_id is not None:
        base = base.where(ResearchTask.user_id == user_id)
    if strategy_id is not None:
        base = base.where(ResearchTask.strategy_id == strategy_id)
    if status:
        base = base.where(ResearchTask.status == status)
    if profile_name:
        base = base.where(ResearchTask.profile_name == profile_name)
    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(ResearchTask.title.ilike(pattern), ResearchTask.analysis_goal.ilike(pattern))
        )

    # total
    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    # items
    offset = (page - 1) * page_size
    stmt = base.order_by(desc(ResearchTask.created_at)).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_research_result(db: AsyncSession, task_id: int) -> dict | None:
    """获取研究结果

    Returns
    -------
    dict | None : 结构化结果或 None（未完成/不存在）
    """
    task = await db.get(ResearchTask, task_id)
    if not task or task.status != "completed" or not task.result_data:
        return None

    return {
        "id": task.id,
        "analysis_goal": task.analysis_goal,
        "status": task.status,
        "findings_by_question": task.result_data.get("findings_by_question"),
        "synthesis": task.result_data.get("synthesis"),
        "sources": task.result_data.get("sources"),
        "coverage": task.result_data.get("coverage"),
        "information_gaps": task.result_data.get("information_gaps") or [],
        "stats": task.stats,
    }


async def delete_research_task(db: AsyncSession, task_id: int) -> bool:
    """删除研究任务，若 Celery 任务仍在运行则同时 revoke"""
    from src.celery_app import celery_app
    from src.jobs.models import AnalysisJob

    task = await db.get(ResearchTask, task_id)
    if not task:
        return False

    # 尝试 revoke 正在运行的 Celery 任务，并主动 fail 对应的 AnalysisJob
    if task.job_id and task.status in ("pending", "running"):
        job = await db.get(AnalysisJob, task.job_id)
        if job:
            if job.celery_task_id:
                celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
                logger.info("revoked celery task %s for ResearchTask %d", job.celery_task_id, task_id)
            # 主动标记 AnalysisJob 为失败，避免 revoke 竞态时 job 永远停在 running
            if job.status in ("pending", "running"):
                from datetime import datetime, timezone
                job.status = "failed"
                job.error_message = "研究任务已被删除"
                job.completed_at = datetime.now(timezone.utc)

    await db.delete(task)
    await db.commit()
    return True


async def get_strategy_research_synthesis(
    db: AsyncSession, strategy_id: int
) -> str:
    """获取策略关联的最新研究综合分析

    供 strategies/service.py 中 _retrieve_strategy_market_context 替换调用。
    返回 synthesis markdown 或 ""（无结果/未完成）。
    """
    stmt = (
        select(ResearchTask)
        .where(
            ResearchTask.strategy_id == strategy_id,
            ResearchTask.status == "completed",
        )
        .order_by(desc(ResearchTask.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task or not task.result_data:
        return ""

    return task.result_data.get("synthesis", "")
