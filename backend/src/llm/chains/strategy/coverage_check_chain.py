"""Strategy Coverage Check Chain — 数据覆盖度验证

基于切片量化指标对照研究问题评估覆盖度。三态判定 + 渠道相对量级指引，
输出 per-RQ status / overall_ready / warnings / data_highlights / slice_adjustments。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位数据覆盖度评估专家，负责判断已采集数据是否足以支撑下游产出生成。

## 任务
对每个研究问题判定其在切片中的覆盖度，并给出整体就绪判定与跨问题警示。

## 字段说明

切片摘要中每个实体 / 话题带量化指标：
- `mentions`：被提及的总次数（含同源帖多次）
- `sources`：独立源帖数（**关键信号**——同样 mentions 下，sources 越多代表信号越分散可靠，sources=1 代表单帖伪相关）
- `sentiment`：综合情感（-1 ~ +1）

### 实体 role 标签解读

实体行末尾括号内是 role 标签，**所有 role 都是 RQ 的有效证据来源**，不可因 role 跳过：
- `(Target)`：研究主体品牌
- `(Competitor)`:竞品品牌
- `(Context)`：被消费者主动讨论的**非品牌概念**——成分 / 技术 / 品类 / 使用场景等。例：奶粉行业的某种营养成分；汽车膜的某种材质；降噪耳机的某种降噪技术；母婴产品的某个使用场景。**这是消费者声音的核心载体，绝不是"上下文背景"或"无关词"**——RQ 涉及成分/技术/概念/场景认知时，证据主要来自 Context 实体（社媒新闻通用）

## 判定逻辑（per 研究问题）

### Step 1: 语义匹配（强制先做）

**判定前必须把 RQ 中的关键术语展开为别名集合，再扫描切片实体/话题列表做匹配**。专业术语常以多种形态出现，字面匹配漏判率高。

**展开维度**（基于你自己的领域常识自由产生别名，不限于 RQ 字面词）：

1. **中英文 / 缩写 / 全称互译**：行业术语的英文缩写、中文译名、英文全称都属同一概念
2. **同义说法 / 近义说法**：领域内表达同一含义的不同用词（含书面 ↔ 口语、专业 ↔ 通俗）
3. **品牌名 ↔ 系列名 ↔ 产品线名**：同一品牌下不同系列、子品牌、产品线名属同一商业实体
4. **概念 ↔ 该概念的具体表现**：抽象概念与其在切片中的具体话题表述（如 RQ 中的"认知"对应切片中的"了解情况"/"知道率"等具体表述）

**跨领域示意**（说明展开类型，不是穷举词典——需对当前 RQ 自行展开）：
- 奶粉行业某成分英文缩写 ↔ 该成分中文译名 ↔ 该成分专业全称
- 汽车后市场某保护材料英文 ↔ 中文行业名 ↔ 消费者口语称谓
- 电子产品某技术英文缩写 ↔ 中文技术名 ↔ 营销话术名
- 母婴产品某使用场景的不同口语化说法

任一别名命中即视为相关。**禁止仅因 RQ 字面词不出现就判 uncovered**——必须先证明所有别名形式（你自行展开的全部）都未命中。

### 判定边界（极重要，避免越界）

你的工作是判**「下游分析所需的数据是否已采集到」**，**不是**判「该 RQ 是否已被回答」。后者属于 Insight 阶段的事，不属于本判定。

具体地：
- 切片中存在 ≥3 source 的相关实体或话题 → 数据**已采集**到 → covered，**无论这些数据是否直接回答 RQ 字面问题**
- 反模式（要避免）：RQ 问"消费者对 X 的理解水平 / 评估障碍 / 决策路径"等深度问题时，看到 X 相关实体只有提及量、没看到"理解到什么程度"的细节，就降级为 partial/uncovered。这是越界——"理解到什么程度" / "障碍是什么" 是下游 Insight 从源帖中提炼的工作，不是覆盖度判定的范围
- 你只判"数据能不能让下游开工"，不判"下游能产出什么质量的结论"

### Step 2: 按命中条目的量化指标判定状态

**evidence_summary 必须显式说明语义匹配过程**——格式："识别到 RQ 关键词 X 的别名包括 [Y1, Y2]，命中实体 …"，让审查者可追溯匹配链。

**covered（充分支撑）**：
- 至少一个相关实体 / 话题被 **≥3 个独立源帖** 讨论
  - 社媒切片：source ≥3 个帖子
  - 新闻切片：source ≥3 篇独立文章
- 数字 3 是统计学上"互相佐证"的最低线（避免单帖偏见 / 双帖巧合）

**partial（部分支撑）**：
- 有相关实体 / 话题命中，但 source 仅 1-2（信号偏单薄）
- 或多个相关项但分布零散（每项都仅 1 源帖支撑）
- 全量阶段可能补强但当前 evidence 不充分

**uncovered（无支撑）**：
- 切片中完全无相关实体 / 话题命中
- 或仅有 mention=1 / source=1 的极端单点提及（噪音级别）

## overall_ready 规则

- **true**：所有 `priority=high` 的 RQ 状态 ∈ {{covered, partial}}
- **false**：任一 `priority=high` 的 RQ 状态 = uncovered
- medium / low priority RQ 不影响 overall_ready，仅影响 warnings

## warnings 字段（关键）

当存在以下情况时，输出 warning（每条单句，明确指出受影响 RQ）：
- 多个 RQ 共同因为同一个 slice 数据稀疏而 partial / uncovered（例："slice X 数据稀疏，影响 rq1/rq2"）
- subject 在某 slice 完全缺失但该 slice 是该 RQ 的唯一数据源
- partial RQ 的具体补强建议（如"在维度 X 增补关键词 Y 可能改善 rq3"）

无 warning 时返回空数组。

## 输出格式

只输出 JSON，不要 markdown 标记：

{{
  "question_coverage": [
    {{
      "question_id": "rq1",
      "question": "研究问题原文",
      "term_aliases_explored": ["RQ 关键词的英文缩写", "中文译名", "全称", "同义说法等——按当前 RQ 自行展开"],
      "matched_items": [
        {{"slice": "切片名", "type": "entity|topic", "name": "命中条目名", "sources": 12}}
      ],
      "status": "covered",
      "covered_by": ["切片名称1"],
      "evidence_summary": "RQ 关键词 X 展开为 [Y1, Y2]，命中切片 A 中实体「Y1」(source=12)，≥3 独立源帖充分支撑"
    }}
  ],
  "overall_ready": true,
  "warnings": ["slice X 整体数据稀疏，影响 rq2/rq3——建议在维度 Y 增补关键词"],
  "data_highlights": ["数据亮点1", "数据亮点2"],
  "slice_adjustments": [
    {{
      "slice_name": "切片名称",
      "issue": "问题描述",
      "suggestion": "调整建议"
    }}
  ]
}}

## 要求

- question_coverage 必须覆盖所有研究问题，status 三态之一
- **term_aliases_explored 必填**：列出该 RQ 关键术语的所有别名形式（中英文/缩写/全称/同义词），即使最终判 uncovered 也必须列。这是审查者验证你是否做过语义匹配的依据
- **matched_items 必填**：列出所有 term_aliases_explored 在切片中命中的实体/话题（≥1 即视为 partial 起步，再按 source 量级升级到 covered）。空数组时才能判 uncovered
- evidence_summary **必须包含量化数字**（mentions / sources），让审查者可追溯
- data_highlights：2-4 条对策略生成有价值的数据发现
- slice_adjustments：仅当切片配置确有问题时输出，否则空数组
- warnings 优先承载跨 RQ 共性诊断，不要把每个 partial RQ 都当 warning
"""

