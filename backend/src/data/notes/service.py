"""Service layer for note data operations."""

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
# Note operations
# ---------------------------------------------------------------------------


async def create_note(db: AsyncSession, data: schemas.NoteCreate) -> models.Note:
    """Create a new note in the database."""
    note = models.Note(
        platform=data.platform,
        note_id=data.note_id,
        title=data.title,
        content=data.content,
        note_type=data.note_type,
        author_id=data.author_id,
        author_name=data.author_name,
        liked_count=data.liked_count,
        collected_count=data.collected_count,
        comment_count=data.comment_count,
        shared_count=data.shared_count,
        view_count=data.view_count,
        images=data.images,
        video_url=data.video_url,
        note_url=data.note_url,
        ip_location=data.ip_location,
        tags=data.tags,
        published_at=data.published_at,
        last_modified_at=data.last_modified_at,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    logger.info(f"Created note: {note.note_id} from platform {note.platform}")
    return note


async def get_or_create_note(
    db: AsyncSession, data: schemas.NoteCreate
) -> tuple[models.Note, bool]:
    """
    Get existing note or create a new one.
    Returns (note, created) where created is True if the note was newly created.
    """
    # Try to find existing note by platform and note_id
    stmt = select(models.Note).where(
        models.Note.platform == data.platform, models.Note.note_id == data.note_id
    )
    result = await db.execute(stmt)
    existing_note = result.scalars().first()

    if existing_note:
        # Update statistics if they changed
        update_dict = data.model_dump(exclude_unset=True, exclude_none=True)
        changed = False
        for field, value in update_dict.items():
            if field in [
                "liked_count",
                "collected_count",
                "comment_count",
                "shared_count",
                "view_count",
                "title",
                "content",
            ]:
                current_value = getattr(existing_note, field)
                if current_value != value:
                    setattr(existing_note, field, value)
                    changed = True

        if changed:
            existing_note.updated_at = datetime.now()
            await db.commit()
            await db.refresh(existing_note)
            logger.info(f"Updated note: {existing_note.note_id}")

        return existing_note, False

    # Create new note
    note = await create_note(db, data)
    return note, True


async def list_notes(
    db: AsyncSession,
    platform: PlatformType | None = None,
    author_id: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Note]:
    """List notes with optional filters."""
    stmt: Select[models.Note] = select(models.Note)

    if platform is not None:
        stmt = stmt.where(models.Note.platform == platform)
    if author_id is not None:
        stmt = stmt.where(models.Note.author_id == author_id)

    stmt = stmt.order_by(models.Note.crawled_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_note(db: AsyncSession, note_id: int) -> models.Note | None:
    """Get note by database ID."""
    return await db.get(models.Note, note_id)


async def get_note_by_platform_id(
    db: AsyncSession, platform: str, note_id: str
) -> models.Note | None:
    """Get note by platform and platform's note ID."""
    stmt = select(models.Note).where(
        models.Note.platform == platform, models.Note.note_id == note_id
    )
    result = await db.execute(stmt)
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Task-Note association operations
# ---------------------------------------------------------------------------


async def associate_note_with_task(
    db: AsyncSession,
    task_id: int,
    note_id: int,
    keyword: str | None = None,
) -> models.TaskNote:
    """Create association between task and note."""
    # Check if association already exists
    stmt = select(models.TaskNote).where(
        models.TaskNote.task_id == task_id, models.TaskNote.note_id == note_id
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing:
        logger.debug(f"Task-Note association already exists: task={task_id}, note={note_id}")
        return existing

    # Create new association
    task_note = models.TaskNote(task_id=task_id, note_id=note_id, keyword=keyword)
    db.add(task_note)
    await db.commit()
    await db.refresh(task_note)
    logger.info(f"Created Task-Note association: task={task_id}, note={note_id}")
    return task_note


async def get_notes_by_task(
    db: AsyncSession, task_id: int, skip: int = 0, limit: int = 100
) -> List[models.Note]:
    """Get all notes associated with a task."""
    stmt = (
        select(models.Note)
        .join(models.TaskNote)
        .where(models.TaskNote.task_id == task_id)
        .order_by(models.TaskNote.crawled_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_tasks_by_note(
    db: AsyncSession, note_id: int
) -> List[models.TaskNote]:
    """Get all task associations for a note (with task metadata)."""
    stmt = (
        select(models.TaskNote)
        .where(models.TaskNote.note_id == note_id)
        .order_by(models.TaskNote.crawled_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_notes_by_task(db: AsyncSession, task_id: int) -> int:
    """Count how many notes are associated with a task."""
    from sqlalchemy import func

    stmt = select(func.count(models.TaskNote.id)).where(
        models.TaskNote.task_id == task_id
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def bulk_save_notes_from_crawler(
    db: AsyncSession,
    task_id: int,
    platform: str,
    notes_data: List[dict],
) -> List[models.Note]:
    """
    Bulk save notes from crawler results.

    This function:
    1. Creates or updates Note records
    2. Creates Task-Note associations
    3. Returns the list of saved notes

    Args:
        db: Database session
        task_id: Crawler task ID
        platform: Platform identifier (e.g., "xhs")
        notes_data: List of note dictionaries from crawler

    Returns:
        List of saved Note models
    """
    if not notes_data:
        return []

    saved_notes = []

    for note_dict in notes_data:
        try:
            # Extract keyword from note data (added by crawler)
            keyword = note_dict.get("keyword")

            # Convert crawler data to Note schema
            # Map crawler fields to our schema fields
            note_create = schemas.NoteCreate(
                platform=platform,
                note_id=note_dict.get("note_id", ""),
                title=note_dict.get("title", note_dict.get("desc", "Untitled")),
                content=note_dict.get("content") or note_dict.get("desc"),
                note_type=note_dict.get("type"),
                author_id=note_dict.get("user_id") or note_dict.get("author_id"),
                author_name=note_dict.get("user_name") or note_dict.get("author_name") or note_dict.get("nickname"),
                liked_count=note_dict.get("liked_count", 0) or note_dict.get("likes", 0),
                collected_count=note_dict.get("collected_count", 0) or note_dict.get("collects", 0),
                comment_count=note_dict.get("comment_count", 0) or note_dict.get("comments", 0),
                shared_count=note_dict.get("shared_count", 0) or note_dict.get("shares", 0),
                view_count=note_dict.get("view_count", 0) or note_dict.get("views", 0),
                images=str(note_dict.get("images")) if note_dict.get("images") else None,
                video_url=note_dict.get("video_url"),
                note_url=note_dict.get("note_url"),
                ip_location=note_dict.get("ip_location") or note_dict.get("ip_loc"),
                tags=str(note_dict.get("tags")) if note_dict.get("tags") else None,
                published_at=note_dict.get("published_at") or note_dict.get("publish_time"),
                last_modified_at=note_dict.get("last_modified_at") or note_dict.get("last_update_time"),
            )

            # Get or create note
            note, created = await get_or_create_note(db, note_create)

            # Associate with task
            await associate_note_with_task(db, task_id, note.id, keyword)

            saved_notes.append(note)

            if created:
                logger.debug(f"Created new note: {note.note_id}")
            else:
                logger.debug(f"Updated existing note: {note.note_id}")

        except Exception as exc:
            logger.error(f"Failed to save note {note_dict.get('note_id')}: {exc}", exc_info=True)
            continue

    logger.info(f"Bulk saved {len(saved_notes)} notes for task {task_id}")
    return saved_notes
