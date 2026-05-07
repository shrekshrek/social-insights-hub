"""Strategy Big Idea Chain — 创意层: Big Idea + Content Strategy

brand_strategy 三阶段递进分析的**第 3 层（终层）**：insight → brand_role → big_idea。
基于 insight 层的洞察和 brand_role 层的策略结果，推导创意概念和内容策略。

## 输入上下文（USER_TEMPLATE 的占位符）

- brief_section  : 品牌 Brief，与前两层一致
- research_context_section: 研究问题 + 需求理解摘要
- insight_focused_section : 当前分支聚焦的单一 tension + 相关 opportunities（多分支模式）
- branch_brand_role_section : 当前分支的 brand_role 结果（与该 tension 同源）
- slice_data        : 切片数据（与 insight 层相同来源，但仅提取 big_idea 层所需字段）
                      包含高互动内容特征、KOL 生态、受众画像、topic_aspects

## 关键设计决策

1. **多分支模式（v2026-05+）**
   - 每个 tension 走独立 brand_role + big_idea 路径
   - 本 chain 只看当前分支的 tension + brand_role，不看其他分支
   - 不同分支的 big_idea 应有明显差异化（同品牌不同创意概念由 tension+role 共同决定）

2. **insight + brand_role 同时传入，而非仅传入 brand_role**
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
基于**当前分支**的洞察层 tension（insight_focused_section）+ 该分支的策略层 brand_role
（branch_brand_role_section）结果，推导：
1. **Big Idea（创意概念）**：用一个创意概念统领整个传播。
2. **Content Strategy（内容策略）**：具体的内容支柱和方向。

**多分支约束**：当前分支的 big_idea 应与**该 tension + 该 brand_role 紧密绑定**——
每个 tension 切入下的 big_idea 应有差异化创意视角，不要产出"放之四海皆准"的概念。
其他分支由其他 tensions 走独立路径，**不要去综合或对标其他分支**。

## 分析框架
- Big Idea 应回应当前分支的核心 Social Tension，体现该分支的 Brand Social Role
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
        "strategic_role": "anchor|leverage|conversion|disruption",
        "reference_examples": ["参考案例1", "参考案例2"]
      }}
    ],
    "evidence": [
      {{"type": "content_insight", "description": "高互动内容特征", "source": "<取自切片 _source_label>"}},
      {{"type": "kol_ecosystem", "description": "KOL 生态特征", "source": "<取自切片 _source_label>"}}
    ]
  }}
}}

## evidence.source 来源约束

每条 evidence.source 必须填具体可追溯标签：
- 切片：取切片对象 `_source_label` 字段值（如 `Social Slice #0: ...` / `News Slice #0: ...`）
- 上游层：`insight:tension:<i>` / `brand_role:role` / `brand_role:strategy`
- 行业研究 / 创意参考：`Research: <主题>` / `Creative: <案例名>`

## 要求
- big_idea.statement 简洁、有创意张力，能引起共鸣
- big_idea.tension_echo 必须说明创意如何回应核心矛盾
- content_strategy.pillars 2-4 个，每个含 name + description + strategic_role + reference_examples
- strategic_role 含义：anchor=品牌核心价值长期表达, leverage=借势话题/热点扩散, conversion=推动认知或行为转变, disruption=品类颠覆型内容（至少 1 个支柱须为 disruption）
- reference_examples 基于切片数据中的内容特征（KOL声音风格、实体高频属性）结合品类创意参考推导，可借鉴其他品类形式
- evidence 至少 2 条，类型可选: tension_ref, role_alignment, strategy_ref, content_insight, kol_ecosystem, audience_insight
- 如切片数据中包含 audiences（受众画像），content_strategy 的各支柱需明确面向哪类受众，reference_examples 也要考虑受众匹配度

## 反常规要求（重要）

**Big Idea** 需通过自我检验：先想象这个品类"最平庸的创意概念"是什么，再确认输出与之有本质差异。Big Idea 应该让看到它的人有轻微的"没想到"感，而不是"嗯，对"感。

**Content Strategy** 中至少 1 个支柱的 strategic_role 须为 `disruption`——内容方向挑战该品类的惯常做法，而非在品类既有框架内执行。具体要求：
- 在该支柱的 description 中注明"品类通常如何做 X，我们反其道而行的逻辑是什么"
- reference_examples 可以借鉴**其他品类**的内容形式，不限于本品类 KOL

## 新闻媒体数据使用指南

如果输入包含"新闻媒体视角"数据，请注意：
- 新闻叙事聚类（narratives）揭示媒体如何定义品类议题，Big Idea 可以**借势或颠覆**媒体已有的叙事框架
- 关键引述（key_quotes）中的行业权威发言可作为 Content Strategy 的话题锚点
- Content Strategy 的支柱可考虑"媒体议题再造"——将新闻中的行业话题转化为社媒可传播的消费者语言
- 新闻数据作为补充创意灵感

## 创意版图（creative_references）使用指南

- 创意参考数据来自数英、广告门、SocialBeta 等创意媒体的竞品 Campaign 案例库
- 核心用途：绘制品类**创意版图全貌**，用排除法找到未被竞品占据的**创意白空间**
- 使用逻辑：Brand Role 已确定"我们是谁"→ 创意版图告诉你"竞品已在哪"→ Big Idea 找到"没人去的地方"
- Big Idea 的 statement 应能在创意版图中定位到一个明确的**差异化坐标**
- information_gaps（创意盲点）往往是品类未被尝试的方向，优先考虑作为 Big Idea 方向
- 如 `{{creative_references}}` 段落为空，**正常忽略**，不影响创意推导
"""

