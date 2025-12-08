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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from collections import defaultdict, Counter

from src.langchain.chains.entity_normalization_chain import (
    format_entities_for_clustering,
    cluster_entities_with_review_sync,
)
from src.langchain.chains.attribute_cleaning_chain import (
    create_attribute_cleaning_chain,
    format_attributes_for_cleaning,
    parse_cleaning_response,
)
from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_score,
    normalize_name,
    are_similar,
    build_similarity_mapping,
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
    """对实体进行主体角色分类 (Legacy / Fallback)

    主要用于旧版展示逻辑或 LLM 标签缺失时的兜底。
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
                # 新增：竞品共现统计，用于生成线索
                "competitor_stats": Counter(),
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
            # 处理 competitors：既要存 post_id 索引，也要存统计计数
            for comp in entity.get("competitors", []):
                if comp:
                    data["competitors"][comp].add(post_id)
                    data["competitor_stats"][comp] += 1

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


def _extract_for_llm(raw_entity_data: dict[str, dict]) -> list[dict[str, Any]]:
    """从原始实体数据中提取 LLM 归一化所需的信息
    
    提取 name, type, mentions, heat, score, hint
    - hint: 基于高频竞品生成的线索
    """
    result = []
    for data in raw_entity_data.values():
        # 生成线索：Top 3 高频竞品
        hint_text = ""
        if data["competitor_stats"]:
            top_competitors = [item[0] for item in data["competitor_stats"].most_common(3)]
            hint_text = f"常与 {', '.join(top_competitors)} 对比"

        result.append({
            "name": data["name"],
            "type": data["type"],
            "mentions": len(data["post_ids"]),
            "heat": round(data["heat"], 1),
            "score": round(calculate_score(data["heat"], len(data["post_ids"])), 1),
            "hint": hint_text,
        })
    return result


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
    sorted_entities = sorted(raw_entities, key=lambda x: x.get("score", 0), reverse=True)[:max_entities]

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

    # 打印 LLM 输入
    print("\n" + "=" * 80)
    print("[实体归一化] LLM 输入内容 (含线索)")
    print("=" * 80)
    print(f"输入实体数量: {len(entities_list)}")
    print(f"锚点关键词: {task_keywords}")
    print("-" * 40)
    print(formatted_input)
    print("=" * 80 + "\n")

    # 调用两阶段归一化 (注意：现在返回 tags_mapping)
    result, token_stats = cluster_entities_with_review_sync(
        formatted_input,
        invoke_chain_with_stats_sync,
        task_keywords=task_keywords,  # 传入锚点
        enable_review=enable_review,
        llm_type="chat",
    )

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

    # 打印每个归一化组的详情 (含标签)
    if normalized_groups:
        print("\n  归一化组详情:")
        for i, group in enumerate(normalized_groups, 1):
            canonical = group.get("canonical_name", "")
            merged = group.get("merged_entities", [])
            tags = group.get("tags", {})
            print(f"    [{i}] {canonical} <- {merged}")
            print(f"        Tags: {tags}")

    print("-" * 40 + "\n")

    summary = token_stats.get('summary', {}) if token_stats else {}
    logger.info(
        f"[实体归一化] LLM: {len(entities_list)} -> {output_count} 个, "
        f"calls={summary.get('total_calls', 0)}, "
        f"tokens={summary.get('total_tokens', 0)}, cost=¥{summary.get('total_cost_cny', 0):.4f}"
    )

    return result.get("entity_mapping", {}), result.get("tags_mapping", {}), token_stats


def build_entity_name_mapping(
    raw_entities: list[dict[str, Any]],
    task_keywords: list[str],
    enable_llm: bool = True,
    max_entities: int = 50,
) -> tuple[dict[str, str], dict[str, dict], dict[str, Any] | None]:
    """构建实体名称映射与标签

    Returns:
        tuple: (name_mapping, tags_mapping, token_stats)
    """
    token_stats = None
    raw_count = len(raw_entities)
    tags_mapping: dict[str, dict] = {} # {标准名称: tags}

    if not raw_entities:
        return {}, {}, None

    # 程序相似度映射
    similarity_mapping = build_similarity_mapping(raw_entities)
    after_similarity_count = len(set(similarity_mapping.values()))
    similarity_merged = raw_count - after_similarity_count

    logger.info(f"[实体归一化] 程序相似度: {raw_count} -> {after_similarity_count} 个")

    # 3. LLM 同义词映射（可选）
    if enable_llm and len(raw_entities) >= 5:
        try:
            llm_mapping, llm_tags_mapping, token_stats = _build_llm_mapping(
                raw_entities, task_keywords, max_entities
            )
            
            # 保存 tags 映射
            tags_mapping = llm_tags_mapping

            if llm_mapping:
                # 合并映射：LLM 映射优先级更高
                for name, canonical in llm_mapping.items():
                    if name in similarity_mapping:
                        old_canonical = similarity_mapping[name]
                        # 级联更新：将映射到 old_canonical 的所有名称都更新为 canonical
                        for k, v in list(similarity_mapping.items()):
                            if v == old_canonical:
                                similarity_mapping[k] = canonical
                
                final_unique = len(set(similarity_mapping.values()))
                logger.info(f"[名称映射] LLM 归一化后: {final_unique} 个唯一实体")
        except Exception as e:
            logger.warning(f"[名称映射] LLM 归一化失败，使用程序映射: {e}")

    return similarity_mapping, tags_mapping, token_stats


# ============================================================================
# 属性清洗
# ============================================================================

def _clean_entity_attributes_sync(
    entity_data: dict[str, dict],
    top_n_scores: set[float],
    top_k_attrs: int = 50,  # 新增：每个字段只清洗Top K
    invoke_with_stats_fn = invoke_chain_with_stats_sync,
    llm_type: str = "chat",
) -> tuple[dict[str, dict], dict[str, Any]]:
    """对 Top N 实体的属性进行同步清洗 (并发执行)
    
    Args:
        entity_data: 已聚合的实体数据 {canonical_name: data}
        top_n_scores: 需要清洗的实体评分集合
        top_k_attrs: 每个属性字段最多发送给LLM的短语数量
        
    Returns:
        (清洗后的实体数据, token统计)
    """
    token_stats = {
        'summary': {'total_calls': 0, 'total_tokens': 0, 'total_cost_cny': 0.0},
        'call_details': []
    }
    
    fields_to_clean = ["features", "issues", "expectations"]
    try:
        # 预先创建 chain 可能会有线程安全问题，但在 LangChain Runnable 中通常是安全的。
        # 为了更安全，可以在每个线程中创建，或者确保 Runnable 是无状态的。
        # 这里为了简单，假设 Runnable 是线程安全的 (ChatPromptTemplate + ChatModel 通常是)。
        cleaning_chain = create_attribute_cleaning_chain()
    except Exception as e:
        logger.warning(f"[属性清洗] 初始化 LLM 失败，跳过清洗: {e}")
        return entity_data, token_stats
    
    # 筛选需要清洗的实体
    entities_to_clean = [
        e for e in entity_data.values() 
        if calculate_score(e["total_cii"], len(e["post_ids"])) in top_n_scores
    ]
    
    logger.info(f"[属性清洗] 开始清洗 {len(entities_to_clean)} 个 Top 实体的属性 (Top K={top_k_attrs}, 并发)")
    print(f"\n[属性清洗] 开始清洗 {len(entities_to_clean)} 个 Top 实体的属性 (Top K={top_k_attrs}, 并发)")
    
    # 定义单个清洗任务
    def clean_single_field(entity_name, field, raw_map):
        if not raw_map:
            return None
            
        # 过滤低频词 (至少出现1次，测试环境调整)
        # 同时按频次降序排序，为 Top K 截断做准备
        sorted_terms = sorted(
            [(k, v) for k, v in raw_map.items() if len(v) >= 1],
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        # 如果有效词太少 (<2)，不清洗，直接使用原始数据
        if len(sorted_terms) < 2:
            return None
            
        # 截取 Top K 发送给 LLM
        terms_to_clean = sorted_terms[:top_k_attrs]
        # 剩下的长尾词 (不清洗，保持原样)
        tail_terms = sorted_terms[top_k_attrs:]
        
        # 构建待清洗的映射
        valid_terms_map = {k: v for k, v in terms_to_clean}
        
        # 格式化输入
        formatted_attrs = format_attributes_for_cleaning(valid_terms_map)
        
        # [Debug] 打印输入
        debug_input = f"[属性清洗 DEBUG] 实体 '{entity_name}' 字段 '{field}' 输入:\n{formatted_attrs}"
        logger.info(debug_input)
        print(f"\n{debug_input}")
        
        try:
            # 调用 LLM
            response, stats = invoke_with_stats_fn(
                cleaning_chain,
                {"attributes": formatted_attrs},
                llm_type
            )
            
            response_text = response.content if hasattr(response, "content") else str(response)
            clusters = parse_cleaning_response(response_text)
            
            # [Debug] 打印输出
            import json
            debug_output = f"[属性清洗 DEBUG] 实体 '{entity_name}' 字段 '{field}' 输出:\n{json.dumps(clusters, ensure_ascii=False, indent=2)}"
            logger.info(debug_output)
            print(f"\n{debug_output}")
            
            if not clusters:
                return None
                
            # 重建映射：{standard_term: all_post_ids}
            new_map = defaultdict(set)
            
            # 1. 加入清洗后的聚类
            cleaned_original_terms = set()  # 记录已被清洗的词
            for cluster in clusters:
                label = cluster.get("label")
                originals = cluster.get("original_terms", [])
                
                if not label:
                    continue
                    
                for term in originals:
                    if term in raw_map:
                        new_map[label].update(raw_map[term])
                        cleaned_original_terms.add(term)
                        
            # 2. 加入虽在 Top K 但未被 LLM 归入任何聚类的词 (通常不应发生，但为了保险)
            for term, post_ids in terms_to_clean:
                if term not in cleaned_original_terms:
                    new_map[term].update(post_ids)
                    
            # 3. 加入长尾词 (保留原始数据)
            for term, post_ids in tail_terms:
                new_map[term].update(post_ids)
            
            return {
                "entity_name": entity_name,
                "field": field,
                "new_map": new_map,
                "stats": stats
            }
                
        except Exception as e:
            logger.error(f"[属性清洗] 实体 {entity_name} 字段 {field} 清洗失败: {e}")
            return None

    # 提交所有任务
    tasks = []
    # 使用 max_workers=10 (或根据实际 LLM API 并发限制调整)
    with ThreadPoolExecutor(max_workers=10) as executor:
        for entity in entities_to_clean:
            for field in fields_to_clean:
                raw_map = entity.get(field, {})
                if raw_map:
                    tasks.append(executor.submit(clean_single_field, entity["name"], field, raw_map))
        
        # 收集结果
        for future in as_completed(tasks):
            result = future.result()
            if result:
                # 更新实体数据
                # 注意：这里需要再次查找 entity 对象，因为是引用传递，直接修改即可
                # 但我们需要找到对应的 entity 对象。由于 entity_data 是 dict，我们可以通过 name 找到吗？
                # entity_data 是 {canonical_name: data}
                # clean_single_field 返回了 entity_name (canonical_name)
                entity_name = result["entity_name"]
                field = result["field"]
                new_map = result["new_map"]
                stats = result["stats"]
                
                if entity_name in entity_data:
                    entity_data[entity_name][field] = new_map
                
                # 合并统计
                if stats:
                    s = stats.get('summary', {})
                    token_stats['summary']['total_calls'] += s.get('total_calls', 0)
                    token_stats['summary']['total_input_tokens'] = token_stats['summary'].get('total_input_tokens', 0) + s.get('total_input_tokens', 0)
                    token_stats['summary']['total_output_tokens'] = token_stats['summary'].get('total_output_tokens', 0) + s.get('total_output_tokens', 0)
                    token_stats['summary']['total_tokens'] += s.get('total_tokens', 0)
                    token_stats['summary']['total_cost_cny'] += s.get('total_cost_cny', 0.0)
                    token_stats['summary']['total_duration_seconds'] = token_stats['summary'].get('total_duration_seconds', 0.0) + s.get('total_duration_seconds', 0.0)
                    token_stats['call_details'].extend(stats.get('call_details', []))

    return entity_data, token_stats


# ============================================================================
# 根据名称映射合并原始实体数据
# ============================================================================

def _merge_by_mapping(
    raw_entity_data: dict[str, dict],
    name_mapping: dict[str, str],
    tags_mapping: dict[str, dict],  # 新增
    post_cii_map: dict[int, float],
) -> dict[str, dict]:
    """根据名称映射合并原始实体数据，并应用标签"""
    merged_data: dict[str, dict] = {}

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
    top_k_attrs: int = 50,  # 新增参数
) -> dict[str, Any]:
    """聚合任务内的实体，生成焦点地图"""
    start_time = time.time()
    task_keywords = task_keywords or []

    # ========================================
    # 1. 收集原始实体完整数据（只遍历一次！）
    # ========================================
    raw_entity_data, post_cii_map = _collect_raw_entities_full(posts_data)

    # ========================================
    # 2. 基于收集的数据构建名称映射与标签
    # ========================================
    raw_entities_for_llm = _extract_for_llm(raw_entity_data)
    name_mapping, tags_mapping, llm_token_stats = build_entity_name_mapping(
        raw_entities_for_llm,
        task_keywords,
        enable_llm=enable_llm_normalization,
    )

    # ========================================
    # 3. 根据映射合并原始数据（无需再遍历 posts_data）
    # ========================================
    entity_data = _merge_by_mapping(
        raw_entity_data, 
        name_mapping, 
        tags_mapping, 
        post_cii_map
    )

    logger.info(f"[实体聚合] {len(raw_entity_data)} 个唯一实体 -> 归一化后 {len(entity_data)} 个")

    # ========================================
    # 4. 属性清洗 (新增)
    # ========================================
    # 先确定 Top N 实体的分数线
    all_scores = [
        calculate_score(e["total_cii"], len(e["post_ids"])) 
        for e in entity_data.values()
    ]
    all_scores.sort(reverse=True)
    top_n_scores = set(all_scores[:top_n])
    
    if enable_llm_normalization:
        entity_data, cleaning_stats = _clean_entity_attributes_sync(
            entity_data,
            top_n_scores,
            top_k_attrs=top_k_attrs
        )
        
        # 合并 token 统计
        if cleaning_stats and llm_token_stats:
            s1 = llm_token_stats.get('summary', {})
            s2 = cleaning_stats.get('summary', {})
            
            # 累加所有数值字段
            s1['total_calls'] += s2.get('total_calls', 0)
            s1['total_input_tokens'] += s2.get('total_input_tokens', 0)
            s1['total_output_tokens'] += s2.get('total_output_tokens', 0)
            s1['total_tokens'] += s2.get('total_tokens', 0)
            s1['total_cost_cny'] += s2.get('total_cost_cny', 0.0)
            s1['total_duration_seconds'] += s2.get('total_duration_seconds', 0.0)
            
            # 重新计算平均值
            if s1['total_calls'] > 0:
                s1['avg_tokens_per_call'] = s1['total_tokens'] / s1['total_calls']
                s1['avg_cost_per_call'] = s1['total_cost_cny'] / s1['total_calls']
                
            llm_token_stats['call_details'].extend(cleaning_stats.get('call_details', []))
        elif cleaning_stats:
            llm_token_stats = cleaning_stats

    # ========================================
    # 5. 提取竞品名称、角色分类 (Legacy / Helper)
    # ========================================
    competitor_names = extract_competitor_names(entity_data, task_keywords)

    # ========================================
    # 6. 格式化输出
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
        score = round(calculate_score(data["total_cii"], mentions), 1)

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
        
        # 添加多维标签
        if data.get("tags"):
            result["tags"] = data["tags"]

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
        score = round(calculate_score(data["total_cii"], mentions), 1)

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
        
        # 添加多维标签
        if data.get("tags"):
            entity_dict["tags"] = data["tags"]

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
        # 计算总耗时 (Wall Clock Time)
        execution_duration = time.time() - start_time
        
        # 将 API 累计耗时重命名为 total_api_duration_seconds
        if 'total_duration_seconds' in llm_token_stats['summary']:
            llm_token_stats['summary']['total_api_duration_seconds'] = llm_token_stats['summary']['total_duration_seconds']
            
        # 使用实际执行时间覆盖 total_duration_seconds，以符合 AnalysisJob 的语义
        llm_token_stats['summary']['total_duration_seconds'] = execution_duration
        
        result["llm_token_stats"] = llm_token_stats

    return result
