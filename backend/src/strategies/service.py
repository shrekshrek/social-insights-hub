"""策略定义业务逻辑"""

import asyncio
import io
import logging
import time

from fastapi import HTTPException, status
from sqlalchemy import select, func
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
    create_probe_review_chain,
    format_probe_review_inputs,
    parse_probe_review_response,
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
    FeasibilityAssessment,
    ParseBriefResponse,
    ProbeStatusResponse,
    ProbeTaskStatus,
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


async def load_slice_data(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """读取策略关联的切片 result_data"""
    slice_ids = [s.slice_id for s in strategy.slices]
    if not slice_ids:
        return []

    query = select(AnalysisSlice).where(AnalysisSlice.id.in_(slice_ids))
    result = await db.execute(query)
    slices = result.scalars().all()
    return [s.result_data for s in slices if s.result_data]


async def load_slice_data_with_names(
    db: AsyncSession, strategy: Strategy
) -> list[tuple[str | None, dict]]:
    """读取策略关联的切片 (name, result_data)，用于评估链"""
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
    slices_data = await load_slice_data(db, strategy)
    _validate_slices_have_data(slices_data, strategy)

    chain = create_strategy_phase1_chain()
    inputs = format_slice_data_for_phase1(
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
    )

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase1_response(response.content)
    logger.info("Strategy %d Phase 1 生成完成 (%.1fs)", strategy.id, duration)

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

    slices_data = await load_slice_data(db, strategy)
    _validate_slices_have_data(slices_data, strategy)

    chain = create_strategy_phase2_chain()
    inputs = format_data_for_phase2(
        strategy.phase1_result,
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
    )

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase2_response(response.content)
    logger.info("Strategy %d Phase 2 生成完成 (%.1fs)", strategy.id, duration)

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

    slices_data = await load_slice_data(db, strategy)
    _validate_slices_have_data(slices_data, strategy)

    chain = create_strategy_phase3_chain()
    inputs = format_data_for_phase3(
        strategy.phase1_result,
        strategy.phase2_result,
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
    )

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase3_response(response.content)
    logger.info("Strategy %d Phase 3 生成完成 (%.1fs)", strategy.id, duration)

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


async def design_research(
    db: AsyncSession,
    strategy: Strategy,
    user_input: str,
) -> DesignResearchResponse:
    """AI 研究设计：基于 Brief 生成结构化研究计划

    输出研究问题、数据采集方案、切片蓝图、产出类型建议。
    每次调用覆盖上一次结果。
    LLM 解析失败时抛出 HTTPException(500)，strategy 不更新。
    """
    chain = create_research_design_chain()
    inputs = format_research_design_inputs(
        user_input=user_input,
        brief=strategy.brand_brief,
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

    feasibility_data = parsed.get("feasibility") or {}
    response = DesignResearchResponse(
        feasibility=FeasibilityAssessment(**feasibility_data),
        understanding_summary=parsed["understanding_summary"],
        research_questions=parsed["research_questions"],
        data_plan=parsed["data_plan"],
        slice_blueprint=parsed["slice_blueprint"],
        output_type=parsed["output_type"],
        output_type_rationale=parsed.get("output_type_rationale", ""),
    )
    logger.info(
        "Strategy %d 研究设计完成 (%.1fs, fit=%.1f/%s, %d 个研究问题, %d 个数据维度)",
        strategy.id,
        duration,
        feasibility_data.get("fit_score", 0.5),
        feasibility_data.get("recommendation", "proceed"),
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
    task_params 包含 probe_size 用于增量采集协议。
    """
    from src.social_media.monitors.crud import get_monitor_by_name, get_platform_by_code
    from src.social_media.monitors.schemas import MonitorCreate
    from src.social_media.monitors.service import create_monitor
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task

    if STATUS_ORDER.get(strategy.status, 0) > STATUS_ORDER["planned"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="策略已进入探测/采集阶段，如需重新确认请先重置到研究设计阶段",
        )

    data_plan = research_design.get("data_plan") or []
    if not data_plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="研究计划中无数据采集方案",
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

        task_params = {
            "max_notes_count": notes_per_task,
            "probe_size": probe_notes,
            "enable_comments": 1,
            "per_note_max_comments_count": 20,
        }

        for keyword in clean_keywords:
            for platform_name in platforms:
                code = PLATFORM_NAME_TO_CODE.get(platform_name, platform_name)
                try:
                    platform = await get_platform_by_code(db, code)
                    if not platform:
                        partial_errors.append(f"平台「{platform_name}」不存在，跳过")
                        continue
                    task = await create_task(
                        db,
                        DataTaskCreate(
                            name=f"{keyword}-{platform.name}",
                            monitor_id=monitor.id,
                            platform_id=platform.id,
                            task_type="search",
                            keywords=keyword,
                            data_source="remote_crawler",
                            task_params=task_params,
                            auto_analyze=True,
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

    statuses = []
    analyzed_summaries = []

    for task in tasks:
        has_analysis = task.analysis_result is not None
        no_data = (task.posts_count or 0) == 0

        # 0 条数据：不会触发分析流程，但无需 LLM 判断，直接视为已处理（客观规则层会自动 fail）
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
                await _approve_all_probe_tasks(db, list(strategy.task_ids or []))
                strategy.status = "collecting"
                await db.commit()
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

    # 仅在有模糊案例时调用 LLM（auto-fail 任务不送 LLM，已有规则建议）
    if ambiguous_summaries:
        chain = create_probe_review_chain()
        inputs = format_probe_review_inputs(
            research_design=strategy.research_design or {},
            tasks=ambiguous_summaries,
            brief=strategy.brand_brief,
        )

        start = time.time()
        llm_result = await chain.ainvoke(inputs)
        duration = time.time() - start

        try:
            parsed = parse_probe_review_response(llm_result.content)
            llm_assessments = parsed.get("assessments", [])
            llm_add_suggestions = parsed.get("add_suggestions", [])
        except ValueError as e:
            logger.warning("Strategy %d probe review 解析失败: %s", strategy.id, e)
            parse_error = str(e)

        logger.info(
            "Strategy %d probe review LLM 完成 (%.1fs, 模糊=%d)",
            strategy.id, duration, len(ambiguous_summaries),
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



async def _approve_all_probe_tasks(
    db: AsyncSession,
    task_ids: list[int],
) -> int:
    """将所有 probe_ready 任务标记为 approved

    爬虫端通过 status 字段区分探测(pending)和续采(approved)模式，
    不再依赖 probe_size 是否存在来判断。task_params 保持不变。
    """
    from sqlalchemy import update as sa_update
    from src.social_media.tasks.models import DataTask

    result = await db.execute(
        sa_update(DataTask)
        .where(DataTask.id.in_(task_ids), DataTask.status == "probe_ready")
        .values(status="approved")
    )
    return result.rowcount or 0


async def check_probe_status(
    db: AsyncSession,
    strategy: Strategy,
) -> ProbeStatusResponse:
    """查询探测进度，全部分析完成后自动触发审查（后台非阻塞）

    轮询语义：
    - 未全部分析完成 → 返回进度，all_analyzed=False
    - 全部完成 + 无审查结果 → 触发后台审查任务（首次），或等待进行中的任务完成
    - 审查结果已就绪 → 返回结果（含 strategy 快照）
    - all_pass → 后台任务已自动 approve + 状态推进到 collecting
    """
    task_ids = list(strategy.task_ids or [])
    statuses, analyzed_summaries = await _build_probe_task_summaries(db, task_ids)

    total = len(statuses)
    analyzed = sum(1 for s in statuses if s.has_analysis)
    all_analyzed = total > 0 and analyzed == total

    # 已有审查结果 → 直接返回缓存
    if strategy.probe_review_result:
        fresh = await get_strategy_by_id(db, strategy.id)
        return ProbeStatusResponse(
            all_analyzed=all_analyzed,
            tasks=statuses,
            analyzed_count=analyzed,
            total_count=total,
            probe_review_result=strategy.probe_review_result,
            strategy=build_strategy_read(fresh),
        )

    # 未全部分析完成 → 返回进度
    if not all_analyzed:
        return ProbeStatusResponse(
            all_analyzed=False,
            tasks=statuses,
            analyzed_count=analyzed,
            total_count=total,
        )

    # 全部分析完成 + 无审查结果 → 触发后台任务（防重复启动）
    if strategy.id not in _probe_review_in_progress:
        _probe_review_in_progress.add(strategy.id)
        asyncio.create_task(
            _run_probe_review_bg_task(strategy.id, analyzed_summaries)
        )
        logger.info("Strategy %d 探测审查后台任务已触发", strategy.id)

    # 审查进行中，客户端继续轮询
    return ProbeStatusResponse(
        all_analyzed=True,
        tasks=statuses,
        analyzed_count=analyzed,
        total_count=total,
        probe_review_result=None,
    )


async def approve_probe(
    db: AsyncSession,
    strategy: Strategy,
) -> ApproveProbeResponse:
    """手动确认探测通过，状态 → collecting"""
    if strategy.status != "probing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前状态不在探测验证阶段",
        )
    task_ids = list(strategy.task_ids or [])
    approved_count = await _approve_all_probe_tasks(db, task_ids)

    strategy.status = "collecting"
    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)

    return ApproveProbeResponse(
        approved_task_count=approved_count,
        strategy=build_strategy_read(updated),
    )


async def refine_probe(
    db: AsyncSession,
    strategy: Strategy,
    refinements: list[dict],
    current_user_id: int,
) -> RefineProbeResponse:
    """调整关键词，创建新探测任务

    1. 检查 probe_round < 3
    2. 软删除不合格的旧任务
    3. 用新关键词创建新探测任务
    4. 更新 strategy.task_ids + probe_round
    """
    from src.social_media.monitors.crud import get_platform_by_code
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task
    from src.social_media.tasks import crud as task_crud

    _PROBE_MIN_TASKS = 3
    _PROBE_MAX_TASKS = 20

    if strategy.status != "probing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前状态不在探测验证阶段",
        )

    if strategy.probe_round >= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已达最大探测轮次（3 轮），请手动确认或回到研究设计阶段",
        )

    if not strategy.monitor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略尚未创建监测",
        )

    # 预检：验证调整后总任务数在合理范围内
    current_total = len(list(strategy.task_ids or []))
    net_change = sum(
        1 if item.get("task_id") is None          # 纯新增
        else (-1 if not item.get("new_keyword")   # 纯移除
              else 0)                              # 替换（±0）
        for item in refinements
    )
    projected_total = current_total + net_change
    if projected_total < _PROBE_MIN_TASKS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"调整后任务数（{projected_total}）低于最小值 {_PROBE_MIN_TASKS}，请保留足够的探测任务",
        )
    if projected_total > _PROBE_MAX_TASKS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"调整后任务数（{projected_total}）超过最大值 {_PROBE_MAX_TASKS}，请减少新增数量",
        )

    # 获取原 task 的 probe_size / notes_per_task
    research_design = strategy.research_design or {}
    data_plan = research_design.get("data_plan", [])
    # 从第一个 data_plan 条目取 probe_size，默认 20（与 confirm_research 保持一致）
    default_probe_size = 20
    default_full_size = 50
    if data_plan:
        default_probe_size = data_plan[0].get("probe_size", 20)
        default_full_size = data_plan[0].get("full_size", 50)

    removed_task_ids = []
    created_task_ids = []
    current_task_ids = list(strategy.task_ids or [])
    old_to_new_task_ids: dict[int, int] = {}  # 追踪旧→新 task ID 映射，用于继承维度

    from src.social_media.tasks.models import DataTask

    new_task_dim_map: dict[int, str] = {}  # 新建 task_id → dimension，用于更新 dim_map

    for item in refinements:
        old_task_id = item.get("task_id")
        new_keyword = item.get("new_keyword")
        platform_code = item.get("platform", "")

        # ── 纯新增（task_id=None）──
        if old_task_id is None:
            platform = await get_platform_by_code(db, platform_code)
            if not platform:
                logger.warning("refine_probe: 平台 %s 不存在，跳过新增", platform_code)
                continue
            new_task = await create_task(
                db,
                DataTaskCreate(
                    name=f"{new_keyword}-{platform.name}",
                    monitor_id=strategy.monitor_id,
                    platform_id=platform.id,
                    task_type="search",
                    keywords=new_keyword,
                    data_source="remote_crawler",
                    task_params={
                        "max_notes_count": default_full_size,
                        "probe_size": default_probe_size,
                        "enable_comments": 1,
                        "per_note_max_comments_count": 20,
                    },
                    auto_analyze=True,
                ),
                current_user_id,
            )
            created_task_ids.append(new_task.id)
            current_task_ids.append(new_task.id)
            new_task_dim_map[new_task.id] = item.get("dimension") or ""
            continue

        # ── 软删除旧任务（替换 or 移除）──
        old_task = await db.get(DataTask, old_task_id)
        if old_task and not old_task.is_deleted:
            await task_crud.delete_task(db, old_task)
            removed_task_ids.append(old_task_id)
            if old_task_id in current_task_ids:
                current_task_ids.remove(old_task_id)

        # new_keyword 为空：仅移除，不创建替换任务
        if not new_keyword:
            continue

        # ── 创建替换任务 ──
        platform = await get_platform_by_code(db, platform_code)
        if not platform:
            logger.warning("refine_probe: 平台 %s 不存在，跳过替换", platform_code)
            continue

        new_task = await create_task(
            db,
            DataTaskCreate(
                name=f"{new_keyword}-{platform.name}",
                monitor_id=strategy.monitor_id,
                platform_id=platform.id,
                task_type="search",
                keywords=new_keyword,
                data_source="remote_crawler",
                task_params={
                    "max_notes_count": default_full_size,
                    "probe_size": default_probe_size,
                    "enable_comments": 1,
                    "per_note_max_comments_count": 20,
                },
                auto_analyze=True,
            ),
            current_user_id,
        )
        created_task_ids.append(new_task.id)
        current_task_ids.append(new_task.id)
        old_to_new_task_ids[old_task_id] = new_task.id

    # 更新策略
    strategy.task_ids = current_task_ids
    flag_modified(strategy, "task_ids")
    strategy.probe_round = (strategy.probe_round or 0) + 1
    strategy.probe_review_result = None  # 清除旧审查结果
    flag_modified(strategy, "probe_review_result")

    # 更新 research_design：继承替换任务的维度 + 写入新增任务的维度
    rd = strategy.research_design or {}
    dim_map = dict(rd.get("_task_dimension_map") or {})
    for old_id, new_id in old_to_new_task_ids.items():
        old_dim = dim_map.get(str(old_id), "")
        if old_dim:
            dim_map[str(new_id)] = old_dim
    for new_id, dim in new_task_dim_map.items():
        dim_map[str(new_id)] = dim
    rd["_task_dimension_map"] = dim_map
    strategy.research_design = rd
    flag_modified(strategy, "research_design")

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)

    return RefineProbeResponse(
        removed_task_ids=removed_task_ids,
        created_task_ids=created_task_ids,
        probe_round=strategy.probe_round,
        strategy=build_strategy_read(updated),
    )


# ==================== ③ 数据就绪 ====================


async def check_collection_status(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> CollectionStatusResponse:
    """查询全量采集进度，全部完成后自动建切片 + 覆盖度验证

    自动化链：
    1. 检查所有 task_ids 完成情况
    2. 全部完成且有分析结果 → 自动建切片（如果尚未创建）
    3. 切片就绪 → 运行 coverage_check_chain
    4. overall_ready → 状态 → ready
    """
    from src.social_media.tasks.models import DataTask

    task_ids = list(strategy.task_ids or [])
    if not task_ids:
        return CollectionStatusResponse(total_count=0)

    query = select(DataTask).where(
        DataTask.id.in_(task_ids), DataTask.is_deleted.is_(False)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    statuses = []
    completed_count = 0
    analyzed_count = 0
    for t in tasks:
        is_completed = t.status == "completed"
        has_analysis = t.analysis_result is not None
        if is_completed:
            completed_count += 1
        if has_analysis:
            analyzed_count += 1
        statuses.append(
            CollectionTaskStatus(
                task_id=t.id,
                status=t.status,
                has_analysis=has_analysis,
            )
        )

    total = len(statuses)
    all_completed = completed_count == total and total > 0
    all_analyzed = analyzed_count == total and total > 0

    # 尚未全部完成分析 → 返回进度
    if not all_analyzed:
        return CollectionStatusResponse(
            all_completed=all_completed,
            all_analyzed=False,
            tasks=statuses,
            completed_count=completed_count,
            total_count=total,
        )

    # 检查是否已建切片
    has_slices = len(strategy.slices) > 0

    # 全部分析完成但尚未建切片 → 自动建切片
    if not has_slices:
        await _create_auto_slices(db, strategy, current_user_id)
        # 重新加载策略
        strategy = await get_strategy_by_id(db, strategy.id)

    has_slices = len(strategy.slices) > 0

    # 切片已就绪 → 运行覆盖度验证（如果尚未运行）
    if has_slices and not strategy.coverage_check_result:
        await _run_coverage_check(db, strategy)
        strategy = await get_strategy_by_id(db, strategy.id)

    # 自动判定 ready
    if (
        strategy.coverage_check_result
        and strategy.coverage_check_result.get("overall_ready")
        and STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["ready"]
    ):
        strategy.status = "ready"
        await db.commit()
        strategy = await get_strategy_by_id(db, strategy.id)

    return CollectionStatusResponse(
        all_completed=True,
        all_analyzed=True,
        slices_created=has_slices,
        tasks=statuses,
        completed_count=completed_count,
        total_count=total,
        coverage_check_result=strategy.coverage_check_result,
        strategy=build_strategy_read(strategy),
    )


async def _create_auto_slices(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> None:
    """按 slice_blueprint 自动创建切片并关联到策略"""
    from src.social_media.analysis.service import create_monitor_slice

    research_design = strategy.research_design or {}
    blueprint = research_design.get("slice_blueprint", [])
    data_plan = research_design.get("data_plan", [])
    task_dim_map = research_design.get("_task_dimension_map", {})

    if not blueprint or not strategy.monitor_id:
        logger.warning(
            "Strategy %d: 无法自动建切片（无 blueprint 或 monitor_id）", strategy.id
        )
        return

    # 建立 dimension_name → task_ids 映射
    dim_to_tasks: dict[str, list[int]] = {}
    for task_id_str, dim_name in task_dim_map.items():
        dim_to_tasks.setdefault(dim_name, []).append(int(task_id_str))

    # 如果 _task_dimension_map 为空，按 data_plan 顺序分配
    if not dim_to_tasks and data_plan:
        all_task_ids = list(strategy.task_ids or [])
        # 简单均分
        for i, dp in enumerate(data_plan):
            dim_name = dp.get("dimension_name", f"dim_{i}")
            dim_to_tasks[dim_name] = all_task_ids

    created_count = 0
    for slice_spec in blueprint:
        source_dims = slice_spec.get("source_dimensions", [])
        task_ids_for_slice = []
        for dim in source_dims:
            task_ids_for_slice.extend(dim_to_tasks.get(dim, []))

        # 去重
        task_ids_for_slice = list(dict.fromkeys(task_ids_for_slice))
        if not task_ids_for_slice:
            logger.warning(
                "Strategy %d: 切片 '%s' 无对应任务，跳过",
                strategy.id,
                slice_spec.get("name", ""),
            )
            continue

        try:
            slice_obj = await create_monitor_slice(
                db,
                monitor_id=strategy.monitor_id,
                task_ids=task_ids_for_slice,
                current_user_id=current_user_id,
                name=slice_spec.get("name"),
                subject=slice_spec.get("subject") or None,
                competitors=slice_spec.get("competitors"),
            )
            # 关联到策略
            existing = await db.get(
                StrategySlice,
                {"strategy_id": strategy.id, "slice_id": slice_obj.id},
            )
            if not existing:
                db.add(StrategySlice(strategy_id=strategy.id, slice_id=slice_obj.id))
            created_count += 1
        except Exception as e:
            logger.error(
                "Strategy %d: 自动建切片 '%s' 失败: %s",
                strategy.id,
                slice_spec.get("name", ""),
                e,
            )

    if created_count > 0:
        await db.commit()
        logger.info("Strategy %d: 自动创建 %d 个切片", strategy.id, created_count)


async def _run_coverage_check(
    db: AsyncSession,
    strategy: Strategy,
) -> dict:
    """运行覆盖度验证并存储结果"""
    research_design = strategy.research_design or {}
    research_questions = research_design.get("research_questions", [])

    # 加载切片数据
    slices_data = await load_slice_data_with_names(db, strategy)

    chain = create_coverage_check_chain()
    inputs = format_coverage_check_inputs(
        brief=strategy.brand_brief,
        research_questions=research_questions,
        slices_data=slices_data,
    )

    start = time.time()
    llm_result = await chain.ainvoke(inputs)
    duration = time.time() - start

    try:
        parsed = parse_coverage_check_response(llm_result.content)
    except ValueError as e:
        logger.warning("Strategy %d coverage check 解析失败: %s", strategy.id, e)
        parsed = {
            "question_coverage": [],
            "overall_ready": True,  # 解析失败时默认就绪，不阻塞用户
            "data_highlights": [],
            "slice_adjustments": [],
            "_parse_error": str(e),
        }

    logger.info(
        "Strategy %d coverage check 完成 (%.1fs, ready=%s)",
        strategy.id,
        duration,
        parsed.get("overall_ready"),
    )

    strategy.coverage_check_result = parsed
    flag_modified(strategy, "coverage_check_result")
    await db.commit()

    return parsed


async def get_data_overview(
    db: AsyncSession,
    strategy: Strategy,
) -> DataOverviewResponse:
    """数据全景：切片列表 + 覆盖度结果"""
    return DataOverviewResponse(
        slices=[
            SliceSummary(
                slice_id=ss.slice_id,
                slice_name=ss.slice.name if ss.slice else None,
                monitor_id=ss.slice.monitor_id if ss.slice else 0,
                monitor_name=(
                    ss.slice.monitor.name if ss.slice and ss.slice.monitor else ""
                ),
            )
            for ss in strategy.slices
        ],
        coverage_check_result=strategy.coverage_check_result,
        strategy=build_strategy_read(strategy),
    )


async def adjust_slices(
    db: AsyncSession,
    strategy: Strategy,
    adjustments: list[dict],
    current_user_id: int,
) -> StrategyRead:
    """微调切片配置（重命名/调整主体/竞品），然后重新验证覆盖度"""
    for adj in adjustments:
        slice_id = adj["slice_id"]
        slice_obj = await db.get(AnalysisSlice, slice_id)
        if not slice_obj:
            continue

        if adj.get("name") is not None:
            slice_obj.name = adj["name"]

        # subject/competitors 变更需要重建切片 result_data
        need_rebuild = False
        if adj.get("subject") is not None or adj.get("competitors") is not None:
            need_rebuild = True

        if need_rebuild:
            from src.social_media.analysis.service import create_monitor_slice

            # 删除旧的 StrategySlice 关联
            old_link = await db.get(
                StrategySlice,
                {"strategy_id": strategy.id, "slice_id": slice_id},
            )
            if old_link:
                await db.delete(old_link)

            # 重建切片
            try:
                new_slice = await create_monitor_slice(
                    db,
                    monitor_id=slice_obj.monitor_id,
                    task_ids=slice_obj.included_task_ids,
                    current_user_id=current_user_id,
                    name=adj.get("name") or slice_obj.name,
                    subject=adj.get("subject"),
                    competitors=adj.get("competitors"),
                )
                db.add(StrategySlice(strategy_id=strategy.id, slice_id=new_slice.id))
            except Exception as e:
                logger.error("adjust_slices: 重建切片 %d 失败: %s", slice_id, e)

    # 清除旧覆盖度结果，触发重新验证
    strategy.coverage_check_result = None
    flag_modified(strategy, "coverage_check_result")
    await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    return build_strategy_read(updated)


# ==================== 编辑 Phase ====================


async def edit_phase_result(
    db: AsyncSession, strategy: Strategy, phase: int, result: dict
) -> Strategy:
    """编辑阶段结果，自动清除下游"""
    if phase == 1:
        strategy.phase1_result = result
        strategy.phase2_result = None
        strategy.phase3_result = None
        strategy.status = "phase1_done"
    elif phase == 2:
        strategy.phase2_result = result
        strategy.phase3_result = None
        strategy.status = "phase2_done"
    elif phase == 3:
        strategy.phase3_result = result
        # 保持 status="completed"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的阶段: {phase}",
        )

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


# ==================== Brief 文档解析 ====================

_MAX_BRIEF_TEXT_CHARS = 12000


def _extract_text_from_bytes(content: bytes, filename: str) -> str:
    """从文件字节提取纯文本"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)

    if ext == "docx":
        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # TXT / MD — UTF-8 with fallback to GBK
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("gbk", errors="replace")


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
