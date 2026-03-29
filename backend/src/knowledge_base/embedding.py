"""知识库向量嵌入服务

通过 OpenAI-compatible Embedding API（默认：SiliconFlow BAAI/bge-large-zh-v1.5）
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
    默认指向 SiliconFlow 的 BAAI/bge-large-zh-v1.5（1024 维）。
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY or "placeholder",
            base_url=settings.EMBEDDING_BASE_URL,
        )
        self._model = settings.EMBEDDING_MODEL

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转为向量嵌入列表

        Args:
            texts: 待嵌入的文本列表

        Returns:
            1024 维浮点向量列表（余弦归一化由 API 保证，normalize_embeddings=True 等效）
        """
        response = await self._client.embeddings.create(
            input=texts,
            model=self._model,
        )
        return [item.embedding for item in response.data]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """获取 EmbeddingService 单例"""
    return EmbeddingService()
