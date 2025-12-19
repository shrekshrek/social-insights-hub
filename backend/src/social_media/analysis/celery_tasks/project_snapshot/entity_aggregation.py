from __future__ import annotations

import logging
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.social_media.analysis.celery_tasks.aggregation.utils import calculate_score, are_similar
from src.langchain.chains.entity_normalization_chain import (
    format_entities_for_clustering,
    cluster_entities_with_review_sync,
)

from .utils import fallback_alias_map, merge_attr_items

logger = logging.getLogger(__name__)


def _program_cluster_entities(
    entities: list[dict[str, Any]],
    threshold: float = 0.92,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """程序归一：按相似度把实体名预聚类，返回用于 LLM 的压缩列表与 raw->rep 映射。"""
    ents = sorted(
        [e for e in entities if isinstance(e, dict) and (e.get("name") or "").strip()],
        key=lambda x: float(x.get("score") or 0.0),
        reverse=True,
    )

    rep_list: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}

    for e in ents:
        name = (e.get("name") or "").strip()
        if not name:
            continue

        assigned = None
        for rep in rep_list:
            if are_similar(rep["name"], name, threshold=threshold):
                assigned = rep["name"]
                rep.setdefault("_members", []).append(name)
                # 把重要度累加，让 LLM 更关注这个 cluster
                try:
                    rep["score"] = float(rep.get("score") or 0.0) + float(e.get("score") or 0.0)
                except Exception:
                    pass
                break

        if assigned is None:
            rep_item = {
                "name": name,
                "type": e.get("type") or "其他",
                "score": float(e.get("score") or 0.0),
                "hint": e.get("hint") or "",
                "_members": [name],
            }
            rep_list.append(rep_item)
            assigned = name

        mapping[name] = assigned

    # 把 cluster 成员信息塞进 hint，帮助 LLM 在 original_names 中覆盖全量
    for rep in rep_list:
        members = [m for m in rep.get("_members", []) if isinstance(m, str)]
        extras = [m for m in members if m != rep["name"]]
        if extras:
            base = (rep.get("hint") or "").strip()
            suffix = f"同义候选: {', '.join(extras[:8])}"
            rep["hint"] = f"{base} | {suffix}".strip(" |")
        rep.pop("_members", None)

    return rep_list, mapping


def normalize_entity_aliases(
    *,
    top_entities: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    topn: int = 200,
) -> dict[str, Any]:
    """Stage2-B1：实体别名归一（先程序预聚类，再 LLM 两阶段归一；失败降级）。"""
    task_keywords = task_keywords or []
    entity_llm_used = False
    entity_token_stats: dict[str, Any] | None = None
    entity_mapping: dict[str, str] = {}
    tags_mapping: dict[str, Any] = {}
    entity_mapping_program: dict[str, str] = {}
    # 统计信息
    input_count = 0
    program_clustered_count = 0
    input_names: list[str] = []

    try:
        ents_sorted = sorted(
            [e for e in top_entities if isinstance(e, dict) and (e.get("name") or "").strip()],
            key=lambda x: float(x.get("score") or 0.0),
            reverse=True,
        )[:topn]

        ent_inputs = []
        for e in ents_sorted:
            name = (e.get("name") or "").strip()
            etype = str(e.get("type") or "")
            score = float(e.get("score") or 0.0)
            p = (e.get("platform_distribution") or {}) if isinstance(e.get("platform_distribution"), dict) else {}
            k = (e.get("keyword_distribution") or {}) if isinstance(e.get("keyword_distribution"), dict) else {}
            p_hint = ",".join([kk for kk, _ in sorted(p.items(), key=lambda x: x[1], reverse=True)[:2]])
            k_hint = ",".join([kk for kk, _ in sorted(k.items(), key=lambda x: x[1], reverse=True)[:2]])
            hint = f"平台:{p_hint} 关键词:{k_hint}".strip()
            ent_inputs.append({"name": name, "type": etype or "其他", "score": score, "hint": hint})
            input_names.append(name)
        input_count = len(ent_inputs)

        # 程序预聚类（减少 token + 给 LLM original_names 提示）
        ent_inputs_program, entity_mapping_program = _program_cluster_entities(ent_inputs)
        program_clustered_count = len(ent_inputs_program)

        formatted = format_entities_for_clustering(ent_inputs_program)
        if formatted.strip():
            # 项目级：输入已是各任务级归一后的精华，只需别名合并，无需复查修正
            llm_result, stats = cluster_entities_with_review_sync(
                formatted,
                invoke_chain_with_stats_sync,
                task_keywords=task_keywords,
                enable_review=False,  # 项目级跳过复查阶段
                llm_type="chat",
            )
            entity_mapping = (llm_result or {}).get("entity_mapping") or {}
            tags_mapping = (llm_result or {}).get("tags_mapping") or {}
            if entity_mapping:
                entity_llm_used = True
                entity_token_stats = stats
    except Exception as e:
        logger.error(f"[Snapshot Stage2] Entity alias normalization failed: {e}", exc_info=True)

    if not entity_mapping:
        # 降级：优先用程序预聚类的映射
        if entity_mapping_program:
            entity_mapping = dict(entity_mapping_program)
        else:
            names = [str(e.get("name")).strip() for e in top_entities if isinstance(e, dict) and e.get("name")]
            entity_mapping = fallback_alias_map(names)

    # 补全：确保程序聚类成员都有映射（避免 LLM 漏掉某些 original_names）
    if entity_mapping_program:
        for raw, rep in entity_mapping_program.items():
            if raw in entity_mapping:
                continue
            entity_mapping[raw] = entity_mapping.get(rep, rep)

    # ========== 输出归一化差异总结 ==========
    merged_groups: dict[str, list[str]] = {}
    for raw, canon in entity_mapping.items():
        if raw != canon:
            merged_groups.setdefault(canon, []).append(raw)
    
    final_unique = list(set(entity_mapping.values()))
    
    logger.info("=" * 60)
    logger.info(f"[项目级实体归一化] 统计总结:")
    logger.info(f"  - 原始输入: {input_count} 个实体")
    logger.info(f"  - 程序归一后: {program_clustered_count} 个实体")
    logger.info(f"  - LLM 归一后: {len(final_unique)} 个实体")
    logger.info(f"  - 被合并的实体组数: {len(merged_groups)}")
    logger.info(f"  - LLM 是否使用: {entity_llm_used}")
    
    # 打印输入实体名称（前30）
    if input_names:
        logger.info(f"[项目级实体归一化] 输入实体名称（前30）:")
        logger.info(f"  {input_names[:30]}")
    
    # 打印归一化后的实体名称（前30）
    if final_unique:
        sorted_final = sorted(final_unique)[:30]
        logger.info(f"[项目级实体归一化] 归一化后实体名称（前30）:")
        logger.info(f"  {sorted_final}")
    
    if merged_groups:
        logger.info(f"[项目级实体归一化] 合并详情（显示前 20 组）:")
        for i, (canon, members) in enumerate(sorted(merged_groups.items(), key=lambda x: len(x[1]), reverse=True)[:20]):
            logger.info(f"  {i+1}. [{canon}] ← {members}")
    logger.info("=" * 60)

    return {
        "used": entity_llm_used,
        "token_stats": entity_token_stats,
        "entity_mapping": entity_mapping,
        "tags_mapping": tags_mapping,
        "program_mapping": entity_mapping_program,
        # 统计信息：原始数量、程序归一后送入 LLM 的数量
        "input_count": input_count,
        "program_clustered_count": program_clustered_count,
    }


