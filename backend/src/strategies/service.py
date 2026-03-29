"""策略定义业务逻辑"""

import asyncio
import io
import logging
import time
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func, delete as sa_delete
from src.utils import run_cpu_bound_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from src.langchain.chains.strategy_research_design_chain import (
    create_research_design_chain,
    format_research_design_inputs,
    parse_research_design_response,
)
from src.langchain.chains.strategy_probe_review_chain import (
    create_single_task_probe_review_chain,
    format_single_task_probe_review_inputs,
    parse_single_task_probe_review_response,
)
from src.langchain.chains.strategy_coverage_check_chain import (
    create_coverage_check_chain,
    format_coverage_check_inputs,
    parse_coverage_check_response,
)
from src.langchain.chains.strategy_phase1_chain import (
    create_strategy_phase1_chain,
    format_slice_data_for_phase1,
    parse_phase1_response,
)
from src.langchain.chains.strategy_phase2_chain import (
    create_strategy_phase2_chain,
    format_data_for_phase2,
    parse_phase2_response,
)
from src.langchain.chains.strategy_phase3_chain import (
    create_strategy_phase3_chain,
    format_data_for_phase3,
    parse_phase3_response,
)
from src.langchain.chains.strategy_brief_parser_chain import (
    create_strategy_brief_parser_chain,
    parse_brief_parser_response,
)
from src.database import AsyncSessionLocal
from src.langchain import extract_token_usage
from src.social_media.analysis.jobs.factory import create_analysis_job_async
from src.social_media.analysis.models import AnalysisType
from src.social_media.analysis.models import AnalysisSlice
from src.social_media.monitors.crud import check_monitor_access
from .models import Strategy, StrategySlice
from .schemas import (
    ApproveProbeResponse,
    CollectionStatusResponse,
    CollectionTaskStatus,
    ConfirmResearchResponse,
    DataOverviewResponse,
    DesignResearchResponse,
    ParseBriefResponse,
    ProbeStatusResponse,
    ProbeTaskStatus,
    RefineProbeRequest,
    RefineProbeResponse,
    StrategyCreate,
    StrategyUpdate,
    StrategyRead,
    StrategyListItem,
    SliceSummary,
)

logger = logging.getLogger(__name__)


async def create_strategy(
    db: AsyncSession, data: StrategyCreate, user_id: int
) -> Strategy:
    """创建策略

    校验每个 slice_id 的存在性和项目访问权限，
    然后创建 Strategy + StrategySlice 记录。
    """
    # 校验每个 slice
    for sid in data.slice_ids:
        slice_obj = await db.get(AnalysisSlice, sid)
        if not slice_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"切片 {sid} 不存在",
            )
        has_access = await check_monitor_access(db, slice_obj.monitor_id, user_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权访问切片 {sid} 所属项目",
            )

    # 创建 Strategy
    brief_dict = data.brand_brief.model_dump() if data.brand_brief else None
    strategy = Strategy(
        name=data.name,
        created_by=user_id,
        brand_brief=brief_dict,
    )
    db.add(strategy)
    await db.flush()

    # 创建关联
    for sid in data.slice_ids:
        db.add(StrategySlice(strategy_id=strategy.id, slice_id=sid))

    await db.commit()

    # 重新查询以加载关系
    return await get_strategy_by_id(db, strategy.id)


