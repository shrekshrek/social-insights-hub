"""社媒切片 → JSON 导出（面向 agent / 知识库）。

按需投影、不落库。相比 Markdown，JSON 保留全部富定性字段（top_scenarios /
top_features / top_audience、topic_radar 含 controversy_depth 等 MD 丢掉的二阶信号），
不做无脑 top-N 截断。相比原始 result_data，做三类裁剪让产物可被下游消费：

1. 去三阶 / 运维噪声：剔除 reports（Stage3 叙事综述，是 Word 导出的内容、LLM 可再
   生成）、pipeline（内部流水线状态 / 耗时 / job_id）、meta.task_diagnostics（逐任务
   调试信息）。
2. 去 per-entity 表冗余：aligned_entities / sov_ranking / industry_quadrant 是同一批
   实体的三张重叠表——只保留超集 aligned_entities（并入 sov_ranking 独有的 share 字段），
   删除另两张薄投影。
3. 砍长尾噪声：按实体保留 role∈{target, competitor}（显式追踪的主体 / 竞品必留，呼应
   focus_report 防系统性低估竞品）或 mentions ≥ _MIN_ENTITY_MENTIONS 的实体；单帖偶现
   的长尾 context 实体（多为采集噪声）不进导出。entity_matrix 同步只保留被保留实体的行。

meta 仅保留识别信息（id / subject / competitors…）+ 采集口径（scope / weights_used，
解释声量数值的权重前提）。
"""

from src.social_media.analysis.models import SocialSlice

# 与 coverage_check 的"≥3 source 才算可靠信号"对齐：单/双帖偶现视为长尾噪声
_MIN_ENTITY_MENTIONS = 3


def _keep_entity(entity: dict) -> bool:
    """显式追踪的主体 / 竞品必留；其余按 mentions 达到可靠信号线才保留。"""
    if (entity.get("role") or "").lower() in ("target", "competitor"):
        return True
    return (entity.get("mentions") or 0) >= _MIN_ENTITY_MENTIONS


def render_social_slice_json(slice_obj: SocialSlice) -> dict:
    """投影单个社媒切片为结构化 JSON（识别元信息 + 去冗余裁剪后的 foundation + layers）。

    调用方需保证 result_data 非空（未完成的切片由端点返回 404）。
    全程浅拷贝 + 新建对象，不修改原 result_data。
    """
    data = slice_obj.result_data or {}
    raw_meta = data.get("meta") or {}
    foundation = dict(data.get("foundation") or {})
    layers = dict(data.get("layers") or {})

    # --- per-entity 表去冗余 + 砍长尾 ---
    landscape = dict(layers.get("landscape") or {})
    share_by_name = {
        r.get("name"): r.get("share")
        for r in (landscape.get("sov_ranking") or [])
        if isinstance(r, dict) and r.get("name")
    }
    kept_names: set = set()
    enriched_entities: list = []
    for entity in foundation.get("aligned_entities") or []:
        if not isinstance(entity, dict) or not _keep_entity(entity):
            continue
        kept_names.add(entity.get("name"))
        share = share_by_name.get(entity.get("name"))
        # 并入 sov_ranking 独有的 share（新建对象，不改原 entity）
        enriched_entities.append(
            {**entity, "share": share} if share is not None else entity
        )
    foundation["aligned_entities"] = enriched_entities

    # entity_matrix 同步只保留被保留实体的行
    drivers = dict(foundation.get("drivers") or {})
    if drivers.get("entity_matrix"):
        drivers["entity_matrix"] = [
            row
            for row in drivers["entity_matrix"]
            if isinstance(row, dict) and row.get("entity") in kept_names
        ]
        foundation["drivers"] = drivers

    # 删两张冗余的薄投影表（数据已并入 / 被 aligned_entities 覆盖）
    landscape.pop("sov_ranking", None)
    landscape.pop("industry_quadrant", None)
    layers["landscape"] = landscape

    created = (
        slice_obj.created_at.date().isoformat()
        if getattr(slice_obj, "created_at", None)
        else None
    )
    return {
        "meta": {
            "type": "social_slice",
            "id": slice_obj.id,
            "monitor_id": slice_obj.monitor_id,
            "name": slice_obj.name or None,
            "subject": slice_obj.subject or None,
            "competitors": [c for c in (slice_obj.competitors or []) if c],
            "status": slice_obj.status,
            "created_at": created,
            "scope": raw_meta.get("scope"),
            "weights_used": raw_meta.get("weights_used"),
        },
        "foundation": foundation,
        "layers": layers,
    }
