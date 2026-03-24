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
    AdjustSlicesRequest,
    ApproveProbeResponse,
    CollectionStatusResponse,
    ConfirmResearchRequest,
    ConfirmResearchResponse,
    DataOverviewResponse,
    DesignResearchRequest,
    DesignResearchResponse,
    ParseBriefResponse,
    PhaseResultEdit,
    ProbeStatusResponse,
    RefineProbeRequest,
    RefineProbeResponse,
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


# ==================== ① 研究设计 ====================


@router.post(
    "/{strategy_id}/design-research",
    response_model=DesignResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 生成研究计划",
)
async def design_research(
    data: DesignResearchRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """基于 Brief 生成研究计划（研究问题+数据方案+切片蓝图+产出类型）"""
    return await service.design_research(db, strategy, data.user_input)


@router.post(
    "/{strategy_id}/confirm-research",
    response_model=ConfirmResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="确认研究计划，创建 Monitor + 探测任务",
)
async def confirm_research(
    data: ConfirmResearchRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """确认研究计划，一键创建 Monitor 和探测任务，状态推进到 probing"""
    return await service.confirm_research(
        db, strategy, data.research_design, current_user.id,
        notes_per_task=data.notes_per_task,
        probe_notes=data.probe_notes,
    )


# ==================== ② 探测验证 ====================


@router.get(
    "/{strategy_id}/probe-status",
    response_model=ProbeStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="探测进度 + 自动审查",
    tags=["Strategies"],
)
async def get_probe_status(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """查询探测任务进度，全部分析完成后自动运行审查"""
    return await service.check_probe_status(db, strategy)


@router.post(
    "/{strategy_id}/approve-probe",
    response_model=ApproveProbeResponse,
    status_code=status.HTTP_200_OK,
    summary="手动确认探测通过",
    tags=["Strategies"],
)
async def approve_probe(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """手动确认探测通过，所有 probe_ready 任务标记为 approved，状态 → collecting"""
    return await service.approve_probe(db, strategy)


@router.post(
    "/{strategy_id}/refine-probe",
    response_model=RefineProbeResponse,
    status_code=status.HTTP_200_OK,
    summary="调整关键词，创建新探测任务",
    tags=["Strategies"],
)
async def refine_probe(
    data: RefineProbeRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """调整不合格的关键词，创建新探测任务，probe_round++"""
    return await service.refine_probe(
        db, strategy,
        [item.model_dump() for item in data.refinements],
        current_user.id,
    )


# ==================== ③ 数据就绪 ====================


@router.get(
    "/{strategy_id}/collection-status",
    response_model=CollectionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="全量采集进度 + 自动建切片",
    tags=["Strategies"],
)
async def get_collection_status(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """查询全量采集进度，全部完成后自动建切片并验证覆盖度"""
    return await service.check_collection_status(db, strategy, current_user.id)


@router.get(
    "/{strategy_id}/data-overview",
    response_model=DataOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="数据全景",
    tags=["Strategies"],
)
async def get_data_overview(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
):
    """数据全景：切片列表 + 覆盖度结果"""
    return await service.get_data_overview(db, strategy)


@router.post(
    "/{strategy_id}/adjust-slices",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="微调切片配置",
    tags=["Strategies"],
)
async def adjust_slices(
    data: AdjustSlicesRequest,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """微调切片配置（名称/主体/竞品），自动重新验证覆盖度"""
    return await service.adjust_slices(
        db, strategy,
        [item.model_dump() for item in data.adjustments],
        current_user.id,
    )


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
