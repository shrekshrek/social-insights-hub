"""社媒切片 → JSON 导出（面向 agent / 知识库的 LLM 直接消费）。

按需投影、不落库。判据与 Stage3 报告 / 策略链喂 LLM 的方式一致：把一二阶计算
结果直接交给 LLM 做后续分析——不让 LLM 重算（排序类预计算物化为名次字段），
也不喂任何链都不会放进 prompt 的噪声。相比原始 result_data 做四类处理：

1. 去三阶 / 运维噪声：剔除 reports（Stage3 叙事综述，是 Word 导出的内容、LLM 可再
   生成）、pipeline（内部流水线状态 / 耗时 / job_id）、meta.task_diagnostics（逐任务
   调试信息）、foundation.drivers.dimension_stats（原始维度词 tally，全系统没有任何
   链喂给 LLM，可用聚合是 entity_matrix）。
2. 去 per-entity 表冗余：aligned_entities / sov_ranking / industry_quadrant 是同一批
   实体的三张重叠表——只保留超集 aligned_entities，并入 sov_ranking 独有的 share，
   并把排名「序」物化为 sov_rank / organic_rank 字段（LLM 直读名次，不再跨实体比较
   数值重排）。名次在全实体集上计算（反映切片内真实排位），不受长尾过滤影响。
3. 实体砍长尾：保留 role∈{target, competitor}（显式追踪的主体 / 竞品必留，呼应
   focus_report 防系统性低估竞品）或 mentions ≥ _MIN_MENTIONS 的实体；单帖偶现的
   长尾 context 实体（多为采集噪声）不进导出。entity_matrix 同步只保留被保留实体的行。
4. 话题砍长尾：保留 mentions ≥ _MIN_MENTIONS 或被 topic_radar（intent 层策展的
   gains / pains / controversies）收录的话题，与报告链喂 LLM 的口径一致。

meta 仅保留识别信息（id / subject / competitors…）+ 采集口径（scope / weights_used，
解释声量数值的权重前提）。
"""

from src.social_media.analysis.models import SocialSlice

# 与 coverage_check 的"≥3 source 才算可靠信号"对齐：单/双帖偶现视为长尾噪声
_MIN_MENTIONS = 3


def _keep_entity(entity: dict) -> bool:
    """显式追踪的主体 / 竞品必留；其余按 mentions 达到可靠信号线才保留。"""
    if (entity.get("role") or "").lower() in ("target", "competitor"):
        return True
    return (entity.get("mentions") or 0) >= _MIN_MENTIONS


def _rank_by(entities: list[dict], value_of) -> dict:
    """按 value_of 降序给实体编名次（1 起），无值的实体不参与排名。"""
    ordered = sorted(
        (e for e in entities if isinstance(value_of(e), (int, float))),
        key=value_of,
        reverse=True,
    )
    return {e.get("name"): i + 1 for i, e in enumerate(ordered)}


def render_social_slice_json(slice_obj: SocialSlice) -> dict:
    """投影单个社媒切片为结构化 JSON（识别元信息 + 去冗余裁剪后的 foundation + layers）。

    调用方需保证 result_data 非空（未完成的切片由端点返回 404）。
    全程浅拷贝 + 新建对象，不修改原 result_data。
    """
    data = slice_obj.result_data or {}
    raw_meta = data.get("meta") or {}
    foundation = dict(data.get("foundation") or {})
    layers = dict(data.get("layers") or {})

    # --- per-entity 表去冗余 + 名次物化 + 砍长尾 ---
    landscape = dict(layers.get("landscape") or {})
    share_by_name = {
        r.get("name"): r.get("share")
        for r in (landscape.get("sov_ranking") or [])
        if isinstance(r, dict) and r.get("name")
    }
    raw_entities = [
        e for e in (foundation.get("aligned_entities") or []) if isinstance(e, dict)
    ]
    sov_rank_by_name = _rank_by(
        raw_entities, lambda e: share_by_name.get(e.get("name"))
    )
    organic_rank_by_name = _rank_by(raw_entities, lambda e: e.get("organic_heat"))

    kept_names: set = set()
    enriched_entities: list = []
    for entity in raw_entities:
        if not _keep_entity(entity):
            continue
        name = entity.get("name")
        kept_names.add(name)
        # 并入 share + 预计算名次（新建对象，不改原 entity）
        extra = {}
        if share_by_name.get(name) is not None:
            extra["share"] = share_by_name[name]
        if name in sov_rank_by_name:
            extra["sov_rank"] = sov_rank_by_name[name]
        if name in organic_rank_by_name:
            extra["organic_rank"] = organic_rank_by_name[name]
        enriched_entities.append({**entity, **extra} if extra else entity)
    foundation["aligned_entities"] = enriched_entities

    # drivers：剔除 dimension_stats；entity_matrix 同步只保留被保留实体的行
    if foundation.get("drivers"):
        drivers = dict(foundation["drivers"])
        drivers.pop("dimension_stats", None)
        if drivers.get("entity_matrix"):
            drivers["entity_matrix"] = [
                row
                for row in drivers["entity_matrix"]
                if isinstance(row, dict) and row.get("entity") in kept_names
            ]
        foundation["drivers"] = drivers

    # 删两张冗余的薄投影表（字段已并入 aligned_entities，序已物化为名次字段）
    landscape.pop("sov_ranking", None)
    landscape.pop("industry_quadrant", None)
    layers["landscape"] = landscape

    # --- 话题砍长尾：可靠信号线以上，或被 intent 层策展（topic_radar）收录 ---
    radar = (layers.get("intent") or {}).get("topic_radar") or {}
    radar_names = {
        t.get("name")
        for bucket in radar.values()
        if isinstance(bucket, list)
        for t in bucket
        if isinstance(t, dict)
    }
    foundation["aligned_topics"] = [
        t
        for t in (foundation.get("aligned_topics") or [])
        if isinstance(t, dict)
        and ((t.get("mentions") or 0) >= _MIN_MENTIONS or t.get("name") in radar_names)
    ]

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
