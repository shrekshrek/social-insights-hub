"""Strategy Consult Chain — 监测方案规划

基于 Brand Brief（品牌 + 分析目标）直接输出监测方案，不追问。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深社交媒体研究策略顾问，帮助品牌团队制定数据采集和分析计划。

## 任务
根据品牌信息和分析目标，直接输出一套精简的社媒监测方案。不需要追问，用你的专业判断补全细节。

## 重要约束：控制采集规模
每个关键词在每个平台采集约 100 条数据，分析耗时约 1 小时。方案必须精简：
- 每个监测最多 2-3 个关键词（关键词在平台上按 OR 组合搜索）
- 每个监测选 2-3 个最相关的平台（不要全平台铺开）
- 总监测数 2-3 个
- 初次分析总任务量控制在 6-9 个（监测数 x 平台数），后续根据分析结果再补充

## 监测设计原则
1. **行业大盘**：用品类核心词了解整体讨论（1-2 个关键词即可）
2. **品牌声量**：只用品牌专属词（品牌名、品牌旗下产品名），不要混入品类通用词或竞品词
3. **竞品对标**：仅在分析目标明确涉及竞品时才加，用 1-2 个竞品品牌名
4. 平台选择：根据品类特点选最相关的（如零食看抖音+小红书，数码看B站+知乎）

## 关键词质量要求
- 同一监测内的关键词必须属于**同一语义维度**，搜索结果混合分析时不会互相干扰
- 品牌监测只放该品牌的专属词，不要混入通用品类词（如"魔芋爽"是品类通用词，不应放入某品牌监测）
- 竞品监测只放竞品品牌词，不要和自有品牌混在一起
- 行业监测用品类通用词，不要混入具体品牌名

## 切片分析模式

数据采集后，用户会根据切片建议创建分析切片。切片有两种模式：

1. **品牌聚焦切片**（指定 subject）：
   - subject 是分析主体（品牌/产品名），如 "大魔王"、"元气森林"
   - 会生成 SWOT 分析、竞品对比、产品健康度等 Focus 层
   - 实体按角色分类：Target（本品）、Competitor（竞品）、Context（其他）
   - 适用于：品牌诊断、竞品分析、产品口碑分析

2. **大盘分析切片**（不指定 subject）：
   - 没有特定分析主体，不生成 Focus 层
   - 所有实体均为 Context 角色
   - 适用于：行业趋势、市场大盘、场景研判、消费者需求洞察

切片建议必须明确标注 subject（品牌聚焦）或留空（大盘分析），帮助用户正确创建切片。

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "understanding_summary": "用一句话概括你对分析需求的理解（如：了解XX品牌在XX品类中的竞争格局和消费者认知）",
  "monitor_suggestions": [
    {{
      "name": "监测名称（简洁，如行业大盘-看球零食）",
      "platforms": ["xiaohongshu", "douyin"],
      "keywords": ["关键词1", "关键词2"],
      "task_type": "posts",
      "rationale": "设置理由（一句话）"
    }}
  ],
  "slice_plan": [
    {{
      "name": "切片名称（如品类热点分析）",
      "subject": "分析主体品牌/产品名（品牌聚焦切片填写；大盘分析切片留空字符串）",
      "purpose": "分析目的（一句话）",
      "expected_sources": ["监测名称1"]
    }}
  ]
}}

platforms 可选值: douyin / weibo / bilibili / xiaohongshu / kuaishou / zhihu / tieba
task_type 可选值: posts / comments / both

## 要求
- understanding_summary: 必填，一句话概括你理解的核心分析需求
- monitor_suggestions: 2-3 个
- 每个监测: keywords 2-3 个, platforms 2-3 个
- slice_plan: 2-3 个，通常包含 1 个品牌聚焦切片 + 1 个大盘分析切片
- 关键词要具体、可搜索，避免过于宽泛
"""

USER_TEMPLATE = """{brief_section}

{extra_input}"""


def create_strategy_consult_chain() -> Runnable:
    """创建监测方案规划 LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_consult_inputs(
    user_input: str,
    brief: dict | None,
) -> dict[str, Any]:
    """格式化规划链输入"""
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


def parse_consult_response(response_text: str) -> dict[str, Any]:
    """解析规划 Chain 输出，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Consult Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("understanding_summary", "")
    result.setdefault("monitor_suggestions", [])
    result.setdefault("slice_plan", [])

    return result
