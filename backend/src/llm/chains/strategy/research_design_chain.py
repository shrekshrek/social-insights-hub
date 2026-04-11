"""Strategy Research Design Chain — 多渠道研究设计

接收各渠道的 channel_brief（由 brief_parser_chain 生成），
将研究方向分解为结构化的研究计划：
研究问题 → 数据采集方案（社媒 + 新闻） → 切片蓝图 → 主数据源判定 → 产出类型建议。

## 两条产出路径（核心架构）

本模块不再把三个渠道（social_media / news_media / knowledge_base）视为平级，
而是按"主数据源"划分两条独立产出路径：

| 数据形态 (primary_sources)                  | 产出路径 (output_type) | 后续链                                               |
|----------------------------------------------|-----------------------|------------------------------------------------------|
| 含 social_media (有/无 news_media)           | brand_strategy (默认) | insight → brand_role → big_idea (Tension→Role→Idea)  |
| 仅 news_media（无 social_media）             | market_report (强制)  | agenda_map → landscape → strategic_brief             |

- brand_strategy 的 insight/brand_role/big_idea prompt 结构性依赖消费者声音（KOL/topic_aspects/pains/gains），
  纯新闻无法跑通——因此仅 news_media 时必须强制走 market_report 路径。
- knowledge_base 不是第三条路径，它只作为 insight / brand_role 层的补充背景（RAG 注入 `{market_context}`）。

本链的 `primary_sources` / `output_type` 字段是下游 service.confirm_research
校验的硬性依据，不能由 LLM 自由发挥。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深研究策略顾问，帮助品牌团队设计数据驱动的多渠道研究计划。

## 任务
根据输入的渠道研究方向，输出结构化的研究计划：研究问题 → 数据采集方案 → 切片蓝图 → 主数据源判定 → 产出类型建议。不需要追问，用你的专业判断补全细节。

输入可能包含"社媒渠道研究方向"和/或"新闻渠道研究方向"——**只为输入中出现的渠道生成对应的 data_plan 维度**。如果只有社媒方向则只生成 social_media 维度；如果只有新闻方向则只生成 news_media 维度；两者都有则两种都生成。渠道分配已由上游确认，无需重新评估适配度。

## 产出路径决策表（硬性规则，不可自由发挥）

`primary_sources` 字段枚举本次研究计划实际使用的主数据源（仅看 data_plan 维度），
`output_type` 字段严格按下表推导：

| data_plan 维度组合                      | primary_sources                   | output_type          |
|-----------------------------------------|-----------------------------------|----------------------|
| 同时含 social_media 和 news_media 维度  | ["social_media", "news_media"]    | brand_strategy       |
| 仅含 social_media 维度                  | ["social_media"]                  | brand_strategy       |
| 仅含 news_media 维度                    | ["news_media"]                    | market_report        |

**推导原则**：
- 只要 data_plan 中有任何 social_media 维度，primary_sources 就必须包含 "social_media"
- 只要 data_plan 中有任何 news_media 维度，primary_sources 就必须包含 "news_media"
- 若 primary_sources 包含 social_media → output_type 必须是 brand_strategy（insight/brand_role/big_idea 的 prompt 结构性依赖消费者声音，brand_strategy 是它的承载路径）
- 若 primary_sources 仅有 news_media（不含 social_media）→ output_type 必须是 market_report（insight/brand_role/big_idea 的消费者声音输入为空，跑不出 Social Tension / Brand Social Role / Big Idea，必须走 market_report 路径）

**严禁**：
- 把 knowledge_base 写进 primary_sources（知识库只是 brand_strategy/market_report 三阶段的 RAG 补充背景，不是主数据源）
- 在 data_plan 里只有 news_media 维度的情况下却输出 output_type=brand_strategy
- 在 primary_sources 没有 social_media 的情况下却输出 output_type=brand_strategy

## 研究设计原则

### 1. 先拆问题，再定数据
将分析目标拆解为 2-4 个具体的研究问题，每个问题对应一个数据维度：
- **brand_voice**: 品牌在社媒中的声音（口碑、认知、评价）
- **consumer_voice**: 消费者需求和行为（痛点、场景、偏好）
- **competitive**: 竞品格局（竞品声量、差异化、定位对比）
- **industry**: 行业/品类趋势（大盘热度、新兴话题、消费趋势）

### 2. 数据源与关键词质量

数据采集方案支持两种渠道，每个维度通过 `channel` 字段指定：

**社交媒体（channel = "social_media"，默认）**：
- 需指定 `platforms`（1-2 个，最多 3 个）
- 每个数据维度 1-3 个关键词（关键词在平台上按 OR 组合搜索）
- 品牌维度只用品牌专属词，不混入品类通用词或竞品词
- 竞品维度只放竞品品牌词，不和自有品牌混在一起
- 行业维度用品类通用词，不混入具体品牌名
- **同一维度的关键词必须属于同一赛道/品类**。如果 Brief 涉及多个不同赛道（如"B2B 媒体"和"咨询公司"），必须拆成独立维度分别采集，不要混在同一组关键词中——混合搜索会导致数据噪音，实体提取和竞品对比无法正确归类
- **关键词必须对目标平台有效**——对每个关键词×平台组合，想象一个真实用户在该平台搜索栏输入该词，能否返回足够多的相关内容？如果一个关键词在某平台上大概率搜不到有意义的结果（如在小红书搜"企业采购"、在抖音搜"B2B媒体"），就不要选这个平台。宁可少一个平台也不要采一堆噪音
- 避免过于宽泛的行业热词（如"数字化转型""商业决策"）——这类词在任何平台都返回海量不相关内容，信噪比极低。关键词应精确到能圈定目标讨论群体
- **每条关键词是提交给平台的单一搜索查询**（可包含空格，如"某品牌 用户评价"）。禁止用 `|` 在同一条目内拼接多个备选查询；如需多个备选查询，各自单独列为 keywords 数组的独立条目
- **关键词设计核心原则**：先想清楚"我希望采集到谁在讨论什么"，再反推哪个词能召回这类内容。同一品牌的不同关键词，召回的可能是消费者、求职者、从业者或媒体——目标受众决定关键词类型
- **各平台搜索特点**（关键词格式需适配平台机制）：
  - 知乎：问题型关键词效果最好（"如何选择X""X行业趋势"）；**警惕"品牌名+怎么样"在B2B场景下大量召回求职/雇主评价内容**，适合讨论产品/服务的用户不一定在用这个词提问
  - 微博：事件/热点驱动，品牌名 + 口碑类词（口碑/评价/怎么样）适用于消费品；B2B场景改用新闻/事件类词（品牌名 + 合作/战略/发布）；纯品牌名噪音大
  - 小红书：体验测评导向，"测评/体验/推荐/避坑"类词精准召回消费者真实评价；B2B话题关键词搜索数据质量有限
  - 抖音：简短品牌名 + 场景词/评测词适合大众消费品；B2B话题不推荐
  - B站：内容深度优于抖音，消费品/科技产品用场景词/评测词；专业话题可用行业分析型词（"行业趋势/技术对比"）

**新闻媒体（channel = "news_media"）**：
- **不需要** `platforms` 字段（系统自动通过百度+搜狗+DuckDuckGo 搜索引擎检索）
- 可选启用微信公众号搜索（通过搜狗微信专用入口），适合行业分析、企业深度报道、品牌自媒体内容
- 每个维度 1-2 个关键词，面向搜索引擎优化（与社媒平台搜索习惯不同）
- 关键词应偏向新闻报道视角：品牌动态、行业趋势、市场分析、政策影响等
- 适合场景：品牌媒体曝光监测、行业新闻动态追踪、竞品公关/融资/战略动向、市场趋势的媒体视角
- 不适合场景：消费者个人体验和评价（这是社媒的强项）
- 新闻维度数量控制在 1-2 个，每个维度 1-2 个关键词

### 3. 控制采集规模
每个关键词在每个平台的采集量约 50 条，分析耗时适中。方案必须精简：
- 总维度 2-6 个，按输入的渠道分配：社媒维度 2-4 个（如有社媒方向），新闻维度 1-2 个（如有新闻方向）
- 每个社媒维度 **1-2 个关键词**，最多 3 个（超过 2 个需有充分理由）
- 每个社媒维度选 **1-2 个平台**，最多 3 个（质量优先，宁精不滥）
- 每个新闻维度 **1-2 个关键词**（无需选平台）
- **社媒总任务数 = Σ(各社媒维度关键词数 × 平台数)，目标 8-12 个；生成后自行验算，超过则删减关键词或平台**
- **社媒平台选择必须同时考虑品类特点和关键词适配性**（只能从以下 5 个平台中选择，策略研究不使用 kuaishou / tieba）：
  - 知乎：专业讨论、行业分析、深度评价（适合 B2B、技术、专业领域；B2B 研究首选）
  - 微博：新闻热点、品牌公关、大众舆论（适合有公众讨论度的消费品话题；B2B 仅限舆情事件监测，不适合深度洞察）
  - 小红书：消费体验、生活方式、种草测评（适合 B2C 消费品，**不适合 B2B 专业话题**）
  - 抖音：泛娱乐、生活消费、短视频种草（适合大众消费品，**不适合专业/小众话题**）
  - B站：数码测评、行业深度分析、技术教程（适合科技数码和 **B2B 专业领域**；内容深度优于抖音）

### 4. 切片蓝图
为最终分析规划切片组合，每个切片有两种模式：
- **品牌聚焦**（指定 subject）：含 SWOT、竞品对比，实体分 Target/Competitor/Context
- **大盘分析**（不指定 subject）：无特定主体，适用于行业趋势/消费场景
通常包含 1 个品牌聚焦切片 + 1 个大盘分析切片。
- 品牌聚焦切片的 subject 必须是 Brief 中**用户最关心的分析主体**（通常是 subject 或其核心竞品），而非随意选择数据中出现的某个实体
- 如果 Brief 涉及多个赛道，每个赛道需要独立切片（不同赛道的实体不应混在同一个切片中进行对比）
- 切片的 `source_dimensions` 可以同时引用社媒和新闻维度——系统会按渠道分别创建独立切片（社媒 SocialSlice + 新闻 NewsSlice），最终在 brand_strategy / market_report 两条路径的三层产出中合并两方数据
- 每个切片建议同时引用社媒和新闻维度，让两个渠道的分析结果能在报告中交叉验证
- 纯新闻切片（无社媒维度）和纯社媒切片（无新闻维度）都是允许的

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "understanding_summary": "一句话概括你对分析需求的理解（如 adjust_scope 则注明范围收窄）",
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
      "channel": "social_media",
      "keywords": ["关键词1", "关键词2"],
      "platforms": ["xiaohongshu", "douyin"],
      "rationale": "设置理由（一句话）",
      "question_ids": ["rq1"]
    }},
    {{
      "dimension_name": "品牌媒体报道",
      "channel": "news_media",
      "keywords": ["品牌名 行业动态", "品牌名 市场分析"],
      "rationale": "追踪品牌在新闻媒体中的曝光与行业定位",
      "question_ids": ["rq1"]
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
  "primary_sources": ["social_media"],
  "output_type": "brand_strategy",
  "output_type_rationale": "选择理由（一句话，必须说明为何依据决策表推导出该 output_type）"
}}

channel 可选值: social_media（默认，需 platforms）/ news_media（无 platforms）
platforms 可选值（仅 social_media）: douyin / weibo / bilibili / xiaohongshu / zhihu
dimension 可选值: brand_voice / consumer_voice / competitive / industry
priority 可选值: high / medium / low
mode 可选值: 品牌聚焦 / 大盘分析
primary_sources 可选值（数组，按决策表推导）: social_media / news_media
output_type 可选值（按决策表推导）: brand_strategy / market_report

## 要求
- understanding_summary: 必填
- research_questions: 2-4 个，覆盖所有渠道研究方向中的核心分析目标
- data_plan: 只为输入中出现的渠道生成维度。社媒维度（如有）2-4 个，每个 1-2 关键词 + 1-2 平台，社媒总任务数目标 8-12；新闻维度（如有）1-2 个，每个 1-2 关键词，无 platforms
- data_plan 中每个条目必须包含 `channel` 字段（"social_media" 或 "news_media"）
- slice_blueprint: 2-3 个切片，覆盖所有研究问题
- 每个切片的 source_dimensions 必须引用 data_plan 中存在的 dimension_name
- 每个切片的 serves_questions 必须引用 research_questions 中存在的 id
- 每个 data_plan 条目的 question_ids 必须引用 research_questions 中存在的 id（该维度的数据采集服务哪些研究问题）
- primary_sources: 按上文"产出路径决策表"从 data_plan 的 channel 分布推导，非空数组
- output_type: 按上文"产出路径决策表"从 primary_sources 推导，不得违反决策表
- output_type_rationale: 必须引用决策表说明为何是 brand_strategy 或 market_report
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
    channel_brief: str,
    subject: str = "",
    constraints: str = "",
    news_channel_brief: str = "",
) -> dict[str, Any]:
    """格式化研究设计链输入

    channel_brief 是社媒渠道专属描述（1-2句），提供社媒研究方向。
    news_channel_brief 是新闻渠道专属描述（1-2句），提供新闻研究方向。
    subject / constraints 作为补充上下文，帮助链生成精确的关键词和平台选择。
    """
    lines: list[str] = []

    if channel_brief:
        lines.append(f"## 社媒渠道研究方向\n{channel_brief}")
    else:
        lines.append("## 社媒渠道研究方向\n用户未提供渠道描述，请根据背景信息推断研究方向。")

    if news_channel_brief:
        lines.append(f"\n## 新闻渠道研究方向\n{news_channel_brief}")

    if subject or constraints:
        lines.append("\n## 研究背景（供参考）")
        if subject:
            lines.append(f"研究主体：{subject}")
        if constraints:
            lines.append(f"补充说明：{constraints}")

    extra_input = f"## 用户补充\n{user_input}" if user_input.strip() else ""

    return {
        "brief_section": "\n".join(lines),
        "extra_input": extra_input,
    }


def _derive_primary_sources_and_output_type(
    data_plan: list[dict[str, Any]],
) -> tuple[list[str], str]:
    """根据决策表从 data_plan 的 channel 分布推导 primary_sources + output_type。

    这是硬性规则，不依赖 LLM 的自我申报——LLM 可能写错，后端必须能单独基于 data_plan
    复核，防止 brand_strategy 路径（Insight/Brand Role/Big Idea）在纯新闻数据上跑。
    """
    has_social = any(
        (dp.get("channel") or "social_media") == "social_media"
        for dp in data_plan
    )
    has_news = any((dp.get("channel") == "news_media") for dp in data_plan)

    primary_sources: list[str] = []
    if has_social:
        primary_sources.append("social_media")
    if has_news:
        primary_sources.append("news_media")

    # 决策表：含 social_media → brand_strategy；否则 market_report
    if has_social:
        output_type = "brand_strategy"
    elif has_news:
        output_type = "market_report"
    else:
        # 空 data_plan 的兜底值，实际会被上游校验拦截
        output_type = "brand_strategy"

    return primary_sources, output_type


def parse_research_design_response(response_text: str) -> dict[str, Any]:
    """解析研究设计 Chain 输出，失败时抛出 ValueError

    primary_sources / output_type 不信任 LLM 自报值，统一由 data_plan 的 channel
    分布按决策表推导覆盖——即使 LLM 写错也不影响下游路径判定。
    """
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
    result.setdefault("output_type_rationale", "")

    # 硬性覆盖 primary_sources + output_type（不信任 LLM 自报）
    derived_sources, derived_type = _derive_primary_sources_and_output_type(
        result["data_plan"]
    )
    llm_reported_type = result.get("output_type")
    if llm_reported_type and llm_reported_type != derived_type:
        logger.warning(
            "Research Design Chain 输出 output_type=%s 与决策表推导 %s 不一致，已强制修正",
            llm_reported_type,
            derived_type,
        )
    result["primary_sources"] = derived_sources
    result["output_type"] = derived_type

    return result
