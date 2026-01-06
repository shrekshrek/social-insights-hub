"""社交媒体数据任务CRUD操作"""

from typing import List, Optional
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import DataTask, SocialPost, SocialComment


# ==================== DataTask CRUD ====================


async def get_task_by_id(
    db: AsyncSession, task_id: int, load_relations: bool = False
) -> Optional[DataTask]:
    """根据ID获取任务"""
    query = select(DataTask).where(
        DataTask.id == task_id, DataTask.is_deleted.is_(False)
    )

    if load_relations:
        query = query.options(
            selectinload(DataTask.project),
            selectinload(DataTask.platform),
            selectinload(DataTask.creator),
        )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_tasks(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    project_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    data_source: Optional[str] = None,
    creator_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[List[DataTask], int]:
    """获取任务列表（带过滤和分页）"""
    # 构建查询条件
    conditions = [DataTask.is_deleted.is_(False)]

    if project_id is not None:
        conditions.append(DataTask.project_id == project_id)

    if platform_id is not None:
        conditions.append(DataTask.platform_id == platform_id)

    if task_type:
        conditions.append(DataTask.task_type == task_type)

    if status:
        conditions.append(DataTask.status == status)

    if data_source:
        conditions.append(DataTask.data_source == data_source)

    if creator_id is not None:
        conditions.append(DataTask.creator_id == creator_id)

    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                DataTask.name.ilike(search_pattern),
                DataTask.description.ilike(search_pattern),
                DataTask.keywords.ilike(search_pattern),
            )
        )

    # 统计总数
    count_query = select(func.count()).select_from(DataTask).where(and_(*conditions))
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # 查询数据
    query = (
        select(DataTask)
        .where(and_(*conditions))
        .options(
            selectinload(DataTask.project),
            selectinload(DataTask.platform),
            selectinload(DataTask.creator),
        )
        .offset(skip)
        .limit(limit)
        .order_by(DataTask.created_at.desc())
    )

    result = await db.execute(query)
    tasks = result.scalars().all()

    return list(tasks), total


async def create_task(db: AsyncSession, task_data: dict, creator_id: int) -> DataTask:
    """创建任务"""
    task = DataTask(**task_data, creator_id=creator_id)
    db.add(task)
    await db.flush()  # 获取任务ID
    await db.refresh(task, ["project", "platform", "creator"])
    return task


async def update_task(db: AsyncSession, task: DataTask, update_data: dict) -> DataTask:
    """更新任务"""
    for key, value in update_data.items():
        if value is not None:
            setattr(task, key, value)

    await db.flush()
    await db.refresh(task)
    return task


async def update_task_status(
    db: AsyncSession, task: DataTask, status: str, error_message: Optional[str] = None
) -> DataTask:
    """更新任务状态"""
    task.status = status
    if error_message:
        task.error_message = error_message

    if status == "completed":
        from datetime import datetime, timezone

        task.completed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(task)
    return task


async def update_task_counts(
    db: AsyncSession,
    task: DataTask,
    posts_count: Optional[int] = None,
    comments_count: Optional[int] = None,
) -> DataTask:
    """更新任务统计数据"""
    if posts_count is not None:
        task.posts_count = posts_count
    if comments_count is not None:
        task.comments_count = comments_count

    await db.flush()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task: DataTask) -> None:
    """软删除任务"""
    task.is_deleted = True
    await db.flush()


async def delete_task_posts_and_comments(db: AsyncSession, task_id: int) -> dict:
    """删除任务的所有帖子和评论（硬删除，用于重新上传数据）

    Args:
        db: 数据库会话
        task_id: 任务ID

    Returns:
        删除统计：{"posts_deleted": int, "comments_deleted": int}
    """
    from sqlalchemy import delete

    # 先删除评论
    comments_result = await db.execute(
        delete(SocialComment).where(SocialComment.task_id == task_id)
    )
    comments_deleted = comments_result.rowcount

    # 再删除帖子
    posts_result = await db.execute(
        delete(SocialPost).where(SocialPost.task_id == task_id)
    )
    posts_deleted = posts_result.rowcount

    # 同时删除帖子分析结果
    from src.social_media.analysis.models import PostAnalysis

    await db.execute(delete(PostAnalysis).where(PostAnalysis.task_id == task_id))

    await db.flush()

    return {"posts_deleted": posts_deleted, "comments_deleted": comments_deleted}


# ==================== SocialPost CRUD ====================


