"""聚合模块共享工具函数

提供实体聚合和观点聚合共用的工具函数，避免代码重复。
"""

import math
import re
from difflib import SequenceMatcher


import logging
from typing import Any, List, Callable, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


def run_parallel_normalization(
    tasks: List[dict],
    chain_factory: Callable[[], Runnable],
    invoke_func: Callable,
    parse_response_func: Callable[[str], Any],
    llm_type: str = "chat",
    max_workers: int = 10,
    task_name_key: str = "task_id",
) -> tuple[List[dict], dict]:
    """通用并行归一化执行器
    
    统一处理并行调用 LLM、异常捕获和 Token 统计汇总。
    
    Args:
        tasks: 任务列表，每个 task 必须包含 chain 需要的 input_variables
        chain_factory: 创建 chain 的工厂函数
        invoke_func: invoke_chain_with_stats_sync 函数
        parse_response_func: 响应解析函数
        llm_type: LLM 类型
        max_workers: 最大并发数
        task_name_key: 用于日志记录的任务标识键名 (如 'group_key' 或 'entity_name')
        
    Returns:
        tuple: (results, combined_token_stats)
            - results: List[{ "task": original_task, "parsed_result": result, "stats": stats }]
            - combined_token_stats: 汇总后的 token 统计字典
    """
    results = []
    combined_stats = {
        'summary': {
            'total_calls': 0,
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'total_cost_cny': 0.0,
            'total_duration_seconds': 0.0,
        },
        'call_details': [],
    }
    
    if not tasks:
        return results, combined_stats

    logger.info(f"[并行归一化] 准备执行 {len(tasks)} 个任务 (max_workers={max_workers})")

    # 定义单个执行任务
    def _run_single_task(task_input):
        task_id = task_input.get(task_name_key, "unknown")
        try:
            # 在线程中创建 chain (确保线程安全)
            chain = chain_factory()
            
            # 调用 LLM
            # 注意：invoke_func (invoke_chain_with_stats_sync) 的签名通常是 (chain, inputs, llm_type)
            # task_input 中包含了 chain 需要的所有参数
            response, stats = invoke_func(chain, task_input, llm_type)
            
            response_text = response.content if hasattr(response, "content") else str(response)
            parsed_result = parse_response_func(response_text)
            
            return {
                "task": task_input,
                "parsed_result": parsed_result,
                "stats": stats,
                "success": True
            }
        except Exception as e:
            logger.error(f"[并行归一化] 任务 '{task_id}' 失败: {e}", exc_info=True)
            return {
                "task": task_input,
                "error": str(e),
                "success": False
            }

    # 并行执行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_task = {executor.submit(_run_single_task, task): task for task in tasks}
        
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                if not result["success"]:
                    continue
                    
                results.append(result)
                
                # 汇总统计
                stats = result.get("stats")
                if stats:
                    s = stats.get('summary', {})
                    combined_stats['summary']['total_calls'] += s.get('total_calls', 0)
                    combined_stats['summary']['total_input_tokens'] = combined_stats['summary'].get('total_input_tokens', 0) + s.get('total_input_tokens', 0)
                    combined_stats['summary']['total_output_tokens'] = combined_stats['summary'].get('total_output_tokens', 0) + s.get('total_output_tokens', 0)
                    combined_stats['summary']['total_tokens'] += s.get('total_tokens', 0)
                    combined_stats['summary']['total_cost_cny'] += s.get('total_cost_cny', 0.0)
                    # duration 不需要累加用于计费，但用于统计总的计算资源占用
                    combined_stats['summary']['total_duration_seconds'] += s.get('total_duration_seconds', 0.0)
                    combined_stats['call_details'].extend(stats.get('call_details', []))
                    
            except Exception as e:
                logger.error(f"[并行归一化] 线程执行异常: {e}", exc_info=True)

    # 重新计算平均值
    total_calls = combined_stats['summary']['total_calls']
    if total_calls > 0:
        combined_stats['summary']['avg_tokens_per_call'] = (
            combined_stats['summary']['total_tokens'] / total_calls
        )
        combined_stats['summary']['avg_cost_per_call'] = (
            combined_stats['summary']['total_cost_cny'] / total_calls
        )

    return results, combined_stats


def calculate_score(heat: float, mentions: int) -> float:
    """计算综合评分：heat × log(mentions + 1)

    综合考虑影响力（heat）和讨论广泛性（mentions）

    Args:
        heat: CII 加权热度
        mentions: 提及次数（唯一帖子数）

    Returns:
        float: 综合评分
    """
    return heat * math.log(mentions + 1)


def normalize_name(name: str) -> str:
    """归一化名称：去除空格、转小写

    Args:
        name: 原始名称

    Returns:
        str: 归一化后的名称
    """
    return re.sub(r"\s+", "", name.lower())


def are_similar(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """判断两个名称是否相似

    使用 SequenceMatcher 计算相似度，支持：
    - 完全包含关系
    - 字符序列相似度

    Args:
        name1: 名称1
        name2: 名称2
        threshold: 相似度阈值，默认 0.8

    Returns:
        bool: 是否相似
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    # 完全相同
    if n1 == n2:
        return True

    # 包含关系
    if n1 in n2 or n2 in n1:
        return True

    # 字符相似度
    ratio = SequenceMatcher(None, n1, n2).ratio()
    return ratio >= threshold


def build_similarity_mapping(
    items: list[dict],
    threshold: float = 0.8,
    name_key: str = "name",
    score_key: str = "score",
) -> dict[str, str]:
    """构建程序相似度映射（相似度 >= threshold 合并）

    通用的相似度映射构建函数，适用于实体和观点。

    Args:
        items: 待处理项列表，每个包含 name_key 和 score_key 字段
        threshold: 相似度阈值，默认 0.8
        name_key: 名称字段名，默认 "name"
        score_key: 评分字段名，默认 "score"

    Returns:
        dict: {原始名称: 标准名称}
    """
    name_mapping: dict[str, str] = {}
    canonical_list: list[str] = []

    # 按综合评分排序，高分优先成为标准名称
    sorted_items = sorted(items, key=lambda x: x.get(score_key, 0), reverse=True)

    for item in sorted_items:
        name = item[name_key]

        # 检查是否与已有标准名称相似
        matched_canonical = None
        for canonical in canonical_list:
            if are_similar(name, canonical, threshold):
                matched_canonical = canonical
                break

        if matched_canonical:
            name_mapping[name] = matched_canonical
        else:
            name_mapping[name] = name
            canonical_list.append(name)

    return name_mapping
