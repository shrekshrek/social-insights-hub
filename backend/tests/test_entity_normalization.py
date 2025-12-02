#!/usr/bin/env python3
"""实体归一化功能测试

测试 LLM 实体归一化的同义词合并功能。
"""

import sys
import os
import json
import logging

# 添加项目根目录到 PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载测试环境配置
from dotenv import load_dotenv
load_dotenv('.env.test')

from src.langchain.chains.entity_normalization_chain import (
    create_entity_normalization_chain,
    format_entities_for_normalization,
    parse_normalization_response,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_format_entities():
    """测试实体格式化函数"""
    entities = [
        {"name": "甲醛检测", "type": "服务", "heat": 85.5, "mentions": 120},
        {"name": "测甲醛", "type": "服务", "heat": 45.2, "mentions": 60},
        {"name": "华为", "type": "品牌", "heat": 100.0, "mentions": 200},
    ]
    formatted = format_entities_for_normalization(entities)
    logger.info(f"格式化结果:\n{formatted}")
    assert "甲醛检测" in formatted
    assert "测甲醛" in formatted
    assert "华为" in formatted
    logger.info("✅ format_entities_for_normalization 测试通过")
    return formatted


def test_parse_response():
    """测试响应解析函数"""
    mock_response = '''```json
{
  "normalized_groups": [
    {
      "canonical_name": "甲醛检测",
      "type": "服务",
      "merged_entities": ["甲醛检测", "测甲醛", "甲醛测试"]
    }
  ],
  "standalone_entities": ["华为", "小米手机"]
}
```'''
    result = parse_normalization_response(mock_response)
    logger.info(f"解析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    assert "normalized_groups" in result
    assert "standalone_entities" in result
    assert "entity_mapping" in result
    assert result["entity_mapping"]["甲醛检测"] == "甲醛检测"
    assert result["entity_mapping"]["测甲醛"] == "甲醛检测"
    assert result["entity_mapping"]["甲醛测试"] == "甲醛检测"
    assert result["entity_mapping"]["华为"] == "华为"
    logger.info("✅ parse_normalization_response 测试通过")
    return result


def test_llm_normalization():
    """测试 LLM 实体归一化（需要真实 API 调用）"""
    # 准备测试数据：包含同义词的实体列表
    test_entities = [
        {"name": "甲醛检测", "type": "服务", "heat": 85.5, "mentions": 120},
        {"name": "测甲醛", "type": "服务", "heat": 45.2, "mentions": 60},
        {"name": "甲醛测试", "type": "服务", "heat": 30.0, "mentions": 40},
        {"name": "华为", "type": "品牌", "heat": 100.0, "mentions": 200},
        {"name": "Huawei", "type": "品牌", "heat": 50.0, "mentions": 80},
        {"name": "小米手机", "type": "产品", "heat": 75.0, "mentions": 150},
        {"name": "Xiaomi手机", "type": "产品", "heat": 25.0, "mentions": 30},
        {"name": "室内空气治理", "type": "服务", "heat": 60.0, "mentions": 90},
        {"name": "除甲醛", "type": "服务", "heat": 55.0, "mentions": 85},
        {"name": "空气净化", "type": "服务", "heat": 40.0, "mentions": 50},
    ]

    logger.info("=" * 60)
    logger.info("开始 LLM 实体归一化测试")
    logger.info("=" * 60)
    logger.info(f"输入实体数量: {len(test_entities)}")

    # 格式化输入
    formatted = format_entities_for_normalization(test_entities)
    logger.info(f"\n格式化后的输入:\n{formatted}")

    # 调用 LLM
    logger.info("\n调用 LLM 进行归一化...")
    chain = create_entity_normalization_chain()
    response = chain.invoke({
        "entities": formatted,
    })

    response_text = response.content if hasattr(response, "content") else str(response)
    logger.info(f"\nLLM 原始响应:\n{response_text}")

    # 解析响应
    result = parse_normalization_response(response_text)

    logger.info("\n" + "=" * 60)
    logger.info("归一化结果")
    logger.info("=" * 60)

    # 打印归一化组
    logger.info("\n📦 归一化组:")
    for group in result.get("normalized_groups", []):
        canonical = group.get("canonical_name", "")
        entity_type = group.get("type", "")
        merged = group.get("merged_entities", [])
        if len(merged) > 1:
            logger.info(f"  ✅ {canonical} ({entity_type})")
            logger.info(f"     合并了: {merged}")
        else:
            logger.info(f"  - {canonical} ({entity_type}) [单独]")

    # 打印独立实体
    standalone = result.get("standalone_entities", [])
    if standalone:
        logger.info(f"\n📌 独立实体: {standalone}")

    # 打印映射表
    logger.info(f"\n🗺️ 实体映射表:")
    for original, canonical in result.get("entity_mapping", {}).items():
        if original != canonical:
            logger.info(f"  {original} → {canonical}")

    logger.info("\n✅ LLM 实体归一化测试完成")
    return result


def test_aggregated_entities_normalization():
    """测试 aggregate_entities 的完整流程（包含 LLM 归一化）"""
    from src.social_media.analysis.celery_tasks.aggregation.entity_aggregation import (
        aggregate_entities,
        build_entity_name_mapping,
    )

    # 模拟 posts_data 数据结构
    mock_posts_data = [
        {
            "post_id": 1,
            "cii": 85.5,
            "post_deep_result": {
                "entities": [
                    {"name": "甲醛检测", "type": "服务", "sentiment": 1, "features": ["快速出结果"], "issues": [], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []},
                ]
            },
            "comment_deep_result": None,
        },
        {
            "post_id": 2,
            "cii": 45.2,
            "post_deep_result": {
                "entities": [
                    {"name": "测甲醛", "type": "服务", "sentiment": 1, "features": ["上门服务"], "issues": [], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []},
                ]
            },
            "comment_deep_result": None,
        },
        {
            "post_id": 3,
            "cii": 30.0,
            "post_deep_result": {
                "entities": [
                    {"name": "甲醛测试", "type": "服务", "sentiment": 0, "features": [], "issues": ["价格偏高"], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []},
                ]
            },
            "comment_deep_result": None,
        },
        {
            "post_id": 4,
            "cii": 100.0,
            "post_deep_result": {
                "entities": [
                    {"name": "华为", "type": "品牌", "sentiment": 1, "features": [], "issues": [], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []},
                ]
            },
            "comment_deep_result": None,
        },
        {
            "post_id": 5,
            "cii": 50.0,
            "post_deep_result": {
                "entities": [
                    {"name": "Huawei", "type": "品牌", "sentiment": 1, "features": [], "issues": [], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []},
                ]
            },
            "comment_deep_result": None,
        },
    ]

    task_keywords = ["甲醛"]

    logger.info("=" * 60)
    logger.info("测试 aggregate_entities 完整流程")
    logger.info("=" * 60)
    logger.info(f"输入帖子数量: {len(mock_posts_data)}")

    # 1. 先测试 build_entity_name_mapping（不调用 LLM）
    logger.info("\n--- 测试 build_entity_name_mapping（仅程序相似度）---")
    name_mapping, token_stats = build_entity_name_mapping(
        mock_posts_data,
        task_keywords,
        enable_llm=False,  # 不调用 LLM
    )
    logger.info(f"名称映射: {name_mapping}")
    logger.info(f"Token 统计: {token_stats}")

    # 2. 测试 aggregate_entities（启用 LLM 归一化）
    logger.info("\n--- 测试 aggregate_entities（启用 LLM）---")
    result = aggregate_entities(
        mock_posts_data,
        task_keywords=task_keywords,
        enable_llm_normalization=True,
    )

    aggregated = result.get("aggregated_entities", [])
    logger.info(f"聚合后实体数量: {len(aggregated)}")

    # 检查合并结果（数组格式）
    for data in aggregated:
        name = data.get("name", "")
        merged_from = data.get("merged_from", [])
        if merged_from:
            logger.info(f"\n✅ 合并成功: {name}")
            logger.info(f"   - 来源: {merged_from}")
            logger.info(f"   - 合并后 heat: {data.get('heat', 0)}")
            logger.info(f"   - 合并后 mentions: {data.get('mentions', 0)}")
            logger.info(f"   - 合并后 post_ids: {data.get('post_ids', [])}")

    # 检查 top_entities
    top_entities = result.get("top_entities", [])
    logger.info(f"\n📊 top_entities 数量: {len(top_entities)}")
    for entity in top_entities:
        logger.info(f"   - {entity['name']}: heat={entity['heat']}, mentions={entity['mentions']}")
        if entity.get("merged_from"):
            logger.info(f"     合并自: {entity['merged_from']}")

    logger.info("\n✅ aggregate_entities 完整流程测试完成")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="实体归一化功能测试")
    parser.add_argument("--unit-only", action="store_true", help="仅运行单元测试（不调用 LLM）")
    parser.add_argument("--full", action="store_true", help="运行完整测试（包括 aggregated_entities 归一化）")
    args = parser.parse_args()

    # 单元测试（不需要 LLM）
    logger.info("\n" + "=" * 60)
    logger.info("单元测试")
    logger.info("=" * 60)
    test_format_entities()
    test_parse_response()

    if args.unit_only:
        logger.info("\n✅ 单元测试全部通过")
        sys.exit(0)

    # LLM 测试
    logger.info("\n")
    test_llm_normalization()

    # 完整流程测试
    if args.full:
        logger.info("\n")
        test_aggregated_entities_normalization()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有测试完成")
    logger.info("=" * 60)
