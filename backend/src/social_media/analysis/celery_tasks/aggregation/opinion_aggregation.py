"""观点聚合模块 (Opinion Aggregation)

负责观点的聚合和归一化。
aggregated_opinions 是后续 insights 分析的核心数据来源。

处理流程：
1. 收集原始 category 名称
2. 构建 category 映射（程序相似度 + LLM同义词）
3. 使用映射按 (category, sentiment) 进行聚合
4. 输出 aggregated_opinions 数组

注意：KANO 需求分层已移至 insights.py，因为它同时依赖 entity 和 opinion 数据。

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md §4.4
"""

import logging
from difflib import SequenceMatcher
from typing import Any
from collections import defaultdict

from src.langchain.chains.category_normalization_chain import (
    create_category_normalization_chain,
    format_categories_for_normalization,
    parse_category_normalization_response,
)
from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync

logger = logging.getLogger(__name__)


# ============================================================================
# Category 名称处理工具函数
# ============================================================================

def _normalize_category_name(name: str) -> str:
    """标准化 category 名称（小写、去空格）"""
    return name.lower().strip()


def _are_similar_categories(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """判断两个 category 名称是否相似（用于合并）

    默认阈值 0.8：适中的合并策略
    - 会合并: "价格" vs "价格问题", "性能" vs "性能表现"
    - 不会合并: "价格" vs "定价"（需要 LLM 处理）
    """
    n1 = _normalize_category_name(name1)
    n2 = _normalize_category_name(name2)
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


# ============================================================================
# Category 映射构建（程序相似度 + LLM同义词）
# ============================================================================

def _collect_raw_categories(posts_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 posts_data 收集所有原始 category 名称（去重，带出现次数）"""
    category_counts: dict[str, int] = {}

    for post in posts_data:
        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        for opinion in post_deep_result.get("general_opinions", []):
            category = opinion.get("category", "")
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

        for opinion in comment_deep_result.get("general_opinions", []):
            category = opinion.get("category", "")
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

    return [
        {"name": name, "type": "话题", "count": count}
        for name, count in category_counts.items()
    ]


def _build_similarity_mapping(raw_categories: list[dict], threshold: float = 0.8) -> dict[str, str]:
    """构建程序相似度映射（相似度 >= threshold 合并）

    Returns:
        dict: {原始名称: 标准名称}
    """
    name_mapping: dict[str, str] = {}
    canonical_list: list[str] = []

    # 按出现次数排序，高频词优先成为标准名称
    sorted_categories = sorted(raw_categories, key=lambda x: x["count"], reverse=True)

    for item in sorted_categories:
        name = item["name"]

        # 检查是否与已有标准名称相似
        matched_canonical = None
        for canonical in canonical_list:
            if _are_similar_categories(name, canonical, threshold):
                matched_canonical = canonical
                break

        if matched_canonical:
            name_mapping[name] = matched_canonical
        else:
            name_mapping[name] = name
            canonical_list.append(name)

    return name_mapping


def _build_llm_mapping(
    raw_categories: list[dict],
    task_keywords: list[str],
    max_categories: int = 50,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """调用 LLM 构建同义词映射

    Returns:
        tuple: (category_mapping, token_stats)
            - category_mapping: {原始名称: 标准名称}
            - token_stats: token 使用统计（如果调用了 LLM）
    """
    if not raw_categories:
        return {}, None

    # 按出现次数排序，取 Top N
    sorted_categories = sorted(raw_categories, key=lambda x: x["count"], reverse=True)[:max_categories]

    # 调用 LLM（使用带统计的版本）
    chain = create_category_normalization_chain()
    response, token_stats = invoke_chain_with_stats_sync(
        chain,
        {
            "keywords": ", ".join(task_keywords) if task_keywords else "无",
            "categories": format_categories_for_normalization(sorted_categories),
        },
        llm_type="chat",
    )
    response_text = response.content if hasattr(response, "content") else str(response)
    result = parse_category_normalization_response(response_text)

    logger.info(
        f"[观点归一化] LLM 调用完成: "
        f"tokens={token_stats.get('total_tokens', 0)}, "
        f"cost=¥{token_stats.get('total_cost_cny', 0):.4f}"
    )

    return result.get("category_mapping", {}), token_stats


def build_category_mapping(
    posts_data: list[dict[str, Any]],
    task_keywords: list[str],
    enable_llm: bool = True,
    max_categories: int = 50,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """构建 category 名称映射（程序相似度 + LLM同义词）

    处理流程：
    1. 收集原始 category 名称
    2. 程序相似度合并（>=0.8）
    3. LLM 同义词合并（可选）
    4. 合并两个映射

    Args:
        posts_data: 帖子数据列表
        task_keywords: 任务关键词
        enable_llm: 是否启用 LLM 归一化
        max_categories: LLM 最多处理的 category 数量

    Returns:
        tuple: (category_mapping, token_stats)
            - category_mapping: {原始名称: 标准名称}
            - token_stats: token 使用统计（如果调用了 LLM）
    """
    token_stats = None

    # 1. 收集原始 category 名称
    raw_categories = _collect_raw_categories(posts_data)
    logger.info(f"[Category映射] 收集到 {len(raw_categories)} 个唯一话题")

    if not raw_categories:
        return {}, None

    # 2. 程序相似度映射
    similarity_mapping = _build_similarity_mapping(raw_categories)
    similarity_merged = len(raw_categories) - len(set(similarity_mapping.values()))
    logger.info(f"[Category映射] 程序相似度合并: {similarity_merged} 对")

    # 3. LLM 同义词映射（可选）
    if enable_llm and len(raw_categories) >= 5:
        try:
            llm_mapping, token_stats = _build_llm_mapping(raw_categories, task_keywords, max_categories)
            if llm_mapping:
                # 合并映射：LLM 映射优先级更高
                for name, canonical in llm_mapping.items():
                    if name in similarity_mapping:
                        old_canonical = similarity_mapping[name]
                        # 使用 list() 避免在迭代时修改 dict
                        for k, v in list(similarity_mapping.items()):
                            if v == old_canonical:
                                similarity_mapping[k] = canonical

                final_unique = len(set(similarity_mapping.values()))
                logger.info(f"[Category映射] LLM 归一化后: {final_unique} 个唯一话题")
        except Exception as e:
            logger.warning(f"[Category映射] LLM 归一化失败，使用程序映射: {e}")

    return similarity_mapping, token_stats


# ============================================================================
# 观点聚合主函数
# ============================================================================

def aggregate_opinions(
    posts_data: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    enable_llm_normalization: bool = True,
    top_n: int = 10,
) -> dict[str, Any]:
    """聚合任务内的观点，按 (category, sentiment) 分组融合

    处理流程：
    1. 构建 category 映射（程序相似度 + LLM同义词）
    2. 使用映射按 (category, sentiment) 进行聚合
    3. 输出 aggregated_opinions 数组

    Args:
        posts_data: 帖子数据列表
        task_keywords: 任务关键词列表
        enable_llm_normalization: 是否启用 LLM 归一化
        top_n: 返回前多少个观点

    Returns:
        dict: {
            "top_issues": 负面观点 TOP N,
            "top_features": 正面观点 TOP N,
            "aggregated_opinions": 完整融合数据（数组格式）,
            "llm_token_stats": LLM token 使用统计（如果调用了 LLM）,
        }
    """
    task_keywords = task_keywords or []

    # ========================================
    # 1. 构建 category 映射（先归一化）
    # ========================================
    category_mapping, llm_token_stats = build_category_mapping(
        posts_data,
        task_keywords,
        enable_llm=enable_llm_normalization,
    )

    def get_canonical_category(category: str) -> str:
        """获取标准 category 名称"""
        return category_mapping.get(category, category)

    # ========================================
    # 2. 使用映射进行聚合
    # ========================================
    # 内部用 dict，O(1) 查找
    # key 格式: "canonical_category|sentiment"
    opinion_data: dict[str, dict] = defaultdict(lambda: {
        "category": "",
        "canonical_category": "",
        "sentiment": 0,
        "total_cii": 0.0,
        "cii_added_posts": set(),
        "post_sources": set(),
        "comment_sources": set(),
        "post_ids": set(),
        "opinions": defaultdict(set),  # 观点文本 -> 帖子ID集合
        "merged_from": set(),  # 记录合并来源
    })

    def process_opinions(opinions: list, post_id: int, cii: float, source: str):
        """处理观点列表，按 (canonical_category, sentiment) 分组"""
        for opinion in opinions:
            raw_category = opinion.get("category", "其他")
            sentiment = opinion.get("sentiment", 0)
            canonical = get_canonical_category(raw_category)

            key = f"{canonical}|{sentiment}"
            data = opinion_data[key]

            # 更新基本信息
            if not data["category"]:
                data["category"] = canonical
                data["canonical_category"] = canonical
                data["sentiment"] = sentiment

            # 记录合并来源
            if raw_category != canonical:
                data["merged_from"].add(raw_category)

            # CII 只累加一次
            if post_id and post_id not in data["cii_added_posts"]:
                data["total_cii"] += cii
                data["cii_added_posts"].add(post_id)

            # 来源标记
            if post_id:
                if source == "post":
                    data["post_sources"].add(post_id)
                else:
                    data["comment_sources"].add(post_id)
                data["post_ids"].add(post_id)

            # 收集观点文本
            for op_text in opinion.get("opinions", []):
                if op_text and post_id:
                    data["opinions"][op_text].add(post_id)

    # 遍历所有帖子
    raw_opinion_count = 0
    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 0) or 0

        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        post_opinions = post_deep_result.get("general_opinions", [])
        raw_opinion_count += len(post_opinions)
        process_opinions(post_opinions, post_id, cii, "post")

        comment_opinions = comment_deep_result.get("general_opinions", [])
        raw_opinion_count += len(comment_opinions)
        process_opinions(comment_opinions, post_id, cii, "comment")

    logger.info(
        f"[观点聚合] 原始 {raw_opinion_count} 条 -> 聚合后 {len(opinion_data)} 个分组"
    )

    # ========================================
    # 3. 格式化输出
    # ========================================
    issues = []  # 负面观点 (sentiment == -1)
    features = []  # 正面观点 (sentiment == 1)
    aggregated_opinions = []  # 数组格式

    for key, data in opinion_data.items():
        mentions = len(data["post_ids"])
        if mentions == 0:
            continue

        post_source_count = len(data["post_sources"])
        comment_source_count = len(data["comment_sources"])
        total_source_count = post_source_count + comment_source_count

        source_distribution = {
            "post": round(post_source_count / total_source_count, 2) if total_source_count > 0 else 0,
            "comment": round(comment_source_count / total_source_count, 2) if total_source_count > 0 else 0,
        }

        # 按帖子数排序观点
        all_opinions = sorted(
            data["opinions"].items(),
            key=lambda x: len(x[1]),
            reverse=True
        )

        # 构建完整融合数据（数组格式）
        opinion_dict = {
            "category": data["category"],
            "canonical_category": data["canonical_category"],
            "sentiment": data["sentiment"],
            "heat": round(data["total_cii"], 1),
            "mentions": mentions,
            "post_source_count": post_source_count,
            "comment_source_count": comment_source_count,
            "post_ids": list(data["post_ids"]),
            "opinions": [
                {"text": op_text, "post_ids": list(op_post_ids)}
                for op_text, op_post_ids in all_opinions
            ],
        }

        # 添加合并来源信息
        if data["merged_from"]:
            opinion_dict["merged_from"] = list(data["merged_from"])

        aggregated_opinions.append(opinion_dict)

        # 构建展示用 item
        item = {
            "topic": data["category"],
            "heat": round(data["total_cii"], 1),
            "mentions": mentions,
            "sentiment": data["sentiment"],
            "source_distribution": source_distribution,
            "top_opinions": [op[0] for op in all_opinions[:3]] if all_opinions else [],
            "post_ids": list(data["post_ids"]),
        }
        if data["merged_from"]:
            item["merged_from"] = list(data["merged_from"])

        # 按情感分类
        if data["sentiment"] == -1:
            issues.append(item)
        elif data["sentiment"] == 1:
            features.append(item)

    # 按热度排序
    issues.sort(key=lambda x: x["heat"], reverse=True)
    features.sort(key=lambda x: x["heat"], reverse=True)
    aggregated_opinions.sort(key=lambda x: x["heat"], reverse=True)

    # 统计日志
    positive_count = len([o for o in aggregated_opinions if o["sentiment"] == 1])
    negative_count = len([o for o in aggregated_opinions if o["sentiment"] == -1])
    neutral_count = len([o for o in aggregated_opinions if o["sentiment"] == 0])
    logger.info(
        f"[观点聚合] 按 (category, sentiment) 分组: "
        f"总计 {len(aggregated_opinions)} 个 (正面 {positive_count}, 负面 {negative_count}, 中性 {neutral_count})"
    )

    result = {
        "top_issues": issues[:top_n],
        "top_features": features[:top_n],
        "aggregated_opinions": aggregated_opinions,
    }

    # 添加 LLM token 统计（如果有）
    if llm_token_stats:
        result["llm_token_stats"] = llm_token_stats

    return result
