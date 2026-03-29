"""BaseCrawler._upsert() 去重逻辑测试

测试场景（来自 docs/plan.md）：
- ready/processing/pending 状态 → 跳过（返回 True）
- failed 状态 → 重置重试（返回 False，重新派发任务）
- 新 URL → 新建文档（返回 False，派发任务）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.crawlers.base import BaseCrawler, CrawlSource
from src.knowledge_base.models import KnowledgeDocument


class DummyCrawler(BaseCrawler):
    source_type = "cnnic"

    async def discover(self) -> list[CrawlSource]:
        return []


_SRC = CrawlSource(
    url="https://example.com/report.pdf",
    title="测试报告",
    file_bytes=b"pdf-content",
    filename="report.pdf",
    source_meta={"year": 2024},
)


def _make_doc(status: str) -> KnowledgeDocument:
    doc = KnowledgeDocument()
    doc.id = 1
    doc.processing_status = status
    doc.source_type = "cnnic"
    doc.source_url = _SRC.url
    doc.source_meta = {}
    return doc


@pytest.fixture
def crawler():
    return DummyCrawler()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ready", "processing", "pending"])
async def test_upsert_skips_existing_normal_status(crawler, status):
    """已存在且状态正常 → 返回 True（跳过）"""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_doc(status)
    db.execute = AsyncMock(return_value=mock_result)

    with patch("src.knowledge_base.crawlers.base.process_document_task") as mock_task:
        skipped = await crawler._upsert(db, _SRC)

    assert skipped is True
    mock_task.delay.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_retries_failed_document(crawler):
    """failed 状态 → 重置为 pending，派发任务，返回 False"""
    db = AsyncMock()
    doc = _make_doc("failed")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    db.execute = AsyncMock(return_value=mock_result)

    with patch("src.knowledge_base.crawlers.base.process_document_task") as mock_task:
        skipped = await crawler._upsert(db, _SRC)

    assert skipped is False
    assert doc.processing_status == "pending"
    assert doc.error_message is None
    mock_task.delay.assert_called_once_with(doc.id)
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_creates_new_document(crawler):
    """新 URL → 创建文档，workspace_id=None（公共），派发任务，返回 False"""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    added_docs = []
    db.add = lambda doc: added_docs.append(doc)

    async def fake_refresh(doc):
        doc.id = 42

    db.refresh = fake_refresh

    with patch("src.knowledge_base.crawlers.base.process_document_task") as mock_task:
        skipped = await crawler._upsert(db, _SRC)

    assert skipped is False
    assert len(added_docs) == 1
    doc = added_docs[0]
    assert doc.workspace_id is None          # 平台公共
    assert doc.source_type == "cnnic"
    assert doc.source_url == _SRC.url
    assert doc.processing_status == "pending"
    assert "_file_bytes_b64" in doc.source_meta
    mock_task.delay.assert_called_once_with(42)
