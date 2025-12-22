#!/usr/bin/env python3
"""项目级实体合并/打标 Chain（Project Snapshot Entity Merge）

目标：在项目级快照场景下，对跨任务聚合后的 Top 实体进行再归一化，并输出稳定的 Role/Parent 标签。

设计要点（与 PROJECT_SNAPSHOT_PIPELINE_FINAL.md 对齐）：
- Case A（subject 存在）：启用 Role 仲裁（强约束 Target/Competitor）。
- Case B（subject 为空）：去 Role 模式，所有实体 role 必须为 Context（严禁 Target/Competitor）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


PROJECT_ENTITY_MERGE_SYSTEM_TEMPLATE = """你是一位语义分析专家，负责处理社交媒体实体数据（项目级合并场景）。

## 输入说明
- 实体列表：每行包含实体名、类型、重要度与一些线索（平台/关键词）。
  - 线索 hint 中可能包含 `parent候选:XXX`，这是来自上游任务级聚合的父级品牌投票结果（强先验）。
- subject（主体）：{subject}
- competitors（竞品列表）：{competitors}

## 你的任务
1) **归一化**：合并指向同一事物的同义词实体，减少冗余。
2) **打标**：为每个归一化后的实体输出：
   - role: Target / Competitor / Context
   - parent: 品牌归属（产品→品牌；品牌→Self；通用词/场景→""）

## 关键规则（必须严格遵守）
- 如果 subject 为空字符串或 "null"：
  - **启用去 Role 模式**：所有实体 role 必须为 `Context`，严禁输出 Target/Competitor。
- 如果 subject 非空：
  - **启用 Role 仲裁**：
    - 与 subject 指向同一品牌/产品（含子产品/别名）的实体，role 必须为 `Target`。
    - competitors 列表中的品牌/产品（含别名）必须标为 `Competitor`。
    - 其他全部为 `Context`。
- 不要把 Competitor 合并进 Target（严禁）。
- 不要合并不同型号或不同品牌的产品。
- **Parent 处理优先级**：
  - 若实体行的 hint 中包含 `parent候选:XXX`，请优先使用该候选作为 parent，并确保同一品牌/别名下 parent 一致。
  - 若缺失 parent候选 且原数据缺失，请尝试补全（产品→品牌；品牌→Self；通用词/场景→""）。

## 输出格式（只输出 JSON，禁止任何额外文字）
```json
{{
  "entities": [
    {{
      "name": "标准名称（代表性名称）",
      "original_names": ["被合并的原始实体名称列表"],
      "role": "Target/Competitor/Context",
      "parent": "品牌名或空字符串"
    }}
  ]
}}
```
"""


PROJECT_ENTITY_MERGE_USER_TEMPLATE = """请对以下实体列表进行处理：

{entities}
"""


def create_project_entity_merge_chain() -> Runnable:
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PROJECT_ENTITY_MERGE_SYSTEM_TEMPLATE),
            ("user", PROJECT_ENTITY_MERGE_USER_TEMPLATE),
        ]
    )
    return prompt | llm


def parse_project_entity_merge_response(response_text: str) -> Dict[str, Any]:
    """解析项目级实体合并输出（允许被 ```json 包裹），并构建 entity_mapping/tags_mapping。"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
    except Exception:
        logger.error(
            f"Failed to decode JSON from project entity merge response: {response_text[:200]}..."
        )
        return {"entities": [], "entity_mapping": {}, "tags_mapping": {}}

    if not isinstance(result, dict):
        return {"entities": [], "entity_mapping": {}, "tags_mapping": {}}

    entity_mapping: dict[str, str] = {}
    tags_mapping: dict[str, dict[str, Any]] = {}

    for entity in result.get("entities", []) or []:
        if not isinstance(entity, dict):
            continue
        name = (entity.get("name") or "").strip()
        if not name:
            continue
        tags_mapping[name] = {
            "role": entity.get("role", "Context"),
            "parent": entity.get("parent", "") or "",
        }
        originals = entity.get("original_names") or [name]
        if isinstance(originals, list):
            for original in originals:
                if isinstance(original, str) and original.strip():
                    entity_mapping[original.strip()] = name

    result["entity_mapping"] = entity_mapping
    result["tags_mapping"] = tags_mapping
    return result
