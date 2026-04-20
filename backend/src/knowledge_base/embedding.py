"""知识库向量嵌入服务

通过 OpenAI-compatible Embedding API（默认：SiliconFlow BAAI/bge-m3）
将文本向量化，输出维度 1024，适用于余弦相似度检索。
"""

import logging
from functools import lru_cache

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """OpenAI-compatible Embedding API 客户端

    使用 EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL 配置。
    默认指向 SiliconFlow 的 BAAI/bge-m3（1024 维）。
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY or "placeholder",
            base_url=settings.EMBEDDING_BASE_URL,
        )
        self._model = settings.EMBEDDING_MODEL

    async def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """将文本列表转为向量嵌入列表，自动分批以满足 API 限制

        Args:
            texts: 待嵌入的文本列表
            batch_size: 每批大小，默认 32（SiliconFlow 上限）

        Returns:
            1024 维浮点向量列表（余弦归一化由 API 保证，normalize_embeddings=True 等效）
        """
        results: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await self._client.embeddings.create(
                input=batch,
                model=self._model,
            )
            results.extend(item.embedding for item in response.data)
        return results


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """获取 EmbeddingService 单例"""
    return EmbeddingService()
