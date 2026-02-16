"""实体聚合模块 (Entity Aggregation)

负责实体的聚合、归一化和焦点地图生成。
aggregated_entities 是后续 insights 和 charts 分析的核心数据来源。

处理流程：
1. 收集原始实体名称，同时收集竞品共现统计作为线索
2. 构建名称映射与标签（程序相似度 + LLM同义词与多维标签）
3. 使用映射进行聚合（合并数据、应用标签）
4. 对 Top 实体进行属性清洗（Semantic Attribute Cleaning）
5. 输出 aggregated_entities 数组（含 tags 字段和清洗后的属性）

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md §4.3
"""

import logging
import time
import math
from typing import Any
from collections import defaultdict, Counter

from src.langchain.chains.entity_normalization_chain import (
    format_entities_for_clustering,
    cluster_entities_with_review_sync,
)
from src.langchain.chains.attribute_normalization_chain import (
    create_attribute_normalization_chain,
    format_attributes_for_normalization,
    parse_normalization_response,
)
from src.social_media.analysis.celery_tasks.llm_utils import (
    invoke_chain_with_stats_sync,
)
from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_score,
    calculate_impact_score,
    calculate_comment_weight,
    normalize_name,
    are_similar,
    build_similarity_mapping,
    run_parallel_normalization,
    merge_token_stats,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 实体名称处理工具函数
# ============================================================================


def _contains_keyword(entity_name: str, keywords: list[str]) -> bool:
    """检查实体名称是否包含任一关键词（忽略大小写）"""
    normalized_name = normalize_name(entity_name)
    for keyword in keywords:
        normalized_keyword = normalize_name(keyword)
        if (
            normalized_keyword in normalized_name
            or normalized_name in normalized_keyword
        ):
            return True
    return False


# ============================================================================
# 实体角色分类
# ============================================================================


def classify_entity_role(
    entity_name: str,
    entity_data: dict[str, Any],
    task_keywords: list[str],
    competitor_names: set[str],
) -> str:
    """对实体进行主体角色分类

    优先使用 LLM 打的 tags.role，否则基于关键词匹配进行兜底判断。
    """
    # 优先使用 LLM 打的标签
    tags = entity_data.get("tags", {})
    if tags.get("role"):
        role = tags["role"].upper()
        if role == "TARGET":
            return "target"
        elif role == "COMPETITOR":
            return "competitor"
        return "other"

    # 兜底逻辑
    if _contains_keyword(entity_name, task_keywords):
        return "target"

    normalized_entity = normalize_name(entity_name)
    for comp_name in competitor_names:
        if are_similar(normalized_entity, comp_name, threshold=0.8):
            return "competitor"

    return "other"


def extract_competitor_names(
    entities_data: dict[str, dict],
    task_keywords: list[str],
) -> set[str]:
    """从 Target 实体的 competitors 字段提取竞品名称"""
    competitor_names: set[str] = set()

    for data in entities_data.values():
        entity_name = data.get("name", "")
        # 这里可以使用新的 tags 判断
        tags = data.get("tags", {})

        role = tags.get("role", "").upper()
        is_target = role == "TARGET" or _contains_keyword(entity_name, task_keywords)

        if is_target:
            competitors = data.get("competitors", {})
            for comp in competitors.keys():
                if comp:
                    competitor_names.add(normalize_name(comp))

    return competitor_names


# ============================================================================
# 名称映射构建（程序相似度 + LLM同义词）
# ============================================================================