async def get_strategies(
    db: AsyncSession,
    user_id: int,
    is_admin: bool,
    skip: int,
    limit: int,
    search: str | None = None,
) -> tuple[list[Strategy], int]:
    """获取策略列表

    admin 看全部，普通用户只看自己创建的。
    """
    query = select(Strategy)

    if not is_admin:
        query = query.where(Strategy.created_by == user_id)

    if search:
        query = query.where(Strategy.name.ilike(f"%{search}%"))

    # 计数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页 + 排序
    query = query.order_by(Strategy.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_strategy_by_id(db: AsyncSession, strategy_id: int) -> Strategy | None:
    """按 ID 获取策略（含关系）"""
    query = (
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .options(
            selectinload(Strategy.creator),
            selectinload(Strategy.slices)
            .selectinload(StrategySlice.slice)
            .selectinload(AnalysisSlice.monitor),
        )
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_strategy(
    db: AsyncSession, strategy: Strategy, data: StrategyUpdate
) -> Strategy:
    """更新策略基本信息"""
    if data.name is not None:
        strategy.name = data.name
    if data.brand_brief is not None:
        strategy.brand_brief = data.brand_brief

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def delete_strategy(db: AsyncSession, strategy: Strategy) -> None:
    """删除策略（CASCADE 自动清理 strategy_slices）"""
    await db.delete(strategy)
    await db.commit()


async def load_strategy_inputs(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """加载策略输入数据，屏蔽数据来源差异

    当前支持：社媒切片（AnalysisSlice.result_data）。
    未来扩展点：知识库摘要、网络搜索摘要通��此函数统一接入。
    """
    slice_ids = [s.slice_id for s in strategy.slices]
    if not slice_ids:
        return []

    query = select(AnalysisSlice).where(AnalysisSlice.id.in_(slice_ids))
    result = await db.execute(query)
    slices = result.scalars().all()
    return [s.result_data for s in slices if s.result_data]


async def load_strategy_inputs_with_names(
    db: AsyncSession, strategy: Strategy
) -> list[tuple[str | None, dict]]:
    """加载策略输入数据（含切片名），用于覆盖度验证链"""
    slice_ids = [s.slice_id for s in strategy.slices]
    if not slice_ids:
        return []

    query = select(AnalysisSlice).where(AnalysisSlice.id.in_(slice_ids))
    result = await db.execute(query)
    slices = result.scalars().all()
    return [(s.name, s.result_data) for s in slices if s.result_data]




def build_strategy_read(strategy: Strategy) -> StrategyRead:
    """组装 StrategyRead 响应"""
    slices = []
    for ss in strategy.slices:
        slice_obj = ss.slice
        slices.append(
            SliceSummary(
                slice_id=ss.slice_id,
                slice_name=slice_obj.name if slice_obj else None,
                monitor_id=slice_obj.monitor_id if slice_obj else 0,
                monitor_name=(
                    slice_obj.monitor.name if slice_obj and slice_obj.monitor else ""
                ),
            )
        )

    return StrategyRead(
        id=strategy.id,
        name=strategy.name,
        status=strategy.status,
        brand_brief=strategy.brand_brief,
        research_design=strategy.research_design,
        probe_review_result=strategy.probe_review_result,
        probe_round=strategy.probe_round,
        coverage_check_result=strategy.coverage_check_result,
        output_type=strategy.output_type,
        phase1_result=strategy.phase1_result,
        phase2_result=strategy.phase2_result,
        phase3_result=strategy.phase3_result,
        monitor_id=strategy.monitor_id,
        task_ids=list(strategy.task_ids or []),
        slices=slices,
        created_by=strategy.created_by,
        creator_name=strategy.creator.username if strategy.creator else "",
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


def build_strategy_list_item(strategy: Strategy) -> StrategyListItem:
    """组装 StrategyListItem 响应"""
    return StrategyListItem(
        id=strategy.id,
        name=strategy.name,
        status=strategy.status,
        slice_count=len(strategy.slices),
        created_by=strategy.created_by,
        creator_name=strategy.creator.username if strategy.creator else "",
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


# ==================== 生成 + 编辑 ====================

# 状态流转顺序
STATUS_ORDER = {
    "draft": 0,
    "planned": 1,
    "probing": 2,
    "collecting": 3,
    "ready": 4,
    "phase1_done": 5,
    "phase2_done": 6,
    "completed": 7,
}


def _validate_has_slices(strategy: Strategy) -> None:
    """校验策略已关联切片（phase1 前置条件）"""
    if not strategy.slices:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先关联分析切片",
        )


def _validate_slices_have_data(slices_data: list[dict], strategy: Strategy) -> None:
    """校验切片是否有分析数据"""
    if not slices_data:
        slice_ids = [s.slice_id for s in strategy.slices]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"切片 {slice_ids} 尚未完成分析",
        )


async def generate_phase1(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 Phase 1 (洞察层): Social Tension + Brand Opportunity"""
    _validate_has_slices(strategy)
    slices_data = await load_strategy_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy)

    # RAG 注入（有 brief 时执行，无数据时优雅降级为 ""）
    market_context = ""
    if strategy.brand_brief:
        try:
            from src.knowledge_base.service import retrieve_market_context

            brief = strategy.brand_brief
            query = f"{brief.get('subject', '')} {brief.get('analysis_goal', '')}".strip()
            if query:
                market_context = await retrieve_market_context(
                    db, query, user_id=strategy.created_by, top_k=6
                )
        except Exception as e:
            logger.warning("Phase1 RAG 检索失败，降级为空: %s", e)

    chain = create_strategy_phase1_chain()
    inputs = format_slice_data_for_phase1(
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
        market_context=market_context,
    )

    job = await create_analysis_job_async(
        db,
        monitor_id=strategy.monitor_id,
        task_id=None,
        user_id=strategy.created_by,
        analysis_type=AnalysisType.STRATEGY_PHASE1.value,
        source_count=len(slices_data),
        status="processing",
        analysis_config={"strategy_id": strategy.id},
    ) if strategy.monitor_id else None

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase1_response(response.content)
    logger.info("Strategy %d Phase 1 生成完成 (%.1fs)", strategy.id, duration)

    if job:
        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

    strategy.phase1_result = result
    strategy.phase2_result = None
    strategy.phase3_result = None
    strategy.status = "phase1_done"

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def generate_phase2(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 Phase 2 (策略层): Brand Social Role + Social Strategy"""
    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["phase1_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认 Phase 1",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy)

    # RAG 注入（有 brief 时执行，无数据时优雅降级为 ""）
    market_context = ""
    if strategy.brand_brief:
        try:
            from src.knowledge_base.service import retrieve_market_context

            brief = strategy.brand_brief
            query = f"{brief.get('subject', '')} {brief.get('analysis_goal', '')}".strip()
            if query:
                market_context = await retrieve_market_context(
                    db, query, user_id=strategy.created_by, top_k=6
                )
        except Exception as e:
            logger.warning("Phase2 RAG 检索失败，降级为空: %s", e)

    chain = create_strategy_phase2_chain()
    inputs = format_data_for_phase2(
        strategy.phase1_result,
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
        market_context=market_context,
    )

    job = await create_analysis_job_async(
        db,
        monitor_id=strategy.monitor_id,
        task_id=None,
        user_id=strategy.created_by,
        analysis_type=AnalysisType.STRATEGY_PHASE2.value,
        source_count=len(slices_data),
        status="processing",
        analysis_config={"strategy_id": strategy.id},
    ) if strategy.monitor_id else None

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase2_response(response.content)
    logger.info("Strategy %d Phase 2 生成完成 (%.1fs)", strategy.id, duration)

    if job:
        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

    strategy.phase2_result = result
    strategy.phase3_result = None
    strategy.status = "phase2_done"

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def generate_phase3(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 Phase 3 (创意层): Big Idea + Content Strategy"""
    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["phase2_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认 Phase 2",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy)

    chain = create_strategy_phase3_chain()
    inputs = format_data_for_phase3(
        strategy.phase1_result,
        strategy.phase2_result,
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
    )

    job = await create_analysis_job_async(
        db,
        monitor_id=strategy.monitor_id,
        task_id=None,
        user_id=strategy.created_by,
        analysis_type=AnalysisType.STRATEGY_PHASE3.value,
        source_count=len(slices_data),
        status="processing",
        analysis_config={"strategy_id": strategy.id},
    ) if strategy.monitor_id else None

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase3_response(response.content)
    logger.info("Strategy %d Phase 3 生成完成 (%.1fs)", strategy.id, duration)

    if job:
        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

    strategy.phase3_result = result
    strategy.status = "completed"

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


PLATFORM_NAME_TO_CODE = {
    "douyin": "dy",
    "weibo": "wb",
    "bilibili": "bili",
    "xiaohongshu": "xhs",
    "kuaishou": "ks",
    "zhihu": "zhihu",
    "tieba": "tieba",
}


# ==================== ① 研究设计 ====================


def _extract_social_media_channel_brief(brand_brief: dict | None) -> str:
    """从 brand_brief 中提取社媒渠道专属描述，兼容旧格式（无 channel_plan 的记录）"""
    if not brand_brief:
        return ""
    channel_plan = brand_brief.get("channel_plan") or []
    for item in channel_plan:
        if item.get("type") == "social_media":
            brief = item.get("channel_brief", "")
            if brief:
                return brief
    # 兜底：从 brief 字段构建描述（旧格式或 channel_brief 为空时）
    parts = []
    if subject := brand_brief.get("subject"):
        parts.append(f"研究主体：{subject}")
    if goal := brand_brief.get("analysis_goal"):
        parts.append(f"分析目标：{goal}")
    if constraints := brand_brief.get("constraints"):
        parts.append(f"补充说明：{constraints}")
    return "\n".join(parts)


async def design_research(
    db: AsyncSession,
    strategy: Strategy,
    user_input: str,
) -> DesignResearchResponse:
    """AI 研究设计：基于社媒 channel_brief 生成结构化研究计划

    输出研究问题、数据采集方案、切片蓝图、产出类型建议。
    每次调用覆盖上一次结果。
    LLM 解析失败时抛出 HTTPException(500)，strategy 不更新。
    """
    chain = create_research_design_chain()
    brand_brief = strategy.brand_brief or {}
    inputs = format_research_design_inputs(
        user_input=user_input,
        channel_brief=_extract_social_media_channel_brief(brand_brief),
        subject=brand_brief.get("subject", ""),
        constraints=brand_brief.get("constraints") or "",
    )

    start = time.time()
    llm_result = await chain.ainvoke(inputs)
    duration = time.time() - start

    try:
        parsed = parse_research_design_response(llm_result.content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 研究设计解析失败: {e}",
        ) from e

    response = DesignResearchResponse(
        understanding_summary=parsed["understanding_summary"],
        research_questions=parsed["research_questions"],
        data_plan=parsed["data_plan"],
        slice_blueprint=parsed["slice_blueprint"],
        output_type=parsed["output_type"],
        output_type_rationale=parsed.get("output_type_rationale", ""),
    )
    logger.info(
        "Strategy %d 研究设计完成 (%.1fs, %d 个研究问题, %d 个数据维度)",
        strategy.id,
        duration,
        len(parsed["research_questions"]),
        len(parsed["data_plan"]),
    )

    strategy.research_design = parsed
    flag_modified(strategy, "research_design")
    strategy.output_type = parsed["output_type"]

    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["planned"]:
        strategy.status = "planned"

    await db.commit()
    return response


async def reset_to_design(
    db: AsyncSession,
    strategy: Strategy,
) -> StrategyRead:
    """重置策略到研究设计阶段，软删除已创建的任务

    允许用户从探测/采集阶段回退到 planned，重新编辑研究计划。
    保留 Monitor（复用），保留 research_design（可重新编辑后确认）。
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.tasks.models import DataTask

    if STATUS_ORDER.get(strategy.status, 0) <= STATUS_ORDER["planned"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前状态无需重置",
        )

    # 软删除所有已创建的任务
    task_ids = list(strategy.task_ids or [])
    if task_ids:
        query = select(DataTask).where(
            DataTask.id.in_(task_ids), DataTask.is_deleted.is_(False)
        )
        result = await db.execute(query)
        for task in result.scalars().all():
            await task_crud.delete_task(db, task)

    # 清除探测/采集阶段的数据，回退状态
    strategy.task_ids = []
    flag_modified(strategy, "task_ids")
    strategy.probe_review_result = None
    flag_modified(strategy, "probe_review_result")
    strategy.probe_round = 0
    strategy.coverage_check_result = None
    flag_modified(strategy, "coverage_check_result")
    strategy.status = "planned"

    # 清除关联切片（自动创建的）
    for ss in list(strategy.slices):
        await db.delete(ss)

    await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    logger.info(
        "Strategy %d 重置到研究设计阶段 (删除 %d 个任务)",
        strategy.id,
        len(task_ids),
    )
    return build_strategy_read(updated)


async def confirm_research(
    db: AsyncSession,
    strategy: Strategy,
    research_design: dict,
    current_user_id: int,
    *,
    notes_per_task: int = 50,
    probe_notes: int = 20,
) -> ConfirmResearchResponse:
    """确认研究计划，创建一个 Monitor + 探测任务

    遍历 data_plan 中每个维度的关键词×平台组合创建 DataTask，
    task_params 包含 max_pages 用于控制翻页数量（探测任务：1页或2页）。
    """
    from src.social_media.monitors.crud import get_monitor_by_name, get_platform_by_code
    from src.social_media.monitors.schemas import MonitorCreate
    from src.social_media.monitors.service import create_monitor
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task

    if STATUS_ORDER.get(strategy.status, 0) > STATUS_ORDER["probing"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="全量采集已启动，无法重新确认研究计划",
        )

    # 从 probing 状态重新确认：清理旧探测数据，重新创建任务
    if strategy.status == "probing":
        from src.social_media.tasks import crud as task_crud
        from src.social_media.tasks.models import DataTask as _DataTask

        old_task_ids = list(strategy.task_ids or [])
        if old_task_ids:
            _q = select(_DataTask).where(
                _DataTask.id.in_(old_task_ids), _DataTask.is_deleted.is_(False)
            )
            _result = await db.execute(_q)
            for _task in _result.scalars().all():
                await task_crud.delete_task(db, _task)

        strategy.task_ids = []
        flag_modified(strategy, "task_ids")
        strategy.probe_review_result = None
        flag_modified(strategy, "probe_review_result")
        strategy.probe_round = 0
        _probe_review_in_progress.discard(strategy.id)

    data_plan = research_design.get("data_plan") or []
    if not data_plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="研究计划中无数据采集方案",
        )

    # 预估总任务数，超过 20 个视为异常（提示用户精简，而非静默创建大量任务）
    estimated_tasks = sum(
        len(dp.get("keywords") or []) * len(dp.get("platforms") or [])
        for dp in data_plan
    )
    if estimated_tasks > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"研究计划预估任务数（{estimated_tasks}）过多，请精简关键词或平台（建议 6-10 个任务）",
        )

    # 保存用户编辑后的研究计划
    strategy.research_design = research_design
    flag_modified(strategy, "research_design")
    strategy.output_type = research_design.get("output_type", "brand_strategy")

    # 复用已有 Monitor 或创建新的
    if strategy.monitor_id:
        from src.social_media.monitors.models import Monitor

        monitor = await db.get(Monitor, strategy.monitor_id)
        if not monitor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"关联的监测项目 {strategy.monitor_id} 不存在",
            )
    else:
        base_name = strategy.name
        monitor_name = base_name
        suffix = 1
        while await get_monitor_by_name(db, monitor_name):
            suffix += 1
            monitor_name = f"{base_name}({suffix})"

        try:
            result = await create_monitor(
                db,
                MonitorCreate(
                    name=monitor_name,
                    description=f"策略「{strategy.name}」的研究数据采集",
                ),
                current_user_id,
            )
            monitor = result["monitor"]
        except HTTPException as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"创建监测项目失败: {e.detail}",
            ) from e

    # 为每个维度×关键词×平台创建独立任务（每个关键词独立，便于探测审查逐词评估）
    created_task_ids: list[int] = []
    task_dimension_map: dict[int, str] = {}  # task_id → dimension_name
    partial_errors: list[str] = []

    for dimension in data_plan:
        dimension_name = dimension.get("dimension_name", "").strip()
        keywords = dimension.get("keywords") or []
        platforms = dimension.get("platforms") or []

        if not dimension_name or not keywords or not platforms:
            partial_errors.append(f"跳过不完整的数据维度: {dimension_name}")
            continue

        clean_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not clean_keywords:
            continue

        # 探测任务：仅采 probe_notes 条，跳过评论（加快速度），下发给��虫时直接用 max_notes_count
        probe_task_params = {
            "max_notes_count": probe_notes,
            "enable_comments": 0,
            "per_note_max_comments_count": 0,
        }

        for keyword in clean_keywords:
            for platform_name in platforms:
                code = PLATFORM_NAME_TO_CODE.get(platform_name, platform_name)
                try:
                    platform = await get_platform_by_code(db, code)
                    if not platform:
                        partial_errors.append(f"平台「{platform_name}」不存在，跳过")
                        continue

                    # max_pages 用于控制翻页数量：微博/贴吧 10 条/页限 2 页，其他平台 20 条/页限 1 页
                    max_pages = 2 if code in ("wb", "tieba") else 1

                    # 为每个平台单独设置 max_pages
                    probe_task_params["max_pages"] = max_pages

                    task = await create_task(
                        db,
                        DataTaskCreate(
                            name=f"{keyword}-{platform.name}",
                            monitor_id=monitor.id,
                            platform_id=platform.id,
                            task_type="search",
                            keywords=keyword,
                            data_source="remote_crawler",
                            task_params=probe_task_params,
                            auto_analyze=True,
                            phase="probe",
                        ),
                        current_user_id,
                    )
                    created_task_ids.append(task.id)
                    task_dimension_map[task.id] = dimension_name
                except Exception as e:
                    logger.error(
                        "创建任务「%s-%s-%s」失败: %s",
                        keyword,
                        platform_name,
                        dimension_name,
                        e,
                    )
                    partial_errors.append(
                        f"创建任务「{keyword}-{platform_name}」失败: {e}"
                    )

    # 记录 task_id → dimension 映射到 research_design 中，供后续自动建切片使用
    research_design["_task_dimension_map"] = {
        str(tid): dim for tid, dim in task_dimension_map.items()
    }
    strategy.research_design = research_design
    flag_modified(strategy, "research_design")

    strategy.monitor_id = monitor.id
    strategy.task_ids = created_task_ids
    flag_modified(strategy, "task_ids")
    strategy.status = "probing"

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)
    return ConfirmResearchResponse(
        created_monitor_id=monitor.id,
        created_task_count=len(created_task_ids),
        partial_errors=partial_errors,
        strategy=build_strategy_read(updated),
    )


