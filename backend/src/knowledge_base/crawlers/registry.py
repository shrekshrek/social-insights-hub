"""爬虫注册表：source_type → 爬虫类映射"""

from .base import BaseCrawler
from .cnnic import CNNICCrawler
from .govsite import GovsiteCrawler
from .nbs import NBSCrawler

CRAWLER_REGISTRY: dict[str, type[BaseCrawler]] = {
    "cnnic": CNNICCrawler,
    "nbs": NBSCrawler,
    "govsite": GovsiteCrawler,
}

__all__ = ["CRAWLER_REGISTRY"]
