"""Research Agent Brief Parser Chain — 专题研究 brief 解析合流点

`parseBrief(file)` 与 `parseBriefText(text)` 两个入口在 `chain.ainvoke` 这一行
合流到本链。一次 LLM 调用产出三类内容：
- 摄入：title / analysis_goal / research_questions
- 诊断：verdict / recommended_profile / redirect_hint / note
- 方案：keywords / search_angles（按当前选中的 profile 风格生成）

诊断必须独立于 profile 选择——LLM 应就 brief 内容客观判断研究类型适配度，
即使用户当前选错也照常输出建议。方案字段则按当前选中的 profile 风格生成，
让用户即便选错也有产出可见。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm
from src.research_agent.profiles import get_profile

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是专题研究入口的 Brief 解析器。用户在专题研究页面提交一份 Brief，你需要在一次输出中完成三件事：(1) 摄入关键字段，(2) 诊断 brief 与专题研究的适配度，(3) 在用户当前选中的研究类型下生成搜索方案。

## 判断顺序（严格按此顺序，下游依赖上游）

1. **摄入字段**（title / analysis_goal / research_questions）：仅依赖 brief 内容
2. **诊断字段**（verdict / recommended_profile / redirect_hint / note）：**仅依赖 brief 内容**，不受用户当前选中的研究类型影响
3. **方案字段**（keywords / search_angles）：按"用户当前选中的研究类型"风格生成，即使 verdict 非 suitable 也照常生成（让用户至少看到一份产出，是否切换由前端 banner 引导）

## 摄入字段

- `title`：10 个中文字以内的简短研究标题，提炼研究主题的核心对象和目的（例："新能源汽车竞争格局"、"EY 品牌认知渠道"）
- `analysis_goal`：1-2 句话提炼核心研究意图，明确研究对象、核心问题和预期产出（不是 brief 原文复制，是面向研究执行的精炼表述）
- `research_questions`：3-5 个具体可搜索的研究问题，覆盖研究主题的关键子维度。每个问题应具体、可回答、可用搜索引擎找到相关资料

## 诊断字段

专题研究通过定向搜索网络资源，输出**结构化研究报告**——聚合多份权威/案例来源的发现，按研究问题组织成可引用的综述。它**不是**消费者驱动的策略提案、**不是**实时监测、**不是**内部数据分析。

研究类型有两种（按"产物形态需要的素材类型"区分，不按"主题词面"区分）：

- `industry`：产物是行业研报。素材来源于行业报告/白皮书/政策文件/权威机构数据，用于回答市场规模、产业结构、竞争格局结构性、政策趋势、技术原理、产业链等结构性问题。
- `creative`：产物是案例/灵感汇编。素材来源于数英、广告门、SocialBeta 等创意媒体的 Campaign 案例、获奖作品、品牌叙事，**不论用户的目的是研究历史脉络还是借鉴执行思路**。涉及活动执行、KOL 投放参考、视觉风格、传播玩法、品牌内容方向等具体素材诉求时归此类。

判定流程（按优先级，命中即停）：

1. **想要策略框架的战略层产物**（campaign_strategy / market_report / full_strategy 任一）→ `verdict=not_suitable` + `redirect_hint=strategy`
   信号：brief 明确诉求是品牌策略、品牌定位、Insight、Brand Role、Big Idea、Agenda Map、Landscape 竞争格局、Strategic Brief 战略简报、传播方向策略等"应该怎么做"产物。
2. **想要短期监测/复盘** → `verdict=not_suitable` + `redirect_hint=monitor_social` 或 `monitor_news`
   信号：核心动词是监测/追踪/复盘/快照/简报，时间窗为日/周/月级，产出诉求是"看到了什么"。主要看消费者声音 → `monitor_social`；主要看媒体报道 → `monitor_news`。
3. **Brief 信息不足** → `verdict=partial`
   信号：研究主题模糊、诉求不清晰，无法判断该用哪种类型。
4. **以上都不命中** → `verdict=suitable`，给出 `recommended_profile`：
   - 关心结构性背景（市场/政策/技术/竞争结构）→ `industry`
   - 关心具体素材/案例/创意/执行参考 → `creative`
   - 真两者都沾边时按"用户最终拿到产物后会怎么用"裁决：用来读懂行业 → industry；用来做出方案/视觉/活动 → creative

字段约束（强制）：
- `verdict=suitable` → `recommended_profile` 非空，`redirect_hint` 必须为空
- `verdict=not_suitable` → `redirect_hint` 非空，`recommended_profile` 必须为空
- `verdict=partial` → `recommended_profile` 与 `redirect_hint` 均为空
- `note`：始终非空，1-2 句中文说明判断依据

诊断不受用户当前选中的研究类型影响——你的职责是就 brief 内容做客观判断，用户选错了也照样指出。

## 方案字段（按当前选中的研究类型）

用户当前选中的研究类型是：`{current_profile}`。

按下述规则生成 5-8 个 `keywords` 和 2-4 个 `search_angles`，**即使诊断判定不适配也照常按当前选中类型生成**（让用户至少有产出可看，是否切换由 banner 引导）：

{planner_context}

## 输出格式

只输出 JSON，不要 markdown 代码块或额外文字：
{{
  "title": "...",
  "analysis_goal": "...",
  "research_questions": ["..."],
  "verdict": "suitable / partial / not_suitable",
  "recommended_profile": "industry / creative / \\"\\"",
  "redirect_hint": "strategy / monitor_social / monitor_news / \\"\\"",
  "note": "...",
  "keywords": ["..."],
  "search_angles": ["..."]
}}
"""