# ==================== ② 探测验证 ====================

# 防止多个并发请求同时触发同一策略的 LLM 审查
_probe_review_in_progress: set[int] = set()


async def _build_probe_task_summaries(
    db: AsyncSession,
    task_ids: list[int],
) -> tuple[list[ProbeTaskStatus], list[dict]]:
    """查询探测任务状态和分析摘要

    Returns:
        (task_statuses, analyzed_summaries)
        analyzed_summaries 只包含已有分析结果的任务摘要，供审查使用
    """
    from src.social_media.tasks.models import DataTask

    if not task_ids:
        return [], []

    query = select(DataTask).where(
        DataTask.id.in_(task_ids), DataTask.is_deleted.is_(False)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    # 爬虫已完成（含 0 结果）的终态
    _PROBE_TERMINAL_STATUSES = {"probe_ready", "approved", "completed", "failed"}

    statuses = []
    analyzed_summaries = []

    for task in tasks:
        has_analysis = task.analysis_result is not None
        # 只有进入终态（爬虫已结束）且 0 条时才视为已处理，避免把仍在运行的任务提前计入
        no_data = (task.posts_count or 0) == 0 and task.status in _PROBE_TERMINAL_STATUSES

        # 0 条数据：爬虫已完成但无结果，无需 LLM 判断，直接视为已处理（客观规则层会自动 fail）
        statuses.append(
            ProbeTaskStatus(
                task_id=task.id,
                keyword=task.keywords or "",
                platform=task.platform.code if task.platform else "",
                status=task.status,
                has_analysis=has_analysis or no_data,
            )
        )

        if has_analysis:
            ar = task.analysis_result or {}
            insights = ar.get("insights") or {}
            metrics = ar.get("metrics") or {}
            marketing = metrics.get("marketing_analysis") or {}
            data_volume = (ar.get("meta") or {}).get("data_volume") or {}

            # entity_match: 从已分类的实体列表计算，不依赖 LLM 解析
            target_entities = insights.get("target_entities") or []
            competitor_entities = insights.get("competitor_entities") or []
            entity_match = bool(target_entities or competitor_entities)

            top_topics_raw = insights.get("top_topics") or []
            top_topics = [
                {"name": t.get("name", ""), "mentions": t.get("mentions", 0)}
                for t in top_topics_raw[:10]
            ]

            summary = {
                "task_id": task.id,
                "keyword": task.keywords or "",
                "platform": task.platform.code if task.platform else "",
                "posts_count": task.posts_count,
                "deep_analyzed": data_volume.get("deep_analyzed", 0),
                "entity_match": entity_match,
                "top_topics": top_topics,
                "promotion_ratio": marketing.get("promotion_ratio"),
            }
            analyzed_summaries.append(summary)
        elif no_data:
            # 0 条帖子：加入 summaries 供客观规则层直接 fail，不送 LLM
            analyzed_summaries.append({
                "task_id": task.id,
                "keyword": task.keywords or "",
                "platform": task.platform.code if task.platform else "",
                "posts_count": 0,
                "deep_analyzed": 0,
                "entity_match": False,
                "top_topics": [],
                "promotion_ratio": None,
            })

    return statuses, analyzed_summaries


def _auto_verdict_probe_task(summary: dict) -> tuple[str, str] | None:
    """客观规则层：根据量化指标直接判定，返回 (verdict, note) 或 None（交 LLM 判断）

    Hard FAIL：内容极少 / 广告占比极高
    数据门槛：深度分析样本不足，默认 pass 待全量后验证
    None：交 LLM 判断话题与研究问题的相关性
    """
    posts = summary.get("posts_count") or 0
    promo = summary.get("promotion_ratio")
    deep_analyzed = summary.get("deep_analyzed") or 0

    # Hard FAIL
    if posts < 5:
        return "fail", f"平台内容极少（仅 {posts} 条），关键词在此平台可能无效"
    if promo is not None and promo > 0.85:
        return "fail", f"广告内容占比 {promo:.0%}，自然讨论极少"

    # 数据门槛：深度分析样本不足，无法判断话题相关性，默认通过待全量后验证
    if deep_analyzed < 5:
        return "pass", f"深度分析样本较少（{deep_analyzed} 条），待全量采集后验证话题相关性"

    return None  # 交 LLM 判断话题相关性


async def _run_probe_review_bg_task(
    strategy_id: int,
    analyzed_summaries: list[dict],
) -> None:
    """后台任务：运行探测审查，结果写入 DB（不阻塞 HTTP 响应）

    全量评估所有任务（不区分新旧轮次）：
    1. 客观规则层（_auto_verdict_probe_task）处理明确案例
    2. LLM 层处理模糊案例（话题相关性判断）
    temperature=0 保证相同数据重评结果不变。
    """
    try:
        async with AsyncSessionLocal() as db:
            strategy = await get_strategy_by_id(db, strategy_id)
            if strategy is None or strategy.probe_review_result:
                return  # 策略不存在或已有结果（并发任务已完成）

            # 客观规则层：分流（全量评估所有任务，temperature=0 保证相同数据相同结果）
            auto_assessments: list[dict] = []
            rule_suggestions: list[dict] = []  # auto-fail 任务的规则建议（无需 LLM）
            ambiguous_summaries: list[dict] = []

            for summary in analyzed_summaries:
                result = _auto_verdict_probe_task(summary)
                if result is not None:
                    verdict, note = result
                    auto_assessments.append({
                        "task_id": summary["task_id"],
                        "keyword": summary["keyword"],
                        "platform": summary["platform"],
                        "entity_match": summary.get("entity_match", False),
                        "verdict": verdict,
                        "note": note,
                    })
                    if verdict == "fail":
                        # 规则 fail：内容极少或几乎全是广告，LLM 无法从中获取有效话题
                        # 给出通用建议，具体关键词由用户根据研究方向决定
                        rule_suggestions.append({
                            "task_id": summary["task_id"],
                            "original_keyword": summary["keyword"],
                            "suggested_keyword": None,
                            "platform": summary["platform"],
                            "reason": note,
                        })
                else:
                    ambiguous_summaries.append(summary)

            # LLM 层：处理模糊案例（话题相关性判断）
            review_result = await _run_probe_review(
                db,
                strategy,
                ambiguous_summaries=ambiguous_summaries,
                auto_assessments=auto_assessments,
                rule_suggestions=rule_suggestions,
            )

            if review_result.get("overall_verdict") == "all_pass":
                await approve_probe(db, strategy)
    except Exception as e:
        logger.error(
            "Strategy %d probe review background task failed: %s", strategy_id, e, exc_info=True
        )
    finally:
        _probe_review_in_progress.discard(strategy_id)


async def _run_probe_review(
    db: AsyncSession,
    strategy: Strategy,
    ambiguous_summaries: list[dict],
    auto_assessments: list[dict] | None = None,
    rule_suggestions: list[dict] | None = None,
) -> dict:
    """运行 probe_review_chain 并存储结果

    Args:
        ambiguous_summaries: 需要 LLM 判定 verdict 的任务（客观指标无法确定）
        auto_assessments: 已通过客观规则判定的评估结果（直接合并，不送 LLM）
        rule_suggestions: auto-fail 任务的规则建议（不送 LLM，直接合并）
    """
    llm_assessments: list[dict] = []
    llm_add_suggestions: list[dict] = []
    parse_error: str | None = None

    # 仅在有模糊案例时调用 LLM（每个任务独立并行评估，消除批量上下文干扰）
    if ambiguous_summaries:
        chain = create_single_task_probe_review_chain()
        research_design = strategy.research_design or {}
        brief = strategy.brand_brief

        job = await create_analysis_job_async(
            db,
            monitor_id=strategy.monitor_id,
            task_id=None,
            user_id=strategy.created_by,
            analysis_type=AnalysisType.STRATEGY_PROBE_REVIEW.value,
            source_count=len(ambiguous_summaries),
            status="processing",
            analysis_config={"strategy_id": strategy.id},
        ) if strategy.monitor_id else None

        async def _evaluate_one(task_summary: dict) -> tuple[dict | None, dict | None, float]:
            """评估单个任务，返回 (assessment, token_usage, duration)"""
            inputs = format_single_task_probe_review_inputs(
                research_design=research_design,
                task=task_summary,
                brief=brief,
            )
            t0 = time.time()
            try:
                resp = await chain.ainvoke(inputs)
                dur = time.time() - t0
                assessment = parse_single_task_probe_review_response(resp.content)
                usage = extract_token_usage(resp, duration_seconds=dur)
                return assessment, usage, dur
            except Exception as exc:
                logger.warning(
                    "Strategy %d task #%s probe review 失败: %s",
                    strategy.id, task_summary.get("task_id"), exc,
                )
                return None, None, time.time() - t0

        start = time.time()
        call_results = await asyncio.gather(
            *[_evaluate_one(t) for t in ambiguous_summaries]
        )
        duration = time.time() - start  # 并行总耗时

        # 合并结果和 token 统计
        total_input = total_output = total_tokens = 0
        total_cost = 0.0
        call_details = []
        failed_parses = 0

        for idx, (assessment, usage, dur) in enumerate(call_results):
            if assessment is None:
                failed_parses += 1
                continue
            llm_assessments.append(assessment)
            if usage:
                s = usage.get("summary", {})
                total_input += s.get("total_input_tokens", 0)
                total_output += s.get("total_output_tokens", 0)
                total_tokens += s.get("total_tokens", 0)
                total_cost += s.get("total_cost_cny", 0.0)
                for detail in usage.get("call_details", []):
                    call_details.append({**detail, "call_index": idx})

        if failed_parses:
            parse_error = f"{failed_parses} 个任务解析失败"

        merged_token_usage = {
            "summary": {
                "total_calls": len(ambiguous_summaries),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_tokens,
                "total_cost_cny": round(total_cost, 6),
                "total_duration_seconds": round(duration, 2),
                "avg_tokens_per_call": float(total_tokens) / len(ambiguous_summaries) if ambiguous_summaries else 0.0,
                "avg_cost_per_call": round(total_cost / len(ambiguous_summaries), 6) if ambiguous_summaries else 0.0,
            },
            "call_details": call_details,
        }

        if job:
            now = datetime.now(timezone.utc)
            job.status = "completed" if not parse_error else "failed"
            job.completed_at = now
            job.analyzed_count = len(llm_assessments)
            job.processing_time = int(duration)
            job.token_usage = merged_token_usage
            if parse_error:
                job.error_message = parse_error

        logger.info(
            "Strategy %d probe review 并行 LLM 完成 (%.1fs, 模糊=%d, 成功=%d)",
            strategy.id, duration, len(ambiguous_summaries), len(llm_assessments),
        )
    else:
        logger.info("Strategy %d probe review 全部自动判定，跳过 LLM", strategy.id)

    # 合并所有评估结果
    all_assessments = (auto_assessments or []) + llm_assessments

    # 从合并后的 assessments 确定性计算 overall_verdict
    verdicts = [a.get("verdict", "fail") for a in all_assessments]
    fail_count = sum(1 for v in verdicts if v == "fail")
    if not verdicts:
        overall = "fail"
    elif fail_count == 0:
        overall = "all_pass"
    elif fail_count == len(verdicts):
        overall = "fail"
    else:
        overall = "partial_pass"

    # 合并建议：rule_suggestions（auto-fail） + LLM-fail assessments 中的 suggested_keyword
    all_suggestions: list[dict] = list(rule_suggestions or [])
    for a in llm_assessments:
        if a.get("verdict") == "fail" and a.get("suggested_keyword"):
            all_suggestions.append({
                "task_id": a["task_id"],
                "original_keyword": a.get("keyword", ""),
                "suggested_keyword": a["suggested_keyword"],
                "platform": a.get("platform", ""),
                "reason": a.get("suggestion_reason", ""),
            })

    logger.info(
        "Strategy %d probe review 完成 (verdict=%s, 规则自动=%d, LLM=%d)",
        strategy.id, overall,
        len(auto_assessments or []), len(llm_assessments),
    )

    result: dict = {
        "assessments": all_assessments,
        "overall_verdict": overall,
        "refinement_suggestions": all_suggestions,
        "add_suggestions": llm_add_suggestions,
    }
    if parse_error:
        result["_parse_error"] = parse_error

    strategy.probe_review_result = result
    flag_modified(strategy, "probe_review_result")
    await db.commit()

    return result



async def parse_brief_from_file(content: bytes, filename: str) -> ParseBriefResponse:
    """从上传文档提取文本并用 LLM 解析为 BrandBrief 字段"""
    try:
        raw_text = await run_cpu_bound_task(_extract_text_from_bytes, content, filename)
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

    document_text = raw_text[:_MAX_BRIEF_TEXT_CHARS]

    chain = create_strategy_brief_parser_chain()
    try:
        response = await chain.ainvoke({"document_text": document_text})
        response_text = (
            response.content if hasattr(response, "content") else str(response)
        )
        parsed = parse_brief_parser_response(response_text)
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

    return ParseBriefResponse(**parsed)

# ==================== 探测任务审批和调整 ====================

async def approve_probe(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> ApproveProbeResponse:
    """手动确认探测，为每个探测任务创建独立的全量采集任务（phase="collect"）"""
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task

    # 获取当前所有 probe 任务
    probe_task_ids = list(strategy.task_ids or [])
    if not probe_task_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有探测任务，无法确认",
        )

    # 查询 probe 任务
    stmt = select(Strategy).where(Strategy.id == strategy.id)
    stmt = stmt.options(selectinload(Strategy.task_ids))
    result = await db.execute(stmt)
    strategy_result = result.scalar_one_or_none()
    if not strategy_result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="策略不存在")

    strategy_obj = strategy_result
    from sqlalchemy import or_

    # 批量加载 probe 任务（避免 N+1 查询）
    probe_tasks_stmt = select(DataTask).where(
        and_(
            DataTask.id.in_(probe_task_ids),
            DataTask.phase == "probe",
            DataTask.is_deleted.is_(False),
        )
    )
    probe_tasks_result = await db.execute(probe_tasks_stmt)
    probe_tasks = list(probe_tasks_result.scalars().all())

    # 创建全量采集任务
    collect_task_ids = []
    for pt in probe_tasks:
        # 构造任务参数
        collect_task_params = {
            "max_notes_count": 50,  # 全量采集默认 50 条
            "enable_comments": 1,  # 启用评论
            "per_note_max_comments_count": 20,  # 每帖最多 20 条评论
            # max_pages: 不设置，表示不限制翻页
        }

        collect_task = await create_task(
            db,
            DataTaskCreate(
                name=f"{pt.keywords}-{pt.platform.name}",
                monitor_id=strategy.monitor_id,
                platform_id=pt.platform_id,
                task_type="search",
                keywords=pt.keywords,
                data_source="remote_crawler",
                task_params=collect_task_params,
                auto_analyze=True,
                phase="collect",  # 标记为全量采集任务
            ),
            current_user_id,
        )
        collect_task_ids.append(collect_task.id)

    # 更新策略
    strategy_obj.task_ids = collect_task_ids
    strategy_obj.status = "collecting"
    flag_modified(strategy_obj, "task_ids")
    flag_modified(strategy_obj, "status")

    await db.commit()

    return ApproveProbeResponse(
        approved_task_count=len(collect_task_ids),
        strategy=strategy_obj,
    )