def _collect_raw_entities_full(
    posts_data: list[dict[str, Any]],
) -> tuple[dict[str, dict], dict[int, float]]:
    """从 posts_data 收集所有原始实体的完整聚合数据（只遍历一次）

    返回:
        - 按原始实体名称索引的字典，包含完整的聚合信息
        - post_id -> impact_score 的映射，用于合并时正确计算 total_impact
    """
    raw_entity_data: dict[str, dict] = {}
    post_impact_map: dict[int, float] = {}  # 记录每个帖子的 Impact Score

    def get_or_create_entity(name: str, entity_type: str) -> dict:
        """获取或创建实体数据结构"""
        if name not in raw_entity_data:
            raw_entity_data[name] = {
                "name": name,
                "type": entity_type,
                "total_impact": 0.0,  # 累加的 Impact Score
                "impact_added_posts": set(),  # 去重：确保同一帖子的 Impact 只计算一次
                "post_sentiments": {},  # {post_id: sentiment} 用于合并时正确计算
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "post_sources": set(),
                "comment_sources": set(),
                "post_ids": set(),
                "features": defaultdict(set),
                "issues": defaultdict(set),
                "expectations": defaultdict(set),
                "audience": defaultdict(set),
                "scenarios": defaultdict(set),
                "market_factors": defaultdict(set),
                "competitors": defaultdict(set),
                # 新增：竞品共现统计，用于生成线索
                "competitor_stats": Counter(),
            }
        return raw_entity_data[name]

    def process_entity(entity: dict, post_id: int, entity_weight: float, source: str):
        """处理单个实体（收集到原始实体数据中）

        Args:
            entity: 实体数据
            post_id: 帖子ID
            entity_weight: 实体权重（原文使用 post_impact，评论使用 support_score 权重）
            source: 来源类型 ("post" 或 "comment")
        """
        name = entity.get("name", "")
        if not name:
            return

        data = get_or_create_entity(name, entity.get("type", "其他"))
        sentiment = entity.get("sentiment", 0)

        # Impact 只累加一次（per post per entity）
        if post_id and post_id not in data["impact_added_posts"]:
            data["total_impact"] += entity_weight
            data["post_sentiments"][post_id] = sentiment  # 存储情感用于合并时计算
            data["impact_added_posts"].add(post_id)

        # 情感分布
        if sentiment == 1:
            data["positive_count"] += 1
        elif sentiment == -1:
            data["negative_count"] += 1
        else:
            data["neutral_count"] += 1

        # 来源标记
        if post_id:
            if source == "post":
                data["post_sources"].add(post_id)
            else:
                data["comment_sources"].add(post_id)
            data["post_ids"].add(post_id)

        # 聚合维度信息
        if post_id:
            for feature in entity.get("features", []):
                if feature:
                    data["features"][feature].add(post_id)
            for issue in entity.get("issues", []):
                if issue:
                    data["issues"][issue].add(post_id)
            for expectation in entity.get("expectations", []):
                if expectation:
                    data["expectations"][expectation].add(post_id)
            for aud in entity.get("audience", []):
                if aud:
                    data["audience"][aud].add(post_id)
            for scenario in entity.get("scenarios", []):
                if scenario:
                    data["scenarios"][scenario].add(post_id)
            for factor in entity.get("market_factors", []):
                if factor:
                    data["market_factors"][factor].add(post_id)
            # 处理 competitors：既要存 post_id 索引，也要存统计计数
            for comp in entity.get("competitors", []):
                if comp:
                    data["competitors"][comp].add(post_id)
                    data["competitor_stats"][comp] += 1

    # 遍历所有帖子（只遍历一次！）
    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 1.0)
        value_score = post.get("value_score")

        # 计算单帖影响力分数 (Impact Score)
        post_impact = calculate_impact_score(cii, value_score)

        # 记录每个帖子的 Impact Score（用于后续合并时的情感计算）
        if post_id:
            post_impact_map[post_id] = post_impact

        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        # 原文实体：使用 post_impact 作为权重
        for entity in post_deep_result.get("entities", []):
            process_entity(entity, post_id, post_impact, "post")

        # 评论实体：使用 support_score 计算权重
        for entity in comment_deep_result.get("entities", []):
            support_score = entity.get("support_score", 0)
            entity_weight = calculate_comment_weight(support_score, post_impact)
            process_entity(entity, post_id, entity_weight, "comment")

    return raw_entity_data, post_impact_map


def _build_llm_mapping(
    raw_entities: list[dict],
    task_keywords: list[str],
    max_entities: int = 60,
    enable_review: bool = True,
) -> tuple[dict[str, str], dict[str, dict], dict[str, Any] | None]:
    """调用 LLM 构建同义词映射与多维标签

    Returns:
        tuple: (entity_mapping, tags_mapping, token_stats)
            - entity_mapping: {原始名称: 标准名称}
            - tags_mapping: {标准名称: tags dict}
            - token_stats: token 使用统计
    """
    if not raw_entities:
        return {}, {}, None

    # 按综合评分排序，取 Top N
    sorted_entities = sorted(
        raw_entities, key=lambda x: x.get("score", 0), reverse=True
    )[:max_entities]

    # 格式化输入
    entities_list = [
        {
            "name": e["name"],
            "type": e["type"],
            "score": e.get("score", 0),
            "hint": e.get("hint", ""),
        }
        for e in sorted_entities
    ]

    # 格式化输入内容
    formatted_input = format_entities_for_clustering(entities_list)

    # 调用两阶段归一化 (注意：现在返回 tags_mapping)
    result, token_stats = cluster_entities_with_review_sync(
        formatted_input,
        invoke_chain_with_stats_sync,
        task_keywords=task_keywords,  # 传入锚点
        enable_review=enable_review,
        llm_type="chat",
    )

    # 统计融合效果
    output_count = len(result.get("entities", []))

    summary = token_stats.get("summary", {}) if token_stats else {}
    logger.info(
        f"[实体归一化] LLM: {len(entities_list)} -> {output_count} 个, "
        f"calls={summary.get('total_calls', 0)}, "
        f"tokens={summary.get('total_tokens', 0)}, cost=¥{summary.get('total_cost_cny', 0):.4f}"
    )

    return result.get("entity_mapping", {}), result.get("tags_mapping", {}), token_stats


