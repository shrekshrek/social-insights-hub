"""Research Agent API 端点"""

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.rbac.dependencies import (
    require_research_agent_read,
    require_research_agent_write,
    require_research_agent_delete,
)
from src.rbac.utils import is_admin_or_super_admin
from src.research_agent import schemas, service
from src.research_agent.profiles import list_profiles
from src.schemas import PaginatedResponse

router = APIRouter(prefix="/research", tags=["Research Agent"])


@router.get(
    "/profiles",
    response_model=list[schemas.ProfileOption],
    status_code=status.HTTP_200_OK,
    summary="研究类型列表",
)
async def list_research_profiles(
    _: User = Depends(require_research_agent_read),
):
    """返回可选的研究类型（industry / creative / ...），供前端选择器使用"""
    return [{"name": p.name, "display_name": p.display_name} for p in list_profiles()]


@router.post(
    "/parse-brief",
    response_model=schemas.ParseBriefResponse,
    status_code=status.HTTP_200_OK,
    summary="解析 Brief 文件（合流点：摄入 + 诊断 + 方案）",
)
async def parse_brief_file(
    file: UploadFile = File(...),
    profile_name: str = "industry",
    _: User = Depends(require_research_agent_write),
):
    """上传 PDF/DOCX/TXT/MD 文件，一次返回标题/分析目标/研究问题/适配度诊断/搜索方案。"""
    _ALLOWED = {"pdf", "docx", "txt", "md"}
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="仅支持 PDF / DOCX / TXT / MD 文件",
        )
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文件大小不能超过 10 MB",
        )
    return await service.parse_brief_from_file(
        content, file.filename or "", profile_name
    )


@router.post(
    "/parse-brief-text",
    response_model=schemas.ParseBriefResponse,
    status_code=status.HTTP_200_OK,
    summary="解析 Brief 文本（合流点：摄入 + 诊断 + 方案）",
)
async def parse_brief_text(
    body: schemas.ParseBriefTextRequest,
    _: User = Depends(require_research_agent_write),
):
    """粘贴的 brief 文本，一次返回标题/分析目标/研究问题/适配度诊断/搜索方案。"""
    return await service.parse_brief_from_text(body.text, body.profile_name)


@router.post(
    "/tasks",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建研究任务",
)
async def create_task(
    body: schemas.ResearchTaskCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_write),
):
    """创建独立研究任务，后台 Celery 自动执行 LangGraph 研究图"""
    search_config = {**(body.search_config or {})}
    if body.brief:
        search_config["context"] = body.brief
    task = await service.create_research_task(
        db=db,
        user_id=current_user.id,
        analysis_goal=body.analysis_goal,
        title=body.title,
        research_questions=body.research_questions,
        search_config=search_config,
        profile_name=body.profile_name,
    )
    # 重新加载以填充 participants / user 关系（新建时为空但展示字段需要存在）
    refreshed = await service.get_research_task(db, task.id)
    return schemas.ResearchTaskRead.from_orm_full(refreshed or task)


