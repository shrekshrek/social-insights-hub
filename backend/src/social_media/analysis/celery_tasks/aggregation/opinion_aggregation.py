"""观点聚合模块 (Opinion Aggregation)

负责通用观点 (General Opinions) 的聚合与归一化，生成标准化的舆论观点。
这是 Track B (观点归一化) 的核心实现。

处理流程：
1. 收集所有通用观点，按 category|sentiment 分组
2. 对每个分组调用 LLM 进行属性清洗（复用 attribute_cleaning_chain）
3. 生成标准化的 aggregated_opinions 列表
"""

import logging
import time
from collections import defaultdict, Counter
from typing import Any, List, Dict

from src.langchain.chains.category_normalization_chain import (
    create_category_normalization_chain,
    format_categories_for_normalization,
    parse_category_normalization_response
)
from src.langchain.chains.opinion_normalization_chain import (
    create_opinion_normalization_chain,
    format_opinions_for_normalization,
    parse_normalization_response
)
from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_score, 
    run_parallel_normalization,
    merge_token_stats,
    filter_low_frequency_terms
)

logger = logging.getLogger(__name__)


def _normalize_category(category: str) -> str:
    """标准化分类名称 (简单规则，后续可扩展)"""
    if not category:
        return "其他"
    return category.strip()


