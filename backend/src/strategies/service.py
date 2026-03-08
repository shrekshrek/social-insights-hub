"""策略定义业务逻辑"""

import io
import logging
import time

from fastapi import HTTPException, status
from sqlalchemy import select, func
from src.utils import run_cpu_bound_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from src.langchain.chains.strategy_consult_chain import (
    create_strategy_consult_chain,
    format_consult_inputs,
    parse_consult_response,
)
from src.langchain.chains.strategy_architect_chain import (
    create_strategy_architect_chain,
    format_architect_inputs,
    parse_architect_response,
    extract_slice_meta,
)
from src.langchain.chains.strategy_evaluate_chain import (
    create_strategy_evaluate_chain,
    format_evaluate_inputs,
    parse_evaluate_response,
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
from src.social_media.analysis.models import AnalysisSlice
from src.social_media.monitors.crud import check_monitor_access, get_monitors
from src.social_media.monitors.models import Monitor

from .models import Strategy, StrategySlice
from .schemas import (
    ConfirmPlanResponse,
    ConfirmSupplementaryResponse,
    ConsultResponse,
    EvaluationResultResponse,
    ParseBriefResponse,
    StrategyCreate,
    StrategyUpdate,
    StrategyRead,
    StrategyListItem,
    SliceSummary,
    StructureAnalysisResult,
    SupplementaryStatusResponse,
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
            selectinload(Strategy.slices).selectinload(
                StrategySlice.slice
            ).selectinload(AnalysisSlice.monitor),
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


async def load_slice_data(
    db: AsyncSession, strategy: Strategy
) -> list[dict]:
    """读取策略关联的切片 result_data"""
    slice_ids = [s.slice_id for s in strategy.slices]
    if not slice_ids:
        return []

    query = select(AnalysisSlice).where(
        AnalysisSlice.id.in_(slice_ids)
    )
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

    query = select(AnalysisSlice).where(
        AnalysisSlice.id.in_(slice_ids)
    )
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
                    slice_obj.monitor.name
                    if slice_obj and slice_obj.monitor
                    else ""
                ),
            )
        )

    return StrategyRead(
        id=strategy.id,
        name=strategy.name,
        status=strategy.status,
        brand_brief=strategy.brand_brief,
        consultation_rounds=list(strategy.consultation_rounds or []),
        suggested_monitor_ids=list(strategy.suggested_monitor_ids or []),
        slice_plan=list(strategy.slice_plan or []),
        evaluation_result=strategy.evaluation_result,
        phase1_result=strategy.phase1_result,
        phase2_result=strategy.phase2_result,
        phase3_result=strategy.phase3_result,
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


async def filter_existing_monitor_ids(
    db: AsyncSession, monitor_ids: list[int]
) -> list[int]:
    """过滤出仍存在的监测 ID"""
    if not monitor_ids:
        return []
    query = select(Monitor.id).where(Monitor.id.in_(monitor_ids))
    result = await db.execute(query)
    existing = {row[0] for row in result.all()}
    return [mid for mid in monitor_ids if mid in existing]


# ==================== 生成 + 编辑 ====================

# 状态流转顺序
STATUS_ORDER = {
    "briefing": 0,
    "consulting": 1,
    "monitors_created": 2,
    "slices_ready": 3,
    "phase1_done": 4,
    "phase2_done": 5,
    "completed": 6,
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
        consultation_rounds=list(strategy.consultation_rounds or []),
        evaluation_result=strategy.evaluation_result,
    )

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase1_response(response.content)
    logger.info(
        "Strategy %d Phase 1 生成完成 (%.1fs)", strategy.id, duration
    )

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
        consultation_rounds=list(strategy.consultation_rounds or []),
    )

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase2_response(response.content)
    logger.info(
        "Strategy %d Phase 2 生成完成 (%.1fs)", strategy.id, duration
    )

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
        consultation_rounds=list(strategy.consultation_rounds or []),
    )

    start = time.time()
    response = await chain.ainvoke(inputs)
    duration = time.time() - start

    result = parse_phase3_response(response.content)
    logger.info(
        "Strategy %d Phase 3 生成完成 (%.1fs)", strategy.id, duration
    )

    strategy.phase3_result = result
    strategy.status = "completed"

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


