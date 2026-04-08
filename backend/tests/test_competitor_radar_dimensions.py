"""测试 analyze_competitor_radar 的 spam 维度筛选功能"""

import pytest
from src.analysis.celery_tasks.aggregation.insights import analyze_competitor_radar


def test_competitor_radar_without_spam_map():
    """测试无 spam_map 时的行为（返回 3 层结构，所有维度引用相同数据）"""
    target_entity = {"name": "Product A", "type": "Product", "role": "target", "tags": {"parent": "Brand A"}}
    competitor_entities = [{"name": "Product B", "type": "Product", "role": "competitor", "tags": {"parent": "Brand B"}}]
    aggregated_entities = [
        {
            "name": "Product A",
            "type": "Product",
            "role": "target",
            "tags": {"parent": "Brand A"},
            "mentions": 100,
            "heat": 500.0,
            "sentiment": 0.8,
            "sentiment_distribution": {"positive": 80, "negative": 10, "neutral": 10},
            "post_ids": [1, 2, 3],
            "post_source_ids": [1, 2],
            "comment_source_ids": [3],
        },
        {
            "name": "Product B",
            "type": "Product",
            "role": "competitor",
            "tags": {"parent": "Brand B"},
            "mentions": 80,
            "heat": 400.0,
            "sentiment": 0.5,
            "sentiment_distribution": {"positive": 50, "negative": 20, "neutral": 10},
            "post_ids": [4, 5],
            "post_source_ids": [4],
            "comment_source_ids": [5],
        },
    ]

    result = analyze_competitor_radar(
        target_entity, competitor_entities, aggregated_entities, spam_map=None, posts_data=None
    )

    # 应该返回 3 层结构
    assert "all" in result
    assert "organic" in result
    assert "promo" in result

    # 每个版本都应该有完整的雷达图结构
    for version in ["all", "organic", "promo"]:
        assert "mode" in result[version]
        assert "series" in result[version] or result[version]["mode"] == "none"

    # 所有维度应该引用相同的数据对象（无 spam 数据时的优化）
    assert result["organic"] is result["all"]
    assert result["promo"] is result["all"]


def test_competitor_radar_with_spam_map_returns_three_versions():
    """测试提供 spam_map 和 posts_data 时返回 3 版本结构"""
    spam_map = {
        1: "high",  # 推广
        2: "low",   # 有机
        3: "low",   # 有机
        4: "high",  # 推广
        5: "low",   # 有机
    }

    posts_data = [
        {"post_id": 1, "cii": 10, "sentiment": 1},
        {"post_id": 2, "cii": 5, "sentiment": 1},
        {"post_id": 3, "cii": 3, "sentiment": 0},
        {"post_id": 4, "cii": 8, "sentiment": -1},
        {"post_id": 5, "cii": 6, "sentiment": 0},
    ]

    target_entity = {"name": "Product A", "type": "Product", "role": "target", "tags": {"parent": "Brand A"}}
    competitor_entities = [{"name": "Product B", "type": "Product", "role": "competitor", "tags": {"parent": "Brand B"}}]
    aggregated_entities = [
        {
            "name": "Product A",
            "type": "Product",
            "role": "target",
            "tags": {"parent": "Brand A"},
            "mentions": 100,
            "heat": 500.0,
            "sentiment": 0.8,
            "sentiment_distribution": {"positive": 80, "negative": 10, "neutral": 10},
            "post_ids": [1, 2, 3],
            "post_source_ids": [1, 2],
            "comment_source_ids": [3],
        },
        {
            "name": "Product B",
            "type": "Product",
            "role": "competitor",
            "tags": {"parent": "Brand B"},
            "mentions": 80,
            "heat": 400.0,
            "sentiment": 0.5,
            "sentiment_distribution": {"positive": 50, "negative": 20, "neutral": 10},
            "post_ids": [4, 5],
            "post_source_ids": [4],
            "comment_source_ids": [5],
        },
    ]

    result = analyze_competitor_radar(
        target_entity, competitor_entities, aggregated_entities, spam_map=spam_map, posts_data=posts_data
    )

    # 应该返回 3 层结构
    assert "all" in result
    assert "organic" in result
    assert "promo" in result

    # 每个版本都应该有完整的雷达图结构
    for version in ["all", "organic", "promo"]:
        assert "mode" in result[version]
        assert "series" in result[version] or result[version]["mode"] == "none"


def test_competitor_radar_dimension_stats_accuracy():
    """测试按维度重新聚合统计的准确性"""
    spam_map = {
        1: "high",  # 推广 post
        2: "low",   # 有机 post
        3: "low",   # 有机 comment
    }

    # CII: 推广帖 10, 有机帖 5, 有机评论 3
    # Sentiment: 推广 1, 有机帖 1, 有机评论 0
    posts_data = [
        {"post_id": 1, "cii": 10, "sentiment": 1},   # 推广
        {"post_id": 2, "cii": 5, "sentiment": 1},    # 有机
        {"post_id": 3, "cii": 3, "sentiment": 0},    # 有机
    ]

    target_entity = {"name": "Product A", "type": "Product", "role": "target", "tags": {"parent": "Brand A"}}
    competitor_entities = []
    aggregated_entities = [
        {
            "name": "Product A",
            "type": "Product",
            "role": "target",
            "tags": {"parent": "Brand A"},
            "mentions": 3,
            "heat": 18.0,  # 10+5+3
            "sentiment": 0.67,
            "sentiment_distribution": {"positive": 2, "negative": 0, "neutral": 1},
            "post_ids": [1, 2, 3],
            "post_source_ids": [1, 2],  # 推广1个，有机1个
            "comment_source_ids": [3],  # 有机1个
        },
    ]

    result = analyze_competitor_radar(
        target_entity, competitor_entities, aggregated_entities, spam_map=spam_map, posts_data=posts_data
    )

    # organic 版本应该只包含 post 2 和 comment 3
    organic_series = result["organic"].get("series", [])
    if organic_series:  # 如果有数据
        # mentions 应该是 2 (1 post + 1 comment)
        # heat 应该是 8.0 (5+3)
        assert organic_series[0]["data"]["mentions"] == 2
        assert organic_series[0]["data"]["heat"] == pytest.approx(8.0)

    # promo 版本应该只包含 post 1
    promo_series = result["promo"].get("series", [])
    if promo_series:
        # mentions 应该是 1
        # heat 应该是 10.0
        assert promo_series[0]["data"]["mentions"] == 1
        assert promo_series[0]["data"]["heat"] == pytest.approx(10.0)
