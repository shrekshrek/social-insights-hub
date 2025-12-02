"""实体聚合模块 (Entity Aggregation)

负责实体的聚合、归一化和焦点地图生成。
aggregated_entities 是后续 insights 和 charts 分析的核心数据来源。

处理流程：
1. 收集原始实体名称
2. 构建名称映射（程序相似度 + LLM同义词）
3. 使用映射进行聚合（情感分组、来源标记、主体过滤等）
4. 输出 aggregated_entities 数组

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md §4.3
"""

import logging
import math
from difflib import SequenceMatcher
from typing import Any
from collections import defaultdict

from src.langchain.chains.entity_normalization_chain import (
    create_entity_normalization_chain,
    format_entities_for_normalization,
    parse_normalization_response,
)
from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync

logger = logging.getLogger(__name__)


# ============================================================================
# 实体名称处理工具函数
# ============================================================================

def _normalize_entity_name(name: str) -> str:
    """标准化实体名称（小写、去空格）"""
    return name.lower().strip()


def _are_similar_entities(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """判断两个实体名称是否相似（用于合并）

    默认阈值 0.8：适中的合并策略
    - 会合并: "甲醛检测" vs "甲醛检测服务", "iPhone16" vs "iPhone 16"
    - 不会合并: "华为" vs "Huawei"（需要 LLM 处理）
    """
    n1 = _normalize_entity_name(name1)
    n2 = _normalize_entity_name(name2)
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def _contains_keyword(entity_name: str, keywords: list[str]) -> bool:
    """检查实体名称是否包含任一关键词（忽略大小写）"""
    normalized_name = _normalize_entity_name(entity_name)
    for keyword in keywords:
        normalized_keyword = _normalize_entity_name(keyword)
        if normalized_keyword in normalized_name or normalized_name in normalized_keyword:
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

    分类规则 (§4.3)：
    1. Target: 实体名称包含任务关键词 → 本品
    2. Competitor: 实体名称在竞品列表中 → 竞品
    3. Other: 其他实体（人物、场景、技术术语等，不是噪音）
    """
    if _contains_keyword(entity_name, task_keywords):
        return "target"

    normalized_name = _normalize_entity_name(entity_name)
    for comp_name in competitor_names:
        if _are_similar_entities(normalized_name, comp_name, threshold=0.8):
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
        if _contains_keyword(entity_name, task_keywords):
            competitors = data.get("competitors", {})
            for comp in competitors.keys():
                if comp:
                    competitor_names.add(_normalize_entity_name(comp))

    return competitor_names


# ============================================================================
# 名称映射构建（程序相似度 + LLM同义词）
# ============================================================================

def _collect_raw_entities_full(posts_data: list[dict[str, Any]]) -> tuple[dict[str, dict], dict[int, float]]:
    """从 posts_data 收集所有原始实体的完整聚合数据（只遍历一次）

    返回:
        - 按原始实体名称索引的字典，包含完整的聚合信息
        - post_id -> cii 的映射，用于合并时正确计算 total_cii

    后续可直接用于：
    1. 构建名称映射（基于 heat 排序）
    2. 根据映射合并数据（无需再遍历 posts_data）
    """
    raw_entity_data: dict[str, dict] = {}
    post_cii_map: dict[int, float] = {}  # 记录每个帖子的 CII

    def get_or_create_entity(name: str, entity_type: str) -> dict:
        """获取或创建实体数据结构"""
        if name not in raw_entity_data:
            raw_entity_data[name] = {
                "name": name,
                "type": entity_type,
                "heat": 0.0,
                "cii_added_posts": set(),
                "sentiment_weighted_sum": 0.0,
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
            }
        return raw_entity_data[name]

    def process_entity(entity: dict, post_id: int, cii: float, source: str):
        """处理单个实体（收集到原始实体数据中）"""
        name = entity.get("name", "")
        if not name:
            return

        data = get_or_create_entity(name, entity.get("type", "其他"))
        sentiment = entity.get("sentiment", 0)

        # CII 只累加一次（per post per entity）
        if post_id and post_id not in data["cii_added_posts"]:
            data["heat"] += cii
            data["sentiment_weighted_sum"] += sentiment * cii
            data["cii_added_posts"].add(post_id)

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
            for comp in entity.get("competitors", []):
                if comp:
                    data["competitors"][comp].add(post_id)

    # 遍历所有帖子（只遍历一次！）
    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 1.0)

        # 记录每个帖子的 CII
        if post_id:
            post_cii_map[post_id] = cii

        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        for entity in post_deep_result.get("entities", []):
            process_entity(entity, post_id, cii, "post")

        for entity in comment_deep_result.get("entities", []):
            process_entity(entity, post_id, cii, "comment")

    return raw_entity_data, post_cii_map


def _calculate_score(heat: float, mentions: int) -> float:
    """计算综合评分：heat × log(mentions + 1)

    综合考虑影响力（heat）和讨论广泛性（mentions）
    """
    return heat * math.log(mentions + 1)


def _extract_for_llm(raw_entity_data: dict[str, dict]) -> list[dict[str, Any]]:
    """从原始实体数据中提取 LLM 归一化所需的信息

    提取 name, type, mentions, heat, score
    - mentions: 提及帖子数（post_ids 的数量）
    - heat: CII 加权热度
    - score: 综合评分 = heat × log(mentions + 1)
    """
    return [
        {
            "name": data["name"],
            "type": data["type"],
            "mentions": len(data["post_ids"]),
            "heat": round(data["heat"], 1),
            "score": round(_calculate_score(data["heat"], len(data["post_ids"])), 1),
        }
        for data in raw_entity_data.values()
    ]


def _build_similarity_mapping(raw_entities: list[dict], threshold: float = 0.8) -> dict[str, str]:
    """构建程序相似度映射（相似度 >= threshold 合并）

    Returns:
        dict: {原始名称: 标准名称}
    """
    name_mapping: dict[str, str] = {}
    canonical_list: list[str] = []  # 已确定的标准名称

    # 按综合评分排序，高分优先成为标准名称
    sorted_entities = sorted(raw_entities, key=lambda x: x.get("score", 0), reverse=True)

    for entity in sorted_entities:
        name = entity["name"]

        # 检查是否与已有标准名称相似（复用 _are_similar_entities）
        matched_canonical = None
        for canonical in canonical_list:
            if _are_similar_entities(name, canonical, threshold):
                matched_canonical = canonical
                break

        if matched_canonical:
            name_mapping[name] = matched_canonical
        else:
            name_mapping[name] = name
            canonical_list.append(name)

    return name_mapping


def _build_llm_mapping(
    raw_entities: list[dict],
    task_keywords: list[str],
    max_entities: int = 50,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """调用 LLM 构建同义词映射

    Returns:
        tuple: (entity_mapping, token_stats)
            - entity_mapping: {原始名称: 标准名称}
            - token_stats: token 使用统计（如果调用了 LLM）
    """
    if not raw_entities:
        return {}, None

    # 按综合评分排序，取 Top N
    sorted_entities = sorted(raw_entities, key=lambda x: x.get("score", 0), reverse=True)[:max_entities]

    # 格式化输入：name, type, score（综合评分）
    entities_list = [
        {
            "name": e["name"],
            "type": e["type"],
            "score": e.get("score", 0),  # 综合评分 = heat × log(mentions + 1)
        }
        for e in sorted_entities
    ]

    # 格式化输入内容
    formatted_input = format_entities_for_normalization(entities_list)
    keywords_str = ", ".join(task_keywords) if task_keywords else "无"

    # 打印 LLM 输入
    print("\n" + "=" * 80)
    print("[实体归一化] LLM 输入内容")
    print("=" * 80)
    print(f"任务关键词: {keywords_str}")
    print(f"输入实体数量: {len(entities_list)}")
    print("-" * 40)
    print(formatted_input)
    print("=" * 80 + "\n")

    # 调用 LLM
    chain = create_entity_normalization_chain()
    response, token_stats = invoke_chain_with_stats_sync(
        chain,
        {
            "keywords": keywords_str,
            "entities": formatted_input,
        },
        llm_type="chat",
    )
    response_text = response.content if hasattr(response, "content") else str(response)
    result = parse_normalization_response(response_text)

    # 打印 LLM 输出
    print("\n" + "=" * 80)
    print("[实体归一化] LLM 输出内容")
    print("=" * 80)
    print(response_text)
    print("=" * 80)

    # 统计融合效果
    normalized_groups = result.get("normalized_groups", [])
    standalone_entities = result.get("standalone_entities", [])
    output_count = len(normalized_groups) + len(standalone_entities)

    print("\n" + "-" * 40)
    print(f"[实体归一化] 融合统计:")
    print(f"  输入实体数: {len(entities_list)}")
    print(f"  归一化组数: {len(normalized_groups)}")
    print(f"  独立实体数: {len(standalone_entities)}")
    print(f"  输出实体数: {output_count}")
    print(f"  合并减少数: {len(entities_list) - output_count}")

    # 打印每个归一化组的详情
    if normalized_groups:
        print("\n  归一化组详情:")
        for i, group in enumerate(normalized_groups, 1):
            canonical = group.get("canonical_name", "")
            merged = group.get("merged_entities", [])
            print(f"    [{i}] {canonical} <- {merged}")

    print("-" * 40 + "\n")

    summary = token_stats.get('summary', {})
    logger.info(
        f"[实体归一化] LLM: {len(entities_list)} -> {output_count} 个, "
        f"tokens={summary.get('total_tokens', 0)}, cost=¥{summary.get('total_cost_cny', 0):.4f}"
    )

    return result.get("entity_mapping", {}), token_stats


def build_entity_name_mapping(
    raw_entities: list[dict[str, Any]],
    task_keywords: list[str],
    enable_llm: bool = True,
    max_entities: int = 50,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """构建实体名称映射（程序相似度 + LLM同义词）

    处理流程：
    1. 程序相似度合并（>=0.8）
    2. LLM 同义词合并（可选）
    3. 合并两个映射

    Args:
        raw_entities: 预收集的原始实体列表，每个包含 name, type, heat
        task_keywords: 任务关键词
        enable_llm: 是否启用 LLM 归一化
        max_entities: LLM 最多处理的实体数量

    Returns:
        tuple: (name_mapping, token_stats)
            - name_mapping: {原始名称: 标准名称}
            - token_stats: token 使用统计（如果调用了 LLM）
    """
    token_stats = None
    raw_count = len(raw_entities)

    if not raw_entities:
        return {}, None

    # 程序相似度映射
    similarity_mapping = _build_similarity_mapping(raw_entities)
    after_similarity_count = len(set(similarity_mapping.values()))
    similarity_merged = raw_count - after_similarity_count

    # 打印程序归一化统计
    print("\n" + "=" * 80)
    print("[实体归一化] 程序相似度归一化统计")
    print("=" * 80)
    print(f"  原始唯一实体数: {raw_count}")
    print(f"  程序合并后数量: {after_similarity_count}")
    print(f"  程序合并减少数: {similarity_merged}")
    print(f"  发送给 LLM 数量: min({after_similarity_count}, 50) = {min(after_similarity_count, 50)}")
    print("=" * 80 + "\n")

    logger.info(f"[实体归一化] 程序相似度: {raw_count} -> {after_similarity_count} 个")

    # 3. LLM 同义词映射（可选）
    if enable_llm and len(raw_entities) >= 5:
        try:
            llm_mapping, token_stats = _build_llm_mapping(raw_entities, task_keywords, max_entities)
            if llm_mapping:
                # 合并映射：LLM 映射优先级更高
                # 但 LLM 只返回它处理过的实体，未处理的保持程序映射
                for name, canonical in llm_mapping.items():
                    # 如果 LLM 返回了映射，使用 LLM 的结果
                    if name in similarity_mapping:
                        old_canonical = similarity_mapping[name]
                        # 将所有映射到 old_canonical 的名称都更新为新的 canonical
                        # 使用 list() 避免在迭代时修改 dict
                        for k, v in list(similarity_mapping.items()):
                            if v == old_canonical:
                                similarity_mapping[k] = canonical

                final_unique = len(set(similarity_mapping.values()))
                logger.info(f"[名称映射] LLM 归一化后: {final_unique} 个唯一实体")
        except Exception as e:
            logger.warning(f"[名称映射] LLM 归一化失败，使用程序映射: {e}")

    return similarity_mapping, token_stats


# ============================================================================
# 根据名称映射合并原始实体数据
# ============================================================================

def _merge_by_mapping(
    raw_entity_data: dict[str, dict],
    name_mapping: dict[str, str],
    post_cii_map: dict[int, float],
) -> dict[str, dict]:
    """根据名称映射合并原始实体数据

    Args:
        raw_entity_data: 原始实体数据（按原始名称索引）
        name_mapping: 名称映射 {原始名称: 标准名称}
        post_cii_map: {post_id: cii} 映射，用于正确计算合并后的 total_cii

    Returns:
        合并后的实体数据（按标准名称索引）
    """
    merged_data: dict[str, dict] = {}

    def get_or_create_merged(canonical: str, entity_type: str) -> dict:
        """获取或创建合并后的实体数据结构"""
        if canonical not in merged_data:
            merged_data[canonical] = {
                "name": canonical,
                "canonical_name": canonical,
                "type": entity_type,
                "sentiment_weighted_sum": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "total_cii": 0.0,
                "cii_added_posts": set(),
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
                "merged_from": set(),
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

        # 记录合并来源
        if original_name != canonical:
            merged["merged_from"].add(original_name)

        # 合并数值字段（这些是累加的）
        merged["positive_count"] += raw_data["positive_count"]
        merged["negative_count"] += raw_data["negative_count"]
        merged["neutral_count"] += raw_data["neutral_count"]

        # 合并 CII（使用 post_cii_map 精确计算，同一个帖子只算一次）
        for post_id in raw_data["cii_added_posts"]:
            if post_id not in merged["cii_added_posts"]:
                merged["cii_added_posts"].add(post_id)
                # 使用精确的帖子 CII
                cii = post_cii_map.get(post_id, 1.0)
                merged["total_cii"] += cii

        # 情感加权和：直接累加（已经按 CII 加权）
        merged["sentiment_weighted_sum"] += raw_data["sentiment_weighted_sum"]

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


# ============================================================================
# 实体聚合主函数
# ============================================================================

def aggregate_entities(
    posts_data: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    enable_llm_normalization: bool = True,
    top_n: int = 10,
) -> dict[str, Any]:
    """聚合任务内的实体，生成焦点地图

    优化后的处理流程（只遍历 posts_data 一次）：
    1. 收集所有原始实体的完整聚合数据
    2. 基于收集的数据构建名称映射（程序相似度 + LLM）
    3. 根据映射合并原始数据
    4. 输出 aggregated_entities 数组

    Args:
        posts_data: 帖子数据列表，每个包含 post_deep_result 和 cii
        task_keywords: 任务关键词列表，用于主体过滤
        enable_llm_normalization: 是否启用 LLM 归一化
        top_n: 返回前多少个实体

    Returns:
        dict: {
            "top_entities": 热度排名前N的实体列表（展示用）,
            "target_entities": 本品实体列表,
            "competitor_entities": 竞品实体列表,
            "aggregated_entities": 完整融合数据（数组格式）,
            "llm_token_stats": LLM token 使用统计（如果调用了 LLM）,
        }
    """
    task_keywords = task_keywords or []

    # ========================================
    # 1. 收集原始实体完整数据（只遍历一次！）
    # ========================================
    raw_entity_data, post_cii_map = _collect_raw_entities_full(posts_data)

    # ========================================
    # 2. 基于收集的数据构建名称映射
    # ========================================
    raw_entities_for_llm = _extract_for_llm(raw_entity_data)
    name_mapping, llm_token_stats = build_entity_name_mapping(
        raw_entities_for_llm,
        task_keywords,
        enable_llm=enable_llm_normalization,
    )

    # ========================================
    # 3. 根据映射合并原始数据（无需再遍历 posts_data）
    # ========================================
    entity_data = _merge_by_mapping(raw_entity_data, name_mapping, post_cii_map)

    logger.info(f"[实体聚合] {len(raw_entity_data)} 个唯一实体 -> 归一化后 {len(entity_data)} 个")

    # ========================================
    # 3. 提取竞品名称、角色分类
    # ========================================
    competitor_names = extract_competitor_names(entity_data, task_keywords)

    # ========================================
    # 4. 格式化输出
    # ========================================
    def format_entity_for_display(data: dict) -> dict | None:
        """格式化实体用于展示"""
        mentions = len(data["post_ids"])
        if mentions == 0:
            return None

        post_source_count = len(data["post_sources"])
        comment_source_count = len(data["comment_sources"])
        total_source_count = post_source_count + comment_source_count

        source_distribution = {
            "post": round(post_source_count / total_source_count, 2) if total_source_count > 0 else 0,
            "comment": round(comment_source_count / total_source_count, 2) if total_source_count > 0 else 0,
        }

        derived_sentiment = 0.0
        if data["total_cii"] > 0:
            derived_sentiment = round(data["sentiment_weighted_sum"] / data["total_cii"], 2)

        role = classify_entity_role(data["name"], data, task_keywords, competitor_names)

        top_features = sorted(data["features"].items(), key=lambda x: len(x[1]), reverse=True)[:5]
        top_issues = sorted(data["issues"].items(), key=lambda x: len(x[1]), reverse=True)[:5]
        top_expectations = sorted(data["expectations"].items(), key=lambda x: len(x[1]), reverse=True)[:5]

        heat = round(data["total_cii"], 1)
        score = round(_calculate_score(data["total_cii"], mentions), 1)

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
            "top_features": [f[0] for f in top_features],
            "top_issues": [i[0] for i in top_issues],
            "top_expectations": [e[0] for e in top_expectations],
            "post_ids": list(data["post_ids"]),
        }

        # 添加合并来源信息
        if data["merged_from"]:
            result["merged_from"] = list(data["merged_from"])

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
    competitor_entities = [e for e in formatted_entities if e["role"] == "competitor"][:top_n]

    # 构建完整融合数据（数组格式）
    aggregated_entities = []
    for data in entity_data.values():
        mentions = len(data["post_ids"])
        if mentions == 0:
            continue

        derived_sentiment = 0.0
        if data["total_cii"] > 0:
            derived_sentiment = round(data["sentiment_weighted_sum"] / data["total_cii"], 2)

        heat = round(data["total_cii"], 1)
        score = round(_calculate_score(data["total_cii"], mentions), 1)

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
            "features": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["features"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "issues": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["issues"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "expectations": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["expectations"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "audience": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["audience"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "scenarios": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["scenarios"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "market_factors": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["market_factors"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "competitors": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["competitors"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
        }

        # 添加合并来源信息
        if data["merged_from"]:
            entity_dict["merged_from"] = list(data["merged_from"])

        aggregated_entities.append(entity_dict)

    aggregated_entities.sort(key=lambda x: x["score"], reverse=True)

    result = {
        "top_entities": top_entities,
        "target_entities": target_entities,
        "competitor_entities": competitor_entities,
        "aggregated_entities": aggregated_entities,
    }

    # 添加 LLM token 统计（如果有）
    if llm_token_stats:
        result["llm_token_stats"] = llm_token_stats

    return result