@router.get(
    "/tasks",
    response_model=PaginatedResponse[schemas.ResearchTaskRead],
    status_code=status.HTTP_200_OK,
    summary="研究任务列表",
)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    profile_name: str | None = Query(
        None, description="按研究类型过滤：industry / creative"
    ),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_read),
):
    """列出研究任务

    - 管理员/超级管理员：返回所有任务
    - 普通用户：返回自己创建或参与的任务（owner OR participant）
    """
    accessible_to_user_id = (
        None if is_admin_or_super_admin(current_user) else current_user.id
    )
    items, total = await service.list_research_tasks(
        db=db,
        accessible_to_user_id=accessible_to_user_id,
        status=status_filter,
        profile_name=profile_name,
        search=search,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(
        items=[schemas.ResearchTaskRead.from_orm_full(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_200_OK,
    summary="研究任务详情",
)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_read),
):
    """获取研究任务详情（owner / participant / admin 可见）"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    await service.assert_research_task_access(db, task_id, current_user.id)
    return schemas.ResearchTaskRead.from_orm_full(task)


@router.get(
    "/tasks/{task_id}/result",
    response_model=schemas.ResearchTaskResult,
    status_code=status.HTTP_200_OK,
    summary="研究结果",
)
async def get_task_result(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_read),
):
    """获取研究结果（synthesis + findings + sources）"""
    await service.assert_research_task_access(db, task_id, current_user.id)
    result = await service.get_research_result(db, task_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究结果不可用（任务未完成或不存在）",
        )
    return result


@router.get(
    "/tasks/{task_id}/export",
    status_code=status.HTTP_200_OK,
    summary="导出研究结果（Markdown，供 agent / 知识库按需消费）",
)
async def export_research_task(
    task_id: int,
    format: str = Query("md", description="导出格式，目前仅支持 md"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_read),
):
    """按需把研究结果渲染为 Markdown（纯投影 result_data，不落库）。

    agent 按 task_id 调本接口即可拿到带 front-matter 的完整结构化 MD。
    """
    from urllib.parse import quote

    from src.research_agent.export_md import PROFILE_LABELS, render_research_md

    if format != "md":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目前仅支持 format=md",
        )
    await service.assert_research_task_access(db, task_id, current_user.id)
    task = await service.get_research_task(db, task_id)
    if not task or task.status != "completed" or not task.result_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究结果不可用（任务未完成或不存在）",
        )

    md = render_research_md(task)
    prefix = PROFILE_LABELS.get(task.profile_name or "", "专题研究")
    filename = f"{prefix}_{task.title or task_id}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post(
    "/tasks/{task_id}/rerun",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_200_OK,
    summary="重新研究",
)
async def rerun_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_write),
):
    """原地重置研究任务并重新执行，覆盖原有结果"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    await service.assert_research_task_access(db, task_id, current_user.id)
    if task.status in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="任务正在执行中，无法重新研究",
        )
    refreshed = await service.rerun_research_task(db, task)
    return schemas.ResearchTaskRead.from_orm_full(refreshed)


@router.patch(
    "/tasks/{task_id}",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_200_OK,
    summary="编辑研究任务（仅 title）",
)
async def update_task(
    task_id: int,
    body: schemas.ResearchTaskUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_write),
):
    """编辑研究任务可变字段（当前仅 title）。仅 owner / admin。"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    if not is_admin_or_super_admin(current_user) and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有研究任务的创建者或管理员可以编辑",
        )
    updated = await service.update_research_task(db, task, title=body.title)
    return schemas.ResearchTaskRead.from_orm_full(updated)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除研究任务",
)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_delete),
):
    """删除研究任务（仅 owner / admin 可删；participant 不可删）"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    if not is_admin_or_super_admin(current_user) and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有研究任务的创建者或管理员可以删除",
        )
    deleted = await service.delete_research_task(db, task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )


# ==================== Participant Management ====================


@router.post(
    "/tasks/{task_id}/participants",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_200_OK,
    summary="添加研究任务参与者",
)
async def add_participants(
    task_id: int,
    body: schemas.ResearchTaskParticipantAssignment,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_write),
):
    """添加研究任务参与者（仅 owner / admin）"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    if not is_admin_or_super_admin(current_user) and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有研究任务的创建者或管理员可以管理参与者",
        )
    updated = await service.add_participants_to_task(db, task, body.user_ids)
    return schemas.ResearchTaskRead.from_orm_full(updated)


@router.delete(
    "/tasks/{task_id}/participants/{user_id}",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_200_OK,
    summary="移除研究任务参与者",
)
async def remove_participant(
    task_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_research_agent_write),
):
    """移除研究任务参与者（仅 owner / admin；不能移除创建者）"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    if not is_admin_or_super_admin(current_user) and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有研究任务的创建者或管理员可以管理参与者",
        )
    updated = await service.remove_participant_from_task(db, task, user_id)
    return schemas.ResearchTaskRead.from_orm_full(updated)
