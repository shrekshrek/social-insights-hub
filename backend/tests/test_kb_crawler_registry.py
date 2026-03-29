"""爬虫注册表测试"""

from src.knowledge_base.crawlers.registry import CRAWLER_REGISTRY


def test_registry_contains_all_source_types():
    """注册表必须包含全部三个公开数据来源"""
    assert set(CRAWLER_REGISTRY.keys()) == {"cnnic", "nbs", "govsite"}


def test_registry_values_are_crawler_classes():
    """注册表值必须是 BaseCrawler 子类（非实例）"""
    from src.knowledge_base.crawlers.base import BaseCrawler

    for source_type, cls in CRAWLER_REGISTRY.items():
        assert isinstance(cls, type), f"{source_type} 不是类"
        assert issubclass(cls, BaseCrawler), f"{source_type} 不是 BaseCrawler 子类"
        assert cls.source_type == source_type, f"{source_type} source_type 不匹配"
