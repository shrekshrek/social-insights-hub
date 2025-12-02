#!/usr/bin/env python3
"""实体归一化 Chain

对聚合后的实体进行同义词合并，减少冗余。
"""

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


ENTITY_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位专业的实体归一化专家，负责对从社交媒体舆情数据中提取的实体进行同义词合并。

## 任务目标
识别并合并语义相同但表述不同的实体，减少冗余，提升分析报告的可读性。

## 归一化规则（重要：只合并同类型实体）

### 可以合并的情况
- **只有类型相同的实体才能合并**
- 相同概念的不同表述（如"甲醛检测"="测甲醛"="甲醛测试"，都是服务类型）
- 简称和全称（如"小米手机"="Xiaomi手机"，都是产品类型）
- 中英文名（如"苹果"="Apple"，都是品牌类型）

### 不能合并的情况
- 不同类型的实体（如"华为"是品牌，"华为手机"是产品，不能合并）
- 相关但不同义的实体（如"甲醛检测"和"除甲醛"是不同服务，不能合并）
- 品牌和其产品（如"小米"和"小米手机"是不同实体）

## 输入格式
实体列表，每个实体包含：name（名称）、type（类型：品牌/产品/服务/人物/其他）、score（重要度，综合考虑影响力和讨论广泛性）

## 输出格式
```json
{{
  "normalized_groups": [
    {{
      "canonical_name": "代表性名称（选择重要度最高或最规范的名称）",
      "type": "实体类型",
      "merged_entities": ["被合并的原始实体名称列表，包含canonical_name自身"]
    }}
  ],
  "standalone_entities": ["无法归一化的独立实体名称列表"]
}}
```

## 注意事项
1. **保守合并**：只有确定是同义/近义时才合并，不确定的保持独立
2. **保留重要度高的实体**：合并时优先选择重要度高的名称作为canonical_name
3. **类型必须一致**：不同类型的实体绝不能合并
4. **处理所有输入实体**：确保每个输入实体都出现在输出中（要么在merged_entities，要么在standalone_entities）

只输出JSON，不要有其他文字。
"""

ENTITY_NORMALIZATION_USER_TEMPLATE = """请对以下实体列表进行归一化处理：

任务关键词（用于理解业务背景）：{keywords}

实体列表：
{entities}

请输出归一化后的JSON结果。
"""


def create_entity_normalization_chain() -> Runnable:
    """创建实体归一化的LangChain链

    Returns:
        Runnable: 用于实体归一化的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_NORMALIZATION_SYSTEM_TEMPLATE),
        ("user", ENTITY_NORMALIZATION_USER_TEMPLATE),
    ])

    return prompt | llm


def format_entities_for_normalization(entities: list[dict[str, Any]]) -> str:
    """格式化实体列表用于归一化

    Args:
        entities: 实体列表，每个包含 name, type, score 字段

    Returns:
        str: 格式化后的实体列表字符串
    """
    return "\n".join([
        f"- {e['name']} (类型: {e.get('type', '其他')}, 重要度: {e.get('score', 0):.1f})"
        for e in entities
    ])


def parse_normalization_response(response_text: str) -> dict[str, Any]:
    """解析LLM归一化响应

    Args:
        response_text: LLM返回的文本

    Returns:
        dict: 包含 normalized_groups, standalone_entities, entity_mapping
    """
    # 清理可能的 markdown 代码块
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    result = json.loads(response_text.strip())

    # 构建实体映射表（原名称 -> 归一化名称）
    entity_mapping = {}
    for group in result.get("normalized_groups", []):
        canonical_name = group.get("canonical_name", "")
        for merged in group.get("merged_entities", []):
            entity_mapping[merged] = canonical_name

    for standalone in result.get("standalone_entities", []):
        entity_mapping[standalone] = standalone

    result["entity_mapping"] = entity_mapping
    return result
