"""Strategy Phase 2 Chain — 策略层: Brand Social Role + Social Strategy

基于 Phase 1 的洞察结果，推导品牌在社交场域的角色定位和传播策略。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深品牌策略师，擅长从数据洞察推导品牌社交策略。

## 任务
基于已确认的 Phase 1 洞察结果（Social Tension + Brand Opportunity），推导：
1. **Brand Social Role（品牌社交角色）**：品牌在社交场域应该扮演什么角色。
2. **Social Strategy（社交策略）**：整体社交传播的策略方向。

## 分析框架
- Brand Social Role 应基于 Opportunity 自然延伸，结合 KOL 声音风格和 Brief 中的品牌定位
- Social Strategy 应考虑平台特征、KOL 声音风格、传播节奏
- 每条结论引用上游 Phase 1 的 opportunity index

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "brand_social_role": {{
    "statement": "品牌应扮演的角色（一句话）",
    "elaboration": "角色阐释（2-3句）",
    "evidence": [
      {{"type": "opportunity_ref", "description": "基于哪个机会推导", "source": "phase1:opportunity:0"}},
      {{"type": "kol_style", "description": "KOL 声音风格支撑", "source": "slice数据"}}
    ]
  }},
  "social_strategy": {{
    "statement": "策略主张（一句话）",
    "core_message": "核心沟通信息",
    "rhythm": "传播节奏建议",
    "evidence": [
      {{"type": "platform_insight", "description": "平台特征支撑", "source": "slice数据"}},
      {{"type": "kol_style", "description": "KOL 声音风格支撑", "source": "slice数据"}}
    ]
  }}
}}

## 要求
- brand_social_role.statement 简洁有力，一句话定义角色
- brand_social_role.elaboration 解释为什么是这个角色，如何体现
- social_strategy.rhythm 包含具体的传播节奏建议（如"日常种草+事件引爆"）
- evidence 至少 2 条，类型可选: opportunity_ref, kol_style, platform_insight, brief_alignment, audience_insight
- 如切片数据中包含 audiences（受众画像），需在 brand_social_role 和 social_strategy 中明确品牌面向的主要目标受众，而非泛泛而谈

## 反陈词约束（重要）

品类中品牌惯用的"默认角色"（如"陪伴者"、"健康倡导者"、"生活方式品牌"）大同小异，毫无差异化价值。

输出 brand_social_role 之前，先问自己：**"这个品类里其他品牌会不会说同样��话？"** 若答案是"会"，则角色定义不够。

推荐角色必须满足：
- 以 Phase 1 中最具反直觉性的 Tension 作为切入点，而非最显眼的那条
- 说明竞品为何无法或不愿占据此角色（结构性原因，不是品牌自夸）
- elaboration 中明确"我们不是 X（品类惯常角色），我们是 Y（数据揭示的差异化角色）"
"""

USER_TEMPLATE = """{brief_section}

{consult_summary}

## Phase 1 洞察结果

{phase1_result}

## 补充数据

{supplementary_data}"""


def create_strategy_phase2_chain() -> Runnable:
    """创建 Phase 2 (策略层) LLM 链"""
    llm = get_llm(llm_type="reasoner")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_data_for_phase2(
    phase1_result: dict,
    slices: list[dict],
    brief: dict | None = None,
    consultation_rounds: list[dict] | None = None,
) -> dict[str, Any]:
    """将 Phase 1 结果 + 补充数据格式化为 Phase 2 输入"""
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

    # 提取 KOL 声音、平台特征
    supplementary_parts = []
    for i, s in enumerate(slices):
        meta = s.get("meta") or {}
        layers = s.get("layers") or {}
        landscape = layers.get("landscape") or {}

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

        # 注意：不读取 time_distribution — 采集样本的时间分布可能误导 LLM 的节奏建议

        # 平台分布（overview 中的去重平台帖子量）
        overview = landscape.get("overview") or {}
        platform_vol = overview.get("unique_platform_volume")
        if platform_vol:
            part["platform_distribution"] = platform_vol

        # 平台 DNA（各实体在不同平台的声量占比，Social Strategy 的平台策略数据源）
        platform_dna = landscape.get("platform_dna")
        if platform_dna and isinstance(platform_dna, list):
            part["platform_dna"] = [
                {
                    "name": d.get("name"),
                    "role": d.get("role"),
                    "platform_shares": d.get("platform_shares"),
                }
                for d in platform_dna[:10]
                if isinstance(d, dict)
            ]

        # 受众画像（Brand Social Role 的目标人群 + Social Strategy 的触达对象）
        intent = layers.get("intent") or {}
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

        supplementary_parts.append(part)

    return {
        "brief_section": brief_section,
        "consult_summary": consult_summary,
        "phase1_result": json.dumps(phase1_result, ensure_ascii=False, indent=2),
        "supplementary_data": json.dumps(
            supplementary_parts, ensure_ascii=False, indent=2
        ),
    }


def parse_phase2_response(response_text: str) -> dict[str, Any]:
    """解析 Phase 2 LLM 输出"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Phase 2 JSON 解析失败: %s...", text[:200])
        return {
            "brand_social_role": {
                "statement": "",
                "elaboration": "",
                "evidence": [],
            },
            "social_strategy": {
                "statement": "",
                "core_message": "",
                "rhythm": "",
                "evidence": [],
            },
        }

    # 确保字段存在
    if "brand_social_role" not in result:
        result["brand_social_role"] = {
            "statement": "",
            "elaboration": "",
            "evidence": [],
        }
    if "social_strategy" not in result:
        result["social_strategy"] = {
            "statement": "",
            "core_message": "",
            "rhythm": "",
            "evidence": [],
        }

    return result
