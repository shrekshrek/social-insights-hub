import pytest

from types import SimpleNamespace

from src.signing import SignatureGenerationError
from src.platforms.xhs.adapter import XiaoHongShuAdapter


class DummyContext:
    def __init__(self, config):
        self.task = SimpleNamespace(id=1, config=config)
        self.logged = []
        self.progress_updates = []

    async def update_progress(
        self, progress, crawled_count, checkpoint_id=None, checkpoint_data=None
    ):
        self.progress_updates.append((progress, crawled_count))

    async def log(self, level, message, detail=None):
        self.logged.append((level, message))


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_xhs_adapter_with_keywords(monkeypatch):
    adapter = XiaoHongShuAdapter()
    context = DummyContext({"keywords": "ai, nuxt", "max_count": 3})

    async def fake_signature(platform, payload):
        return {"signature": f"sig-{payload['keyword']}"}

    monkeypatch.setattr("src.platforms.xhs.adapter.generate_signature", fake_signature)

    await adapter.execute(context)

    assert context.progress_updates[-1] == (100, 6)
    assert any("开始执行小红书任务" in msg for _, msg in context.logged)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_xhs_adapter_without_keywords(monkeypatch):
    adapter = XiaoHongShuAdapter()
    context = DummyContext({})

    async def fake_signature(platform, payload):  # pragma: no cover
        return {"signature": "unused"}

    monkeypatch.setattr("src.platforms.xhs.adapter.generate_signature", fake_signature)

    await adapter.execute(context)

    assert context.progress_updates[-1] == (100, 0)
    assert any("未配置关键词" in msg for _, msg in context.logged)


@pytest.mark.asyncio
async def test_xhs_adapter_signature_failure(monkeypatch):
    adapter = XiaoHongShuAdapter()
    context = DummyContext({"keywords": "ai"})

    async def fake_signature(platform, payload):
        raise SignatureGenerationError("签名失败")

    monkeypatch.setattr("src.platforms.xhs.adapter.generate_signature", fake_signature)

    with pytest.raises(SignatureGenerationError):
        await adapter.execute(context)

    assert any("签名失败" in msg for _, msg in context.logged)
