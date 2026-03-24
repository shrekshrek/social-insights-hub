"""Strategy Research Design Chain — 研究设计

基于 Brand Brief 将分析需求分解为结构化的研究计划：
研究问题 → 数据采集方案 → 切片蓝图 → 产出类型建议。
替代原有 strategy_consult_chain。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深社交媒体研究策略顾问，帮助品牌团队设计数据驱动的研究计划。

## 任务
根据品牌信息和分析目标，输出一份结构化的研究计划。不需要追问，用你的专业判断补全细节。

## 研究设计原则

### 1. 先拆问题，再定数据
将分析目标拆解为 2-4 个具体的研究问题，每个问题对应一个数据维度：
- **brand_voice**: 品牌在社媒中的声音（口碑、认知、评价）
- **consumer_voice**: 消费者需求和行为（痛点、场景、偏好）
- **competitive**: 竞品格局（竞品声量、差异化、定位对比）
- **industry**: 行业/品类趋势（大盘热度、新兴话题、消费趋势）

### 2. 关键词质量要求
- 每个数据维度 1-3 个关键词（关键词在平台上按 OR 组合搜索）
- 品牌维度只用品牌专属��，不混入品类通用词或竞品词
- 竞品维度只放竞品品牌词，不和自有品牌混在一起
- 行业维度用品类通用词，不混入具体品牌名
- 关键词要具体、可搜索，避免过于宽泛

### 3. 控制采集规模
每个关键词在每个平台的采集量约 50 条，分析耗时适中。方案必须精简：
- 每个数据维度选 2-3 个最相关的平台（不要全平台铺开）
- 总数据维度 2-4 个
- 初次分析总任务量控制在 4-8 个（维度数 × 平均平台数）
- 平台选择根据品类特点（如零食→抖音+小红书，数码→B站+知乎）

### 4. 切片蓝图
为最终分析规划切片组合，每个切片有两种模式：
- **品牌聚焦**（指定 subject）：含 SWOT、竞品对比，实体分 Target/Competitor/Context
- **大盘分析**（不指定 subject）：无特定主体，适用于行业趋势/消费场景
通常包含 1 个品牌聚焦切片 + 1 个大盘分析切片。

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "understanding_summary": "一句话概括你对分析需求的理解",
  "research_questions": [
    {{
      "id": "rq1",
      "question": "具体的研究问题（如：大魔王在零食品类中的消费者认知如何？）",
      "dimension": "brand_voice",
      "priority": "high"
    }}
  ],
  "data_plan": [
    {{
      "dimension_name": "品牌声量",
      "keywords": ["关键词1", "关键词2"],
      "platforms": ["xiaohongshu", "douyin"],
      "probe_size": 15,
      "full_size": 50,
      "rationale": "设置理由（一句话）"
    }}
  ],
  "slice_blueprint": [
    {{
      "name": "切片名称",
      "mode": "品牌聚焦",
      "subject": "分析主体品牌名（大盘分析留空字符串）",
      "competitors": ["竞品1"],
      "source_dimensions": ["品牌声量"],
      "serves_questions": ["rq1"]
    }}
  ],
  "output_type": "brand_strategy",
  "output_type_rationale": "选择理由（一句话）"
}}

platforms 可选值: douyin / weibo / bilibili / xiaohongshu / kuaishou / zhihu / tieba
dimension 可选值: brand_voice / consumer_voice / competitive / industry
priority 可选值: high / medium / low
mode 可选值: 品牌聚焦 / 大盘分析
output_type 可选值: brand_strategy / insight_report

## 要求
- understanding_summary: 必填
- research_questions: 2-4 个，覆盖 Brief 的核心分析目标
- data_plan: 2-4 个维度，每个维度 1-3 个关键词 + 2-3 个平台
- slice_blueprint: 2-3 个切片，覆盖所有研究问题
- probe_size 统一为 15，full_size 统一为 50（除非用户有特殊需求）
- 每个切片的 source_dimensions 必须引用 data_plan 中存在的 dimension_name
- 每个切片的 serves_questions 必须引用 research_questions 中存在的 id
"""

USER_TEMPLATE = """{brief_section}

{extra_input}"""


def create_research_design_chain() -> Runnable:
    """创建研究设计 LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_research_design_inputs(
    user_input: str,
    brief: dict | None,
) -> dict[str, Any]:
    """格式化研究设计链输入"""
    if brief:
        lines = ["## Brand Brief"]
        if brief.get("brand_name"):
            lines.append(f"品牌：{brief['brand_name']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
        if brief.get("constraints"):
            lines.append(f"补充说明：{brief['constraints']}")
        brief_section = "\n".join(lines)
    else:
        brief_section = "## Brand Brief\n用户未提供 Brief，请根据补充说明推断需求。"

    extra_input = f"## 用户补充\n{user_input}" if user_input.strip() else ""

    return {
        "brief_section": brief_section,
        "extra_input": extra_input,
    }


def parse_research_design_response(response_text: str) -> dict[str, Any]:
    """解析研究设计 Chain 输出，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Research Design Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("understanding_summary", "")
    result.setdefault("research_questions", [])
    result.setdefault("data_plan", [])
    result.setdefault("slice_blueprint", [])
    result.setdefault("output_type", "brand_strategy")
    result.setdefault("output_type_rationale", "")

    return result
