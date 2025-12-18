from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_topic_aspects_from_topics(
    topics_aligned: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """基于对齐后的 topics 重新聚合 topic_aspects（Stage2 insights）。"""
    topic_aspects_aligned_v2: list[dict[str, Any]] = []
    asp2: dict[str, dict[str, Any]] = {}

    for t in topics_aligned or []:
        if not isinstance(t, dict):
            continue
        cat = (t.get("category") or "其他").strip() or "其他"
        b = asp2.get(cat)
        if not b:
            b = {
                "category": cat,
                "heat": 0.0,
                "sentiment_sum": 0.0,
                "sentiment_weight": 0.0,
                "mention_count": 0,
                "platform_distribution": defaultdict(int),
                "keyword_distribution": defaultdict(int),
                "top_terms": defaultdict(int),
            }
            asp2[cat] = b

        heat = float(t.get("heat") or 0.0)
        mentions = int(t.get("mentions") or 0)
        sent = float(t.get("sentiment") or 0.0)
        b["heat"] += heat
        b["sentiment_sum"] += sent * float(mentions)
        b["sentiment_weight"] += float(mentions)
        b["mention_count"] += mentions
        b["top_terms"][t.get("name") or ""] += mentions

        for k, v in (t.get("platform_distribution") or {}).items():
            b["platform_distribution"][k] += int(v or 0)
        for k, v in (t.get("keyword_distribution") or {}).items():
            b["keyword_distribution"][k] += int(v or 0)

    for cat, b in asp2.items():
        avg_sent = (b["sentiment_sum"] / b["sentiment_weight"]) if b["sentiment_weight"] > 0 else 0.0
        topic_aspects_aligned_v2.append({
            "category": cat,
            "heat": round(float(b["heat"]), 2),
            "sentiment": round(float(avg_sent), 2),
            "mention_count": int(b["mention_count"]),
            "top_keywords": [k for k, _ in sorted(b["top_terms"].items(), key=lambda x: x[1], reverse=True)[:6] if k],
            "platform_distribution": dict(b["platform_distribution"]),
            "keyword_distribution": dict(b["keyword_distribution"]),
        })

    topic_aspects_aligned_v2.sort(key=lambda x: x.get("heat", 0.0), reverse=True)
    return topic_aspects_aligned_v2