def _merge_entity_data(
    raw_entity_data: dict[str, dict],
    name_mapping: dict[str, str],
    tags_mapping: dict[str, dict] | None = None,
    post_impact_map: dict[int, float] | None = None,
) -> dict[str, dict]:
    """通用实体数据合并函数

    Args:
        raw_entity_data: 原始实体数据 {original_name: entity_dict}
        name_mapping: 名称映射 {original_name: canonical_name}
        tags_mapping: 标签映射 {canonical_name: tags_dict} (可选)
        post_impact_map: 帖子 Impact Score 映射 {post_id: impact} (可选)

    Returns:
        合并后的实体数据 {canonical_name: merged_entity_dict}
    """
    merged_data: dict[str, dict] = {}
    tags_mapping = tags_mapping or {}
    post_impact_map = post_impact_map or {}

    def get_or_create_merged(canonical: str, entity_type: str) -> dict:
        """获取或创建合并后的实体数据结构"""
        if canonical not in merged_data:
            # 尝试获取 LLM 生成的标签
            tags = tags_mapping.get(canonical, {})

            merged_data[canonical] = {
                "name": canonical,
                "canonical_name": canonical,
                "type": entity_type,
                "tags": tags,  # 保存标签
                "sentiment_weighted_sum": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "total_impact": 0.0,  # Total Impact (原始热度)
                "total_weight": 0.0,  # 用于情感计算的平滑权重和
                "impact_added_posts": set(),  # 去重：确保同一帖子的 Impact 只计算一次
                "post_sources": set(),
                "comment_sources": set(),
                "post_ids": set(),
                "features": defaultdict(set),
                "issues": defaultdict(set),
                "expectations": defaultdict(set),
                "audience": defaultdict(set),
                "scenarios": defaultdict(set),
                "market_factors": defaultdict(set),
                "competitors": defaultdict(set),
                "original_terms": [],  # 统一使用 original_terms 替代 merged_from
            }
        return merged_data[canonical]

    def merge_dict_of_sets(target: dict, source: dict):
        """合并两个 defaultdict(set) 字典"""
        for key, post_ids in source.items():
            target[key].update(post_ids)

    for original_name, raw_data in raw_entity_data.items():
        # 获取标准名称
        canonical = name_mapping.get(original_name, original_name)

        # 获取或创建合并目标
        merged = get_or_create_merged(canonical, raw_data["type"])

        # 记录原始词条及其频次 (统一结构)
        # 即使是 canonical 本身，如果出现在原始数据中，也记录下来
        term_count = len(raw_data["post_ids"])
        if term_count > 0:
            merged["original_terms"].append(
                {"text": original_name, "count": term_count}
            )

        # 合并数值字段（这些是累加的）
        merged["positive_count"] += raw_data["positive_count"]
        merged["negative_count"] += raw_data["negative_count"]
        merged["neutral_count"] += raw_data["neutral_count"]

        # 合并 Impact 和 sentiment_weighted_sum（同一个帖子只算一次）
        post_sentiments = raw_data.get("post_sentiments", {})
        if post_impact_map:
            for post_id in raw_data["impact_added_posts"]:
                if post_id not in merged["impact_added_posts"]:
                    merged["impact_added_posts"].add(post_id)
                    impact = post_impact_map.get(post_id, 1.0)

                    # 1. 累加原始 Impact (用于热度展示)
                    merged["total_impact"] += impact

                    # 2. 计算对数平滑权重 (用于情感计算)
                    # 使用 log10(max(impact, 1)) + 1
                    # Impact=1 -> Weight=1; Impact=10 -> Weight=2; Impact=10000 -> Weight=5
                    smoothed_weight = math.log10(max(impact, 1)) + 1
                    merged["total_weight"] += smoothed_weight

                    # 使用该帖子的 sentiment 正确计算加权和
                    sentiment = post_sentiments.get(post_id, 0)
                    merged["sentiment_weighted_sum"] += sentiment * smoothed_weight
        else:
            # 预处理阶段：直接累加 total_impact（近似值，用于排序）
            merged["total_impact"] += raw_data.get("total_impact", 0.0)

        # 合并集合字段
        merged["post_sources"].update(raw_data["post_sources"])
        merged["comment_sources"].update(raw_data["comment_sources"])
        merged["post_ids"].update(raw_data["post_ids"])

        # 合并维度信息
        merge_dict_of_sets(merged["features"], raw_data["features"])
        merge_dict_of_sets(merged["issues"], raw_data["issues"])
        merge_dict_of_sets(merged["expectations"], raw_data["expectations"])
        merge_dict_of_sets(merged["audience"], raw_data["audience"])
        merge_dict_of_sets(merged["scenarios"], raw_data["scenarios"])
        merge_dict_of_sets(merged["market_factors"], raw_data["market_factors"])
        merge_dict_of_sets(merged["competitors"], raw_data["competitors"])

    return merged_data