USER_TEMPLATE = """{brief_section}

{research_questions_section}

{slices_summary_section}"""


def create_coverage_check_chain() -> Runnable:
    """创建覆盖度验证 LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_TEMPLATE),
            ("user", USER_TEMPLATE),
        ]
    )
    return prompt | llm


def _format_entity_line(e: dict, *, source_key: str) -> str:
    """渲染单个实体/话题行，统一格式：name(role): mentions=N, sources=M, sentiment=..."""
    name = e.get("name", "")
    role = e.get("role", "") or e.get("category", "")
    mentions = e.get("mentions") or e.get("mention_count") or 0
    sources = e.get(source_key) or 0
    sentiment = e.get("sentiment") or e.get("sentiment_avg")
    parts = [f"mentions={mentions}", f"sources={sources}"]
    if sentiment is not None:
        try:
            parts.append(f"sentiment={float(sentiment):+.2f}")
        except (TypeError, ValueError):
            pass
    role_str = f"({role})" if role else ""
    return f"  - {name}{role_str}: {', '.join(parts)}"


# 与 SYSTEM_TEMPLATE §covered 阈值对齐：source >= 3 即可作为 covered 候选证据
_COVERED_SOURCE_THRESHOLD = 3
# 兜底高频补充（source < 阈值但仍可能贡献 partial 信号）
_PARTIAL_BACKUP_COUNT = 15
# 单切片单维度（实体/话题）总条目硬上限，防止 prompt 爆炸
_PER_SLICE_HARD_CAP = 80


def _select_evidence(
    items: list[dict],
    *,
    source_key: str,
) -> tuple[list[dict], int, int]:
    """按 source_count 降序排，保留所有 source>=阈值 + 兜底 top-N partial 信号。

    ⚠️ 历史 bug（v2026.05 修）：原实现直接 `items[:15]` 不排序，导致切片实体/话题
    多达数百个时 LLM 仅看到前 15 条存储顺序的样本——这一头未必包含 source 高的
    covered 候选，造成假阴性 uncovered 判定（典型场景：strategy 41 的「乳脂球膜」
    实体 source=12 因排序靠后被截断，rq1 被误判 uncovered）。

    设计原则：传给 LLM 的证据样本必须与 SYSTEM_TEMPLATE 内嵌的判定阈值对齐——
    凡 source>=阈值 的全部传入（不能因 top-N 截断而丢 covered 证据），其余按
    source desc 兜底 N 条以提供 partial 上下文。

    Returns:
        (selected_items, total_count, covered_count)
    """

    def src(i: dict) -> int:
        try:
            return int(i.get(source_key) or 0)
        except (TypeError, ValueError):
            return 0

    sorted_items = sorted(items, key=src, reverse=True)
    covered = [i for i in sorted_items if src(i) >= _COVERED_SOURCE_THRESHOLD]
    backup = [i for i in sorted_items if src(i) < _COVERED_SOURCE_THRESHOLD][
        :_PARTIAL_BACKUP_COUNT
    ]
    selected = (covered + backup)[:_PER_SLICE_HARD_CAP]
    return selected, len(items), len(covered)


def format_coverage_check_inputs(
    brief: dict | None,
    research_questions: list[dict],
    slices_data: list[tuple[str, dict]],
) -> dict[str, Any]:
    """格式化覆盖度验证链输入

    Args:
        brief: Brand Brief dict
        research_questions: 研究问题列表
        slices_data: [(slice_name, result_data), ...] 切片名和分析结果
    """
    # Brief
    if brief:
        lines = ["## Brand Brief"]
        if brief.get("subject"):
            lines.append(f"研究主体：{brief['subject']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
        brief_section = "\n".join(lines)
    else:
        brief_section = "## Brand Brief\n未提供"

    # 研究问题
    rq_lines = ["## 研究问题"]
    for rq in research_questions:
        priority = rq.get("priority", "medium")
        rq_lines.append(
            f"- [{rq.get('id')}] {rq.get('question')} "
            f"(维度: {rq.get('dimension')}, 优先级: {priority})"
        )
    research_questions_section = "\n".join(rq_lines)

    # 切片摘要
    slice_lines = ["## 切片分析摘要"]
    for name, data in slices_data:
        slice_lines.append(f"\n### {name}")
        is_news = name.startswith("[新闻]")

        if is_news:
            # 新闻切片 result_data 结构（ADR-003 后）：
            #   descriptive: sentiment_distribution / sentiment_overall / articles_unique / articles_filtered
            #   entities: [{name, role, mention_count, source_count, sentiment_avg, ...}]
            #   event_clusters / media_landscape / competitive: 派生层
            #   page_synthesis: Pass 2 LLM 散文（briefing + event_titles），策略层禁用
            descriptive = data.get("descriptive") or {}
            entities = data.get("entities") or []
            dist = descriptive.get("sentiment_distribution") or {}
            total_articles = sum(
                dist.get(k, 0) for k in ("positive", "neutral", "negative")
            )
            slice_lines.append(f"渠道: 新闻 | 原文数: {total_articles}")
            overall_sent = descriptive.get("sentiment_overall")
            if overall_sent is not None:
                label = (
                    "正面"
                    if overall_sent > 0.6
                    else "负面"
                    if overall_sent < 0.4
                    else "中性"
                )
                slice_lines.append(f"整体情感: {label}（{overall_sent:.2f}）")
            if entities:
                ents, total, covered_n = _select_evidence(
                    entities, source_key="source_count"
                )
                slice_lines.append(
                    f"实体（共 {total} 个，其中 source≥{_COVERED_SOURCE_THRESHOLD} 的 {covered_n} 个，"
                    f"按 source 降序展示 {len(ents)} 个）:"
                )
                for e in ents:
                    if e.get("name"):
                        slice_lines.append(
                            _format_entity_line(e, source_key="source_count")
                        )
        else:
            # 社媒切片 result_data 结构: {meta, foundation, layers, reports, pipeline}
            foundation = data.get("foundation") or {}
            landscape = (data.get("layers") or {}).get("landscape") or {}
            overview = landscape.get("overview") or {}
            total_volume = overview.get("total_volume", 0) or overview.get(
                "unique_posts", 0
            )
            slice_lines.append(f"渠道: 社媒 | 总声量: {total_volume}")

            global_nsr = overview.get("global_nsr")
            if global_nsr is not None:
                label = (
                    "正面"
                    if global_nsr > 0.3
                    else "负面"
                    if global_nsr < -0.3
                    else "中性"
                )
                slice_lines.append(f"整体情感: {label}（NSR={global_nsr:.2f}）")

            all_entities = foundation.get("aligned_entities") or []
            if all_entities:
                ents, total, covered_n = _select_evidence(
                    all_entities, source_key="source_count"
                )
                slice_lines.append(
                    f"实体（共 {total} 个，其中 source≥{_COVERED_SOURCE_THRESHOLD} 的 {covered_n} 个，"
                    f"按 source 降序展示 {len(ents)} 个）:"
                )
                for e in ents:
                    if e.get("name"):
                        slice_lines.append(
                            _format_entity_line(e, source_key="source_count")
                        )

            all_topics = foundation.get("aligned_topics") or []
            if all_topics:
                tps, total, covered_n = _select_evidence(
                    all_topics, source_key="source_count"
                )
                slice_lines.append(
                    f"话题（共 {total} 个，其中 source≥{_COVERED_SOURCE_THRESHOLD} 的 {covered_n} 个，"
                    f"按 source 降序展示 {len(tps)} 个）:"
                )
                for t in tps:
                    if t.get("name"):
                        slice_lines.append(
                            _format_entity_line(t, source_key="source_count")
                        )

    slices_summary_section = "\n".join(slice_lines)

    return {
        "brief_section": brief_section,
        "research_questions_section": research_questions_section,
        "slices_summary_section": slices_summary_section,
    }


def parse_coverage_check_response(response_text: str) -> dict[str, Any]:
    """解析覆盖度验证 Chain 输出，失败时抛出 ValueError。

    Schema: question_coverage[].status (covered/partial/uncovered) + warnings 字段。
    """
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Coverage Check Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("question_coverage", [])
    result.setdefault("overall_ready", False)
    result.setdefault("warnings", [])
    result.setdefault("data_highlights", [])
    result.setdefault("slice_adjustments", [])

    return result
