"""Models for crawler execution results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.database import Base
from src.tasks.models import PlatformType


class CrawlerNoteResult(Base):
    __tablename__ = "crawler_note_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer, ForeignKey("crawler_tasks.id", ondelete="CASCADE"), nullable=False
    )
    platform = Column(String(50), nullable=False)
    note_id = Column(String(255), nullable=False)
    title = Column(String(512), nullable=False)
    keyword = Column(String(255), nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    task = relationship("CrawlerTask", backref="note_results")

    @classmethod
    def from_dict(cls, task_id: int, platform: PlatformType, data: dict[str, str]):
        return cls(
            task_id=task_id,
            platform=platform.value,
            note_id=data["note_id"],
            title=data.get("title", ""),
            keyword=data.get("keyword"),
            raw_data=data,
        )
