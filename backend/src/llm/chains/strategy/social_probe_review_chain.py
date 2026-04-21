"""Strategy Social Probe Review Chain — 社媒探测数据质量审查

与 `news_probe_review_chain` 对称，专门审查策略研究流程中 social_media 渠道的 probe 任务。
基于探测采集（≈20 条）的分析结果，评估每个关键词×平台任务的话题相关性：
- 客观规则（代码层）：数量、广告占比 → 明确 pass/fail（由调用方处理）
- 语义判断（LLM 层）：话题是否对应研究维度的研究问题（模糊案例）
- 优化建议（LLM 层）：为 fail 任务推荐更合适的关键词

每个任务独立并行评估（SINGLE_TASK_SYSTEM_TEMPLATE），消除批量上下文的锚定效应。
输出每个任务的 pass/fail 判定、判定依据、关键词建议。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SINGLE_TASK_SYSTEM_TEMPLATE = """你是一位研究设计顾问，负责评估单个社交媒体采集任务的话题相关性。

## 字段说明

- **主要话题**：从深度分析帖子中聚合出的核心话题，括号内为提及次数，代表该平台用户真实在讨论的内容
- **entity_match**：目标品牌或竞品实体是否在采集内容中出现（true=有出现，false=未出现）
- **广告占比**：被判定为推广/软文的帖子比例

## 判定规则

**核心问题**：话题内容能否支撑该任务所属维度对应的研究问题？

每个任务已标注维度，请只对照该维度下的研究问题进行判断。

- **pass**：话题与该维度研究问题的核心关注点有明显关联
- **fail**：话题与该维度研究问题明显无关（收集到的内容完全答不上研究问题）

**保守偏置**：存疑时判 pass——全量采集后分析结果会暴露真正的问题，误判 fail 会浪费关键词调整机会。

## 关键词建议（仅 fail 时填写）

好的替换关键词应满足：在该平台搜索时，能召回与研究问题核心关注点直接相关的内容。
结合「已采集到的话题（知道现在收到了什么）」与「研究问题（知道需要什么）」之间的差距来推导建议词。
**suggested_keyword 是提交给平台的单一搜索查询**（可包含空格），禁止用 `|` 拼接多个备选查询。
如果 fail 的原因是「该品牌/话题在该平台的讨论量本身稀少（无论换什么关键词都搜不到足量相关内容）」，可将 suggested_keyword 设为 null，表示平台级数据稀疏，建议移除。这与「关键词不精准」不同——前者换词也无法解决，后者可以通过换词改善。

**替换关键词必须遵守研究设计的维度规则**：
- **维度词汇隔离**：brand_voice 只用品牌自发声相关词（官方账号/Campaign名），competitive 只用竞品品牌词，consumer_voice 可用「主品名+评价词」或通用需求词（不与竞品混用），media_narrative 用事件+报道类词，industry 只用品类通用词——替换关键词不得跨维度混入不属于该维度的词汇
- **同维度风格一致**：替换关键词的词性结构和语义粒度应与本维度内现有关键词保持一致（输入中会列出本维度现有关键词作为参考），确保跨平台数据可比

**竞品维度的平台对称保护**：若当前 fail 任务属于竞品维度（competitive），且其所在平台同时被主品 UGC 维度（consumer_voice）使用，应优先尝试换词（调整 suggested_keyword）而非建议移除该平台（suggested_keyword=null）。主品和竞品在相同平台采集是横向对比的基础，轻易移除竞品在某平台的任务会破坏数据对称性，导致后续对比结论失真。只有在确认该平台对竞品研究完全无效（无论如何换词都无法召回相关内容）时，才允许建议移除。

**注意**：你在评估单个任务，看不到其他任务的结果。主品与竞品跨平台的整体对称性问题（如主品只在平台 A 有数据、竞品只在平台 B 有数据）由系统在汇总所有评估后统一检测处理，你无需承担跨任务的协调责任——聚焦判断当前任务本身是否能召回有价值的内容即可。