async def refine_probe(
    db: AsyncSession,
    strategy: Strategy,
    data: RefineProbeRequest,
    current_user_id: int,
) -> RefineProbeResponse:
    """调整探测任务关键词，创建新的探测任务（phase="probe"），probe_round++"""
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task
    from src.social_media.monitors.crud import get_platform_by_code

    if STATUS_ORDER.get(strategy.status, 0) > STATUS_ORDER["probing"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="全量采集已启动，无法调整探测任务",
        )

    # 获取当前所有 probe 任务
    probe_task_ids = list(strategy.task_ids or [])
    if not probe_task_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有探测任务，无法调整",
        )

    # 软删除旧探测任务
    from sqlalchemy import select, and_, delete as sa_delete
    from src.social_media.tasks.models import DataTask

    old_tasks_stmt = select(DataTask).where(
        and_(
            DataTask.id.in_(probe_task_ids),
            DataTask.phase == "probe",
            DataTask.is_deleted.is_(False),
        )
    )
    old_tasks_result = await db.execute(old_tasks_stmt)
    
    # 构造新任务
    new_task_ids = []
    for item in data.refinements:
        if item.task_id is None and item.new_keyword is None:
            raise ValueError("新增任务时 new_keyword 不能为空")
        
        if item.task_id is not None and item.new_keyword is not None:
            raise ValueError("task_id 和 new_keyword 不能同时指定")
        
        if item.task_id is not None and not item.dimension:
            raise ValueError("新增任务时 dimension 不能为空")

        # 软删除旧任务
        await db.execute(
            sa_delete(DataTask).where(DataTask.id == item.task_id)
        )
        
        # 为每个平台创建新任务
        for platform_name in item.platform:
            code = PLATFORM_NAME_TO_CODE.get(platform_name, platform_name)
            platform = await get_platform_by_code(db, code)
            if not platform:
                continue
            
            # 设置 max_pages 根据平台（同 confirm_research 逻辑）
            max_pages = 2 if code in ("wb", "tieba") else 1
            
            new_task = await create_task(
                db,
                DataTaskCreate(
                    name=f"{item.new_keyword}-{platform.name}",
                    monitor_id=strategy.monitor_id,
                    platform_id=platform.id,
                    task_type="search",
                    keywords=item.new_keyword,
                    data_source="remote_crawler",
                    task_params={
                        "max_notes_count": 20,  # 探测任务默认 20 条
                        "enable_comments": 0,
                        "per_note_max_comments_count": 0,
                        "max_pages": max_pages,
                    },
                    auto_analyze=True,
                    phase="probe",
                ),
                current_user_id,
            )
            new_task_ids.append(new_task.id)
    
    # 更新 strategy
    strategy.task_ids = new_task_ids
    strategy.probe_round = strategy.probe_round + 1 if strategy.probe_round else 1
    flag_modified(strategy, "task_ids")
    flag_modified(strategy, "probe_round")
    
    await db.commit()

    return RefineProbeResponse(
        removed_task_ids=list(strategy.task_ids),
        created_task_ids=new_task_ids,
        probe_round=strategy.probe_round,
        strategy=strategy,
    )