def build_entities_aligned(
    *,
    top_entities: list[dict[str, Any]],
    entity_mapping: dict[str, str],
    tags_mapping: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """根据 entity_mapping 合并 Stage1 top_entities，产出对齐后的实体列表。"""
    tags_mapping = tags_mapping or {}
    bucket: dict[str, dict[str, Any]] = {}
    for e in top_entities or []:
        if not isinstance(e, dict):
            continue
        raw_name = (e.get("name") or "").strip()
        if not raw_name:
            continue
        canon = (entity_mapping.get(raw_name) or raw_name).strip()
        b = bucket.get(canon)
        if not b:
            b = {
                "name": canon,
                "type": e.get("type"),
                "role": e.get("role"),
                "heat": 0.0,
                "mentions": 0,
                "platform_distribution": {},
                "keyword_distribution": {},
                "top_features": [],
                "top_issues": [],
                "original_names": [],
            }
            bucket[canon] = b
        b["original_names"].append(raw_name)
        b["heat"] += float(e.get("heat") or 0.0)
        b["mentions"] += int(e.get("mentions") or 0)
        for k, v in (e.get("platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["platform_distribution"][k] = int(b["platform_distribution"].get(k, 0)) + vv
        for k, v in (e.get("keyword_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["keyword_distribution"][k] = int(b["keyword_distribution"].get(k, 0)) + vv
        b["top_features"].extend(e.get("top_features") or [])
        b["top_issues"].extend(e.get("top_issues") or [])

    aligned: list[dict[str, Any]] = []
    for _, b in bucket.items():
        mentions = int(b["mentions"] or 0)
        heat = float(b["heat"] or 0.0)
        score = float(calculate_score(heat, mentions)) if mentions > 0 else 0.0
        aligned.append({
            "name": b["name"],
            "type": b.get("type"),
            "role": (tags_mapping.get(b["name"], {}) or {}).get("role") or b.get("role"),
            "parent": (tags_mapping.get(b["name"], {}) or {}).get("parent") or "",
            "heat": round(heat, 3),
            "mentions": mentions,
            "score": round(score, 3),
            "platform_distribution": b["platform_distribution"],
            "keyword_distribution": b["keyword_distribution"],
            "top_features": merge_attr_items(b.get("top_features")),
            "top_issues": merge_attr_items(b.get("top_issues")),
            "original_names": sorted(set(b["original_names"])),
        })
    aligned.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return aligned


