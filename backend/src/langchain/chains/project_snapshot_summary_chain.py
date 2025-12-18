#!/usr/bin/env python3
"""项目级快照整体总结 Chain（Stage3 / Analyst）

输入：项目级 Stage2 已完成后的对齐数据（实体/观点/类目/差异摘要等）。
输出：面向业务的整体总结（JSON），用于前端“整体分析”模块展示。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


PROJECT_SNAPSHOT_SUMMARY_SYSTEM_TEMPLATE = """你是一位资深的社媒洞察分析师。
你将基于输入的【项目级快照对齐结果】输出一份专业、克制、可落地的总结。

## 重要原则
1. 只基于输入数据做归纳，不要编造事实。
2. 结论要“可解释”：尽量引用输入中的分布/mentions/平台/关键词差异作为证据线索。
3. 聚焦验收目标：平台差异、关键词差异。
4. 输出必须是 JSON，禁止额外文本。

## 输出格式（只输出 JSON）
```json
{
  "executive_summary": "2-5 句话，总结项目全局",
  "differences": [
    {"dimension": "platform|keyword", "key": "具体平台或关键词", "insight": "差异一句话", "evidence": "mentions/分布等证据线索"}
  ],
  "drivers": [
    {"driver": "维度/驱动因素", "entities": ["实体A","实体B"], "sentiment": "positive|negative|mixed", "evidence": "来自矩阵/属性的证据线索"}
  ],
  "risks": ["风险要点1", "风险要点2"],
  "opportunities": ["机会要点1", "机会要点2"],
  "next_questions": ["下一步应验证的问题1", "问题2"]
}
```
"""

PROJECT_SNAPSHOT_SUMMARY_USER_TEMPLATE = """请基于以下快照对齐数据输出整体总结：

【项目元信息】
{meta}

【概览】
{overview}

【差异摘要（四象限/实体网络等）】
{differences}

【类目/观点聚合（对齐后）】
{topic_aspects}

【Top 实体（对齐后，含属性）】
{top_entities}

【Top 观点（对齐后）】
{top_topics}

【归因矩阵（对齐后，截断）】
{drivers_matrix}
"""


def create_project_snapshot_summary_chain() -> Runnable:
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROJECT_SNAPSHOT_SUMMARY_SYSTEM_TEMPLATE),
        ("user", PROJECT_SNAPSHOT_SUMMARY_USER_TEMPLATE),
    ])
    return prompt | llm


def parse_project_snapshot_summary_response(response_text: str) -> Dict[str, Any]:
    """解析总结输出 JSON（允许被 ```json 包裹）"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
        if isinstance(result, dict):
            return result
        return {}
    except Exception:
        logger.error(f"Failed to decode JSON from project snapshot summary: {response_text[:200]}...")
        return {}