# ==================== 新增：阶段 A 咨询流程 ====================


async def consult_strategy(
    db: AsyncSession,
    strategy: Strategy,
    user_input: str,
) -> ConsultResponse:
    """AI 监测方案规划：基于 Brand Brief 直接输出监测建议

    每次调用覆盖上一次结果（不累积轮次）。
    LLM 解析失败时抛出 HTTPException(500)，strategy 不更新。
    """
    chain = create_strategy_consult_chain()
    inputs = format_consult_inputs(
        user_input=user_input,
        brief=strategy.brand_brief,
    )

    start = time.time()
    llm_result = await chain.ainvoke(inputs)
    duration = time.time() - start

    try:
        parsed = parse_consult_response(llm_result.content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 方案规划解析失败: {e}",
        ) from e

    response = ConsultResponse(
        understanding_summary=parsed.get("understanding_summary", ""),
        monitor_suggestions=parsed["monitor_suggestions"],
        slice_plan=parsed["slice_plan"],
    )
    logger.info(
        "Strategy %d 监测方案生成完成 (%.1fs, %d 个监测建议)",
        strategy.id, duration, len(parsed["monitor_suggestions"]),
    )

    # 保存方案到 consultation_rounds（覆盖式，只保留最新一次）
    strategy.consultation_rounds = [{
        "user_input": user_input,
        "ai_response": response.model_dump(),
    }]
    flag_modified(strategy, "consultation_rounds")

    # 保存切片规划
    strategy.slice_plan = parsed["slice_plan"]
    flag_modified(strategy, "slice_plan")

    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["consulting"]:
        strategy.status = "consulting"

    await db.commit()
    return response


PLATFORM_NAME_TO_CODE = {
    "douyin": "dy",
    "weibo": "wb",
    "bilibili": "bili",
    "xiaohongshu": "xhs",
    "kuaishou": "ks",
    "zhihu": "zhihu",
    "tieba": "tieba",
}


async def confirm_plan(
    db: AsyncSession,
    strategy: Strategy,
    monitor_suggestions: list[dict],
    current_user_id: int,
    *,
    slice_plan: list[dict] | None = None,
    notes_per_task: int = 50,
) -> ConfirmPlanResponse:
    """确认 AI 建议，创建一个监测项目 + 所有数据任务

    所有 AI 建议的搜索维度（行业/品牌/竞品）作为任务放进同一个监测，
    便于后续自由组合切片做交叉分析。
    """
    from src.social_media.monitors.schemas import MonitorCreate
    from src.social_media.monitors.service import create_monitor
    from src.social_media.monitors.crud import get_platform_by_code, get_monitor_by_name
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task

    partial_errors: list[str] = []

    # 确定不重复的监测名称
    base_name = strategy.name
    monitor_name = base_name
    suffix = 1
    while await get_monitor_by_name(db, monitor_name):
        suffix += 1
        monitor_name = f"{base_name}({suffix})"

    # 创建一个监测项目
    try:
        result = await create_monitor(
            db,
            MonitorCreate(
                name=monitor_name,
                description=f"策略「{strategy.name}」的监测数据采集",
            ),
            current_user_id,
        )
        monitor = result["monitor"]
    except HTTPException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=f"创建监测项目失败: {e.detail}",
        ) from e

    # 爬虫参数：采集量由用户选择
    task_params = {
        "max_notes_count": notes_per_task,
        "enable_comments": 1,
        "per_note_max_comments_count": 20,
    }

    # 为每个关键词 x 平台组合创建独立任务
    for suggestion in monitor_suggestions:
        suggestion_name = suggestion.get("name", "").strip()
        if not suggestion_name:
            partial_errors.append("跳过一条空名称的建议")
            continue

        platforms = suggestion.get("platforms") or []
        keywords = suggestion.get("keywords") or []
        if not keywords:
            keywords = [suggestion_name]

        for keyword in keywords:
            keyword = keyword.strip()
            if not keyword:
                continue
            for platform_name in platforms:
                code = PLATFORM_NAME_TO_CODE.get(platform_name, platform_name)
                try:
                    platform = await get_platform_by_code(db, code)
                    if not platform:
                        partial_errors.append(f"平台「{platform_name}」不存在，跳过")
                        continue
                    await create_task(
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
                except Exception as e:
                    logger.error("创建任务「%s-%s」失败: %s", keyword, platform_name, e)
                    partial_errors.append(f"创建任务「{keyword}-{platform_name}」失败: {e}")

    # 保存编辑后的切片规划
    if slice_plan is not None:
        strategy.slice_plan = slice_plan
        flag_modified(strategy, "slice_plan")

    # 记录监测 ID（覆盖式，每次确认只保留最新创建的监测）
    strategy.suggested_monitor_ids = [monitor.id]
    flag_modified(strategy, "suggested_monitor_ids")
    strategy.status = "monitors_created"

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)
    return ConfirmPlanResponse(
        created_monitor_ids=[monitor.id],
        partial_errors=partial_errors,
        strategy=build_strategy_read(updated),
    )


