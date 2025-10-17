"""Service layer for comment data operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.tasks.models import PlatformType

from . import models, schemas

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Comment operations
# ---------------------------------------------------------------------------


async def create_comment(
    db: AsyncSession, data: schemas.CommentCreate
) -> models.Comment:
    """Create a new comment in the database."""
    comment = models.Comment(
        platform=data.platform,
        comment_id=data.comment_id,
        content=data.content,
        note_id=data.note_id,
        note_title=data.note_title,
        parent_comment_id=data.parent_comment_id,
        author_id=data.author_id,
        author_name=data.author_name,
        author_avatar=data.author_avatar,
        sub_comment_count=data.sub_comment_count,
        liked_count=data.liked_count,
        reply_count=data.reply_count,
        ip_location=data.ip_location,
        published_at=data.published_at,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    logger.info(
        f"Created comment: {comment.comment_id} from platform {comment.platform}"
    )
    return comment


async def get_or_create_comment(
    db: AsyncSession, data: schemas.CommentCreate
) -> tuple[models.Comment, bool]:
    """
    Get existing comment or create a new one.
    Returns (comment, created) where created is True if the comment was newly created.
    """
    # Try to find existing comment by platform and comment_id
    stmt = select(models.Comment).where(
        models.Comment.platform == data.platform,
        models.Comment.comment_id == data.comment_id,
    )
    result = await db.execute(stmt)
    existing_comment = result.scalars().first()

    if existing_comment:
        # Update statistics if they changed
        update_dict = data.model_dump(exclude_unset=True, exclude_none=True)
        changed = False
        for field, value in update_dict.items():
            if field in [
                "sub_comment_count",
                "liked_count",
                "reply_count",
                "content",
            ]:
                current_value = getattr(existing_comment, field)
                if current_value != value:
                    setattr(existing_comment, field, value)
                    changed = True

        if changed:
            existing_comment.updated_at = datetime.now()
            await db.commit()
            await db.refresh(existing_comment)
            logger.info(f"Updated comment: {existing_comment.comment_id}")

        return existing_comment, False

    # Create new comment
    comment = await create_comment(db, data)
    return comment, True


async def list_comments(
    db: AsyncSession,
    platform: PlatformType | None = None,
    note_id: str | None = None,
    author_id: str | None = None,
    parent_comment_id: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Comment]:
    """List comments with optional filters."""
    stmt: Select[models.Comment] = select(models.Comment)

    if platform is not None:
        stmt = stmt.where(models.Comment.platform == platform)
    if note_id is not None:
        stmt = stmt.where(models.Comment.note_id == note_id)
    if author_id is not None:
        stmt = stmt.where(models.Comment.author_id == author_id)
    if parent_comment_id is not None:
        stmt = stmt.where(models.Comment.parent_comment_id == parent_comment_id)

    stmt = stmt.order_by(models.Comment.crawled_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_comment(db: AsyncSession, comment_id: int) -> models.Comment | None:
    """Get comment by database ID."""
    return await db.get(models.Comment, comment_id)


async def get_comment_by_platform_id(
    db: AsyncSession, platform: str, comment_id: str
) -> models.Comment | None:
    """Get comment by platform and platform's comment ID."""
    stmt = select(models.Comment).where(
        models.Comment.platform == platform, models.Comment.comment_id == comment_id
    )
    result = await db.execute(stmt)
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Task-Comment association operations
# ---------------------------------------------------------------------------