async def check_collection_status(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> CollectionStatusResponse:
    """查询全量采集任务的完成状态，全部完成后自动建切片"""
    """查询全量采集进度，全部完成后自动建切片并验证覆盖度"""
    from src.social_media.tasks.models import DataTask
    from src.langchain.chains.strategy_coverage_check_chain import (
        create_coverage_check_chain,
        format_coverage_inputs,
        parse_coverage_check_response,
    )

    # 获取当前 collect 任务（task_ids 现在存的是 collect 任务）
    task_ids = list(strategy.task_ids or [])
    if not task_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有任务，无法查询进度",
        )

    # 查询 collect 任务
    stmt = select(DataTask).where(
        and_(
            DataTask.id.in_(task_ids),
            DataTask.phase == "collect",
            DataTask.is_deleted.is_(False),
        )
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到采集任务",
        )

    # 检查任务完成状态
    all_completed = all(task.status == "completed" for task in tasks)
    all_analyzed = all(task.analysis_result is not None for task in tasks)

    # 构造任务摘要
    task_statuses = [
        CollectionTaskStatus(
            task_id=task.id,
            keyword=task.keywords or "",
            platform=task.platform.code if task.platform else "",
            status=task.status,
            posts_count=task.posts_count,
            has_analysis=task.analysis_result is not None,
        )
        for task in tasks
    ]

    # 如果全部完成且全部已分析，触发覆盖度检查
    if all_completed and all_analyzed:
        # 检查是否已经创建过切片
        from src.social_media.analysis.crud import check_slice_exists
        from src.langchain.chains.strategy_coverage_check_chain import run_coverage_check_chain_async
        
        has_slices = await check_slice_exists(db, strategy.monitor_id)
        
        if not has_slices:
            # 触发覆盖度检查
            logger.info(
                f"Strategy {strategy.id}: 所有任务完成且已分析，触发覆盖度检查"
            )
            
            try:
                # 准备输入
                monitor_name = strategy.monitor.name if strategy.monitor else ""
                
                inputs = format_coverage_inputs(
                    task_statuses=task_statuses,
                    monitor_name=monitor_name,
                )
                
                # 创建分析任务
                from src.social_media.analysis.jobs.factory import create_analysis_job_async
                from src.social_media.analysis.models import AnalysisType
                
                job = await create_analysis_job_async(
                    db,
                    monitor_id=strategy.monitor_id,
                    task_id=None,
                    user_id=strategy.created_by,
                    analysis_type=AnalysisType.STRATEGY_COVERAGE_CHECK.value,
                    source_count=len(task_statuses),
                    status="processing",
                    analysis_config={"strategy_id": strategy.id},
                )
                
                logger.info(
                    f"Strategy {strategy.id}: 覆盖度检查任务已创建，job_id={job.id}"
                )
                
            except Exception as e:
                logger.error(
                    f"Strategy {strategy.id}: 触发覆盖度检查失败: {e}",
                    exc_info=True,
                )
                # 不阻塞主流程，让用户可以手动触发
    elif all_completed:
        logger.info(f"Strategy {strategy.id}: 所有任务已完成，等待分析")
    
    return CollectionStatusResponse(
        tasks=task_statuses,
        all_completed=all_completed,
        all_analyzed=all_analyzed,
        strategy=strategy,
    )
