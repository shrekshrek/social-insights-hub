#!/usr/bin/env python3
"""项目级快照三报告 Chain（Landscape/Topic/Focus）

输出统一为 JSON：{"content": "..."}，便于后端直接写入 `reports.*_report`。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


# 注意：LangChain ChatPromptTemplate 使用 {var} 做占位符，JSON 花括号必须转义为 {{ / }}。
REPORT_OUTPUT_JSON_SPEC = """只输出 JSON，禁止任何额外文本。
```json
{{"content": "..."}}
```"""


LANDSCAPE_SYSTEM = (
    """你是一位资深市场分析师。
你将基于【项目级快照的结构化数据】输出宏观行业格局总结。

要求：
- 只基于输入数据，不要编造事实
- 结论要可解释，引用输入中的 mentions/平台分布/份额等作为证据线索
- **必须引用用户原话（original_terms）作为证据**，格式如：正如用户所说"..."
- 需要定义当前市场阶段（垄断型/寡头竞争/充分竞争/碎片化），并说明头部玩家的核心品牌心智
"""
    + REPORT_OUTPUT_JSON_SPEC
)

LANDSCAPE_USER = """【meta】
{meta}

【landscape layer】
{layers}

【Top entities（用于举例）】
{top_entities}

【用户原话（evidence）】
{original_terms}
"""


TOPIC_SYSTEM = (
    """你是一位敏锐的产品经理。
你将基于【项目级快照的结构化数据】输出话题洞察总结（痛点/爽点/争议点）。

要求：
- 只基于输入数据，不要编造事实
- 结论要可解释，引用输入中的 heat/mentions/分布等作为证据线索
- **必须引用用户原话（original_terms）作为证据**，格式如：正如用户所说"..."
- 深入剖析痛点背后的原因（是产品缺陷还是服务问题？）
- 验证"未被满足需求"的真实性，用原话佐证
"""
    + REPORT_OUTPUT_JSON_SPEC
)

TOPIC_USER = """【meta】
{meta}

【intent layer】
{layers}

【Top topics（用于举例）】
{top_topics}

【痛点用户原话（pains evidence）】
{pains_original_terms}

【爽点用户原话（gains evidence）】
{gains_original_terms}

【未满足需求用户原话（unmet needs evidence）】
{unmet_original_terms}
"""


FOCUS_SYSTEM = (
    """你是一位首席战略官（CSO）与"AI 顾问"。
你将基于【项目级快照的结构化数据】输出战略诊断（SWOT/差异/行动建议）。

硬性要求（必须满足，否则视为无效输出）：
- 只基于输入数据，不要编造事实
- **必须引用用户原话作为证据**，格式如：正如用户所说"..."
- 必须包含以下固定小标题（顺序一致）：
  1) 数据质量提示
  2) 关键结论
  3) SWOT
  4) 差异化诊断（相对竞品/或竞品不足的说明）
  5) 行动建议（必须拆成三段：营销建议 / 产品建议 / 公关建议）
- "行动建议"中每一条建议都必须附带证据线索，格式为：`证据：...`
  - 证据线索必须来源于输入（例如：entity/topic 的 heat/mentions/sentiment，平台分布，drivers_matrix 维度差异，用户原话等）
- 如果竞品列表为空或 focus layer 信息不足，必须在【数据质量提示】里明确说明对结论置信度的影响

输出内容建议用 Markdown（但仍然只能包在 JSON 的 content 里）。
"""
    + REPORT_OUTPUT_JSON_SPEC
)

FOCUS_USER = """【meta】
{meta}

【focus layer】
{layers}

【drivers_matrix（用于举例）】
{drivers_matrix}

【目标品牌负面评价原话（weakness evidence）】
{target_negative_terms}

【竞品正面评价原话（threat evidence）】
{competitor_positive_terms}
"""


def _chain(system: str, user: str) -> Runnable:
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    return prompt | llm


def create_project_snapshot_landscape_report_chain() -> Runnable:
    return _chain(LANDSCAPE_SYSTEM, LANDSCAPE_USER)


def create_project_snapshot_topic_report_chain() -> Runnable:
    return _chain(TOPIC_SYSTEM, TOPIC_USER)


def create_project_snapshot_focus_report_chain() -> Runnable:
    return _chain(FOCUS_SYSTEM, FOCUS_USER)


def parse_project_snapshot_report_response(response_text: str) -> Dict[str, Any]:
    """解析 report JSON（允许被 ```json 包裹）"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
        if isinstance(result, dict) and isinstance(result.get("content"), str):
            return {"content": result.get("content") or ""}
        return {}
    except Exception:
        logger.error(
            f"Failed to decode JSON from project snapshot report: {response_text[:200]}..."
        )
        return {}
