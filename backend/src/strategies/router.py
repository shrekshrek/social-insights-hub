"""策略定义 API 端点"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.pagination import get_pagination_params, PaginationParams
from src.schemas import MessageResponse, PaginatedResponse

from . import service
from .dependencies import is_admin_or_super_admin, validate_strategy_owner
from .models import Strategy
from .schemas import (
    AddSlicesRequest,
    ConfirmPlanRequest,
    ConfirmPlanResponse,
    ConsultRequest,
    ConsultResponse,
    EvaluationResultResponse,
    PhaseResultEdit,
    StrategyCreate,
    StrategyListItem,
    StrategyRead,
    StrategyUpdate,
)

router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.post(
    "",
    response_model=StrategyRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建策略",
)
async def create_strategy(
    data: StrategyCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建新策略，关联指定切片"""
    strategy = await service.create_strategy(db, data, current_user.id)
    return service.build_strategy_read(strategy)


@router.get(
    "",
    response_model=PaginatedResponse[StrategyListItem],
    status_code=status.HTTP_200_OK,
    summary="策略列表",
)
async def list_strategies(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    pagination: PaginationParams = Depends(get_pagination_params),
    search: str | None = Query(None, description="搜索策略名称"),
):
    """获取策略列表，admin 看全部，普通用户看自己的"""
    is_admin = is_admin_or_super_admin(current_user)
    items, total = await service.get_strategies(
        db,
        user_id=current_user.id,
        is_admin=is_admin,
        skip=pagination.offset,
        limit=pagination.limit,
        search=search,
    )
    return PaginatedResponse[StrategyListItem].create(
        items=[service.build_strategy_list_item(s) for s in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{strategy_id}",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="策略详情",
)
async def get_strategy(
    strategy: Strategy = Depends(validate_strategy_owner),
):
    """获取策略详情"""
    return service.build_strategy_read(strategy)


@router.put(
    "/{strategy_id}",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="更新策略",
)
async def update_strategy(
    data: StrategyUpdate,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """更新策略基本信息（名称/Brief）"""
    updated = await service.update_strategy(db, strategy, data)
    return service.build_strategy_read(updated)


@router.delete(
    "/{strategy_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除策略",
)
async def delete_strategy(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """删除策略"""
    await service.delete_strategy(db, strategy)
    return MessageResponse(message="策略已删除")


# ==================== 阶段 A: 咨询流程 ====================


@router.post(
    "/{strategy_id}/consult",
    response_model=ConsultResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 多轮咨询",
)
async def consult_strategy(
    data: ConsultRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """AI 咨询：理解 Brief → 追问澄清 → 输出监测建议草案 + 切片规划"""
    return await service.consult_strategy(
        db, strategy, data.user_input, data.answers
    )


@router.post(
    "/{strategy_id}/confirm-plan",
    response_model=ConfirmPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="确认 AI 建议，一键创建监测",
)
async def confirm_plan(
    data: ConfirmPlanRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """确认 AI 监测建议，一键创建监测+任务，状态推进到 monitors_created"""
    return await service.confirm_plan(
        db, strategy, data.monitor_suggestions, current_user.id
    )


# ==================== 阶段 C: 数据评估 ====================


@router.post(
    "/{strategy_id}/slices",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="批量关联切片",
)
async def add_slices(
    data: AddSlicesRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """批量关联切片到策略（支持重复调用，自动 upsert）"""
    updated = await service.batch_add_slices(db, strategy, data.slice_ids, current_user.id)
    return service.build_strategy_read(updated)


@router.post(
    "/{strategy_id}/evaluate",
    response_model=EvaluationResultResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 评估切片充分性",
)
async def evaluate_strategy(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """AI 评估已关联切片是否满足 Brief 需求，输出充分性评分与缺口分析"""
    return await service.evaluate_strategy(db, strategy)


@router.post(
    "/{strategy_id}/confirm-ready",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="确认数据就绪",
)
async def confirm_ready(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """用户确认数据就绪，状态推进到 slices_ready，解锁 Phase 1 生成"""
    updated = await service.confirm_ready(db, strategy)
    return service.build_strategy_read(updated)


# ==================== 生成端点 ====================


@router.post(
    "/{strategy_id}/generate/phase1",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 Phase 1 洞察层",
)
async def generate_phase1(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """AI 生成 Phase 1: Social Tension + Brand Opportunity"""
    updated = await service.generate_phase1(db, strategy)
    return service.build_strategy_read(updated)


@router.post(
    "/{strategy_id}/generate/phase2",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 Phase 2 策略层",
)
async def generate_phase2(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """AI 生成 Phase 2: Brand Social Role + Social Strategy"""
    updated = await service.generate_phase2(db, strategy)
    return service.build_strategy_read(updated)


@router.post(
    "/{strategy_id}/generate/phase3",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 Phase 3 创意层",
)
async def generate_phase3(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """AI 生成 Phase 3: Big Idea + Content Strategy"""
    updated = await service.generate_phase3(db, strategy)
    return service.build_strategy_read(updated)


# ==================== 编辑端点 ====================


@router.put(
    "/{strategy_id}/phase1",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Phase 1 结果",
)
async def edit_phase1(
    data: PhaseResultEdit,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """编辑 Phase 1 结果（自动清除 Phase 2/3）"""
    updated = await service.edit_phase_result(db, strategy, phase=1, result=data.result)
    return service.build_strategy_read(updated)


@router.put(
    "/{strategy_id}/phase2",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Phase 2 结果",
)
async def edit_phase2(
    data: PhaseResultEdit,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """编辑 Phase 2 结果（自动清除 Phase 3）"""
    updated = await service.edit_phase_result(db, strategy, phase=2, result=data.result)
    return service.build_strategy_read(updated)


@router.put(
    "/{strategy_id}/phase3",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Phase 3 结果",
)
async def edit_phase3(
    data: PhaseResultEdit,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """编辑 Phase 3 结果"""
    updated = await service.edit_phase_result(db, strategy, phase=3, result=data.result)
    return service.build_strategy_read(updated)


# ==================== 导出端点 ====================


@router.get(
    "/{strategy_id}/export",
    status_code=status.HTTP_200_OK,
    summary="导出策略报告 Word",
    tags=["Strategies"],
)
async def export_strategy(
    strategy: Strategy = Depends(validate_strategy_owner),
):
    """导出策略报告为 Word 文档"""
    from .export_docx import generate_strategy_docx

    buf = generate_strategy_docx(strategy)
    filename = f"{strategy.name}_策略报告.docx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            ),
        },
    )