各平台替换词格式参考：
- 知乎：加"怎么样/如何评价"等评价词能精准命中问题标题，纯品牌名召回较泛
- 微博：品牌名 + 口碑类词（口碑/评价/怎么样）效果好；纯品牌名噪音大
- 小红书：加"测评/体验/推荐/避坑"类词能精准召回消费者评价
- 抖音/B站：简短品牌名 + 场景词/评测词效果好

## 输出格式（只输出 JSON，不含 markdown）

{{
  "task_id": 123,
  "keyword": "关键词",
  "platform": "平台",
  "verdict": "pass",
  "note": "一句话判定依据（说明话题与研究问题的关联或差距）",
  "suggested_keyword": null,
  "suggestion_reason": null
}}

**规则：**
- verdict 只能是 pass 或 fail
- verdict=fail 时：suggested_keyword 给出替换关键词，suggestion_reason 说明「当前收到了什么 vs 需要什么 → 为何推荐这个词」；pass 时均为 null
"""

USER_TEMPLATE = """{research_design_section}

{probe_tasks_section}"""


def create_single_task_probe_review_chain() -> Runnable:
    """创建单任务探测审查 LLM 链（用于并行评估，每个任务独立调用）"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SINGLE_TASK_SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_single_task_probe_review_inputs(
    research_design: dict,
    task: dict,
    brief: dict | None = None,
) -> dict[str, Any]:
    """格式化单任务探测审查输入（供并行调用使用）"""
    task_dim_map = research_design.get("_task_dimension_map") or {}
    data_plan = research_design.get("data_plan", [])
    all_rqs = research_design.get("research_questions", [])

    rq_by_id = {rq.get("id"): rq for rq in all_rqs}
    dim_to_rqs: dict[str, list[dict]] = {}
    # dim_name → dimension type（brand_voice / competitive / ...）
    dim_to_type: dict[str, str] = {}
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        q_ids = dp.get("question_ids") or []
        if dim_name and q_ids:
            rqs = [rq_by_id[qid] for qid in q_ids if qid in rq_by_id]
            dim_to_rqs[dim_name] = rqs
            # 取第一个 research_question 的 dimension 类型代表该维度
            if rqs:
                dim_to_type[dim_name] = rqs[0].get("dimension", "")

    # consumer_voice 维度（主品 UGC）的平台集合（供竞品对称保护判断）
    consumer_voice_platforms: list[str] = []
    for dp in data_plan:
        dp_type = dim_to_type.get(dp.get("dimension_name", ""), "")
        if dp_type == "consumer_voice" and dp.get("channel", "social_media") == "social_media":
            consumer_voice_platforms.extend(dp.get("platforms") or [])
    # 去重保序
    seen: set[str] = set()
    consumer_voice_platforms = [p for p in consumer_voice_platforms if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]

    lines = ["## 研究背景"]
    if brief:
        if brief.get("subject"):
            lines.append(f"研究主体：{brief['subject']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
    understanding = research_design.get("understanding_summary", "")
    if understanding:
        lines.append(f"需求理解：{understanding}")

    research_design_section = "\n".join(lines)

    dim_name = task_dim_map.get(str(task["task_id"]), "")
    current_dim_type = dim_to_type.get(dim_name, "")
    task_lines = ["## 待判定任务"]
    task_lines.append(f"\n### 任务 #{task['task_id']}")
    task_lines.append(
        f"关键词: {task.get('keyword', '')} | 平台: {task.get('platform', '')}"
        + (f" | 维度: {dim_name}" if dim_name else "")
    )
    # 竞品维度时注入主品平台，供对称保护判断
    if current_dim_type == "competitive" and consumer_voice_platforms:
        task_lines.append(
            f"⚠️ 竞品对称保护：主品 UGC 维度（consumer_voice）采集平台为 {', '.join(consumer_voice_platforms)}。"
            f"当前平台 {task.get('platform', '')} {'已被主品维度使用，建议换词而非移除' if task.get('platform', '') in consumer_voice_platforms else '未被主品维度使用，可视情况移除'}。"
        )

    # 注入同维度的其他关键词，供 LLM 保持替换建议的风格一致性
    if dim_name:
        for dp in data_plan:
            if dp.get("dimension_name") == dim_name and dp.get("channel", "social_media") == "social_media":
                other_keywords = dp.get("keywords") or []
                other_platforms = dp.get("platforms") or []
                if other_keywords:
                    task_lines.append(
                        f"本维度（{dim_name}）现有关键词: {', '.join(other_keywords)}"
                        f" | 平台: {', '.join(other_platforms)}"
                    )
                    task_lines.append("↑ 替换建议应与上述关键词风格保持一致，确保跨平台可比性")
                break

    rqs_for_dim = dim_to_rqs.get(dim_name) if dim_name else None
    if rqs_for_dim:
        task_lines.append("本维度研究问题：")
        for rq in rqs_for_dim:
            task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")
    elif all_rqs:
        task_lines.append("研究问题（参考全部，重点关注与本维度相关的）：")
        for rq in all_rqs:
            task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")

    entity_match = task.get("entity_match", False)
    task_lines.append(f"entity_match: {entity_match}（{'品牌/竞品实体在内容中有出现' if entity_match else '品牌/竞品实体未在内容中出现'}）")
    task_lines.append(
        f"采集: {task.get('posts_count', 0)} 条"
        f"（深度分析 {task.get('deep_analyzed', 0)} 条）"
    )

    top_topics = task.get("top_topics") or []
    if top_topics:
        topic_parts = []
        for topic in top_topics[:8]:
            if isinstance(topic, dict):
                name = topic.get("name", "")
                mentions = topic.get("mentions")
                topic_parts.append(f"{name}（{mentions}次）" if mentions else name)
            else:
                topic_parts.append(str(topic))
        task_lines.append(f"主要话题: {', '.join(topic_parts)}")
    else:
        task_lines.append("主要话题: （暂无，深度分析样本不足）")

    if task.get("promotion_ratio") is not None:
        task_lines.append(f"广告占比: {task['promotion_ratio']:.0%}（推广/软文帖子比例）")

    return {
        "research_design_section": research_design_section,
        "probe_tasks_section": "\n".join(task_lines),
    }


def parse_single_task_probe_review_response(response_text: str) -> dict[str, Any]:
    """解析单任务探测审查响应，返回单条 assessment dict，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Single Task Probe Review JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    if "verdict" not in result:
        raise ValueError(f"响应缺少 verdict 字段: {text[:200]}")

    return result


def detect_and_replace_symmetry_suggestions(
    all_assessments: list[dict[str, Any]],
    existing_suggestions: list[dict[str, Any]],
    research_design: dict[str, Any],
) -> list[dict[str, Any]]:
    """检测 consumer_voice（主品 UGC）与 competitive 的互补平台失败，将受影响任务的建议替换为平台统一建议。

    互补失败模式：consumer_voice 在平台 A 多数失败、在平台 B 多数通过；
    competitive 在平台 B 多数失败、在平台 A 多数通过。
    此时逐任务换词无法解决根本问题（平台对该品牌数据天然稀疏），
    应改为将主品与竞品统一迁移到共同可通过的平台。

    目标平台优先级：
    1. 主品和竞品均通过的平台（取通过任务最多的）
    2. 若无共同通过平台，取主品通过最多的平台（保留主品数据完整性）
    """
    task_dim_map = research_design.get("_task_dimension_map") or {}
    data_plan = research_design.get("data_plan", [])
    research_questions = research_design.get("research_questions", [])

    # dim_name → dimension type（brand_voice / competitive / ...）
    rq_by_id = {rq.get("id"): rq for rq in research_questions}
    dim_to_type: dict[str, str] = {}
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        for qid in (dp.get("question_ids") or []):
            rq = rq_by_id.get(qid)
            if rq and rq.get("dimension"):
                dim_to_type[dim_name] = rq["dimension"]
                break

    # platform_results[dim_type][platform] = {"pass": [...assessments], "fail": [...]}
    platform_results: dict[str, dict[str, dict[str, list[dict]]]] = {}

    for a in all_assessments:
        platform = a.get("platform", "")
        if not platform or platform == "news_media":
            continue
        dim_name = task_dim_map.get(str(a.get("task_id", "")), "")
        dim_type = dim_to_type.get(dim_name, "")
        if dim_type not in ("consumer_voice", "competitive"):
            continue
        verdict = a.get("verdict", "pass")
        platform_results.setdefault(dim_type, {}).setdefault(platform, {"pass": [], "fail": []})
        platform_results[dim_type][platform][verdict].append(a)

    cv = platform_results.get("consumer_voice", {})
    comp = platform_results.get("competitive", {})

    if not cv or not comp:
        return existing_suggestions

    def _majority_failing(results: dict[str, dict[str, list]]) -> set[str]:
        return {p for p, r in results.items() if len(r["fail"]) > len(r["pass"])}

    def _majority_passing(results: dict[str, dict[str, list]]) -> set[str]:
        return {p for p, r in results.items() if r["pass"] and len(r["pass"]) >= len(r["fail"])}

    cv_failing = _majority_failing(cv)
    cv_passing = _majority_passing(cv)
    comp_failing = _majority_failing(comp)
    comp_passing = _majority_passing(comp)

    # 互补失败：主品失败于竞品通过的平台，且竞品失败于主品通过的平台
    cv_fails_where_comp_passes = cv_failing & comp_passing
    comp_fails_where_cv_passes = comp_failing & cv_passing

    if not cv_fails_where_comp_passes or not comp_fails_where_cv_passes:
        return existing_suggestions

    # 选目标平台
    common_passing = cv_passing & comp_passing
    if common_passing:
        target = max(
            common_passing,
            key=lambda p: len(cv.get(p, {}).get("pass", [])) + len(comp.get(p, {}).get("pass", [])),
        )
    elif cv_passing:
        target = max(cv_passing, key=lambda p: len(cv.get(p, {}).get("pass", [])))
    else:
        return existing_suggestions

    reason = (
        f"主品在 {'、'.join(sorted(cv_fails_where_comp_passes))} 数据稀疏，"
        f"竞品在 {'、'.join(sorted(comp_fails_where_cv_passes))} 数据稀疏，"
        f"两者呈互补平台失败——换词无法解决平台级稀疏问题。"
        f"建议将主品与竞品统一迁移至「{target}」以确保横向对比基准一致。"
        f"注意：已通过的任务不受影响，如需完全统一数据来源，可手动将其一并移除。"
    )

    # 受影响任务：cv 在非目标平台失败 + comp 在非目标平台失败
    consolidation: list[dict[str, Any]] = []
    affected_ids: set[int] = set()

    for platform in cv_fails_where_comp_passes:
        for a in cv[platform]["fail"]:
            tid = int(a["task_id"])
            affected_ids.add(tid)
            consolidation.append({
                "task_id": tid,
                "original_keyword": a.get("keyword", ""),
                "suggested_keyword": a.get("keyword", ""),
                "platform": target,
                "reason": reason,
            })

    for platform in comp_fails_where_cv_passes:
        for a in comp[platform]["fail"]:
            tid = int(a["task_id"])
            affected_ids.add(tid)
            consolidation.append({
                "task_id": tid,
                "original_keyword": a.get("keyword", ""),
                "suggested_keyword": a.get("keyword", ""),
                "platform": target,
                "reason": reason,
            })

    # 替换受影响任务的原有建议（原建议是针对同一平台换词，已不适用）
    kept = [s for s in existing_suggestions if s.get("task_id") not in affected_ids]
    final = kept + consolidation

    logger.info(
        "平台对称检测：互补失败（consumer_voice↓%s，competitive↓%s）→ 目标平台=%s，替换 %d 条建议",
        sorted(cv_fails_where_comp_passes),
        sorted(comp_fails_where_cv_passes),
        target,
        len(consolidation),
    )

    return final

