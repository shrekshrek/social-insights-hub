"""Spam Distribution Builder

为全部分析模块附加 spam 分布信息，统一入口，三种处理模式：
- 4 维 (SpamDistribution): 实体、观点、IPA、竞品雷达 — 高/低广告 × 原文/评论
- 2 维 (SpamCountBreakdown): 时间分布 — 高/低广告
- 单帖标记 (spam_group): 四象限、KOL 声音
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_spam_map(
    posts_data: list[dict], threshold: float
) -> dict[int, str]:
    """构建 post_id → spam 分组映射，仅处理 spam_score 非 None 的帖子。"""
    spam_map: dict[int, str] = {}
    for post in posts_data:
        score = post.get("spam_score")
        if score is None:
            continue
        post_id = post.get("post_id")
        if post_id is not None:
            spam_map[post_id] = "high" if score >= threshold else "low"
    return spam_map


def _compute_spam_dist_4d(
    post_source_ids: list[int],
    comment_source_ids: list[int],
    spam_map: dict[int, str],
) -> dict[str, dict[str, int]] | None:
    """计算 4 维 spam 分布 (高/低广告 × 原文/评论)。

    Returns None if no source IDs are found in spam_map.
    """
    high_post = 0
    high_comment = 0
    low_post = 0
    low_comment = 0
    found = False

    for pid in post_source_ids:
        group = spam_map.get(pid)
        if group is not None:
            found = True
            if group == "high":
                high_post += 1
            else:
                low_post += 1

    for pid in comment_source_ids:
        group = spam_map.get(pid)
        if group is not None:
            found = True
            if group == "high":
                high_comment += 1
            else:
                low_comment += 1

    if not found:
        return None

    return {
        "high_spam": {
            "total": high_post + high_comment,
            "post": high_post,
            "comment": high_comment,
        },
        "low_spam": {
            "total": low_post + low_comment,
            "post": low_post,
            "comment": low_comment,
        },
    }


def _compute_spam_dist_2d(
    post_ids: list[int], spam_map: dict[int, str]
) -> dict[str, int] | None:
    """计算 2 维 spam 分布 (高/低广告，无原文/评论区分)。

    Returns None if no post IDs are found in spam_map.
    """
    high = 0
    low = 0
    found = False

    for pid in post_ids:
        group = spam_map.get(pid)
        if group is not None:
            found = True
            if group == "high":
                high += 1
            else:
                low += 1

    if not found:
        return None

    return {"high": high, "low": low}


def _compute_spam_group(
    post_id: int | None, spam_map: dict[int, str]
) -> str | None:
    """获取单帖的 spam 分组标记。"""
    if post_id is None:
        return None
    return spam_map.get(post_id)


def build_spam_distributions(
    aggregated_entities: list[dict],
    aggregated_opinions: list[dict],
    quadrant_data: list[dict],
    kol_voices: list[dict],
    ipa_points: list[dict],
    competitor_series: list[dict],
    time_distribution: list[dict],
    posts_data: list[dict],
    threshold: float = 6.0,
) -> dict[str, Any]:
    """为全部分析模块附加 spam 分布信息。

    就地修改传入的数据结构，按数据类型分派处理逻辑。

    Returns:
        spam_config dict (含 threshold)
    """
    spam_map = _build_spam_map(posts_data, threshold)

    # 4 维: 实体
    for entity in aggregated_entities:
        entity["spam_distribution"] = _compute_spam_dist_4d(
            entity.get("post_source_ids", []),
            entity.get("comment_source_ids", []),
            spam_map,
        )

    # 4 维: 观点
    for opinion in aggregated_opinions:
        opinion["spam_distribution"] = _compute_spam_dist_4d(
            opinion.get("post_source_ids", []),
            opinion.get("comment_source_ids", []),
            spam_map,
        )

    # 单帖标记: 四象限
    for point in quadrant_data:
        point["spam_group"] = _compute_spam_group(
            point.get("post_id"), spam_map
        )

    # 单帖标记: KOL 声音
    for voice in kol_voices:
        voice["spam_group"] = _compute_spam_group(
            voice.get("post_id"), spam_map
        )

    # 4 维: IPA 分析
    for point in ipa_points:
        point["spam_distribution"] = _compute_spam_dist_4d(
            point.get("post_source_ids", []),
            point.get("comment_source_ids", []),
            spam_map,
        )

    # 4 维: 竞品雷达
    for series in competitor_series:
        series["spam_distribution"] = _compute_spam_dist_4d(
            series.get("post_source_ids", []),
            series.get("comment_source_ids", []),
            spam_map,
        )

    # 2 维: 时间分布
    for bucket in time_distribution:
        bucket["spam_breakdown"] = _compute_spam_dist_2d(
            bucket.get("post_ids", []), spam_map
        )

    logger.info(
        f"[spam_distribution] 处理完成: "
        f"实体={len(aggregated_entities)}, 观点={len(aggregated_opinions)}, "
        f"四象限={len(quadrant_data)}, KOL={len(kol_voices)}, "
        f"IPA={len(ipa_points)}, 竞品={len(competitor_series)}, "
        f"时间={len(time_distribution)}, spam_map={len(spam_map)}条"
    )

    return {"threshold": threshold}
