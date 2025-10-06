import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.results import service as result_service
from src.tasks.models import CrawlerTask, PlatformType, TaskStatus, CrawlerType


@pytest.mark.asyncio
async def test_bulk_create_notes(async_db_session: AsyncSession):
    task = CrawlerTask(
        name="test",
        platform=PlatformType.XHS,
        crawler_type=CrawlerType.SEARCH,
        status=TaskStatus.PENDING,
        config={},
    )
    async_db_session.add(task)
    await async_db_session.commit()
    await async_db_session.refresh(task)

    notes = [
        {"note_id": "n1", "title": "Note 1", "keyword": "ai"},
        {"note_id": "n2", "title": "Note 2", "keyword": "ai"},
    ]

    created = await result_service.bulk_create_notes(async_db_session, task, notes)

    assert len(created) == 2
    db_notes = await result_service.list_notes_by_task(async_db_session, task.id)
    assert len(db_notes) == 2
    assert {n.note_id for n in db_notes} == {"n1", "n2"}