async def associate_comment_with_task(
    db: AsyncSession,
    task_id: int,
    comment_id: int,
    keyword: str | None = None,
) -> models.TaskComment:
    """Create association between task and comment."""
    # Check if association already exists
    stmt = select(models.TaskComment).where(
        models.TaskComment.task_id == task_id,
        models.TaskComment.comment_id == comment_id,
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing:
        logger.debug(
            f"Task-Comment association already exists: task={task_id}, comment={comment_id}"
        )
        return existing

    # Create new association
    task_comment = models.TaskComment(
        task_id=task_id, comment_id=comment_id, keyword=keyword
    )
    db.add(task_comment)
    await db.commit()
    await db.refresh(task_comment)
    logger.info(
        f"Created Task-Comment association: task={task_id}, comment={comment_id}"
    )
    return task_comment


async def get_comments_by_task(
    db: AsyncSession, task_id: int, skip: int = 0, limit: int = 100
) -> List[models.Comment]:
    """Get all comments associated with a task."""
    stmt = (
        select(models.Comment)
        .join(models.TaskComment)
        .where(models.TaskComment.task_id == task_id)
        .order_by(models.TaskComment.crawled_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_tasks_by_comment(
    db: AsyncSession, comment_id: int
) -> List[models.TaskComment]:
    """Get all task associations for a comment (with task metadata)."""
    stmt = (
        select(models.TaskComment)
        .where(models.TaskComment.comment_id == comment_id)
        .order_by(models.TaskComment.crawled_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_comments_by_task(db: AsyncSession, task_id: int) -> int:
    """Count how many comments are associated with a task."""
    from sqlalchemy import func

    stmt = select(func.count(models.TaskComment.id)).where(
        models.TaskComment.task_id == task_id
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def bulk_save_comments_from_crawler(
    db: AsyncSession,
    task_id: int,
    platform: str,
    comments_data: List[dict],
) -> List[models.Comment]:
    """
    Bulk save comments from crawler results.

    This function:
    1. Creates or updates Comment records
    2. Creates Task-Comment associations
    3. Returns the list of saved comments

    Args:
        db: Database session
        task_id: Crawler task ID
        platform: Platform identifier (e.g., "xhs")
        comments_data: List of comment dictionaries from crawler

    Returns:
        List of saved Comment models
    """
    if not comments_data:
        return []

    saved_comments = []

    for comment_dict in comments_data:
        try:
            # Extract keyword from comment data (added by crawler)
            keyword = comment_dict.get("keyword")

            # Parse published_at timestamp (ms)
            published_at = None
            create_time = comment_dict.get("published_at") or comment_dict.get(
                "create_time"
            )
            if create_time:
                try:
                    # XHS API returns timestamp in milliseconds
                    if isinstance(create_time, int):
                        published_at = datetime.fromtimestamp(create_time / 1000)
                    elif isinstance(create_time, datetime):
                        published_at = create_time
                except Exception:
                    published_at = None

            # Convert crawler data to Comment schema
            # Map crawler fields to our schema fields
            comment_create = schemas.CommentCreate(
                platform=platform,
                comment_id=comment_dict.get("comment_id", ""),
                content=comment_dict.get("content", ""),
                note_id=comment_dict.get("note_id", ""),
                note_title=comment_dict.get("note_title"),
                parent_comment_id=comment_dict.get("parent_comment_id"),
                author_id=comment_dict.get("user_id")
                or comment_dict.get("author_id", ""),
                author_name=comment_dict.get("user_name")
                or comment_dict.get("author_name")
                or comment_dict.get("nickname"),
                author_avatar=comment_dict.get("avatar")
                or comment_dict.get("author_avatar"),
                sub_comment_count=comment_dict.get("sub_comment_count", 0),
                liked_count=comment_dict.get("liked_count", 0)
                or comment_dict.get("likes", 0),
                reply_count=comment_dict.get("reply_count", 0),
                ip_location=comment_dict.get("ip_location")
                or comment_dict.get("ip_loc"),
                published_at=published_at,
            )

            # Get or create comment
            comment, created = await get_or_create_comment(db, comment_create)

            # Associate with task
            await associate_comment_with_task(db, task_id, comment.id, keyword)

            saved_comments.append(comment)

            if created:
                logger.debug(f"Created new comment: {comment.comment_id}")
            else:
                logger.debug(f"Updated existing comment: {comment.comment_id}")

        except Exception as exc:
            logger.error(
                f"Failed to save comment {comment_dict.get('comment_id')}: {exc}",
                exc_info=True,
            )
            continue

    logger.info(f"Bulk saved {len(saved_comments)} comments for task {task_id}")
    return saved_comments
