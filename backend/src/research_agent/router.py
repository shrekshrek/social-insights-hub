"""Research Agent API 端点"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.research_agent import schemas, service
from src.schemas import PaginatedResponse

router = APIRouter(prefix="/research", tags=["Research Agent"])


@router.post(
    "/tasks/extract-brief",
    response_model=schemas.BriefExtractResult,
    status_code=status.HTTP_200_OK,
    summary="从文件提取 Brief 文本",
)
async def extract_brief(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    """上传 PDF/DOCX/TXT/MD 文件，返回提取的纯文本，供前端填入研究主题输入框。"""
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
    text = await service.extract_brief_from_file(content, file.filename or "")
    return {"text": text}


@router.post(
    "/tasks/preview",
    response_model=schemas.ResearchPlanPreviewResult,
    status_code=status.HTTP_200_OK,
    summary="预览研究计划",
)
async def preview_task(
    body: schemas.ResearchPlanPreviewRequest,
    _: User = Depends(get_current_user),
):
    """调用 planner LLM 生成研究计划预览，不创建任务。
    用于创建页的两步流程：用户确认 title + research_questions 后再正式提交。
    """
    plan = await service.preview_research_plan(
        analysis_goal=body.analysis_goal,
        brief=body.brief,
        research_questions=body.research_questions,
    )
    return plan


@router.post(
    "/tasks",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建研究任务",
)
async def create_task(
    body: schemas.ResearchTaskCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
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
    )
    return task


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
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户的研究任务"""
    items, total = await service.list_research_tasks(
        db=db,
        user_id=current_user.id,
        status=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(
        items=items, total=total, page=page, page_size=page_size
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
    current_user: User = Depends(get_current_user),
):
    """获取研究任务详情"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    return task


@router.get(
    "/tasks/{task_id}/result",
    response_model=schemas.ResearchTaskResult,
    status_code=status.HTTP_200_OK,
    summary="研究结果",
)
async def get_task_result(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取研究结果（synthesis + findings + sources）"""
    result = await service.get_research_result(db, task_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究结果不可用（任务未完成或不存在）",
        )
    return result


@router.post(
    "/tasks/{task_id}/rerun",
    response_model=schemas.ResearchTaskRead,
    status_code=status.HTTP_200_OK,
    summary="重新研究",
)
async def rerun_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """原地重置研究任务并重新执行，覆盖原有结果"""
    task = await service.get_research_task(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
    if task.status in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="任务正在执行中，无法重新研究",
        )
    return await service.rerun_research_task(db, task)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除研究任务",
)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除研究任务"""
    deleted = await service.delete_research_task(db, task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="研究任务不存在",
        )