def build_entity_name_mapping(
    raw_entities: list[dict[str, Any]],
    task_keywords: list[str],
    enable_llm: bool = True,
    max_entities: int = 60,
) -> tuple[dict[str, str], dict[str, dict], dict[str, Any] | None]:
    """构建实体名称映射与标签

    Returns:
        tuple: (name_mapping, tags_mapping, token_stats)
    """
    token_stats = None
    raw_count = len(raw_entities)
    tags_mapping: dict[str, dict] = {}  # {标准名称: tags}

    if not raw_entities:
        return {}, {}, None

    # 为每个实体计算 score（确保程序相似度映射排序正确）
    for entity in raw_entities:
        if "score" not in entity:
            impact = entity.get("total_impact", 0.0)
            mentions = len(entity.get("post_ids", set()))
            entity["score"] = calculate_score(impact, mentions)

    # 程序相似度映射 (阈值 0.8)
    similarity_mapping = build_similarity_mapping(raw_entities, threshold=0.8)
    after_similarity_count = len(set(similarity_mapping.values()))
    similarity_merged = raw_count - after_similarity_count

    logger.info(
        f"[实体归一化] 程序相似度: {raw_count} -> {after_similarity_count} 个 (合并了 {similarity_merged} 个)"
    )

    # 3. LLM 同义词映射（可选）
    if enable_llm:
        try:
            # 预合并：利用程序映射和通用合并函数生成“预合并实体列表”
            # 构建一个临时字典适配 _merge_entity_data 的输入格式
            raw_data_map = {e["name"]: e for e in raw_entities}

            # 调用通用合并函数 (无 post_impact_map，total_impact 是近似累加，用于 Top 50 排序足够)
            pre_merged_data = _merge_entity_data(raw_data_map, similarity_mapping)

            # 构建 LLM 输入列表
            llm_input_entities = []
            for canonical, entity in pre_merged_data.items():
                impact = entity.get("total_impact", 0.0)
                mentions = len(entity["post_ids"])

                # 创建副本用于 LLM 输入
                new_entity = {
                    "name": canonical,
                    "type": entity["type"],
                    "mentions": mentions,
                    "heat": impact,  # LLM 输入仍用 heat 字段名（对外接口）
                    "score": calculate_score(impact, mentions),
                    "hint": "",
                }
                llm_input_entities.append(new_entity)

            # 按重新计算后的 Score 排序
            llm_input_entities.sort(key=lambda x: x.get("score", 0), reverse=True)

            # 只有当预合并后的实体数量足够多时才调用 LLM
            if len(llm_input_entities) >= 5:
                llm_mapping, llm_tags_mapping, token_stats = _build_llm_mapping(
                    llm_input_entities, task_keywords, max_entities
                )

                # 保存 tags 映射
                tags_mapping = llm_tags_mapping

                if llm_mapping:
                    # 合并映射：将 LLM 的映射叠加到 程序映射 上
                    # 逻辑：Name -> [Similarity] -> Prog_Canonical -> [LLM] -> Final_Canonical
                    for name, prog_canonical in similarity_mapping.items():
                        if prog_canonical in llm_mapping:
                            final_canonical = llm_mapping[prog_canonical]
                            similarity_mapping[name] = final_canonical

                    final_unique = len(set(similarity_mapping.values()))
                    llm_merged = after_similarity_count - final_unique
                    logger.info(
                        f"[名称映射] LLM 归一化后: {final_unique} 个唯一实体 (合并了 {llm_merged} 个)"
                    )
        except Exception as e:
            logger.warning(
                f"[名称映射] LLM 归一化失败，使用程序映射: {e}", exc_info=True
            )

    return similarity_mapping, tags_mapping, token_stats


# ============================================================================
# 属性清洗
# ============================================================================


