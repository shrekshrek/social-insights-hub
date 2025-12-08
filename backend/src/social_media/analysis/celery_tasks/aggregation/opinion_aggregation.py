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

from src.langchain.chains.opinion_normalization_chain import (
    create_opinion_normalization_chain,
    format_opinions_for_normalization,
    parse_normalization_response
)
from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.social_media.analysis.celery_tasks.aggregation.utils import calculate_score

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
                    
                    category = _normalize_category(raw_category)
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
    # 2. 组内归纳 (LLM Opinion Normalization)
    # ========================================
    aggregated_opinions = []
    
    try:
        normalization_chain = create_opinion_normalization_chain()
        
        for group_key, raw_map in grouped_raw_opinions.items():
            category, sentiment_str = group_key.split("|")
            sentiment = int(sentiment_str)
            
            # 过滤低频词
            min_freq = 2 if len(raw_map) > 20 else 1
            filtered_map = {k: v for k, v in raw_map.items() if len(v) >= min_freq}
            
            if not filtered_map:
                continue
                
            # 按频次排序并截取 Top K
            sorted_items = sorted(filtered_map.items(), key=lambda x: len(x[1]), reverse=True)
            top_k_map = dict(sorted_items[:top_k_opinions])
            
            # 格式化输入
            formatted_input = format_opinions_for_normalization(top_k_map)
            
            logger.info(f"[观点聚合] 归一化分组 '{group_key}': {len(top_k_map)} 个观点")
            
            # 调用 LLM
            response, stats = invoke_chain_with_stats_sync(
                normalization_chain,
                {
                    "category": category,
                    "opinions": formatted_input
                },
                llm_type
            )
            
            # 合并统计
            if stats:
                s = stats.get('summary', {})
                token_stats['summary']['total_calls'] += s.get('total_calls', 0)
                token_stats['summary']['total_tokens'] += s.get('total_tokens', 0)
                token_stats['summary']['total_cost_cny'] += s.get('total_cost_cny', 0.0)
                token_stats['call_details'].extend(stats.get('call_details', []))
                
            response_text = response.content if hasattr(response, "content") else str(response)
            clusters = parse_normalization_response(response_text)
            
            # ========================================
            # 3. 数据回填与聚合
            # ========================================
            # 处理聚类结果
            processed_terms = set()
            
            for cluster in clusters:
                label = cluster.get("label")
                originals = cluster.get("original_terms", [])
                
                if not label or not originals:
                    continue
                    
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
                    "label": label,  # 标准观点
                    "name": label,   # 兼容旧字段
                    "heat": round(merged_heat, 1),
                    "mentions": mentions,
                    "score": round(score, 1),
                    "post_ids": list(merged_post_ids),
                    "sub_opinions": merged_originals, # 兼容旧字段
                    "original_terms": merged_originals
                })
            
            # 处理未被聚类的 Top K 词 (作为独立观点)
            # 也可以选择忽略，这里选择保留大头
            for term, post_ids in top_k_map.items():
                if term not in processed_terms:
                    heat = grouped_term_heat[group_key][term]
                    mentions = len(post_ids)
                    score = calculate_score(heat, mentions)
                    
                    aggregated_opinions.append({
                        "category": category,
                        "sentiment": sentiment,
                        "label": term,
                        "name": term,
                        "heat": round(heat, 1),
                        "mentions": mentions,
                        "score": round(score, 1),
                        "post_ids": list(post_ids),
                        "sub_opinions": [{"text": term, "count": mentions}],
                        "original_terms": [{"text": term, "count": mentions}]
                    })
                    
    except Exception as e:
        logger.error(f"[观点聚合] 聚合失败: {e}", exc_info=True)

    # 按综合评分排序
    aggregated_opinions.sort(key=lambda x: x["score"], reverse=True)

    # 计算总耗时
    execution_duration = time.time() - start_time
    token_stats['summary']['total_duration_seconds'] = execution_duration

    return {
        "topics": aggregated_opinions, # 保持字段名兼容
        "llm_token_stats": token_stats
    }
