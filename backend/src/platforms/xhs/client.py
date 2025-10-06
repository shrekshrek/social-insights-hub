"""Simplified XiaoHongShu client for prototype execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class XhsNote:
    note_id: str
    title: str
    keyword: str


class XhsClient:
    """Minimal client returning simulated search results."""

    async def search_notes(self, keyword: str, limit: int = 5) -> List[XhsNote]:
        keyword = keyword.strip()
        if not keyword:
            return []
        notes = []
        for idx in range(1, limit + 1):
            notes.append(
                XhsNote(
                    note_id=f"{keyword}-{idx}",
                    title=f"模拟笔记 {idx} - {keyword}",
                    keyword=keyword,
                )
            )
        return notes