def _clean_entity_attributes_sync(
    entity_data: dict[str, dict],
    top_n_scores: set[float],
    top_3_scores: set[float],  # 新增：Top 3 实体评分集合
    top_k_attrs: int = 50,  # 每个字段只清洗 Top K
    invoke_with_stats_fn=invoke_chain_with_stats_sync,
    llm_type: str = "chat",
) -> tuple[dict[str, dict], dict[str, Any]]:
    """对 Top N 实体的属性进行同步清洗 (并发执行)

    Args:
        entity_data: 已聚合的实体数据 {canonical_name: data}
        top_n_scores: 需要清洗的实体评分集合 (Top 4-10)
        top_3_scores: Top 3 实体评分集合（清洗所有属性字段）
        top_k_attrs: 每个属性字段最多发送给LLM的短语数量

    Returns:
        (清洗后的实体数据, token统计)
    """
    token_stats = {
        "summary": {
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_cny": 0.0,
            "total_duration_seconds": 0.0,
        },
        "call_details": [],
    }

    # Top 3 实体清洗所有 7 个属性字段，Top 4-10 只清洗核心 3 个字段
    core_fields = ["features", "issues", "expectations"]
    all_fields = [
        "features",
        "issues",
        "expectations",
        "audience",
        "scenarios",
        "market_factors",
        "competitors",
    ]

    try:
        # 预先创建 chain 可能会有线程安全问题，但在 LangChain Runnable 中通常是安全的。
        # 为了更安全，可以在每个线程中创建，或者确保 Runnable 是无状态的。
        # 这里为了简单，假设 Runnable 是线程安全的 (ChatPromptTemplate + ChatModel 通常是)。
        _ = create_attribute_normalization_chain()
    except Exception as e:
        logger.warning(f"[属性清洗] 初始化 LLM 失败，跳过清洗: {e}")
        return entity_data, token_stats

    # 筛选需要清洗的实体，并根据评分确定清洗字段范围
    all_top_scores = top_n_scores | top_3_scores
    entities_to_clean = [
        e
        for e in entity_data.values()
        if calculate_score(e["total_impact"], len(e["post_ids"])) in all_top_scores
    ]

    logger.info(
        f"[属性清洗] 开始清洗 {len(entities_to_clean)} 个 Top 实体的属性 (Top 3 清洗全部字段, Top 4-10 清洗核心字段)"
    )

    # 准备任务列表
    tasks = []
    for entity in entities_to_clean:
        entity_name = entity["name"]
        entity_score = calculate_score(entity["total_impact"], len(entity["post_ids"]))

        # Top 3 实体清洗所有字段，其余只清洗核心字段
        fields_to_clean = all_fields if entity_score in top_3_scores else core_fields

        for field in fields_to_clean:
            raw_map = entity.get(field, {})
            if not raw_map:
                continue

            # 过滤低频词 (移除：小样本场景下保留长尾词交给 LLM 聚类)
            # filtered_map = filter_low_frequency_terms(raw_map)

            # 按频次排序 (直接使用 raw_map)
            sorted_terms = sorted(
                [(k, v) for k, v in raw_map.items()],
                key=lambda x: len(x[1]),
                reverse=True,
            )

            # 优化：如果不同词条数 <= 5，不需要 LLM 聚类，直接保留原样
            if len(sorted_terms) <= 5:
                # 直接将这些词条保留，不调用 LLM
                # 重新构建 map，保留这 <= 5 个词
                # 注意：这里我们实际上是跳过了"清洗"步骤，保留了原始数据
                # 如果之前 raw_map 有更多词，这里只保留了 sorted_terms (即全部)
                # 但 sorted_terms 本身就是 raw_map 的全部内容（因为移除了低频过滤）

                # 由于这是 update 操作，我们需要确保 entity_data 中的数据保持原样
                # 实际上不需要做任何操作，只要不把 task 加入 tasks 列表即可
                # 原始数据已经在 entity_data 中了
                continue

            # 截取 Top K
            terms_to_clean = sorted_terms[:top_k_attrs]
            tail_terms = sorted_terms[top_k_attrs:]

            # 构建待清洗映射
            valid_terms_map = {k: v for k, v in terms_to_clean}
            formatted_attrs = format_attributes_for_normalization(valid_terms_map)

            tasks.append(
                {
                    "task_id": f"{entity_name}|{field}",
                    "entity_name": entity_name,
                    "field": field,
                    "raw_map": raw_map,
                    "tail_terms": tail_terms,
                    "terms_to_clean": terms_to_clean,
                    "attributes": formatted_attrs,  # input for chain
                }
            )

    # 使用通用并行执行器
    results, stats = run_parallel_normalization(
        tasks=tasks,
        chain_factory=create_attribute_normalization_chain,
        invoke_func=invoke_with_stats_fn,
        parse_response_func=parse_normalization_response,
        llm_type=llm_type,
        max_workers=10,
    )

    token_stats = stats  # 直接使用返回的统计

    # 处理结果并更新 entity_data
    for res in results:
        task = res["task"]
        clusters = res["parsed_result"]

        entity_name = task["entity_name"]
        field = task["field"]
        raw_map = task["raw_map"]
        tail_terms = task["tail_terms"]
        terms_to_clean = task["terms_to_clean"]

        if not clusters:
            continue

        # 重建映射
        new_map = {}  # {label: {post_ids: set, original_terms: list[{text, count}]}}
        cleaned_original_terms = set()

        # 1. 加入清洗后的聚类
        for cluster in clusters:
            label = cluster.get("name")
            originals = cluster.get("original_terms", [])

            if not label:
                continue

            if label not in new_map:
                new_map[label] = {"post_ids": set(), "original_terms": []}

            cluster_terms_stats = {}

            for term in originals:
                if term in raw_map:
                    # 合并 post_ids
                    new_map[label]["post_ids"].update(raw_map[term])
                    cleaned_original_terms.add(term)

                    # 收集统计信息
                    cluster_terms_stats[term] = len(raw_map[term])

            # 将统计信息转为 list 格式
            for term, count in cluster_terms_stats.items():
                new_map[label]["original_terms"].append({"text": term, "count": count})

        # 2. 加入未被 LLM 聚类的 Top K 词（保留在清洗结果中）
        for term, post_ids in terms_to_clean:
            if term not in cleaned_original_terms:
                if term not in new_map:
                    new_map[term] = {"post_ids": set(), "original_terms": []}
                new_map[term]["post_ids"].update(post_ids)
                new_map[term]["original_terms"].append(
                    {"text": term, "count": len(post_ids)}
                )

        # 注意：不再加入长尾词（>Top K 的部分直接丢弃）

        if entity_name in entity_data:
            entity_data[entity_name][field] = new_map

    return entity_data, token_stats


