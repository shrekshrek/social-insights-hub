"""Strategy Brief Parser Chain — 从上传文档中提取 BrandBrief 结构化信息

支持从 PDF / DOCX / TXT / MD 提取的原始文本，输出可直接用于创建策略的
BrandBrief 字段（subject / analysis_goal / constraints）以及建议策略名称。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位数据策略分析师，负责从用户上传的 Brief 文档中提取关键信息，并判断哪些数据采集渠道适合回答这份 brief 提出的研究问题。

## 背景
该表单用于启动一个"多源数据驱动的策略研究"项目。你的输出分为两部分：
1. 结构化提取 brief 的核心字段
2. 渠道分发判断：评估本 brief 适合走哪些数据采集渠道，以及每个渠道能/不能解决什么问题

## 字段说明

### 基础字段

- **strategy_name**: 策略名称建议（简洁，反映研究主体+核心分析场景）

- **subject**: 研究主体（数据采集和分析的核心聚焦对象）
  - **核心问题**：如果要搜索数据，最主要的研究对象是谁？
  - **三种典型情境**：
    - 品牌/产品洞察 → subject = 该品牌或产品名（如"小米SU7"、"元气森林"）
    - 用户行为/决策研究 → subject = 行为主体（如"职场新人"、"中国B2B企业"），提到的品牌放入 constraints
    - 品类竞争格局 → subject = 品类名（如"新能源汽车"、"功能性饮料"）
  - **辨别括号里的内容**：
    - "分析某品牌（如：小米）的用户口碑" → subject = "小米"
    - "了解用户如何选择某类服务（如：EY、麦肯锡）" → subject = 用户群体，括号是示例竞品
    - 判断依据：brief 的核心动词是"分析[某品牌]"还是"了解[某群体]的行为"
  - 若同时涉及集团和子品牌，取更具体的子品牌名

- **analysis_goal**: 整体研究目标（200字以内，综合所有渠道的视角）
  - 从文档的研究意图出发，描述"通过数据分析需要了解/验证什么"
  - 应包含：场景背景 + 需要洞察的核心问题 + 分析结果如何支持决策

- **constraints**: 补充说明（200字以内）
  - 优先提取：具体产品/品类名称、主要竞品、目标受众、时间节点/范围、已有资料来源
  - 格式：用分号分隔，如"产品：XX；竞品：A/B；时间：XX年XX月"
  - 只提取文档中明确出现的信息，不推断，宁可留空

### channel_plan（渠道分发判断）

针对每种数据渠道，评估本 brief 的适合度。各渠道特性：
- **social_media**（社交媒体）：覆盖小红书、抖音、微博、知乎、B站、快手、贴吧（不含脉脉、LinkedIn、Twitter 等平台）；适合消费者情感/口碑/行为观察、品牌认知研究、趋势话题分析；B2B/专业领域同样适用——知乎有大量企业决策者的专业讨论，B站有深度行业分析
- **knowledge_base**（市场知识库）：平台内置公共数据（CNNIC报告、国家统计局指标、政策文件）+ 用户上传的内部文档（研报、历史资料）；适合需要市场数据背景、行业趋势参考、内部资料佐证的场景
- **news_media**（新闻媒体）：通过多渠道搜索引擎（百度+搜狗+DuckDuckGo）检索公开新闻报道、行业资讯、媒体评论，可选启用微信公众号搜索（搜狗微信入口）获取行业深度分析和品牌自媒体内容；适合行业动态与竞品动向追踪、品牌舆情与 PR 效果评估、市场趋势与政策变化的媒体视角分析、专业自媒体和行业 KOL 深度观点

每个渠道条目包含：
- `type`: 渠道类型
- `available`: 是否当前可用（social_media=true，knowledge_base=true，news_media=true）
- `solvable`: 该渠道能解决 brief 中的哪些问题（1-3条，简短描述）
- `unsolvable`: 该渠道对本 brief 有哪些明显局限（0-2条；若无明显局限则为空数组）
- `channel_brief`: 针对该渠道的定制化研究描述（1-2句；聚焦该渠道能做的部分，是该渠道 research_design 的输入）

**规则**：
- 按需分配渠道，只输出与本 brief 相关的渠道，若某渠道完全不适合则不输出该条目
- 社媒渠道覆盖面广（消费品在小红书/抖音，专业/B2B 话题在知乎/B站），大多数研究主题都适用，但不强制——根据 brief 实际需要判断

### platform_verdict（当前平台支持度）

当前平台已覆盖社交媒体、新闻媒体、市场知识库三大数据源，能满足大多数消费者洞察、品牌策略、行业分析类研究。基于 channel_plan 中各渠道的综合覆盖度，判断能否满足本 brief：
- **sufficient**：三渠道组合基本能回答 brief 的核心研究问题，可直接推进
- **partial**：能回答部分核心问题，但 brief 涉及平台无法触达的数据类型（如企业内部 CRM/ERP 数据、金融终端数据、线下调研等），需用户知晓局限后决定是否推进
- **insufficient**：brief 的核心问题主要依赖平台无法提供的数据源，该研究类型不适合当前平台

`platform_note`：1-2 句话说明判断依据——当前渠道能覆盖什么、缺失什么关键维度。

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "strategy_name": "策略名称建议",
  "subject": "研究主体",
  "analysis_goal": "整体研究目标描述",
  "constraints": "补充说明（可为空字符串）",
  "platform_verdict": "sufficient",
  "platform_note": "社交媒体数据可支撑消费者情感与口碑分析，能覆盖本研究的核心问题。",
  "channel_plan": [
    {{
      "type": "social_media",
      "available": true,
      "solvable": ["用户对品牌的情感态度", "消费者讨论的核心话题"],
      "unsolvable": ["市场规模等结构化行业数据"],
      "channel_brief": "聚焦[subject]在社媒平台的用户讨论，分析消费者情感倾向与核心话题..."
    }},
    {{
      "type": "knowledge_base",
      "available": true,
      "solvable": ["行业市场数据背景", "政策趋势参考"],
      "unsolvable": ["实时用户互动数据"],
      "channel_brief": "检索知识库中与[subject]相关的行业报告和市场数据，补充宏观背景..."
    }},
    {{
      "type": "news_media",
      "available": true,
      "solvable": ["行业动态与竞品媒体曝光", "品牌相关新闻报道的舆论基调"],
      "unsolvable": ["非公开的企业内部信息"],
      "channel_brief": "搜索[subject]及竞品相关的新闻报道与行业资讯，分析媒体视角下的市场动态与品牌形象..."
    }}
  ]
}}
"""

USER_TEMPLATE = """以下是用户上传的 Brief 文档内容：

{document_text}

请提取 strategy_name、subject、analysis_goal、constraints 字段，并完成渠道分发判断（channel_plan）。"""


def create_strategy_brief_parser_chain() -> Runnable:
    """创建 Brief 解析 Chain"""
    llm = get_llm("chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("human", USER_TEMPLATE),
    ])
    return prompt | llm


def parse_brief_parser_response(response_text: str) -> dict[str, Any]:
    """解析 LLM 输出为结构化字段"""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        result: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Brief Parser Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("strategy_name", "")
    result.setdefault("subject", "")
    result.setdefault("analysis_goal", "")
    result.setdefault("constraints", "")
    result.setdefault("platform_verdict", "partial")
    result.setdefault("platform_note", "")
    if not result.get("channel_plan"):
        result["channel_plan"] = [{
            "type": "social_media",
            "available": True,
            "solvable": ["用户情感态度与口碑分析"],
            "unsolvable": [],
            "channel_brief": "分析相关社媒平台的用户讨论，了解消费者真实反馈。",
        }]

    return result