async def batch_add_slices(
    db: AsyncSession,
    strategy: Strategy,
    slice_ids: list[int],
    user_id: int,
) -> Strategy:
    """批量关联切片（upsert）"""
    for sid in slice_ids:
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
                detail=f"无权访问切片 {sid} 所属监测",
            )

        # upsert: 检查是否已存在
        existing = await db.get(StrategySlice, {"strategy_id": strategy.id, "slice_id": sid})
        if not existing:
            db.add(StrategySlice(strategy_id=strategy.id, slice_id=sid))

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def remove_slice(
    db: AsyncSession,
    strategy: Strategy,
    slice_id: int,
) -> Strategy:
    """移除策略关联的单个切片"""
    link = await db.get(StrategySlice, {"strategy_id": strategy.id, "slice_id": slice_id})
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"切片 {slice_id} 未关联到该策略",
        )
    await db.delete(link)
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def _load_monitors_for_architect(
    db: AsyncSession,
    user_id: int,
    associated_slice_ids: set[int],
) -> list[dict]:
    """加载用户所有可用监测项目及其切片摘要，供 Architect Chain 使用"""
    monitors, _ = await get_monitors(db, participant_id=user_id, limit=200)
    if not monitors:
        return []

    monitor_ids = [m.id for m in monitors]
    slices_result = await db.execute(
        select(AnalysisSlice).where(AnalysisSlice.monitor_id.in_(monitor_ids))
    )
    all_slices = slices_result.scalars().all()

    slices_by_monitor: dict[int, list[AnalysisSlice]] = {}
    for s in all_slices:
        slices_by_monitor.setdefault(s.monitor_id, []).append(s)

    monitors_data = []
    for monitor in monitors:
        monitor_slices = slices_by_monitor.get(monitor.id, [])
        slice_summaries = []
        for s in monitor_slices:
            if not s.result_data:
                continue
            meta = extract_slice_meta(s.result_data)
            slice_summaries.append({
                "slice_id": s.id,
                "name": s.name or f"切片 #{s.id}",
                "is_associated": s.id in associated_slice_ids,
                **meta,
            })
        monitors_data.append({
            "monitor_id": monitor.id,
            "monitor_name": monitor.name,
            "slices": slice_summaries,
        })

    return monitors_data


