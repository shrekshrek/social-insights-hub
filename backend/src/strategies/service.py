"""策略定义业务逻辑"""

import logging
import time

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.langchain.chains.strategy_consult_chain import (
    create_strategy_consult_chain,
    format_consult_inputs,
    parse_consult_response,
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
from src.social_media.analysis.models import AnalysisSlice
from src.social_media.monitors.crud import check_monitor_access

from .models import Strategy, StrategySlice
from .schemas import (
    ConfirmPlanResponse,
    ConsultResponse,
    EvaluationResultResponse,
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
    answers: dict[str, str] | None,
) -> ConsultResponse:
    """AI 多轮咨询：理解需求 → 追问 → 输出监测建议草案

    LLM 解析失败时抛出 HTTPException(500)，strategy 不更新。
    """
    round_number = len(strategy.consultation_rounds or []) + 1

    chain = create_strategy_consult_chain()
    inputs = format_consult_inputs(
        user_input=user_input,
        brief=strategy.brand_brief,
        consultation_rounds=list(strategy.consultation_rounds or []),
        answers=answers,
    )

    start = time.time()
    llm_result = await chain.ainvoke(inputs)
    duration = time.time() - start

    try:
        parsed = parse_consult_response(llm_result.content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 咨询解析失败: {e}",
        ) from e

    response = ConsultResponse(
        round_number=round_number,
        understanding_summary=parsed["understanding_summary"],
        clarification_questions=parsed["clarification_questions"],
        monitor_suggestions=parsed["monitor_suggestions"],
        slice_plan=parsed["slice_plan"],
        confidence=parsed["confidence"],
    )
    logger.info(
        "Strategy %d Consult 第 %d 轮完成 (%.1fs, confidence=%.2f)",
        strategy.id, round_number, duration, parsed["confidence"],
    )

    rounds = list(strategy.consultation_rounds or [])
    rounds.append({
        "round_number": round_number,
        "user_input": user_input,
        "answers": answers,
        "ai_response": response.model_dump(),
    })
    strategy.consultation_rounds = rounds
    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["consulting"]:
        strategy.status = "consulting"

    await db.commit()
    return response


async def confirm_plan(
    db: AsyncSession,
    strategy: Strategy,
    monitor_suggestions: list[dict],
    current_user_id: int,
) -> ConfirmPlanResponse:
    """确认 AI 建议，一键创建监测

    逐条创建监测，部分失败不中断整体流程。
    重复调用时 suggested_monitor_ids 追加而不覆盖。
    """
    from src.social_media.monitors.schemas import MonitorCreate
    from src.social_media.monitors.service import create_monitor

    created_ids: list[int] = []
    partial_errors: list[str] = []

    for suggestion in monitor_suggestions:
        name = suggestion.get("name", "").strip()
        if not name:
            partial_errors.append("跳过一条空名称的监测建议")
            continue
        try:
            result = await create_monitor(
                db,
                MonitorCreate(
                    name=name,
                    description=suggestion.get("rationale") or "",
                ),
                current_user_id,
            )
            monitor = result["monitor"]
            created_ids.append(monitor.id)
        except HTTPException as e:
            partial_errors.append(f"创建监测「{name}」失败: {e.detail}")
        except Exception as e:
            logger.error("confirm_plan 创建监测「%s」意外错误: %s", name, e)
            partial_errors.append(f"创建监测「{name}」意外错误: {e}")

    # 追加到 suggested_monitor_ids（不覆盖历史记录）
    existing_ids = list(strategy.suggested_monitor_ids or [])
    strategy.suggested_monitor_ids = existing_ids + created_ids
    strategy.status = "monitors_created"

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)
    return ConfirmPlanResponse(
        created_monitor_ids=created_ids,
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


async def evaluate_strategy(
    db: AsyncSession,
    strategy: Strategy,
) -> EvaluationResultResponse:
    """AI 评估切片充分性

    LLM 解析失败时抛出 HTTPException(500)，strategy.evaluation_result 不更新。
    """
    slices_data = await load_slice_data(db, strategy)

    chain = create_strategy_evaluate_chain()
    inputs = format_evaluate_inputs(
        brief=strategy.brand_brief,
        slice_plan=list(strategy.slice_plan or []),
        slices_data=slices_data,
    )

    start = time.time()
    llm_result = await chain.ainvoke(inputs)
    duration = time.time() - start

    try:
        parsed = parse_evaluate_response(llm_result.content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 评估解析失败: {e}",
        ) from e

    result = EvaluationResultResponse(
        overall_score=parsed["overall_score"],
        is_sufficient=parsed["is_sufficient"],
        coverage_analysis=parsed["coverage_analysis"],
        slice_suggestions=parsed["slice_suggestions"],
        gap_analysis=parsed["gap_analysis"],
        supplementary_tasks=parsed.get("supplementary_tasks"),
    )
    logger.info(
        "Strategy %d Evaluate 完成 (%.1fs, score=%.2f, sufficient=%s)",
        strategy.id, duration, parsed["overall_score"], parsed["is_sufficient"],
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
