"""Strategy Consult Chain — 多轮需求咨询

理解 Brand Brief → 追问澄清 → 输出监测建议草案 + 切片规划。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深社交媒体研究策略顾问，帮助品牌团队制定���据采集和分析计划。

## 你的工作流程
1. **理解需求**：阅读 Brand Brief（如有）和用户输入，梳理分析目标
2. **评估信息完整性**：判断信息是否足够制定监测方案（0-1 置信度）
3. **追问澄清**：若信息不完整（confidence < 0.7），提出 1-3 个关键问题
4. **输出建议草案**：若信息充分（confidence >= 0.7），给出监测配置建议和切片规划

## 监测建议 (monitor_suggestions) 格式
每个监测代表一个独立的数据采集任务，应指定：
- `name`: 监测名称（简洁，如"竞品小红书种草声量"）
- `platforms`: 平台列表（可选: douyin/weibo/bilibili/xiaohongshu/kuaishou/zhihu/tieba）
- `keywords`: 核心关键词列表（3-8 个）
- `task_type`: 采集类型（posts/comments/both）
- `rationale`: 设置该监测的理由（一句话）

## 切片规划 (slice_plan) 格式
切片是对采集数据的分析视角，应指定：
- `name`: 切片名称（如"竞品对比分析"）
- `purpose`: 分析目的（一句话）
- `expected_sources`: 预期来源的监测名称列表

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "understanding_summary": "对用户需求的一句话总结",
  "clarification_questions": [
    {{"id": "q1", "question": "具体问题"}}
  ],
  "monitor_suggestions": [
    {{
      "name": "监测名称",
      "platforms": ["xiaohongshu", "douyin"],
      "keywords": ["关键词1", "关键词2"],
      "task_type": "posts",
      "rationale": "设置理由"
    }}
  ],
  "slice_plan": [
    {{
      "name": "切片名称",
      "purpose": "分析目的",
      "expected_sources": ["监测名称1"]
    }}
  ],
  "confidence": 0.8
}}

## 要求
- clarification_questions: 信息充分时为空数组 []；不充分时 1-3 条
- monitor_suggestions: confidence >= 0.7 时至少 1 条，< 0.7 时可为空
- slice_plan: 有 monitor_suggestions 时才填写
- confidence: 0-1 浮点数，反映信息完整度
"""

USER_TEMPLATE = """{brief_section}

{history_section}

## 本轮输入

{user_input}"""


def create_strategy_consult_chain() -> Runnable:
    """创建 Strategy Consult LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_consult_inputs(
    user_input: str,
    brief: dict | None,
    consultation_rounds: list[dict],
    answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """格式化咨询链输入"""
    # Brief 段落
    if brief:
        lines = ["## Brand Brief"]
        if brief.get("brand_name"):
            lines.append(f"品牌：{brief['brand_name']}")
        if brief.get("industry"):
            lines.append(f"行业：{brief['industry']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
        if brief.get("competitors"):
            lines.append(f"竞品：{', '.join(brief['competitors'])}")
        if brief.get("focus_areas"):
            lines.append(f"关注维度：{', '.join(brief['focus_areas'])}")
        if brief.get("time_range"):
            lines.append(f"时间范围：{brief['time_range']}")
        if brief.get("constraints"):
            lines.append(f"特殊要求：{brief['constraints']}")
        brief_section = "\n".join(lines)
    else:
        brief_section = "## Brand Brief\n用户未提供 Brief，请根据用户输入推断需求。"

    # 历史轮次摘要
    history_lines = []
    if consultation_rounds:
        history_lines.append("## 历史对话")
        for r in consultation_rounds:
            round_num = r.get("round_number", "?")
            prev_input = r.get("user_input", "")
            ai_resp = r.get("ai_response") or {}
            summary = ai_resp.get("understanding_summary", "")
            history_lines.append(f"### 第 {round_num} 轮")
            history_lines.append(f"用户: {prev_input}")
            if r.get("answers"):
                for k, v in r["answers"].items():
                    history_lines.append(f"  回答({k}): {v}")
            if summary:
                history_lines.append(f"AI 理解: {summary}")
        history_section = "\n".join(history_lines)
    else:
        history_section = ""

    # 如果本轮有追问回答，附加到 user_input
    full_input = user_input
    if answers:
        answer_lines = ["（本轮追问回答）"]
        for qid, ans in answers.items():
            answer_lines.append(f"  {qid}: {ans}")
        full_input = user_input + "\n" + "\n".join(answer_lines)

    return {
        "brief_section": brief_section,
        "history_section": history_section,
        "user_input": full_input,
    }


def parse_consult_response(response_text: str) -> dict[str, Any]:
    """解析咨询 Chain 输出，失败时抛出 ValueError"""
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

    # 确保必要字段存在
    result.setdefault("understanding_summary", "")
    result.setdefault("clarification_questions", [])
    result.setdefault("monitor_suggestions", [])
    result.setdefault("slice_plan", [])
    result.setdefault("confidence", 0.0)

    return result
