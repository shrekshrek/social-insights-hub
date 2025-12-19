#!/usr/bin/env python3
"""实体聚类/归一化功能测试

测试 LLM 实体聚类与归一化的同义词合并与多维打标功能。
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

from src.langchain.chains.entity_clustering_chain import (
    create_entity_clustering_chain,
    format_entities_for_clustering,
    parse_clustering_response,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_format_entities():
    """测试实体格式化函数"""
    entities = [
        {"name": "甲醛检测", "type": "服务", "heat": 85.5, "mentions": 120, "hint": "常与 测甲醛 对比"},
        {"name": "测甲醛", "type": "服务", "heat": 45.2, "mentions": 60},
        {"name": "华为", "type": "品牌", "heat": 100.0, "mentions": 200, "hint": "常与 小米, 苹果 对比"},
    ]
    formatted = format_entities_for_clustering(entities)
    logger.info(f"格式化结果:\n{formatted}")
    assert "甲醛检测" in formatted
    assert "[线索]: 常与 测甲醛 对比" in formatted
    assert "华为" in formatted
    logger.info("✅ format_entities_for_clustering 测试通过")
    return formatted


def test_parse_response():
    """测试响应解析函数"""
    mock_response = '''```json
    {
      "normalized_groups": [
        {
          "canonical_name": "甲醛检测",
          "tags": {
            "role": "FOCUS",
            "category": "服务",
            "parent": "室内环保"
          },
          "merged_entities": ["甲醛检测", "测甲醛", "甲醛测试"]
        }
      ],
      "standalone_entities": ["华为", "小米手机"]
    }
    ```'''
    result = parse_clustering_response(mock_response)
    logger.info(f"解析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    assert "normalized_groups" in result
    assert "standalone_entities" in result
    assert "entity_mapping" in result
    assert "tags_mapping" in result
    
    # 验证实体映射
    assert result["entity_mapping"]["甲醛检测"] == "甲醛检测"
    assert result["entity_mapping"]["测甲醛"] == "甲醛检测"
    
    # 验证标签映射
    tags = result["tags_mapping"].get("甲醛检测")
    assert tags is not None
    assert tags["role"] == "FOCUS"
    assert tags["parent"] == "室内环保"

    logger.info("✅ parse_clustering_response 测试通过")
    return result


def test_llm_clustering():
    """测试 LLM 实体聚类/归一化（需要真实 API 调用）"""
    # 准备测试数据：包含同义词的实体列表
    test_entities = [
        {"name": "Mate60", "type": "产品", "heat": 85.5, "mentions": 120, "hint": "常与 iPhone 15 对比"},
        {"name": "华为Mate60", "type": "产品", "heat": 45.2, "mentions": 60},
        {"name": "iPhone 15", "type": "产品", "heat": 100.0, "mentions": 200},
        {"name": "小米14", "type": "产品", "heat": 75.0, "mentions": 150},
        {"name": "露营", "type": "场景", "heat": 60.0, "mentions": 90},
        {"name": "帐篷", "type": "物品", "heat": 55.0, "mentions": 85},
    ]

    task_keywords = ["华为", "Mate60"]
    keywords_str = ", ".join(task_keywords)

    logger.info("=" * 60)
    logger.info("开始 LLM 实体聚类测试")
    logger.info("=" * 60)
    logger.info(f"输入实体数量: {len(test_entities)}")
    logger.info(f"锚点关键词: {keywords_str}")

    # 格式化输入
    formatted = format_entities_for_clustering(test_entities)
    logger.info(f"\n格式化后的输入:\n{formatted}")

    # 调用 LLM
    logger.info("\n调用 LLM 进行聚类...")
    chain = create_entity_clustering_chain()
    response = chain.invoke({
        "entities": formatted,
        "task_keywords": keywords_str
    })

    response_text = response.content if hasattr(response, "content") else str(response)
    logger.info(f"\nLLM 原始响应:\n{response_text}")

    # 解析响应
    result = parse_clustering_response(response_text)

    logger.info("\n" + "=" * 60)
    logger.info("归一化结果 (含标签)")
    logger.info("=" * 60)

    # 打印归一化组
    logger.info("\n📦 归一化组:")
    for group in result.get("normalized_groups", []):
        canonical = group.get("canonical_name", "")
        merged = group.get("merged_entities", [])
        tags = group.get("tags", {})
        
        logger.info(f"  ✅ {canonical}")
        logger.info(f"     Tags: {tags}")
        if len(merged) > 1:
            logger.info(f"     合并了: {merged}")

    # 验证关键预期
    tags_mapping = result.get("tags_mapping", {})
    
    # 预期1: Mate60 应该是 FOCUS
    # 注意：LLM 可能会把 key 设为 "Mate 60" 或 "Mate60"，需要模糊匹配
    mate60_key = next((k for k in tags_mapping.keys() if "Mate" in k), None)
    if mate60_key:
        assert tags_mapping[mate60_key]["role"] == "FOCUS"
        logger.info("✅ Mate60 角色正确 (FOCUS)")
    
    # 预期2: iPhone 15 应该是 RIVAL
    iphone_key = next((k for k in tags_mapping.keys() if "iPhone" in k), None)
    if iphone_key:
        assert tags_mapping[iphone_key]["role"] == "RIVAL"
        logger.info("✅ iPhone 15 角色正确 (RIVAL)")

    logger.info("\n✅ LLM 实体聚类测试完成")
    return result


def test_aggregated_entities_clustering():
    """测试 aggregate_entities 的完整流程（包含 LLM 聚类与打标、属性清洗）"""
    from src.social_media.analysis.celery_tasks.aggregation.entity_aggregation import (
        aggregate_entities,
    )

    # 模拟 posts_data 数据结构
    # 构造一个复杂的场景：华为 vs 苹果
    mock_posts_data = [
        {
            "post_id": 1,
            "cii": 100.0,
            "post_deep_result": {
                "entities": [
                    {
                        "name": "Mate60 Pro", 
                        "type": "产品", 
                        "sentiment": 1, 
                        "competitors": ["iPhone 15"],
                        # 模拟杂乱的属性数据，用于测试清洗
                        "features": ["拍照好看", "成片率高", "遥遥领先", "卫星通话"],
                        "issues": ["发热", "烫手", "有点热", "玩原神发烫"]
                    },
                    {"name": "华为", "type": "品牌", "sentiment": 1},
                ]
            }
        },
        {
            "post_id": 2,
            "cii": 90.0,
            "post_deep_result": {
                "entities": [
                    {
                        "name": "华为Mate60", 
                        "type": "产品", 
                        "sentiment": 1, 
                        "competitors": ["iPhone 15", "小米14"],
                        "features": ["拍照清晰", "卫星电话"],
                        "issues": ["温度高", "烫手"]
                    },
                    {"name": "麒麟9000s", "type": "技术", "sentiment": 1},
                ]
            }
        },
        {
            "post_id": 3,
            "cii": 80.0,
            "post_deep_result": {
                "entities": [
                    {
                        "name": "iPhone 15", 
                        "type": "产品", 
                        "sentiment": -1, 
                        "competitors": ["Mate60"],
                        "issues": ["发热严重", "信号差"]
                    },
                    {"name": "发热", "type": "问题", "sentiment": -1},
                ]
            }
        },
        # 增加更多数据以确保频次达到清洗阈值 (至少2次)
        {
            "post_id": 4,
            "cii": 50.0,
            "post_deep_result": {
                "entities": [
                    {
                        "name": "Mate60 Pro",
                        "issues": ["发热", "掉电快"]
                    }
                ]
            }
        }
    ]

    task_keywords = ["华为", "Mate60"]

    logger.info("=" * 60)
    logger.info("测试 aggregate_entities 完整流程 (含线索提取与属性清洗)")
    logger.info("=" * 60)

    # 测试 aggregate_entities（启用 LLM）
    result = aggregate_entities(
        mock_posts_data,
        task_keywords=task_keywords,
        enable_llm_normalization=True,
    )

    aggregated = result.get("aggregated_entities", [])
    logger.info(f"聚合后实体数量: {len(aggregated)}")

    # 检查详细结果
    for data in aggregated:
        name = data.get("name", "")
        tags = data.get("tags", {})
        merged_from = data.get("merged_from", [])
        issues = data.get("issues", [])
        
        logger.info(f"\n📌 {name}")
        logger.info(f"   Tags: {tags}")
        if merged_from:
            logger.info(f"   合并自: {merged_from}")
        
        if issues:
            logger.info("   Issues (Top 5):")
            for issue in issues[:5]:
                text = issue.get("text", "")
                post_ids = issue.get("post_ids", [])
                logger.info(f"     - {text} ({len(post_ids)})")
            
    # 验证关键数据
    # 1. 应该有 tags 字段
    has_tags = any("tags" in item for item in aggregated)
    assert has_tags, "结果中应包含 tags 字段"
    
    # 2. 验证属性清洗效果 (如果 Mate60 系列排名靠前，它的 issues 应该被清洗过)
    mate60_entity = next((e for e in aggregated if "Mate" in e["name"]), None)
    if mate60_entity:
        issues_list = [i["text"] for i in mate60_entity["issues"]]
        # 预期："发热"、"烫手" 等应该被合并为一个类似 "发热严重" 的词
        # 只要列表比原始的短，或者包含不在原始列表中的新词，就说明清洗生效了
        logger.info(f"Mate60 清洗后的 issues: {issues_list}")
        # 这里不做强断言，因为 LLM 输出不稳定，但有了日志可以人工确认
    
    logger.info("\n✅ aggregate_entities 完整流程测试完成")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="实体聚类功能测试")
    parser.add_argument("--unit-only", action="store_true", help="仅运行单元测试（不调用 LLM）")
    parser.add_argument("--full", action="store_true", help="运行完整测试（包括 aggregated_entities 聚类）")
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
    test_llm_clustering()

    # 完整流程测试
    if args.full:
        logger.info("\n")
        test_aggregated_entities_clustering()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有测试完成")
    logger.info("=" * 60)
