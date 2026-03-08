"""策略定义 API 端点"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
    ConfirmSupplementaryRequest,
    ConfirmSupplementaryResponse,
    ConsultRequest,
    ConsultResponse,
    EvaluationResultResponse,
    ParseBriefResponse,
    PhaseResultEdit,
    StrategyCreate,
    StrategyListItem,
    StrategyRead,
    StrategyUpdate,
    SupplementaryStatusResponse,
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
    summary="AI 生成监测方案",
)
async def consult_strategy(
    data: ConsultRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """基于 Brand Brief 直接输出监测方案（每次覆盖上次结果）"""
    return await service.consult_strategy(
        db, strategy, data.user_input
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
        db, strategy, data.monitor_suggestions, current_user.id,
        slice_plan=data.slice_plan,
        notes_per_task=data.notes_per_task,
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


@router.delete(
    "/{strategy_id}/slices/{slice_id}",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="移除关联切片",
)
async def remove_slice(
    slice_id: int,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """移除策略关联的单个切片"""
    updated = await service.remove_slice(db, strategy, slice_id)
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
    current_user: User = Depends(get_current_user),
):
    """AI 评估已关联切片是否满足 Brief 需求，输出充分性评分与结构优化建议"""
    return await service.evaluate_strategy(db, strategy, current_user.id)


@router.post(
    "/{strategy_id}/confirm-supplementary",
    response_model=ConfirmSupplementaryResponse,
    status_code=status.HTTP_200_OK,
    summary="确认补充采集",
)
async def confirm_supplementary(
    data: ConfirmSupplementaryRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """确认补充采集建议，在现有监测中创建新任务"""
    return await service.confirm_supplementary(
        db, strategy, data.monitor_suggestions, current_user.id,
        notes_per_task=data.notes_per_task,
    )


@router.get(
    "/{strategy_id}/supplementary-status",
    response_model=SupplementaryStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="补充采集状态",
)
async def get_supplementary_status(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """查询补充采集任务完成进度"""
    return await service.get_supplementary_status(db, strategy)


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


# ==================== Brief 文档解析 ====================

_ALLOWED_BRIEF_EXTENSIONS = {"pdf", "docx", "txt", "md"}
_MAX_BRIEF_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/parse-brief",
    response_model=ParseBriefResponse,
    status_code=status.HTTP_200_OK,
    tags=["Strategies"],
    summary="上传 Brief 文档，AI 自动解析填充表单字段",
)
async def parse_brief(
    file: UploadFile = File(..., description="支持 PDF / DOCX / TXT / MD，最大 10 MB"),
    current_user: User = Depends(get_current_user),
):
    """上传 Brief 文档，AI 提取 brand_name / analysis_goal / constraints 等字段"""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_BRIEF_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支持的文件类型 .{ext}，请上传 PDF、DOCX、TXT 或 MD 文件",
        )

    content = await file.read()
    if len(content) > _MAX_BRIEF_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件大小超过 10 MB 限制",
        )

    return await service.parse_brief_from_file(content, filename)
