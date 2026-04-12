"""Strategy Brand Role Chain — 策略层: Brand Social Role + Social Strategy

brand_strategy 三阶段递进分析的**第 2 层**：insight → brand_role → big_idea。
基于 insight 层的洞察结果（tensions + opportunities），推导品牌在社交场域的角色
定位和传播策略，供下游 big_idea 层使用。

## 输入上下文（USER_TEMPLATE 的占位符）

- brief_section  : 品牌 Brief，与 insight 层一致
- research_context_section: 研究问题 + 需求理解摘要
- insight_result : 上游 insight 层输出的完整 JSON（social_tensions + brand_opportunities），
                   由调用方从 strategy.insight_result 序列化后传入

## 关键设计决策

1. **直接传入 insight JSON，而非摘要**
   - LLM 可直接引用 opportunity index（如 insight:opportunity:0）作为 evidence
   - 保留完整 conventional_wisdom / data_reality，brand_role 的角色定义需要"反直觉推理链"的原始依据

2. **"反陈词约束"（Anti-Cliché）是核心约束**
   - 品类默认角色（"陪伴者"、"生活方式品牌"）毫无差异化价值
   - 要求 LLM 自检："这个品类里其他品牌会不会说同样的话？"——若会，则不合格
   - elaboration 必须显式声明"我们不是 X，我们是 Y"，强制输出对比而非自描述
   - 推荐角色须以 insight 层中"最具反直觉性的 Tension"（非最显眼的那条）为切入点

3. **KOL 声音风格作为角色验证锚点**
   - 切片数据中的 KOL 生态信息会经由 slice_data 传递到 brand_role 层
   - 角色定位须与该品类 KOL 生态的实际内容风格可融合，避免策略与执行脱节

4. **模型选用 chat（非 reasoner）**，原因同 insight 层（token budget 限制）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深品牌策略师，擅长从数据洞察推导品牌社交策略。

## 任务
基于已确认的洞察层结果（Social Tension + Brand Opportunity），推导：
1. **Brand Social Role（品牌社交角色）**：品牌在社交场域应该扮演什么角色。
2. **Social Strategy（社交策略）**：整体社交传播的策略方向。

## 分析框架
- Brand Social Role 应基于 Opportunity 自然延伸，结合 KOL 声音风格和 Brief 中的品牌定位
- Social Strategy 应考虑平台特征、KOL 声音风格、传播节奏
- 每条结论引用上游洞察层的 opportunity index

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "brand_social_role": {{
    "statement": "品牌应扮演的角色（一句话）",
    "elaboration": "角色阐释（2-3句），必须包含'我们不是 X（品类惯常角色），我们是 Y（数据揭示的差异化角色）'",
    "evidence": [
      {{"type": "opportunity_ref", "description": "基于哪个机会推导", "source": "insight:opportunity:0"}},
      {{"type": "kol_style", "description": "KOL 声音风格支撑", "source": "slice数据"}}
    ]
  }},
  "social_strategy": {{
    "statement": "策略主张（一句话）",
    "core_message": "核心沟通信息",
    "rhythm": "传播节奏方向（内容类型比例或触发时机类型，不预测具体发布频率）",
    "evidence": [
      {{"type": "platform_insight", "description": "平台特征支撑", "source": "slice数据"}},
      {{"type": "kol_style", "description": "KOL 声音风格支撑", "source": "slice数据"}}
    ]
  }}
}}

## 要求
- brand_social_role.statement 简洁有力，一句话定义角色
- brand_social_role.elaboration 必须包含"我们不是 X（品类惯常角色），我们是 Y（数据揭示的差异化角色）"
- social_strategy.rhythm 基于 KOL 生态风格和平台分布，给出内容节奏方向（如内容类型比例、触发时机类型），不需要预测具体发布频率
- evidence 至少 2 条，类型可选: opportunity_ref, kol_style, platform_insight, brief_alignment, audience_insight
- 如切片数据中包含 audiences（受众画像），需在 brand_social_role 和 social_strategy 中明确品牌面向的主要目标受众，而非泛泛而谈

## 反陈词约束（重要）

品类中品牌惯用的"默认角色"（如"陪伴者"、"健康倡导者"、"生活方式品牌"）大同小异，毫无差异化价值。

输出 brand_social_role 之前，先问自己：**"这个品类里其他品牌会不会说同样的话？"** 若答案是"会"，则角色定义不够。

推荐角色必须满足：
- 以洞察层中最具反直觉性的 Tension 作为切入点，而非最显眼的那条
- 说明竞品为何无法或不愿占据此角色（结构性原因，不是品牌自夸）
- elaboration 中明确"我们不是 X（品类惯常角色），我们是 Y（数据揭示的差异化角色）"

## 新闻媒体数据使用指南

如果输入包含"新闻媒体视角"数据，请注意：
- 新闻叙事聚类（narratives）反映媒体如何定义品类议题和品牌定位，可作为 Brand Social Role 的**外部锚点**——如果媒体已形成某种品牌叙事，角色定位需考虑是顺势强化还是主动打破
- 新闻中的竞品格局（competitive_landscape）提供媒体视角的竞争定位，与社媒 SOV 互为补充
- Social Strategy 可参考新闻中的关键引述（key_quotes）作为行业话语锚点
- 新闻数据作为补充参考，evidence 中标明 source 为"新闻媒体数据"以区分

## 行业研究数据（research_findings）使用指南

- 行业研究数据来自自动化搜索引擎 + 行业报告 + 公开数据的综合分析，代表**专家/行业视角**
- 可为 Brand Social Role 的差异化定位提供**行业事实锚点**——确保角色不违背行业趋势
- 研究数据中的**置信度**标记（high/medium/low）反映证据充分程度
- 如 `{{research_findings}}` 段落为空，**正常忽略**该部分，仅基于洞察层结果和补充数据推导角色
- evidence 中引用研究数据时标明 source 为"行业研究数据"以区分
"""

