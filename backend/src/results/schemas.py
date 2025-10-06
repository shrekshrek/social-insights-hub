"""Schemas for execution results."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class CrawlerNoteResultResponse(CustomBaseModel):
    id: int
    note_id: str = Field(..., description="原始笔记ID")
    title: str
    keyword: str | None = None
    created_at: datetime
    raw_data: dict | None = None