async def evaluate_strategy(
    db: AsyncSession,
    strategy: Strategy,
    user_id: int,
) -> EvaluationResultResponse:
    """AI 评估切片充分性，并顺序执行结构优化分析

    Step 1: Evaluate Chain — 充分性评分 + 缺口识别
    Step 2: Architect Chain — 结构优化（以 Evaluate 缺口为输入，视野扩展到所有 monitors）
    LLM 解析失败时抛出 HTTPException(500)，strategy.evaluation_result 不更新。
    """
    slices_with_names = await load_slice_data_with_names(db, strategy)

    # 从最新一轮咨询结果中取需求理解摘要
    understanding_summary: str | None = None
    rounds = strategy.consultation_rounds or []
    if rounds:
        latest = rounds[-1]
        understanding_summary = (
            (latest.get("ai_response") or {}).get("understanding_summary")
        )

    # ── Step 1: Evaluate Chain ──────────────────────────────────────────────
    eval_chain = create_strategy_evaluate_chain()
    eval_inputs = format_evaluate_inputs(
        brief=strategy.brand_brief,
        slice_plan=list(strategy.slice_plan or []),
        slices_data=[data for _, data in slices_with_names],
        slice_names=[name for name, _ in slices_with_names],
        understanding_summary=understanding_summary,
    )

    start = time.time()
    eval_llm_result = await eval_chain.ainvoke(eval_inputs)
    eval_duration = time.time() - start

    try:
        eval_parsed = parse_evaluate_response(eval_llm_result.content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 评估解析失败: {e}",
        ) from e

    logger.info(
        "Strategy %d Evaluate 完成 (%.1fs, score=%.2f, sufficient=%s)",
        strategy.id, eval_duration, eval_parsed["overall_score"], eval_parsed["is_sufficient"],
    )

    # ── Step 2: Architect Chain ─────────────────────────────────────────────
    associated_slice_ids = {ss.slice_id for ss in strategy.slices}
    monitors_data = await _load_monitors_for_architect(db, user_id, associated_slice_ids)

    associated_slices_meta = [
        {
            "name": name or f"切片 #{i}",
            **extract_slice_meta(data),
        }
        for i, (name, data) in enumerate(slices_with_names)
        if data
    ]

    arch_chain = create_strategy_architect_chain()
    arch_inputs = format_architect_inputs(
        brief=strategy.brand_brief,
        gap_analysis=eval_parsed.get("gap_analysis", []),
        associated_slices=associated_slices_meta,
        monitors_data=monitors_data,
        understanding_summary=understanding_summary,
    )

    arch_start = time.time()
    arch_llm_result = await arch_chain.ainvoke(arch_inputs)
    arch_duration = time.time() - arch_start

    try:
        arch_parsed = parse_architect_response(arch_llm_result.content)
    except ValueError as e:
        logger.warning("Strategy %d Architect Chain 解析失败: %s，跳过结构分析", strategy.id, e)
        arch_parsed = None

    logger.info(
        "Strategy %d Architect 完成 (%.1fs, issues=%d, opportunities=%d)",
        strategy.id, arch_duration,
        len(arch_parsed.get("current_slice_issues", [])) if arch_parsed else 0,
        len(arch_parsed.get("unused_opportunities", [])) if arch_parsed else 0,
    )

    # ── 组合结果 ────────────────────────────────────────────────────────────
    structure_analysis = (
        StructureAnalysisResult(**arch_parsed) if arch_parsed else None
    )

    result = EvaluationResultResponse(
        overall_score=eval_parsed["overall_score"],
        is_sufficient=eval_parsed["is_sufficient"],
        coverage_analysis=eval_parsed["coverage_analysis"],
        slice_suggestions=eval_parsed["slice_suggestions"],
        gap_analysis=eval_parsed["gap_analysis"],
        supplementary_suggestions=eval_parsed.get("supplementary_suggestions"),
        supplementary_slice_plan=eval_parsed.get("supplementary_slice_plan"),
        structure_analysis=structure_analysis,
    )

    strategy.evaluation_result = result.model_dump()
    await db.commit()
    return result


