"""策略定义 API 端点"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import Field
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.pagination import get_pagination_params, PaginationParams
from src.rbac.dependencies import (
    require_strategy_read,
    require_strategy_write,
    require_strategy_delete,
)
from src.schemas import CustomBaseModel, MessageResponse, PaginatedResponse

from . import service
from .dependencies import is_admin_or_super_admin, validate_strategy_access, validate_strategy_owner
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
    StageResultEdit,
    ProbeStatusResponse,
    RefineProbeRequest,
    RefineProbeResponse,
    StrategyCreate,
    StrategyListItem,
    StrategyParticipantAssignment,
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
    current_user: User = Depends(require_strategy_write),
):
    """创建新策略，关联指定切片"""
    strategy = await service.create_strategy(db, data, current_user.id)
    return StrategyRead.from_orm_full(strategy)


@router.get(
    "",
    response_model=PaginatedResponse[StrategyListItem],
    status_code=status.HTTP_200_OK,
    summary="策略列表",
)
async def list_strategies(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_strategy_read),
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
        items=[StrategyListItem.from_orm_full(s) for s in items],
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
    strategy: Strategy = Depends(validate_strategy_access),
    _: User = Depends(require_strategy_read),
):
    """获取策略详情"""
    return StrategyRead.from_orm_full(strategy)


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
    _: User = Depends(require_strategy_write),
):
    """更新策略基本信息（名称/Brief）"""
    updated = await service.update_strategy(db, strategy, data)
    return StrategyRead.from_orm_full(updated)


@router.delete(
    "/{strategy_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除策略",
)
async def delete_strategy(
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_delete),
):
    """删除策略"""
    await service.delete_strategy(db, strategy)
    return MessageResponse(message="策略已删除")


@router.post(
    "/{strategy_id}/participants",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="为策略添加参与者（同步到关联监测）",
)
async def add_participants(
    data: StrategyParticipantAssignment,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    updated = await service.add_participants_to_strategy(db, strategy, data.user_ids)
    return StrategyRead.from_orm_full(updated)


@router.delete(
    "/{strategy_id}/participants/{user_id}",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="从策略移除参与者（同步到关联监测）",
)
async def remove_participant(
    user_id: int,
    strategy: Strategy = Depends(validate_strategy_owner),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    updated = await service.remove_participant_from_strategy(db, strategy, user_id)
    return StrategyRead.from_orm_full(updated)


# ==================== ① 研究设计 ====================


@router.post(
    "/{strategy_id}/design-research",
    response_model=DesignResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 生成研究计划",
)
async def design_research(
    data: DesignResearchRequest,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """基于 Brief 生成研究计划（研究问题+数据方案+切片蓝图+产出类型）"""
    return await service.design_research(db, strategy, data.user_input)


@router.post(
    "/{strategy_id}/reset-to-design",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="重置到研究设计阶段",
)
async def reset_to_design(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """从探测/采集阶段回退到研究设计，软删除已创建的任务"""
    return await service.reset_to_design(db, strategy)


@router.post(
    "/{strategy_id}/confirm-research",
    response_model=ConfirmResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="确认研究计划，创建 SocialMonitor + 探测任务",
)
async def confirm_research(
    data: ConfirmResearchRequest,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_strategy_write),
):
    """确认研究计划，一键创建 SocialMonitor 和探测任务，状态推进到 probing"""
    return await service.confirm_research(
        db, strategy, data.research_design, current_user.id,
        output_type=data.output_type,
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
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_read),
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
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_strategy_write),
):
    """手动确认探测通过，为每个探测任务创建独立全量采集任务，状态 → collecting"""
    return await service.approve_probe(db, strategy, current_user_id=current_user.id)


@router.post(
    "/{strategy_id}/refine-probe",
    response_model=RefineProbeResponse,
    status_code=status.HTTP_200_OK,
    summary="调整关键词，创建新探测任务",
    tags=["Strategies"],
)
async def refine_probe(
    data: RefineProbeRequest,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_strategy_write),
):
    """调整不合格的关键词，创建新探测任务，probe_round++"""
    return await service.refine_probe(
        db, strategy,
        data,
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
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_strategy_read),
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
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_read),
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
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_strategy_write),
):
    """微调切片配置（名称/主体/竞品），自动重新验证覆盖度"""
    updated = await service.adjust_slices(
        db, strategy,
        [item.model_dump() for item in data.adjustments],
        current_user.id,
    )
    return StrategyRead.from_orm_full(updated)


# ==================== 生成端点 ====================

# ---- brand_strategy 路径产出生成（insight → brand_role → big_idea，三层递进） ----


@router.post(
    "/{strategy_id}/generate/insight",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 brand_strategy 第 1 层: Insight (洞察)",
)
async def generate_insight(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """AI 生成 Insight: Social Tension + Brand Opportunity"""
    updated = await service.generate_insight(db, strategy)
    return StrategyRead.from_orm_full(updated)


@router.post(
    "/{strategy_id}/generate/brand-role",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 brand_strategy 第 2 层: Brand Role (品牌角色)",
)
async def generate_brand_role(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """AI 生成 Brand Role: Brand Social Role + Social Strategy"""
    updated = await service.generate_brand_role(db, strategy)
    return StrategyRead.from_orm_full(updated)


@router.post(
    "/{strategy_id}/generate/big-idea",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 brand_strategy 第 3 层: Big Idea (创意)",
)
async def generate_big_idea(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """AI 生成 Big Idea: Big Idea + Content Strategy"""
    updated = await service.generate_big_idea(db, strategy)
    return StrategyRead.from_orm_full(updated)


# ---- market_report 路径产出生成（agenda_map → landscape → strategic_brief，三层递进） ----


@router.post(
    "/{strategy_id}/generate/agenda-map",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 market_report 第 1 层: Agenda Map (媒体议程图)",
)
async def generate_agenda_map(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """AI 生成 Agenda Map: 媒体议程图"""
    updated = await service.generate_agenda_map(db, strategy)
    return StrategyRead.from_orm_full(updated)


@router.post(
    "/{strategy_id}/generate/landscape",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 market_report 第 2 层: Landscape (竞争格局)",
)
async def generate_landscape(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """AI 生成 Landscape: 竞争格局"""
    updated = await service.generate_landscape(db, strategy)
    return StrategyRead.from_orm_full(updated)


@router.post(
    "/{strategy_id}/generate/strategic-brief",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="生成 market_report 第 3 层: Strategic Brief (战略简报)",
)
async def generate_strategic_brief(
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """AI 生成 Strategic Brief: 战略简报"""
    updated = await service.generate_strategic_brief(db, strategy)
    return StrategyRead.from_orm_full(updated)


# ==================== 编辑端点 ====================

# ---- brand_strategy 路径编辑端点 ----


@router.put(
    "/{strategy_id}/insight",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Insight 结果",
)
async def edit_insight(
    data: StageResultEdit,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """编辑 Insight 结果（自动清除 brand_role/big_idea）"""
    updated = await service.edit_brand_strategy_result(
        db, strategy, stage="insight", result=data.result
    )
    return StrategyRead.from_orm_full(updated)


@router.put(
    "/{strategy_id}/brand-role",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Brand Role 结果",
)
async def edit_brand_role(
    data: StageResultEdit,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """编辑 Brand Role 结果（自动清除 big_idea）"""
    updated = await service.edit_brand_strategy_result(
        db, strategy, stage="brand_role", result=data.result
    )
    return StrategyRead.from_orm_full(updated)


@router.put(
    "/{strategy_id}/big-idea",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Big Idea 结果",
)
async def edit_big_idea(
    data: StageResultEdit,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """编辑 Big Idea 结果"""
    updated = await service.edit_brand_strategy_result(
        db, strategy, stage="big_idea", result=data.result
    )
    return StrategyRead.from_orm_full(updated)


# ---- market_report 路径编辑端点 ----


@router.put(
    "/{strategy_id}/agenda-map",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Agenda Map 结果",
)
async def edit_agenda_map(
    data: StageResultEdit,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """编辑 Agenda Map 结果（自动清除 landscape/strategic_brief）"""
    updated = await service.edit_market_report_result(
        db, strategy, stage="agenda_map", result=data.result
    )
    return StrategyRead.from_orm_full(updated)


@router.put(
    "/{strategy_id}/landscape",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Landscape 结果",
)
async def edit_landscape(
    data: StageResultEdit,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """编辑 Landscape 结果（自动清除 strategic_brief）"""
    updated = await service.edit_market_report_result(
        db, strategy, stage="landscape", result=data.result
    )
    return StrategyRead.from_orm_full(updated)


@router.put(
    "/{strategy_id}/strategic-brief",
    response_model=StrategyRead,
    status_code=status.HTTP_200_OK,
    summary="编辑 Strategic Brief 结果",
)
async def edit_strategic_brief(
    data: StageResultEdit,
    strategy: Strategy = Depends(validate_strategy_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_strategy_write),
):
    """编辑 Strategic Brief 结果"""
    updated = await service.edit_market_report_result(
        db, strategy, stage="strategic_brief", result=data.result
    )
    return StrategyRead.from_orm_full(updated)


# ==================== 导出端点 ====================


@router.get(
    "/{strategy_id}/export",
    status_code=status.HTTP_200_OK,
    summary="导出策略报告 Word",
    tags=["Strategies"],
)
async def export_strategy(
    strategy: Strategy = Depends(validate_strategy_access),
    _: User = Depends(require_strategy_read),
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
    _: User = Depends(require_strategy_write),
):
    """上传 Brief 文档，AI 提取 subject / analysis_goal / constraints 等字段"""
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


class ParseBriefTextRequest(CustomBaseModel):
    text: str = Field(..., min_length=10, description="Brief 原文（自然语言）")


@router.post(
    "/parse-brief-text",
    response_model=ParseBriefResponse,
    status_code=status.HTTP_200_OK,
    tags=["Strategies"],
    summary="输入 Brief 文本，AI 自动解析填充表单字段",
)
async def parse_brief_text(
    body: ParseBriefTextRequest,
    _: User = Depends(require_strategy_write),
):
    """接受纯文本 Brief，AI 提取结构化字段（无需上传文件）"""
    return await service.parse_brief_from_text(body.text)