# ============================================================================
# 实体聚合主函数
# ============================================================================


def aggregate_entities(
    posts_data: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    enable_llm_normalization: bool = True,
    top_n: int = 10,
    top_k_attrs: int = 50,  # 新增参数
) -> dict[str, Any]:
    """聚合任务内的实体，生成焦点地图"""
    start_time = time.time()
    task_keywords = task_keywords or []

    # ========================================
    # 1. 收集原始实体完整数据（只遍历一次！）
    # ========================================
    raw_entity_data, post_impact_map = _collect_raw_entities_full(posts_data)

    # ========================================
    # 2. 基于收集的数据构建名称映射与标签
    # ========================================
    # 直接使用完整的 raw_entity_data (values list) 传给构建函数
    # 这样 _merge_entity_data 就能访问到 positive_count 等所有字段
    raw_entities_list = list(raw_entity_data.values())

    name_mapping, tags_mapping, llm_token_stats = build_entity_name_mapping(
        raw_entities_list,
        task_keywords,
        enable_llm=enable_llm_normalization,
    )

    # ========================================
    # 3. 根据映射合并原始数据（无需再遍历 posts_data）
    # ========================================
    entity_data = _merge_entity_data(
        raw_entity_data, name_mapping, tags_mapping, post_impact_map
    )

    # 只保留 LLM 处理过的实体（有 tags 的）
    if enable_llm_normalization and tags_mapping:
        before_filter = len(entity_data)
        entity_data = {k: v for k, v in entity_data.items() if v.get("tags")}
        logger.info(
            f"[实体聚合] {len(raw_entity_data)} 个原始实体 -> {before_filter} 个归一化 -> {len(entity_data)} 个 LLM 实体"
        )
    else:
        logger.info(
            f"[实体聚合] {len(raw_entity_data)} 个唯一实体 -> 归一化后 {len(entity_data)} 个"
        )

    # ========================================
    # 4. 属性清洗 (新增)
    # ========================================
    # 先确定 Top N 实体的分数线
    all_scores = [
        calculate_score(e["total_impact"], len(e["post_ids"]))
        for e in entity_data.values()
    ]
    all_scores.sort(reverse=True)
    top_n_scores = set(all_scores[:top_n])
    top_3_scores = set(all_scores[:3])  # Top 3 实体清洗所有属性字段

    if enable_llm_normalization:
        entity_data, cleaning_stats = _clean_entity_attributes_sync(
            entity_data, top_n_scores, top_3_scores, top_k_attrs=top_k_attrs
        )

        # 合并 token 统计
        if cleaning_stats and llm_token_stats:
            merge_token_stats(llm_token_stats, cleaning_stats)
        elif cleaning_stats:
            llm_token_stats = cleaning_stats

    # ========================================
    # 5. 提取竞品名称、角色分类 (Legacy / Helper)
    # ========================================
    competitor_names = extract_competitor_names(entity_data, task_keywords)

    # ========================================
    # 6. 格式化输出
    # ========================================

    def get_item_count(item):
        """获取属性项的帖子数"""
        if isinstance(item, dict) and "post_ids" in item:
            return len(item["post_ids"])
        return len(item)

    def should_keep_original_terms(name: str, original_terms: list) -> bool:
        """判断是否需要保留 original_terms（只有真正发生合并时才保留）"""
        if not original_terms:
            return False
        if len(original_terms) > 1:
            return True
        # 只有一个元素时，检查是否与 name 不同
        return original_terms[0].get("text") != name

    def format_entity_for_display(data: dict) -> dict | None:
        """格式化实体用于展示"""
        mentions = len(data["post_ids"])
        if mentions == 0:
            return None

        post_source_count = len(data["post_sources"])
        comment_source_count = len(data["comment_sources"])
        total_source_count = post_source_count + comment_source_count

        source_distribution = {
            "post": round(post_source_count / total_source_count, 2)
            if total_source_count > 0
            else 0,
            "comment": round(comment_source_count / total_source_count, 2)
            if total_source_count > 0
            else 0,
        }

        derived_sentiment = 0.0
        # 使用平滑权重计算情感
        if data["total_weight"] > 0:
            derived_sentiment = round(
                data["sentiment_weighted_sum"] / data["total_weight"], 2
            )

        role = classify_entity_role(data["name"], data, task_keywords, competitor_names)

        # 辅助函数：安全地获取排序后的 keys
        def get_sorted_keys(data_dict):
            if not data_dict:
                return []
            return sorted(
                data_dict.keys(),
                key=lambda k: get_item_count(data_dict[k]),
                reverse=True,
            )

        # 辅助函数：构建 Top 属性详细项（用于前端展示 original_terms）
        def build_top_attr_items(data_dict, max_items: int = 5):
            if not data_dict:
                return []
            sorted_items = sorted(
                data_dict.items(), key=lambda x: get_item_count(x[1]), reverse=True
            )[:max_items]

            result_items = []
            for text, item in sorted_items:
                if isinstance(item, dict) and "post_ids" in item:
                    attr_item = {
                        "text": text,
                        "post_ids": list(item.get("post_ids", [])),
                    }
                    sorted_terms = sorted(
                        item.get("original_terms", []),
                        key=lambda x: x.get("count", 0),
                        reverse=True,
                    )
                    # 只有真正发生合并时才保留 original_terms
                    if sorted_terms and should_keep_original_terms(text, sorted_terms):
                        attr_item["original_terms"] = sorted_terms
                    result_items.append(attr_item)
                else:
                    # 旧结构 (Set) -> 无 original_terms
                    result_items.append(
                        {
                            "text": text,
                            "post_ids": list(item),
                        }
                    )
            return result_items

        top_features = build_top_attr_items(data["features"], 5)
        top_issues = build_top_attr_items(data["issues"], 5)
        top_expectations = build_top_attr_items(data["expectations"], 5)

        # heat 使用原始 Total Impact
        heat = round(data["total_impact"], 1)
        score = round(calculate_score(data["total_impact"], mentions), 1)

        result = {
            "name": data["name"],
            "type": data["type"],
            "role": role,
            "heat": heat,
            "mentions": mentions,
            "score": score,
            "sentiment": derived_sentiment,
            "sentiment_distribution": {
                "positive": data["positive_count"],
                "negative": data["negative_count"],
                "neutral": data["neutral_count"],
            },
            "source_distribution": source_distribution,
            "top_features": top_features,
            "top_issues": top_issues,
            "top_expectations": top_expectations,
            "post_ids": list(data["post_ids"]),
            "post_source_ids": list(data["post_sources"]),
            "comment_source_ids": list(data["comment_sources"]),
        }

        # 添加多维标签
        if data.get("tags"):
            result["tags"] = data["tags"]

        # 添加原始词条信息（只有真正发生合并时才保留）
        if data.get("original_terms"):
            sorted_terms = sorted(
                data["original_terms"], key=lambda x: x["count"], reverse=True
            )
            if should_keep_original_terms(data["name"], sorted_terms):
                result["original_terms"] = sorted_terms

        return result

    # 格式化展示用实体
    formatted_entities = []
    for data in entity_data.values():
        formatted = format_entity_for_display(data)
        if formatted:
            formatted_entities.append(formatted)

    formatted_entities.sort(key=lambda x: x["score"], reverse=True)

    top_entities = formatted_entities[:top_n]
    target_entities = [e for e in formatted_entities if e["role"] == "target"][:top_n]
    competitor_entities = [e for e in formatted_entities if e["role"] == "competitor"][
        :top_n
    ]

    # 构建完整融合数据（数组格式）
    aggregated_entities = []
    for data in entity_data.values():
        mentions = len(data["post_ids"])
        if mentions == 0:
            continue

        derived_sentiment = 0.0
        # 使用平滑权重计算情感
        if data["total_weight"] > 0:
            derived_sentiment = round(
                data["sentiment_weighted_sum"] / data["total_weight"], 2
            )

        heat = round(data["total_impact"], 1)
        score = round(calculate_score(data["total_impact"], mentions), 1)

        # 判断是否是 Top N 实体（已被 LLM 清洗过属性）
        # 通过检查属性字段的数据结构判断：dict 结构说明已清洗，set 结构说明未清洗
        def is_cleaned_attr(attr_dict):
            if not attr_dict:
                return False
            first_item = next(iter(attr_dict.values()), None)
            return isinstance(first_item, dict) and "post_ids" in first_item

        is_top_entity = is_cleaned_attr(data.get("features", {}))

        # 辅助函数：统一格式化属性项
        def format_attr_items(data_dict, max_items: int | None = None):
            if not data_dict:
                return []

            result = []
            # 按 count 排序
            sorted_items = sorted(
                data_dict.items(), key=lambda x: get_item_count(x[1]), reverse=True
            )

            # 非 Top N 实体，限制属性数量
            if max_items is not None:
                sorted_items = sorted_items[:max_items]

            for text, item in sorted_items:
                if isinstance(item, dict) and "post_ids" in item:
                    # 已经是新结构 (Top N 清洗过的)
                    sorted_terms = sorted(
                        item["original_terms"], key=lambda x: x["count"], reverse=True
                    )
                    attr_item = {
                        "text": text,
                        "post_ids": list(item["post_ids"]),
                    }
                    # 只有真正发生合并时才保留 original_terms
                    if should_keep_original_terms(text, sorted_terms):
                        attr_item["original_terms"] = sorted_terms
                    result.append(attr_item)
                else:
                    # 旧结构 (Set，未清洗的) -> 转为新结构，无需 original_terms
                    result.append(
                        {
                            "text": text,
                            "post_ids": list(item),
                        }
                    )
            return result

        # Top N 实体：属性已被 LLM 清洗，无数量限制
        # 非 Top N 实体：属性只保留前 10 个
        attr_limit = None if is_top_entity else 10

        entity_dict = {
            "name": data["name"],
            "canonical_name": data["canonical_name"],
            "type": data["type"],
            "sentiment": derived_sentiment,
            "sentiment_distribution": {
                "positive": data["positive_count"],
                "negative": data["negative_count"],
                "neutral": data["neutral_count"],
            },
            "heat": heat,
            "mentions": mentions,
            "score": score,
            "post_source_count": len(data["post_sources"]),
            "comment_source_count": len(data["comment_sources"]),
            "post_ids": list(data["post_ids"]),
            "post_source_ids": list(data["post_sources"]),
            "comment_source_ids": list(data["comment_sources"]),
            "features": format_attr_items(data.get("features", {}), attr_limit),
            "issues": format_attr_items(data.get("issues", {}), attr_limit),
            "expectations": format_attr_items(data.get("expectations", {}), attr_limit),
            "audience": format_attr_items(data.get("audience", {}), attr_limit),
            "scenarios": format_attr_items(data.get("scenarios", {}), attr_limit),
            "market_factors": format_attr_items(
                data.get("market_factors", {}), attr_limit
            ),
            "competitors": format_attr_items(data.get("competitors", {}), attr_limit),
        }

        # 添加多维标签
        if data.get("tags"):
            entity_dict["tags"] = data["tags"]

        # 添加原始词条信息（只有真正发生合并时才保留）
        if data.get("original_terms"):
            sorted_terms = sorted(
                data["original_terms"], key=lambda x: x["count"], reverse=True
            )
            if should_keep_original_terms(data["name"], sorted_terms):
                entity_dict["original_terms"] = sorted_terms

        aggregated_entities.append(entity_dict)

    aggregated_entities.sort(key=lambda x: x["score"], reverse=True)

    # 只保留 Top 40 个实体
    total_entity_count = len(aggregated_entities)
    aggregated_entities = aggregated_entities[:40]

    logger.info(
        f"[实体聚合] 最终输出: {len(aggregated_entities)} 个实体 (共 {total_entity_count} 个，保留 Top 40)"
    )

    result = {
        "top_entities": top_entities,
        "target_entities": target_entities,
        "competitor_entities": competitor_entities,
        "aggregated_entities": aggregated_entities,
    }

    # 添加 LLM token 统计（如果有）
    if llm_token_stats:
        # 计算总耗时 (Wall Clock Time)
        execution_duration = time.time() - start_time

        # 将 API 累计耗时重命名为 total_api_duration_seconds
        if "total_duration_seconds" in llm_token_stats["summary"]:
            llm_token_stats["summary"]["total_api_duration_seconds"] = llm_token_stats[
                "summary"
            ]["total_duration_seconds"]

        # 使用实际执行时间覆盖 total_duration_seconds，以符合 AnalysisJob 的语义
        llm_token_stats["summary"]["total_duration_seconds"] = execution_duration

        result["llm_token_stats"] = llm_token_stats

    return result
