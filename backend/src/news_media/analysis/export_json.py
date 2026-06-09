"""新闻切片 → JSON 导出（面向 agent / 知识库）。

按需投影、不落库：把切片的二阶结构化数据整体导出，供下游 agent / 知识库消费。
相比 Markdown，JSON 不做 top-N 截断、不丢字段——完整保留实体的分级情感
（sentiment_by_tier / sentiment_weighted_by_tier）、竞争 SOV、事件聚类（首发者 /
时间锚 / tier 加权热度）、报道与情感时间线、跨任务重叠分布等富信号。

剔除 page_synthesis.briefing（headline / key_findings / risks 散文简报）——那是给
业务读者的叙事综述、也是 LLM 自己能从结构化数据再生成的解读；但保留
page_synthesis.event_titles（事件簇的可读标题，给 event_clusters 贴标签，非散文）。
"""

from src.news_media.analysis.models import NewsSlice


def render_news_slice_json(slice_obj: NewsSlice) -> dict:
    """投影单个新闻切片为结构化 JSON（识别元信息 + 二阶聚合/计算/LLM 判断产物）。

    调用方需保证 result_data 非空（未完成的切片由端点返回 404）。
    """
    data = slice_obj.result_data or {}
    page_synthesis = data.get("page_synthesis") or {}
    created = (
        slice_obj.created_at.date().isoformat()
        if getattr(slice_obj, "created_at", None)
        else None
    )
    return {
        "meta": {
            "type": "news_slice",
            "id": slice_obj.id,
            "monitor_id": slice_obj.monitor_id,
            "name": slice_obj.name or None,
            "subject": slice_obj.subject or None,
            "competitors": [c for c in (slice_obj.competitors or []) if c],
            "status": slice_obj.status,
            "created_at": created,
        },
        "descriptive": data.get("descriptive") or {},
        "media_landscape": data.get("media_landscape") or {},
        "entities": data.get("entities") or [],
        "competitive": data.get("competitive") or {},
        "themes": data.get("themes") or [],
        "event_clusters": data.get("event_clusters") or [],
        "event_titles": page_synthesis.get("event_titles") or {},
        "quotes": data.get("quotes") or [],
    }
