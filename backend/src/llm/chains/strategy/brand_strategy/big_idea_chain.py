"""Strategy Big Idea Chain — 创意层: Big Idea + Content Strategy

brand_strategy 三阶段递进分析的**第 3 层（终层）**：insight → brand_role → big_idea。
基于 insight 层的洞察和 brand_role 层的策略结果，推导创意概念和内容策略。

## 输入上下文（USER_TEMPLATE 的占位符）

- brief_section  : 品牌 Brief，与前两层一致
- research_context_section: 研究问题 + 需求理解摘要
- insight_result    : insight 层完整 JSON（social_tensions + brand_opportunities）
- brand_role_result : brand_role 层完整 JSON（brand_social_role + social_strategy）
- slice_data        : 切片数据（与 insight 层相同来源，但仅提取 big_idea 层所需字段）
                      包含高互动内容特征、KOL 生态、受众画像、topic_aspects

## 关键设计决策

1. **insight + brand_role 同时传入，而非仅传入 brand_role**
   - Big Idea 需直接"回应核心 Social Tension"，evidence 引用 insight:tension:X
   - 仅传入 brand_role 会导致 LLM 产出的 Big Idea 与原始矛盾脱节，只是策略的复述

2. **"反常规要求"约束 Big Idea 和 Content Strategy**
   - Big Idea: 须先想象"最平庸的创意概念"，再确认与之有本质差异（"没想到"感而非"嗯对"感）
   - Content Strategy: 必须包含 ≥1 个"品类颠覆型支柱"，要求说明品类惯常做法及反向逻辑
   - reference_examples 可跨品类借鉴，防止 LLM 只在本品类 KOL 案例内循环

3. **topic_aspects 字段的作用**
   - 按主题类别聚合的宏观分布（mention_count / sentiment / representative_topics）
   - 用于发现"某整类话题情感集体偏负"等品类级模式，是单话题视图看不到的维度
   - 为 Content Strategy 的支柱选题提供分类级依据，而非仅依赖高频话题列表

4. **JSON 解析降级策略（重要）**
   - chat 模型偶尔在 JSON 前后输出额外说明文字
   - 解析逻辑：先尝试全文 json.loads，失败后用 text.find("{") / text.rfind("}") 提取块
   - 两次均失败才返回 fallback（空字符串 / 空列表）并记录 ERROR 日志
   - 避免因模型格式抖动导致整个 big_idea 结果清空

5. **模型选用 chat（非 reasoner）**
   - big_idea 层输入最大（含 insight + brand_role 全量 JSON + 切片数据）
   - reasoner 在此输入规模下思考 token 消耗殆尽，JSON 输出截断
   - 早期版本因此出现 Big Idea 只显示"（"的问题（截断后 JSON 解析失败返回空字符串）
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深创意策略师，擅长从策略洞察推导创意概念和内容方向。

## 任务
基于已确认的洞察层（insight）和策略层（brand_role）结果，推导：
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
      {{"type": "tension_ref", "description": "回应了哪个 tension", "source": "insight:tension:0"}},
      {{"type": "role_alignment", "description": "如何体现品牌角色", "source": "brand_role:role"}}
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
- reference_examples 基于切片数据中的内容特征（KOL声音风格、实体高频属性）结合品类创意参考推导，可借鉴其他品类形式
- evidence 至少 2 条，类型可选: tension_ref, role_alignment, strategy_ref, content_insight, kol_ecosystem, audience_insight
- 如切片数据中包含 audiences（受众画像），content_strategy 的各支柱需明确面向哪类受众，reference_examples 也要考虑受众匹配度

## 反常规要求（重要）

**Big Idea** 需通过自我检验：先想象这个品类"最平庸的创意概念"是什么，再确认输出与之有本质差异。Big Idea 应该让看到它的人有轻微的"没想到"感，而不是"嗯，对"感。

**Content Strategy** 中的支柱须包含至少 1 个"品类颠覆型支柱"——内容方向挑战该品类的惯常做法，而非在品类既有框架内执行。具体要求：
- 在该支柱的 description 中注明"品类通常如何做 X，我们反其道而行的逻辑是什么"
- reference_examples 可以借鉴**其他品类**的内容形式，不限于本品类 KOL

## 新闻媒体数据使用指南

如果输入包含"新闻媒体视角"数据，请注意：
- 新闻叙事聚类（narratives）揭示媒体如何定义品类议题，Big Idea 可以**借势或颠覆**媒体已有的叙事框架
- 关键引述（key_quotes）中的行业权威发言可作为 Content Strategy 的话题锚点
- Content Strategy 的支柱可考虑"媒体议题再造"——将新闻中的行业话题转化为社媒可传播的消费者语言
- 新闻数据作为补充创意灵感，evidence 中标明 source 为"新闻媒体数据"以区分
"""