def aggregate_opinions(
    posts_data: list[dict[str, Any]],
    top_k_opinions: int = 100,  # 每个分组限制送入 LLM 的观点数量
    llm_type: str = "chat",
) -> Dict[str, Any]:
    """聚合任务内的通用观点，生成标准化观点结果
    
    Args:
        posts_data: 帖子数据列表 (需包含 general_opinions)
        top_k_opinions: 每个分组截取最高频的前 K 个观点进行清洗
        
    Returns:
        dict: {
            "topics": [...],  # 保持字段名兼容，实际是 aggregated_opinions
            "llm_token_stats": {...}
        }
    """
    start_time = time.time()
    token_stats = {
        'summary': {'total_calls': 0, 'total_tokens': 0, 'total_cost_cny': 0.0},
        'call_details': []
    }

    # ========================================
    # 0. 预扫描与类别归一化 (Category Normalization)
    # ========================================
    raw_category_counts: Dict[str, int] = Counter()
    
    # 第一次遍历：统计 Category 频次
    for post in posts_data:
        sources = []
        if post.get("post_deep_result"): sources.append(post["post_deep_result"])
        if post.get("comment_deep_result"): sources.append(post["comment_deep_result"])
        
        for source in sources:
            opinions = source.get("general_opinions", [])
            if isinstance(opinions, list):
                for op_obj in opinions:
                    if isinstance(op_obj, dict):
                        cat = op_obj.get("category", "")
                        if cat:
                            raw_category_counts[cat] += 1

    # 调用 LLM 进行类别映射 (如果类别数 > 5)
    category_map: Dict[str, str] = {}
    if len(raw_category_counts) > 5:
        try:
            logger.info(f"[观点聚合] 开始类别归一化: {len(raw_category_counts)} 个原始类别")
            cat_norm_chain = create_category_normalization_chain()
            formatted_cats = format_categories_for_normalization(dict(raw_category_counts))
            
            cat_response, cat_stats = invoke_chain_with_stats_sync(
                cat_norm_chain,
                {"categories": formatted_cats},
                llm_type
            )
            
            # 合并统计
            if cat_stats:
                merge_token_stats(token_stats, cat_stats)
            
            response_text = cat_response.content if hasattr(cat_response, "content") else str(cat_response)
            category_map = parse_category_normalization_response(response_text)
            logger.info(f"[观点聚合] 类别归一化完成: 映射规则 {len(category_map)} 条")
            
        except Exception as e:
            logger.error(f"[观点聚合] 类别归一化失败: {e}", exc_info=True)

    def get_normalized_category(raw: str) -> str:
        if not raw: return "其他"
        raw = raw.strip()
        # 优先使用 LLM 映射，否则使用默认规则
        return category_map.get(raw, _normalize_category(raw))

    # ========================================
    # 1. 收集与分组 (Category + Sentiment)
    # ========================================
    # 结构: {group_key: {raw_term: set(post_ids)}}
    grouped_raw_opinions: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    # 结构: {group_key: {raw_term: heat}}
    grouped_term_heat: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    
    # 记录每个帖子已经贡献过的 term (避免重复计算热度)
    # post_id -> set(term_key)
    post_contribution_map = defaultdict(set)

    total_posts = len(posts_data)
    valid_posts_count = 0

    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 1.0)
        
        # 收集来源: post_deep_result 和 comment_deep_result
        sources = []
        if post.get("post_deep_result"):
            sources.append(post["post_deep_result"])
        if post.get("comment_deep_result"):
            sources.append(post["comment_deep_result"])
            
        has_opinion = False
        for source in sources:
            opinions = source.get("general_opinions", [])
            if isinstance(opinions, list):
                for op_obj in opinions:
                    if not isinstance(op_obj, dict):
                        continue
                        
                    raw_category = op_obj.get("category", "")
                    sentiment = op_obj.get("sentiment", 0)
                    terms = op_obj.get("opinions", [])
                    
                    # 使用归一化后的 Category
                    category = get_normalized_category(raw_category)
                    group_key = f"{category}|{sentiment}"
                    
                    for term in terms:
                        if term and isinstance(term, str) and len(term) > 1:
                            term_key = f"{group_key}|{term}"
                            
                            grouped_raw_opinions[group_key][term].add(post_id)
                            
                            # 热度累加 (Per Post Per Term 去重)
                            if post_id and term_key not in post_contribution_map[post_id]:
                                grouped_term_heat[group_key][term] += cii
                                post_contribution_map[post_id].add(term_key)
                                
                            has_opinion = True
        
        if has_opinion:
            valid_posts_count += 1

    logger.info(f"[观点聚合] 从 {valid_posts_count}/{total_posts} 个帖子中收集到 {len(grouped_raw_opinions)} 个分组")

    if not grouped_raw_opinions:
        return {"topics": [], "llm_token_stats": token_stats}

    # ========================================
    # 2. 组内归纳 (LLM Opinion Normalization, Parallel)
    # ========================================
    aggregated_opinions = []
    
    # 准备任务列表
    tasks = []
    
    for group_key, raw_map in grouped_raw_opinions.items():
        category, sentiment_str = group_key.split("|")
        sentiment = int(sentiment_str)
        
        # 过滤低频词 (移除：小样本场景下保留长尾词交给 LLM 聚类)
        # filtered_map = filter_low_frequency_terms(raw_map)
        
        # 按频次排序并截取 Top K (直接使用 raw_map)
        sorted_items = sorted(raw_map.items(), key=lambda x: len(x[1]), reverse=True)
        top_k_map = dict(sorted_items[:top_k_opinions])
        
        # 优化：如果不同词条数 <= 5，不需要 LLM 聚类，直接作为结果
        if len(top_k_map) <= 5:
            for term, post_ids in top_k_map.items():
                heat = grouped_term_heat[group_key][term]
                mentions = len(post_ids)
                score = calculate_score(heat, mentions)
                aggregated_opinions.append({
                    "category": category,
                    "sentiment": sentiment,
                    "name": term,
                    "label": term,
                    "heat": round(heat, 1),
                    "mentions": mentions,
                    "score": round(score, 1),
                    "post_ids": list(post_ids),
                    "original_terms": [{"text": term, "count": mentions}],
                })
            continue

        # 格式化输入
        formatted_input = format_opinions_for_normalization(top_k_map)
        
        tasks.append({
            "task_id": group_key,
            "group_key": group_key,
            "category": category,
            "opinions": formatted_input, # input for chain
            "sentiment": sentiment,
            "raw_map": raw_map,
            "top_k_map": top_k_map
        })

    # 使用通用并行执行器
    results, stats = run_parallel_normalization(
        tasks=tasks,
        chain_factory=create_opinion_normalization_chain,
        invoke_func=invoke_chain_with_stats_sync,
        parse_response_func=parse_normalization_response,
        llm_type=llm_type,
        max_workers=10
    )
    
    token_stats = stats # 直接使用返回的统计

    # 处理结果并更新 aggregated_opinions
    for res in results:
        task = res["task"]
        clusters = res["parsed_result"]
        
        group_key = task["group_key"]
        raw_map = task["raw_map"]
        top_k_map = task["top_k_map"]
        category = task["category"]
        sentiment = task["sentiment"]
        
        if not clusters:
            continue

        # ========================================
        # 3. 数据回填与聚合
        # ========================================
        # 处理聚类结果
        processed_terms = set()
        
        for cluster in clusters:
            label = cluster.get("label")
            originals = cluster.get("original_terms", [])
            
            if not label: continue
                
            # 聚合该 label 下的所有数据
            merged_heat = 0.0
            merged_post_ids = set()
            merged_originals = []
            
            for term in originals:
                if term in raw_map:
                    merged_heat += grouped_term_heat[group_key][term]
                    merged_post_ids.update(raw_map[term])
                    # 记录原始词及其频次
                    merged_originals.append({"text": term, "count": len(raw_map[term])})
                    processed_terms.add(term)
            
            if not merged_post_ids:
                continue

            mentions = len(merged_post_ids)
            score = calculate_score(merged_heat, mentions)
            
            aggregated_opinions.append({
                "category": category,
                "sentiment": sentiment,
                "name": label,   # 统一使用 name
                "label": label,  # 兼容旧字段
                "heat": round(merged_heat, 1),
                "mentions": mentions,
                "score": round(score, 1),
                "post_ids": list(merged_post_ids),
                "original_terms": merged_originals, # 统一使用 original_terms
            })
        
        # 处理未被聚类的 Top K 词 (作为独立观点)
        for term, post_ids in top_k_map.items():
            if term not in processed_terms:
                heat = grouped_term_heat[group_key][term]
                mentions = len(post_ids)
                score = calculate_score(heat, mentions)
                
                aggregated_opinions.append({
                    "category": category,
                    "sentiment": sentiment,
                    "name": term,   # 统一使用 name
                    "label": term,  # 兼容旧字段
                    "heat": round(heat, 1),
                    "mentions": mentions,
                    "score": round(score, 1),
                    "post_ids": list(post_ids),
                    "original_terms": [{"text": term, "count": mentions}], # 统一使用 original_terms
                })

    # 按综合评分排序
    aggregated_opinions.sort(key=lambda x: x["score"], reverse=True)

    # 计算总耗时
    execution_duration = time.time() - start_time
    token_stats['summary']['total_duration_seconds'] = execution_duration

    return {
        "topics": aggregated_opinions, # 保持字段名兼容
        "llm_token_stats": token_stats
    }
