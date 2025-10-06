"""Service helpers for storing crawler results."""

from __future__ import annotations

from typing import List, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.tasks.models import CrawlerTask

from .models import CrawlerNoteResult


async def bulk_create_notes(
    db: AsyncSession,
    task: CrawlerTask,
    notes: Sequence[dict],
) -> List[CrawlerNoteResult]:
    if not notes:
        return []

    entities = [
        CrawlerNoteResult.from_dict(task.id, task.platform, note) for note in notes
    ]
    db.add_all(entities)
    await db.commit()
    for entity in entities:
        await db.refresh(entity)
    return entities


async def list_notes_by_task(db: AsyncSession, task_id: int) -> List[CrawlerNoteResult]:
    stmt = (
        select(CrawlerNoteResult)
        .where(CrawlerNoteResult.task_id == task_id)
        .order_by(CrawlerNoteResult.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