USER_TEMPLATE = """{brief_section}

{research_context_section}

{research_findings}

{creative_references}

## 当前分支聚焦的 Tension（Insight 单分支结果）

{insight_focused_section}

## 当前分支的策略层 (Brand Role) 结果

{branch_brand_role_section}

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


def _slim_insight_focused(insight_result: dict, tension_id: int) -> dict:
    """提取指定 tension + 相关 opportunities，剔除 evidence（big_idea 层只需结论）

    多分支模式：仅传当前分支聚焦的 tension，不要把其他 tensions 喂给 LLM。
    """
    tensions = insight_result.get("social_tensions") or []
    opportunities = insight_result.get("brand_opportunities") or []

    if not (0 <= tension_id < len(tensions)):
        # 容错：tension_id 越界时降级为传所有 tensions（避免 KeyError）
        slim_tensions = [
            {
                "statement": t.get("statement"),
                "conventional_wisdom": t.get("conventional_wisdom"),
                "data_reality": t.get("data_reality"),
                "confidence": t.get("confidence"),
            }
            for t in tensions
        ]
        slim_opps = [
            {
                "statement": o.get("statement"),
                "why_non_obvious": o.get("why_non_obvious"),
                "related_tensions": o.get("related_tensions"),
            }
            for o in opportunities
        ]
        return {"social_tensions": slim_tensions, "brand_opportunities": slim_opps}

    selected_tension = tensions[tension_id]
    related_opps = [
        opp for opp in opportunities
        if isinstance(opp, dict)
        and tension_id in (opp.get("related_tensions") or [])
    ]
    if not related_opps and opportunities:
        related_opps = opportunities[:2]

    return {
        "selected_tension_id": tension_id,
        "selected_tension": {
            "statement": selected_tension.get("statement"),
            "conventional_wisdom": selected_tension.get("conventional_wisdom"),
            "data_reality": selected_tension.get("data_reality"),
            "confidence": selected_tension.get("confidence"),
        },
        "related_opportunities": [
            {
                "statement": o.get("statement"),
                "why_non_obvious": o.get("why_non_obvious"),
            }
            for o in related_opps
        ],
        "_note": (
            "本分支基于此特定 tension 推导。其他分支独立处理其他 tensions，"
            "**不要**综合或对标——保持本分支创意视角的独特性。"
        ),
    }


def _slim_brand_role(branch_brand_role: dict) -> dict:
    """brand_role 结论精简：剔除 evidence"""
    role = branch_brand_role.get("brand_social_role") or {}
    strategy = branch_brand_role.get("social_strategy") or {}
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
    selected_tension_id: int,
    branch_brand_role: dict,
    slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    news_slices: list[dict] | None = None,
    slice_refs: list[dict] | None = None,
    news_slice_refs: list[dict] | None = None,
    research_findings: str = "",
    creative_references: str = "",
) -> dict[str, Any]:
    """将单一 tension 分支的 insight + brand_role + 补充数据格式化为 big_idea 输入

    Args:
        insight_result: 完整 insight 输出（含多 tensions），内部提取 selected_tension
        selected_tension_id: 当前分支聚焦的 tension index
        branch_brand_role: 当前分支的 brand_role 结果（与该 tension 同源）
        slice_refs / news_slice_refs: 与 slices / news_slices 同序的 [{id, name}] 列表，
            用于在每个 slice 部分注入 `_source_label`，让 LLM 在 evidence.source 精准引用
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
        ref_name = (
            slice_refs[i].get("name")
            if slice_refs and i < len(slice_refs)
            else None
        )
        slice_label = (ref_name or "").strip()
        part: dict[str, Any] = {
            "slice_index": i,
            "_source_label": (
                f"Social Slice #{i}: {slice_label}" if slice_label else f"Social Slice #{i}"
            ),
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
        # 窗口 50：big_idea 需要更广概念素材做创意；aligned_entities 按 score 降序，
        # top 20 仍以品牌实体为主，扩到 50 覆盖 source>=3 的 Context（成分/技术概念）
        entities = foundation.get("aligned_entities", [])[:50]
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

    news_media_section = _format_news_media_section(news_slices or [], news_slice_refs)

    return {
        "brief_section": brief_section,
        "research_context_section": research_context_section,
        "insight_focused_section": json.dumps(
            _slim_insight_focused(insight_result, selected_tension_id),
            ensure_ascii=False, indent=2,
        ),
        "branch_brand_role_section": json.dumps(
            _slim_brand_role(branch_brand_role), ensure_ascii=False, indent=2,
        ),
        "supplementary_data": json.dumps(
            supplementary_parts, ensure_ascii=False, indent=2
        ),
        "research_findings": research_findings,
        "creative_references": creative_references,
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