async def confirm_ready(
    db: AsyncSession,
    strategy: Strategy,
) -> Strategy:
    """用户确认数据就绪，状态推进到 slices_ready"""
    if STATUS_ORDER.get(strategy.status, 0) >= STATUS_ORDER["completed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略已完成，无需重新确认就绪",
        )
    strategy.status = "slices_ready"
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


# ==================== 补充采集 ====================


async def confirm_supplementary(
    db: AsyncSession,
    strategy: Strategy,
    monitor_suggestions: list[dict],
    current_user_id: int,
    *,
    notes_per_task: int = 50,
) -> ConfirmSupplementaryResponse:
    """确认补充采集建议，在现有 Monitor 中创建新任务

    复用 confirm_plan 的 keyword×platform 任务创建逻辑，
    但不创建新 Monitor，而是挂到策略关联的现有 Monitor 上。
    """
    from src.social_media.monitors.crud import get_platform_by_code
    from src.social_media.tasks.schemas import DataTaskCreate
    from src.social_media.tasks.service import create_task

    # 获取策略关联的 Monitor
    monitor_ids = list(strategy.suggested_monitor_ids or [])
    if not monitor_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略尚未创建监测，请先完成阶段 A",
        )

    monitor = await db.get(Monitor, monitor_ids[0])
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"监测 {monitor_ids[0]} 不存在",
        )

    partial_errors: list[str] = []
    created_task_ids: list[int] = []

    task_params = {
        "max_notes_count": notes_per_task,
        "enable_comments": 1,
        "per_note_max_comments_count": 20,
    }

    for suggestion in monitor_suggestions:
        suggestion_name = suggestion.get("name", "").strip()
        if not suggestion_name:
            partial_errors.append("跳过一条空名称的建议")
            continue

        platforms = suggestion.get("platforms") or []
        keywords = suggestion.get("keywords") or []
        if not keywords:
            keywords = [suggestion_name]

        for keyword in keywords:
            keyword = keyword.strip()
            if not keyword:
                continue
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
                except Exception as e:
                    logger.error("补充任务「%s-%s」创建失败: %s", keyword, platform_name, e)
                    partial_errors.append(f"创建任务「{keyword}-{platform_name}」失败: {e}")

    # 将补充任务 ID 存入 evaluation_result
    eval_result = dict(strategy.evaluation_result or {})
    existing_ids = eval_result.get("pending_supplementary_task_ids") or []
    eval_result["pending_supplementary_task_ids"] = existing_ids + created_task_ids
    strategy.evaluation_result = eval_result
    flag_modified(strategy, "evaluation_result")

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)
    return ConfirmSupplementaryResponse(
        created_task_ids=created_task_ids,
        task_count=len(created_task_ids),
        partial_errors=partial_errors,
        strategy=build_strategy_read(updated),
    )


async def get_supplementary_status(
    db: AsyncSession,
    strategy: Strategy,
) -> SupplementaryStatusResponse:
    """查询补充采集任务的完成进度"""
    from src.social_media.tasks.models import DataTask

    eval_result = strategy.evaluation_result or {}
    task_ids = eval_result.get("pending_supplementary_task_ids") or []

    if not task_ids:
        return SupplementaryStatusResponse(
            total=0, completed=0, pending=0, all_done=True, completed_task_ids=[],
        )

    query = select(DataTask.id, DataTask.status).where(DataTask.id.in_(task_ids))
    result = await db.execute(query)
    rows = result.all()

    completed_ids = [row[0] for row in rows if row[1] == "completed"]
    total = len(task_ids)
    completed = len(completed_ids)

    return SupplementaryStatusResponse(
        total=total,
        completed=completed,
        pending=total - completed,
        all_done=completed >= total,
        completed_task_ids=completed_ids,
    )


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
        response_text = response.content if hasattr(response, "content") else str(response)
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
