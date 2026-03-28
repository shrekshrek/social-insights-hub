"""知识库向量嵌入服务

BAAI/bge-large-zh 懒加载单例，输出维度 1024，余弦相似度所需单位向量。
CPU 密集型操作通过 run_cpu_bound_task 在线程池中执行。
"""

import logging

from src.utils import run_cpu_bound_task

logger = logging.getLogger(__name__)


class EmbeddingService:
    """BAAI/bge-large-zh 懒加载单例

    首次调用 embed() 时加载模型（约 10s），后续调用直接使用。
    模型加载为 CPU 密集型，通过 run_cpu_bound_task 在线程池中执行。
    """

    _model = None  # 首次调用时加载

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转为向量嵌入列表

        CPU 密集型操作 → 必须通过 run_cpu_bound_task 执行。

        Args:
            texts: 待嵌入的文本列表

        Returns:
            1024 维单位向量列表（normalize_embeddings=True）
        """
        return await run_cpu_bound_task(self._encode, texts)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """同步编码（在线程池中运行）"""
        if self._model is None:
            logger.info("首次加载 BAAI/bge-large-zh 模型...")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("BAAI/bge-large-zh")
            logger.info("BAAI/bge-large-zh 模型加载完成")

        return self._model.encode(texts, normalize_embeddings=True).tolist()


# 模块级单例
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取 EmbeddingService 单例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
