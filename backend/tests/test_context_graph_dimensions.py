"""测试 build_context_graph 的 spam 维度筛选功能"""

import pytest
from src.social_media.analysis.celery_tasks.aggregation.insights import build_context_graph


def test_context_graph_without_spam_map():
    """测试无 spam_map 时的行为（返回 3 层结构，所有维度引用相同数据）"""
    target_entity = {
        "name": "Product A",
        "post_ids": [1, 2, 3],
        "features": [
            {"text": "Feature 1", "post_ids": [1, 2]},
        ],
    }
    aggregated_opinions = [
        {"name": "Topic 1", "post_ids": [1, 3], "sentiment": 0.5},
    ]

    result = build_context_graph(target_entity, aggregated_opinions, spam_map=None)

    # 应该返回 3 层结构
    assert "all" in result
    assert "organic" in result
    assert "promo" in result

    # 每个版本都应该有完整的图结构
    for version in ["all", "organic", "promo"]:
        assert "center_node" in result[version]
        assert "nodes" in result[version]
        assert "edges" in result[version]

    # 所有维度应该引用相同的数据对象（无 spam 数据时的优化）
    assert result["organic"] is result["all"]
    assert result["promo"] is result["all"]


def test_context_graph_with_spam_map_returns_three_versions():
    """测试提供 spam_map 时返回 3 版本结构"""
    spam_map = {
        1: "high",  # 推广
        2: "low",   # 有机
        3: "low",   # 有机
    }

    target_entity = {
        "name": "Product A",
        "post_ids": [1, 2, 3],
        "features": [
            {"text": "Feature 1", "post_ids": [1, 2]},  # 混合
        ],
    }
    aggregated_opinions = [
        {"name": "Topic 1", "post_ids": [1, 3], "sentiment": 0.5},  # 混合
    ]

    result = build_context_graph(target_entity, aggregated_opinions, spam_map=spam_map)

    # 应该返回 3 层结构
    assert "all" in result
    assert "organic" in result
    assert "promo" in result

    # 每个版本都应该有完整的图结构
    for version in ["all", "organic", "promo"]:
        assert "center_node" in result[version]
        assert "nodes" in result[version]
        assert "edges" in result[version]
        assert result[version]["center_node"] == "Product A"


def test_context_graph_dimension_filtering():
    """测试按维度过滤的正确性"""
    spam_map = {
        1: "high",  # 推广
        2: "low",   # 有机
        3: "low",   # 有机
    }

    target_entity = {
        "name": "Product A",
        "post_ids": [1, 2, 3],
        "features": [
            {"text": "Feature 1", "post_ids": [1]},      # 仅推广
            {"text": "Feature 2", "post_ids": [2, 3]},   # 仅有机
        ],
    }
    aggregated_opinions = []

    result = build_context_graph(target_entity, aggregated_opinions, spam_map=spam_map)

    # all 版本应该包含所有节点
    all_nodes = result["all"]["nodes"]
    all_names = {n["name"] for n in all_nodes}

    # organic 版本应该只包含 Feature 2
    organic_nodes = result["organic"]["nodes"]
    organic_names = {n["name"] for n in organic_nodes}
    assert "Feature 2" in organic_names
    assert "Feature 1" not in organic_names

    # promo 版本应该只包含 Feature 1
    promo_nodes = result["promo"]["nodes"]
    promo_names = {n["name"] for n in promo_nodes}
    assert "Feature 1" in promo_names
    assert "Feature 2" not in promo_names


def test_context_graph_empty_dimension():
    """测试某维度过滤后为空的情况"""
    spam_map = {
        1: "low",   # 全部有机
        2: "low",
        3: "low",
    }

    target_entity = {
        "name": "Product A",
        "post_ids": [1, 2, 3],
        "features": [
            {"text": "Feature 1", "post_ids": [1, 2]},
        ],
    }
    aggregated_opinions = []

    result = build_context_graph(target_entity, aggregated_opinions, spam_map=spam_map)

    # promo 版本应该为空（无推广内容）
    assert result["promo"]["nodes"] == []
    assert result["promo"]["edges"] == []

    # organic 版本应该有内容
    assert len(result["organic"]["nodes"]) > 0
