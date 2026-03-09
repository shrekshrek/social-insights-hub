"""Strategy Phase 3 Chain — 创意层: Big Idea + Content Strategy

基于 Phase 1+2 的洞察和策略结果，推导创意概念和内容策略。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深创意策略师，擅长从策略洞察推导创意概念和内容方向。

## 任务
基于已确认的 Phase 1（洞察层）和 Phase 2（策略层）结果，推导：
1. **Big Idea（创意概念）**：用一个创意概念统领整个传播。
2. **Content Strategy（内容策略）**：具体的内容支柱和方向。

## 分析框架
- Big Idea 应回应核心 Social Tension，体现 Brand Social Role
- Content Strategy 应基于高互动内容分析和 KOL 生态
- 每个内容支柱需要具体可执行

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "big_idea": {{
    "statement": "创意概念（一句话）",
    "elaboration": "概念阐释（2-3句）",
    "tension_echo": "这个创意如何回应核心社会矛盾",
    "evidence": [
      {{"type": "tension_ref", "description": "回应了哪个 tension", "source": "phase1:tension:0"}},
      {{"type": "role_alignment", "description": "如何体现品牌角色", "source": "phase2:role"}}
    ]
  }},
  "content_strategy": {{
    "pillars": [
      {{
        "name": "支柱名称",
        "description": "支柱描述和方向",
        "reference_examples": ["参考案例1", "参考案例2"]
      }}
    ],
    "evidence": [
      {{"type": "content_insight", "description": "高互动内容特征", "source": "slice数据"}},
      {{"type": "kol_ecosystem", "description": "KOL 生态特征", "source": "slice数据"}}
    ]
  }}
}}

## 要求
- big_idea.statement 简洁、有创意张力，能引起共鸣
- big_idea.tension_echo 必须说明创意如何回应核心矛盾
- content_strategy.pillars 2-4 个，每个含 name + description + reference_examples
- reference_examples 基于切片数据中的高互动内容特征推导
- evidence 至少 2 条，类型可选: tension_ref, role_alignment, strategy_ref, content_insight, kol_ecosystem, audience_insight
- 如切片数据中包含 audiences（受众画像），content_strategy 的各支柱需明确面向哪类受众，reference_examples 也要考虑受众匹配度
"""

USER_TEMPLATE = """{brief_section}

{consult_summary}

## Phase 1 洞察结果

{phase1_result}

## Phase 2 策略结果

{phase2_result}

## 补充数据（高互动内容 + KOL 生态）

{supplementary_data}"""


def create_strategy_phase3_chain() -> Runnable:
    """创建 Phase 3 (创意层) LLM 链"""
    llm = get_llm(llm_type="reasoner")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_data_for_phase3(
    phase1_result: dict,
    phase2_result: dict,
    slices: list[dict],
    brief: dict | None = None,
    consultation_rounds: list[dict] | None = None,
) -> dict[str, Any]:
    """将 Phase 1+2 结果 + 补充数据格式化为 Phase 3 输入"""
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    consult_summary = ""
    if consultation_rounds:
        latest = consultation_rounds[-1]
        ai_resp = latest.get("ai_response") or {}
        lines = ["## AI 咨询摘要"]
        if ai_resp.get("understanding_summary"):
            lines.append(f"需求理解：{ai_resp['understanding_summary']}")
        slice_plan = ai_resp.get("slice_plan") or []
        if slice_plan:
            lines.append("预期分析切片：")
            for item in slice_plan:
                lines.append(f"- {item.get('name', '')}：{item.get('purpose', '')}")
        consult_summary = "\n".join(lines)

    # 提取高互动内容分析 + KOL 生态
    supplementary_parts = []
    for i, s in enumerate(slices):
        meta = s.get("meta") or {}
        layers = s.get("layers") or {}
        landscape = layers.get("landscape") or {}
        foundation = s.get("foundation") or {}

        subject = meta.get("subject") or None
        part: dict[str, Any] = {
            "slice_index": i,
            "mode": "品牌聚焦" if subject else "大盘分析",
            "subject": subject,
        }

        # KOL 声音（在 landscape 层，由切片 Stage 1 合并）
        kol_voices = landscape.get("kol_voices", [])
        if kol_voices:
            part["kol_voices"] = kol_voices[:10]

        # 注意：不读取 ipa_analysis — LLM 已有 topic_aspects + top_features + SWOT，可自行推理四象限关系

        # Intent 层
        intent = layers.get("intent") or {}

        # 受众画像（内容支柱的受众定向 + reference_examples 匹配度）
        context_analysis = intent.get("context_analysis") or {}
        audiences_raw = context_analysis.get("audiences") or []
        audiences_brief = [
            {
                "label": a.get("label"),
                "heat": a.get("heat"),
                "mentions": a.get("mentions"),
                "preferences": (a.get("preferences") or [])[:3],
            }
            for a in audiences_raw[:8]
            if isinstance(a, dict) and a.get("label")
        ]
        if audiences_brief:
            part["audiences"] = audiences_brief

        # 话题分类维度（Content Strategy 内容支柱的数据源）
        topic_aspects = intent.get("topic_aspects")
        if topic_aspects and isinstance(topic_aspects, list):
            part["topic_aspects"] = [
                {
                    "category": ta.get("category"),
                    "count": ta.get("count"),
                    "avg_sentiment": ta.get("avg_sentiment"),
                    "top_topics": [
                        t.get("name") for t in (ta.get("topics") or [])[:3]
                        if isinstance(t, dict) and t.get("name")
                    ],
                }
                for ta in topic_aspects[:8]
                if isinstance(ta, dict)
            ]

        # 实体 top 特征（高互动内容关联）
        entities = foundation.get("aligned_entities", [])[:20]
        part["top_entities"] = [
            {
                "name": e.get("name"),
                "role": e.get("role"),
                "heat": e.get("heat"),
                "top_features": [
                    f.get("text") for f in (e.get("top_features") or [])[:3]
                    if isinstance(f, dict) and f.get("text")
                ],
            }
            for e in entities
        ]

        supplementary_parts.append(part)

    return {
        "brief_section": brief_section,
        "consult_summary": consult_summary,
        "phase1_result": json.dumps(phase1_result, ensure_ascii=False, indent=2),
        "phase2_result": json.dumps(phase2_result, ensure_ascii=False, indent=2),
        "supplementary_data": json.dumps(
            supplementary_parts, ensure_ascii=False, indent=2
        ),
    }


def parse_phase3_response(response_text: str) -> dict[str, Any]:
    """解析 Phase 3 LLM 输出"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Phase 3 JSON 解析失败: %s...", text[:200])
        return {
            "big_idea": {
                "statement": "",
                "elaboration": "",
                "tension_echo": "",
                "evidence": [],
            },
            "content_strategy": {"pillars": [], "evidence": []},
        }

    # 确保字段存在
    if "big_idea" not in result:
        result["big_idea"] = {
            "statement": "",
            "elaboration": "",
            "tension_echo": "",
            "evidence": [],
        }
    if "content_strategy" not in result:
        result["content_strategy"] = {"pillars": [], "evidence": []}

    return result