USER_TEMPLATE = """{brief_section}

{research_context_section}

{research_findings}

## 洞察层 (Insight) 结果

{insight_result}

## 策略层 (Brand Role) 结果

{brand_role_result}

## 补充数据（高互动内容 + KOL 生态）

{supplementary_data}

{news_media_section}"""


def create_big_idea_chain() -> Runnable:
    """创建 Big Idea (创意层) LLM 链 — brand_strategy 三阶段第 3 层"""
    # 创意生成任务不需要 CoT 推理，chat 模型 token 预算更稳定
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def _slim_insight(insight_result: dict) -> dict:
    """insight 结论精简：剔除 evidence（big_idea 层只需结论，不需要推理链）"""
    tensions = [
        {
            "statement": t.get("statement"),
            "conventional_wisdom": t.get("conventional_wisdom"),
            "data_reality": t.get("data_reality"),
            "confidence": t.get("confidence"),
        }
        for t in (insight_result.get("social_tensions") or [])
    ]
    opportunities = [
        {
            "statement": o.get("statement"),
            "why_non_obvious": o.get("why_non_obvious"),
            "related_tensions": o.get("related_tensions"),
        }
        for o in (insight_result.get("brand_opportunities") or [])
    ]
    return {"social_tensions": tensions, "brand_opportunities": opportunities}


def _slim_brand_role(brand_role_result: dict) -> dict:
    """brand_role 结论精简：剔除 evidence"""
    role = brand_role_result.get("brand_social_role") or {}
    strategy = brand_role_result.get("social_strategy") or {}
    return {
        "brand_social_role": {
            "statement": role.get("statement"),
            "elaboration": role.get("elaboration"),
        },
        "social_strategy": {
            "statement": strategy.get("statement"),
            "core_message": strategy.get("core_message"),
            "rhythm": strategy.get("rhythm"),
        },
    }


def format_data_for_big_idea(
    insight_result: dict,
    brand_role_result: dict,
    slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    news_slices: list[dict] | None = None,
    research_findings: str = "",
) -> dict[str, Any]:
    """将 insight + brand_role 结果 + 补充数据格式化为 big_idea 层输入

    insight / brand_role 只传结论字段，剔除 evidence 数组——big_idea 层只需知道
    「得出了什么结论」，不需要重新审阅推理链，可节省约 30-50% 输入 token。
    """
    from src.llm.chains.strategy.brand_strategy.insight_chain import (
        _build_research_context_section,
        _format_news_media_section,
    )

    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    research_context_section = _build_research_context_section(research_design)

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
                    "mention_count": ta.get("mention_count"),
                    "sentiment": ta.get("sentiment"),
                    "representative_topics": (ta.get("representative_topics") or [])[:4],
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

    news_media_section = _format_news_media_section(news_slices or [])

    return {
        "brief_section": brief_section,
        "research_context_section": research_context_section,
        "insight_result": json.dumps(_slim_insight(insight_result), ensure_ascii=False, indent=2),
        "brand_role_result": json.dumps(_slim_brand_role(brand_role_result), ensure_ascii=False, indent=2),
        "supplementary_data": json.dumps(
            supplementary_parts, ensure_ascii=False, indent=2
        ),
        "research_findings": research_findings,
        "news_media_section": news_media_section,
    }


def parse_big_idea_response(response_text: str) -> dict[str, Any]:
    """解析 Big Idea (创意层) LLM 输出"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        # 兜底：从响应中找最外层 {...} 块
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
            else:
                logger.warning("Big Idea JSON 从 {...} 块中提取成功（原响应有额外内容）")
                # 跳到字段补全逻辑
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
        logger.error("Big Idea JSON 解析失败，原始响应前 500 字符: %s", text[:500])
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
