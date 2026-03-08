"""Strategy Brief Parser Chain — 从上传文档中提取 BrandBrief 结构化信息

支持从 PDF / DOCX / TXT / MD 提取的原始文本，输出可直接用于创建策略的
BrandBrief 字段（brand_name / analysis_goal / constraints）以及建议策略名称。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位社媒策略研究员，负责从用户上传的 Brief 文档中提取关键信息，帮助用户填写社交媒体数据分析策略的创建表单。

## 背景
该表单用于启动一个"社媒数据驱动的品牌策略"项目。后续 AI 将基于这些信息规划监测方案、采集社媒数据、生成品牌洞察与策略建议。因此，提取的字段必须以"用社媒数据解决什么问题"为核心视角，而不是直接描述品牌的营销计划。

## 字段说明

- **strategy_name**: 策略名称建议（简洁，反映品牌+核心分析场景，如"XX品牌夏季营销策略"；若文档中有明确品类/产品，应带入名称）
- **brand_name**: 品牌名或具体产品名（文档中最核心的分析主体；若同时存在品牌名和产品名，优先取更具体的产品名）
- **analysis_goal**: 社媒分析目标（200字以内）
  - 核心问题：从文档的营销目标出发，转化为"需要通过社媒数据了解/验证什么"
  - 应包含：场景/时机背景 + 需要洞察的消费者行为/态度 + 需要了解的竞品/市场状况 + 分析结果如何支持品牌决策
  - 示例转化：营销目标"建立X认知" → 分析目标"了解目标消费者在X场景下的内容偏好与消费行为，分析竞品的内容策略，为品牌找到差异化切入点"
- **constraints**: 补充说明（200字以内，列举文档中明确提到的约束性信息）
  - 优先提取：具体产品/品类名称、主要竞品、目标受众描述、重点关注平台、时间节点/范围、销售/渠道限制
  - 格式建议：用分号分隔各项，如"产品：XX；竞品：A/B；平台：抖音/小红书；时间：XX年XX月"
  - 只提取文档中明确出现的信息，不推断，宁可留空

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "strategy_name": "策略名称建议",
  "brand_name": "品牌/产品名",
  "analysis_goal": "社媒分析目标描述",
  "constraints": "补充说明（可为空字符串）"
}}
"""

USER_TEMPLATE = """以下是用户上传的 Brief 文档内容：

{document_text}

请从中提取 strategy_name、brand_name、analysis_goal、constraints 四个字段。注意将文档中的营销目标转化为社媒数据分析视角的分析目标。"""


def create_strategy_brief_parser_chain() -> Runnable:
    """创建 Brief 解析 Chain"""
    llm = get_llm("chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("human", USER_TEMPLATE),
    ])
    return prompt | llm


def parse_brief_parser_response(response_text: str) -> dict[str, Any]:
    """解析 LLM 输出为结构化字段"""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        result: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Brief Parser Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("strategy_name", "")
    result.setdefault("brand_name", "")
    result.setdefault("analysis_goal", "")
    result.setdefault("constraints", "")

    return result
