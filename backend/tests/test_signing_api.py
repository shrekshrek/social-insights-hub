import pytest

from src.signing.client import SignatureGenerationError


@pytest.mark.asyncio
async def test_signing_generate_success(async_client, monkeypatch):
    async def fake_generate(platform, payload):
        assert platform == "xhs"
        assert payload == {"keyword": "ai"}
        return {"signature": "sig", "timestamp": 123}

    monkeypatch.setattr("src.signing.router.generate_signature", fake_generate)

    response = await async_client.post(
        "/api/v1/signing/xhs",
        json={"payload": {"keyword": "ai"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"signature": "sig", "timestamp": 123}
    assert body["message"] is None


@pytest.mark.asyncio
async def test_signing_generate_failure(async_client, monkeypatch):
    async def fake_generate(platform, payload):
        raise SignatureGenerationError("签名生成失败")

    monkeypatch.setattr("src.signing.router.generate_signature", fake_generate)

    response = await async_client.post(
        "/api/v1/signing/xhs",
        json={"payload": {"keyword": "ai"}},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "签名生成失败"}