USER_TEMPLATE = """{brief_section}

{research_context_section}

{research_findings}

## 洞察层 (Insight) 结果

{insight_result}

## 补充数据

{supplementary_data}

{news_media_section}"""


def create_brand_role_chain() -> Runnable:
    """创建 Brand Role (策略层) LLM 链 — brand_strategy 三阶段第 2 层"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_data_for_brand_role(
    insight_result: dict,
    slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    news_slices: list[dict] | None = None,
    research_findings: str = "",
) -> dict[str, Any]:
    """将 insight 结果 + 补充数据格式化为 brand_role 层输入"""
    from src.llm.chains.strategy.brand_strategy.insight_chain import (
        _build_research_context_section,
        _format_news_media_section,
    )

    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    research_context_section = _build_research_context_section(research_design)

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

        # 平台分布（overview 中的去重平台原文量）
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

    news_media_section = _format_news_media_section(news_slices or [])

    return {
        "brief_section": brief_section,
        "research_context_section": research_context_section,
        "insight_result": json.dumps(insight_result, ensure_ascii=False, indent=2),
        "supplementary_data": json.dumps(
            supplementary_parts, ensure_ascii=False, indent=2
        ),
        "research_findings": research_findings,
        "news_media_section": news_media_section,
    }


def parse_brand_role_response(response_text: str) -> dict[str, Any]:
    """解析 Brand Role (策略层) LLM 输出"""
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
                result = json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                pass
            else:
                logger.warning("Brand Role JSON 从 {...} 块中提取成功（原响应有额外内容）")
                return _ensure_brand_role_fields(result)
        logger.error("Brand Role JSON 解析失败: %s...", text[:200])
        return {
            "brand_social_role": {"statement": "", "elaboration": "", "evidence": []},
            "social_strategy": {"statement": "", "core_message": "", "rhythm": "", "evidence": []},
        }

    return _ensure_brand_role_fields(result)


def _ensure_brand_role_fields(result: dict) -> dict[str, Any]:
    """确保必要字段存在"""
    if "brand_social_role" not in result:
        result["brand_social_role"] = {"statement": "", "elaboration": "", "evidence": []}
    if "social_strategy" not in result:
        result["social_strategy"] = {"statement": "", "core_message": "", "rhythm": "", "evidence": []}
    return result
