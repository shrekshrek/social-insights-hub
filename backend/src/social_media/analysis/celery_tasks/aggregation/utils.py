"""聚合模块共享工具函数

提供实体聚合和观点聚合共用的工具函数，避免代码重复。
"""

import math
import re
from difflib import SequenceMatcher


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
