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
根据品牌信息和分析目标，**先评估课题适配度，再输出结构化研究计划**。不需要追问，用你的专业判断补全细节。

## 第零步：课题适配度评估

在设计研究计划之前，先评估该课题是否适合当前系统能力。

当前系统能力：
- 7 个中国社交媒体平台的关键词搜索采集（抖音 / 小红书 / 微博 / B站 / 快手 / 知乎 / 贴吧）
- 每平台每关键词 50-100 条原文 + 评论
- LLM 分析：实体提取、情感分析、话题聚类、KOL 识别、竞品对比

当前系统**不具备**的能力：
- 微信公众号 / 微信群搜索
- 通用网页 / 新闻搜索
- 行业数据库 / 报告检索
- 线下访谈 / 问卷调研

评估维度：
1. 目标人群是否活跃在上述 7 个平台上？（B2C 消费者 vs B2B 决策者）
2. 相关讨论是否发生在公开社媒上？（vs 微信群、行业会议、内部渠道等封闭场景）
3. 社媒数据能回答 Brief 中多大比例的核心问题？

根据评估结果决定 recommendation：
- "proceed": 课题与社媒数据高度契合（fit_score >= 0.7），正常输出完整方案
- "adjust_scope": 社媒能回答部分问题（0.3 <= fit_score < 0.7），收窄研究范围到社媒可回答的部分，明确指出盲区
- "not_recommended": 社媒数据基本无法回答核心问题（fit_score < 0.3），给出替代建议，data_plan 和 slice_blueprint 可为空

当 recommendation = "adjust_scope" 时：
- research_questions 只包含社媒数据能回答的问题
- understanding_summary 中注明研究范围已收窄及原因
- social_can_tell / social_cannot_tell 帮助用户理解边界

## 研究设计原则

### 1. 先拆问题，再定数据
将分析目标拆解为 2-4 个具体的研究问题，每个问题对应一个数据维度：
- **brand_voice**: 品牌在社媒中的声音（口碑、认知、评价）
- **consumer_voice**: 消费者需求和行为（痛点、场景、偏好）
- **competitive**: 竞品格局（竞品声量、差异化、定位对比）
- **industry**: 行业/品类趋势（大盘热度、新兴话题、消费趋势）

### 2. 关键词质量要求
- 每个数据维度 1-3 个关键词（关键词在平台上按 OR 组合搜索）
- 品牌维度只用品牌专属词，不混入品类通用词或竞品词
- 竞品维度只放竞品品牌词，不和自有品牌混在一起
- 行业维度用品类通用词，不混入具体品牌名
- **同一维度的关键词必须属于同一赛道/品类**。如果 Brief 涉及多个不同赛道（如"B2B 媒体"和"咨询公司"），必须拆成独立维度分别采集，不要混在同一组关键词中——混合搜索会导致数据噪音，实体提取和竞品对比无法正确归类
- **关键词必须对目标平台有效**——对每个关键词×平台组合，想象一个真实用户在该平台搜索栏输入该词，能否返回足够多的相关内容？如果一个关键词在某平台上大概率搜不到有意义的结果（如在小红书搜"企业采购"、在抖音搜"B2B媒体"），就不要选这个平台。宁可少一个平台也不要采一堆噪音
- 避免过于宽泛的行业热词（如"数字化转型""商业决策"）——这类词在任何平台都返回海量不相关内容，信噪比极低。关键词应精确到能圈定目标讨论群体

### 3. 控制采集规模
每个关键词在每个平台的采集量约 50 条，分析耗时适中。方案必须精简：
- 每个数据维度选 1-3 个最相关的平台（质量优先于覆盖面，宁精不滥）
- 总数据维度 2-4 个
- 初次分析总任务量控制在 4-10 个（每个关键词×每个平台 = 1 个独立任务）
- **平台选择必须同时考虑品类特点和关键词适配性**（优先从以下 5 个主力平台中选择）：
  - 知乎：专业讨论、行业分析、深度评价（适合 B2B、技术、专业领域）
  - 微博：新闻热点、品牌公关、大众舆论（适合有公众讨论度的话题）
  - 小红书：消费体验、生活方式、种草测评（适合 B2C 消费品，**不适合 B2B 专业话题**）
  - 抖音：泛娱乐、生活消费、短视频种草（适合大众消费品，**不适合专业/小众话题**）
  - B站：数码测评、学习教程、年轻社区（适合科技数码、教育内容）

### 4. 切片蓝图
为最终分析规划切片组合，每个切片有两种模式：
- **品牌聚焦**（指定 subject）：含 SWOT、竞品对比，实体分 Target/Competitor/Context
- **大盘分析**（不指定 subject）：无特定主体，适用于行业趋势/消费场景
通常包含 1 个品牌聚焦切片 + 1 个大盘分析切片。
- 品牌聚焦切片的 subject 必须是 Brief 中**用户最关心的分析主体**（通常是 brand_name 或其核心竞品），而非随意选择数据中出现的某个实体
- 如果 Brief 涉及多个赛道，每个赛道需要独立切片（不同赛道的实体不应混在同一个切片中进行对比）

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "feasibility": {{
    "fit_score": 0.8,
    "recommendation": "proceed",
    "rationale": "一句话说明评估理由",
    "social_can_tell": ["社媒数据能回答的问题1", "..."],
    "social_cannot_tell": ["社媒数据无法回答的问题1", "..."],
    "complementary_methods": ["建议补充的研究方法1", "..."]
  }},
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

platforms 可选值（优先前 5 个）: douyin / weibo / bilibili / xiaohongshu / zhihu / kuaishou / tieba
dimension 可选值: brand_voice / consumer_voice / competitive / industry
priority 可选值: high / medium / low
mode 可选值: 品牌聚焦 / 大盘分析
output_type 可选值: brand_strategy / insight_report

## 要求
- feasibility: 必填，先评估再规划
- understanding_summary: 必填
- research_questions: 2-4 个，覆盖 Brief 的核心分析目标（adjust_scope 时只包含社媒可回答的）
- data_plan: 2-4 个维度，每个维度 1-3 个关键词 + 2-3 个平台
- slice_blueprint: 2-3 个切片，覆盖所有研究问题
- probe_size 统一为 20，full_size 统一为 50（除非用户有特殊需求）
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

    # feasibility 兜底
    feasibility = result.get("feasibility")
    if not isinstance(feasibility, dict):
        result["feasibility"] = {
            "fit_score": 0.5,
            "recommendation": "proceed",
            "rationale": "",
            "social_can_tell": [],
            "social_cannot_tell": [],
            "complementary_methods": [],
        }
    else:
        feasibility.setdefault("fit_score", 0.5)
        feasibility.setdefault("recommendation", "proceed")
        feasibility.setdefault("rationale", "")
        feasibility.setdefault("social_can_tell", [])
        feasibility.setdefault("social_cannot_tell", [])
        feasibility.setdefault("complementary_methods", [])

    return result