USER_TEMPLATE = """以下是用户提交的 Brief 内容：

{brief}

请按 SYSTEM 中的"判断顺序"输出 JSON。"""


_VALID_VERDICTS = {"suitable", "partial", "not_suitable"}
_VALID_PROFILES = {"industry", "creative"}
_VALID_HINTS = {"strategy", "monitor_social", "monitor_news"}
_MAX_BRIEF_CHARS = 10000


def create_brief_parser_chain(profile_name: str | None) -> Runnable:
    """创建 brief 解析链。profile_name 影响方案字段的生成规则与 note 措辞。"""
    profile = get_profile(profile_name)
    llm = get_llm("chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_TEMPLATE),
            ("human", USER_TEMPLATE),
        ]
    ).partial(
        current_profile=profile.name,
        planner_context=profile.planner_context,
    )
    return prompt | llm


def parse_brief_response(response_text: str) -> dict[str, Any]:
    """解析 LLM JSON 输出 + 强制字段一致性约束"""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        result: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Brief Parser Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("title", "")
    result.setdefault("analysis_goal", "")
    if not isinstance(result.get("research_questions"), list):
        result["research_questions"] = []
    if not isinstance(result.get("keywords"), list):
        result["keywords"] = []
    if not isinstance(result.get("search_angles"), list):
        result["search_angles"] = []

    verdict = result.get("verdict", "")
    if verdict not in _VALID_VERDICTS:
        logger.warning("Brief Parser 返回未知 verdict=%s，回退至 suitable", verdict)
        verdict = "suitable"

    recommended = (result.get("recommended_profile") or "").strip()
    if recommended and recommended not in _VALID_PROFILES:
        recommended = ""

    hint = (result.get("redirect_hint") or "").strip()
    if hint and hint not in _VALID_HINTS:
        hint = ""

    if verdict == "suitable":
        if not recommended:
            recommended = "industry"
        hint = ""
    elif verdict == "not_suitable":
        recommended = ""
        if not hint:
            hint = "strategy"
    else:
        recommended = ""
        hint = ""

    result["verdict"] = verdict
    result["recommended_profile"] = recommended
    result["redirect_hint"] = hint
    result["note"] = (result.get("note") or "").strip()

    return result


async def parse_brief(brief: str, profile_name: str | None) -> dict[str, Any]:
    """异步解析 brief，单链合流点。空内容返回 partial verdict；LLM 失败抛 ValueError"""
    if not brief or not brief.strip():
        return {
            "title": "",
            "analysis_goal": "",
            "research_questions": [],
            "verdict": "partial",
            "recommended_profile": "",
            "redirect_hint": "",
            "note": "Brief 内容为空，请补充研究主题或上传文档。",
            "keywords": [],
            "search_angles": [],
        }

    chain = create_brief_parser_chain(profile_name)
    response = await chain.ainvoke({"brief": brief[:_MAX_BRIEF_CHARS]})
    text = response.content if hasattr(response, "content") else str(response)
    return parse_brief_response(text)
