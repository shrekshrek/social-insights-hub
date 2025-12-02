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
from typing import Any
from collections import defaultdict

from src.langchain.chains.category_normalization_chain import (
    create_category_normalization_chain,
    format_categories_for_normalization,
    parse_category_normalization_response,
)
from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_score,
    build_similarity_mapping,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Category 映射构建（程序相似度 + LLM同义词）
# ============================================================================

def _collect_raw_categories(posts_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 posts_data 收集所有原始 category 名称（去重，带提及数和热度）

    热度计算规则：每个帖子的 CII 只对每个 category 累加一次（避免重复计算）
    提及数规则：每个帖子只对每个 category 计数一次
    """
    # 内部数据结构：{category: {"mentions": int, "heat": float, "cii_added_posts": set}}
    category_data: dict[str, dict] = {}

    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 0) or 0
        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        # 收集该帖子中出现的所有 categories（去重）
        post_categories: set[str] = set()

        for opinion in post_deep_result.get("general_opinions", []):
            category = opinion.get("category", "")
            if category:
                post_categories.add(category)

        for opinion in comment_deep_result.get("general_opinions", []):
            category = opinion.get("category", "")
            if category:
                post_categories.add(category)

        # 更新每个 category 的统计（每帖只计一次）
        for category in post_categories:
            if category not in category_data:
                category_data[category] = {
                    "mentions": 0,
                    "heat": 0.0,
                    "cii_added_posts": set(),
                }

            data = category_data[category]
            data["mentions"] += 1  # 提及帖子数 +1

            # CII 只累加一次（每帖每 category）
            if post_id and post_id not in data["cii_added_posts"]:
                data["heat"] += cii
                data["cii_added_posts"].add(post_id)

    return [
        {
            "name": name,
            "type": "话题",
            "mentions": data["mentions"],
            "heat": round(data["heat"], 1),
            "score": round(calculate_score(data["heat"], data["mentions"]), 1),
        }
        for name, data in category_data.items()
    ]


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

    # 按综合评分排序，取 Top N
    sorted_categories = sorted(raw_categories, key=lambda x: x.get("score", 0), reverse=True)[:max_categories]

    # 格式化输入内容
    formatted_input = format_categories_for_normalization(sorted_categories)
    keywords_str = ", ".join(task_keywords) if task_keywords else "无"

    # 打印 LLM 输入
    print("\n" + "=" * 80)
    print("[观点归一化] LLM 输入内容")
    print("=" * 80)
    print(f"任务关键词: {keywords_str}")
    print(f"输入话题数量: {len(sorted_categories)}")
    print("-" * 40)
    print(formatted_input)
    print("=" * 80 + "\n")

    # 调用 LLM（使用带统计的版本）
    chain = create_category_normalization_chain()
    response, token_stats = invoke_chain_with_stats_sync(
        chain,
        {
            "keywords": keywords_str,
            "categories": formatted_input,
        },
        llm_type="chat",
    )
    response_text = response.content if hasattr(response, "content") else str(response)
    result = parse_category_normalization_response(response_text)

    # 打印 LLM 输出
    print("\n" + "=" * 80)
    print("[观点归一化] LLM 输出内容")
    print("=" * 80)
    print(response_text)
    print("=" * 80)

    # 统计融合效果
    normalized_groups = result.get("normalized_groups", [])
    standalone_categories = result.get("standalone_categories", [])
    output_count = len(normalized_groups) + len(standalone_categories)

    print("\n" + "-" * 40)
    print(f"[观点归一化] 融合统计:")
    print(f"  输入话题数: {len(sorted_categories)}")
    print(f"  归一化组数: {len(normalized_groups)}")
    print(f"  独立话题数: {len(standalone_categories)}")
    print(f"  输出话题数: {output_count}")
    print(f"  合并减少数: {len(sorted_categories) - output_count}")

    # 打印每个归一化组的详情
    if normalized_groups:
        print("\n  归一化组详情:")
        for i, group in enumerate(normalized_groups, 1):
            canonical = group.get("canonical_name", "")
            merged = group.get("merged_categories", [])
            print(f"    [{i}] {canonical} <- {merged}")

    print("-" * 40 + "\n")

    summary = token_stats.get('summary', {})
    logger.info(
        f"[观点归一化] LLM 调用完成: "
        f"tokens={summary.get('total_tokens', 0)}, "
        f"cost=¥{summary.get('total_cost_cny', 0):.4f}, "
        f"输入={len(sorted_categories)} -> 输出={output_count}"
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
    raw_count = len(raw_categories)

    if not raw_categories:
        return {}, None

    # 2. 程序相似度映射
    similarity_mapping = build_similarity_mapping(raw_categories)
    after_similarity_count = len(set(similarity_mapping.values()))
    similarity_merged = raw_count - after_similarity_count

    # 打印程序归一化统计
    print("\n" + "=" * 80)
    print("[观点归一化] 程序相似度归一化统计")
    print("=" * 80)
    print(f"  原始唯一话题数: {raw_count}")
    print(f"  程序合并后数量: {after_similarity_count}")
    print(f"  程序合并减少数: {similarity_merged}")
    print(f"  发送给 LLM 数量: min({after_similarity_count}, 50) = {min(after_similarity_count, 50)}")
    print("=" * 80 + "\n")

    logger.info(f"[Category映射] 收集到 {raw_count} 个唯一话题")
    logger.info(f"[Category映射] 程序相似度合并: {similarity_merged} 对 -> {after_similarity_count} 个")

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

        # 计算综合评分
        heat = round(data["total_cii"], 1)
        score = round(calculate_score(data["total_cii"], mentions), 1)

        # 构建完整融合数据（数组格式）
        opinion_dict = {
            "category": data["category"],
            "canonical_category": data["canonical_category"],
            "sentiment": data["sentiment"],
            "heat": heat,
            "mentions": mentions,
            "score": score,
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
            "heat": heat,
            "mentions": mentions,
            "score": score,
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

    # 按综合评分排序
    issues.sort(key=lambda x: x["score"], reverse=True)
    features.sort(key=lambda x: x["score"], reverse=True)
    aggregated_opinions.sort(key=lambda x: x["score"], reverse=True)

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