async def get_post_by_id(
    db: AsyncSession, post_id: int, load_comments: bool = False
) -> Optional[SocialPost]:
    """根据ID获取原文"""
    query = select(SocialPost).where(
        SocialPost.id == post_id, SocialPost.is_deleted.is_(False)
    )

    if load_comments:
        query = query.options(selectinload(SocialPost.comments))

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_posts_by_task(
    db: AsyncSession,
    task_id: int,
    skip: int = 0,
    limit: int = 20,
    post_id: int | None = None,
) -> tuple[List[dict], int]:
    """获取任务的原文列表（包含已爬取评论数）

    Args:
        db: 数据库会话
        task_id: 任务ID
        skip: 跳过数量
        limit: 返回数量限制
        post_id: 可选，按原文ID精确筛选

    Returns:
        tuple: (帖子数据列表（包含 crawled_comments_count）, 总数)
    """
    # 基础筛选条件
    base_conditions = [SocialPost.task_id == task_id, SocialPost.is_deleted.is_(False)]

    # 如果指定了 post_id，添加精确筛选
    if post_id is not None:
        base_conditions.append(SocialPost.id == post_id)

    # 统计总数
    count_query = (
        select(func.count())
        .select_from(SocialPost)
        .where(*base_conditions)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # 子查询：每个帖子的已爬取评论数
    crawled_count_subquery = (
        select(func.count(SocialComment.id))
        .where(
            SocialComment.post_id == SocialPost.id, SocialComment.is_deleted.is_(False)
        )
        .correlate(SocialPost)
        .scalar_subquery()
    )

    # 查询数据（包含已爬取评论数）
    query = (
        select(SocialPost, crawled_count_subquery.label("crawled_comments_count"))
        .where(*base_conditions)
        .offset(skip)
        .limit(limit)
        .order_by(SocialPost.published_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    # 转换为字典列表，包含 crawled_comments_count
    posts_data = []
    for post, crawled_count in rows:
        post_dict = {
            "id": post.id,
            "task_id": post.task_id,
            "platform_id": post.platform_id,
            "post_id_on_platform": post.post_id_on_platform,
            "post_type": post.post_type,
            "title": post.title,
            "content": post.content,
            "author_id": post.author_id,
            "author_name": post.author_name,
            "likes_count": post.likes_count,
            "comments_count": post.comments_count,
            "shares_count": post.shares_count,
            "collected_count": post.collected_count,
            "views_count": post.views_count,
            "images": post.images,
            "videos": post.videos,
            "published_at": post.published_at,
            "url": post.url,
            "raw_data": post.raw_data,
            "collected_at": post.collected_at,
            "is_deleted": post.is_deleted,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
            "crawled_comments_count": crawled_count or 0,
        }
        posts_data.append(post_dict)

    return posts_data, total


async def get_posts_by_platform_post_id(
    db: AsyncSession,
    platform_id: int,
    post_id_on_platform: str,
    project_id: Optional[int] = None,
) -> List[SocialPost]:
    """跨任务查询同一帖子（按发布时间倒序）"""
    conditions = [
        SocialPost.platform_id == platform_id,
        SocialPost.post_id_on_platform == post_id_on_platform,
        SocialPost.is_deleted.is_(False),
    ]

    # 如果指定项目，只查询该项目下的任务
    if project_id is not None:
        conditions.append(DataTask.project_id == project_id)

        query = (
            select(SocialPost)
            .join(DataTask, SocialPost.task_id == DataTask.id)
            .where(and_(*conditions))
            .order_by(SocialPost.published_at.desc())
        )
    else:
        query = (
            select(SocialPost)
            .where(and_(*conditions))
            .order_by(SocialPost.published_at.desc())
        )

    result = await db.execute(query)
    return list(result.scalars().all())


async def create_post(
    db: AsyncSession, task_id: int, platform_id: int, post_data: dict
) -> SocialPost:
    """创建原文"""
    post = SocialPost(**post_data, task_id=task_id, platform_id=platform_id)
    db.add(post)
    await db.flush()
    return post


async def create_posts_bulk(
    db: AsyncSession, task_id: int, platform_id: int, posts_data: List[dict]
) -> List[SocialPost]:
    """批量创建原文"""
    posts = [
        SocialPost(**post_data, task_id=task_id, platform_id=platform_id)
        for post_data in posts_data
    ]
    db.add_all(posts)
    await db.flush()
    return posts


# ==================== SocialComment CRUD ====================


async def get_comment_by_id(
    db: AsyncSession, comment_id: int
) -> Optional[SocialComment]:
    """根据ID获取评论"""
    result = await db.execute(
        select(SocialComment).where(
            SocialComment.id == comment_id, SocialComment.is_deleted.is_(False)
        )
    )
    return result.scalar_one_or_none()


async def get_comments_by_post(
    db: AsyncSession, post_id: int, skip: int = 0, limit: int = 50
) -> tuple[List[SocialComment], int]:
    """获取帖子的评论列表"""
    # 统计总数
    count_query = (
        select(func.count())
        .select_from(SocialComment)
        .where(SocialComment.post_id == post_id, SocialComment.is_deleted.is_(False))
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # 查询评论，按发布时间倒序
    query = (
        select(SocialComment)
        .where(SocialComment.post_id == post_id, SocialComment.is_deleted.is_(False))
        .offset(skip)
        .limit(limit)
        .order_by(SocialComment.published_at.desc())
    )

    result = await db.execute(query)
    comments = result.scalars().all()

    return list(comments), total


async def get_comments_by_task(
    db: AsyncSession, task_id: int, skip: int = 0, limit: int = 50, post_id: int = None
) -> tuple[List[SocialComment], int]:
    """获取任务的评论列表，可选按原文ID筛选"""
    # 构建查询条件
    conditions = [SocialComment.task_id == task_id, SocialComment.is_deleted.is_(False)]

    # 如果指定了post_id，添加筛选条件
    if post_id is not None:
        conditions.append(SocialComment.post_id == post_id)

    # 统计总数
    count_query = select(func.count()).select_from(SocialComment).where(*conditions)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # 查询数据
    query = (
        select(SocialComment)
        .where(*conditions)
        .offset(skip)
        .limit(limit)
        .order_by(SocialComment.published_at.desc())
    )

    result = await db.execute(query)
    comments = result.scalars().all()

    return list(comments), total


async def create_comment(
    db: AsyncSession, task_id: int, post_id: int, platform_id: int, comment_data: dict
) -> SocialComment:
    """创建评论"""
    comment = SocialComment(
        **comment_data, task_id=task_id, post_id=post_id, platform_id=platform_id
    )
    db.add(comment)
    await db.flush()
    return comment


async def create_comments_bulk(
    db: AsyncSession,
    task_id: int,
    platform_id: int,
    comments_data: List[tuple[int, dict]],  # [(post_id, comment_data), ...]
) -> List[SocialComment]:
    """批量创建评论

    Args:
        comments_data: 列表，每个元素是(post_id, comment_data)元组
    """
    comments = [
        SocialComment(
            **comment_data, task_id=task_id, post_id=post_id, platform_id=platform_id
        )
        for post_id, comment_data in comments_data
    ]
    db.add_all(comments)
    await db.flush()

    # 更新每个原文的评论计数
    from collections import Counter

    post_comment_counts = Counter(post_id for post_id, _ in comments_data)

    for post_id, count in post_comment_counts.items():
        # 获取原文并更新评论计数
        post = await db.get(SocialPost, post_id)
        if post:
            post.comments_count = (post.comments_count or 0) + count

    await db.flush()
    return comments


# ==================== Bulk Task Creation ====================


async def bulk_create_tasks(
    db: AsyncSession,
    project_id: int,
    platform_ids: List[int],
    task_type: str,
    data_source: str,
    creator_id: int,
    keywords: Optional[str] = None,
) -> List[DataTask]:
    """为多个平台批量创建相同配置的任务

    Args:
        db: 数据库会话
        project_id: 项目ID
        platform_ids: 平台ID列表
        task_type: 任务类型（search/homefeed）
        data_source: 数据源
        creator_id: 创建者ID
        keywords: 关键词（search类型必填）

    Returns:
        创建的任务列表
    """
    tasks = []

    for platform_id in platform_ids:
        # 生成任务名称
        task_name = f"{task_type.title()} Task"
        if keywords:
            task_name += f" - {keywords[:20]}"  # 限制长度

        task_data = {
            "project_id": project_id,
            "platform_id": platform_id,
            "task_type": task_type,
            "data_source": data_source,
            "name": task_name,
            "keywords": keywords,
            "status": "pending",
        }

        task = DataTask(**task_data, creator_id=creator_id)
        tasks.append(task)

    db.add_all(tasks)
    await db.flush()

    # 重新查询以获取完整的关系数据
    task_ids = [task.id for task in tasks]
    result = await db.execute(
        select(DataTask)
        .options(
            selectinload(DataTask.project),
            selectinload(DataTask.platform),
            selectinload(DataTask.creator),
        )
        .where(DataTask.id.in_(task_ids))
    )
    refreshed_tasks = result.scalars().all()

    return list(refreshed_tasks)


async def soft_delete_task_posts(db: AsyncSession, task_id: int) -> int:
    """
    软删除指定任务的所有原文

    Args:
        db: 数据库会话
        task_id: 任务ID

    Returns:
        删除的记录数
    """
    from sqlalchemy import update

    result = await db.execute(
        update(SocialPost)
        .where(SocialPost.task_id == task_id)
        .where(SocialPost.is_deleted.is_(False))
        .values(is_deleted=True)
    )

    await db.flush()
    return result.rowcount


async def soft_delete_task_comments(db: AsyncSession, task_id: int) -> int:
    """
    软删除指定任务的所有评论

    Args:
        db: 数据库会话
        task_id: 任务ID

    Returns:
        删除的记录数
    """
    from sqlalchemy import update

    result = await db.execute(
        update(SocialComment)
        .where(SocialComment.task_id == task_id)
        .where(SocialComment.is_deleted.is_(False))
        .values(is_deleted=True)
    )

    await db.flush()
    return result.rowcount
