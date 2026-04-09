from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.database import SyncSessionLocal
from src.analysis.models import AnalysisSlice
from src.jobs.models import AnalysisType
from src.jobs import (
    create_analysis_job_sync,
    complete_analysis_job_sync,
)

from src.analysis.constants import TOP_TERMS_FOR_LLM, MIN_CELL_MENTIONS
from .utils import ensure_pipeline_state, now_iso, set_step, merge_token_usage_stats
from .entity_aggregation import normalize_entity_aliases, build_entities_aligned
from .opinion_aggregation import (
    normalize_opinion_aliases_by_category,
    build_topics_aligned,
)
from .drivers import build_drivers_from_entities
from .insights import build_slice_layers
from .summary import generate_project_reports

logger = logging.getLogger(__name__)


def run_monitor_slice_pipeline_sync(
    *,
    slice_id: int,
    top_terms_for_llm: int = TOP_TERMS_FOR_LLM,
    min_cell_mentions: int = MIN_CELL_MENTIONS,
) -> dict:
    """项目级切片 Stage2 + Stage3 编排

    写回结构：result_data.pipeline.stage2（归一化步骤）/ pipeline.stage3（报告生成）
    衍生数据（drivers）写入 result_data.foundation.drivers（不属于执行状态追踪）。
    """
    db = SyncSessionLocal()
    try:
        stmt = select(AnalysisSlice).where(
            AnalysisSlice.id == slice_id
        )
        slice_record = db.execute(stmt).scalar_one_or_none()
        if not slice_record:
            return {
                "status": "failed",
                "error": "slice_not_found",
                "slice_id": slice_id,
            }

        # 重要：result_data 是 JSON 字段，原地修改默认不会被 SQLAlchemy 追踪到（导致不落库）
        result = slice_record.result_data or {}
        if not isinstance(result, dict):
            result = {}
        # 触发变更追踪：用新 dict 承载本次流水线更新
        result = dict(result)
        stage2, stage3 = ensure_pipeline_state(result)
        stage2.setdefault("jobs", {})

        def commit_result():
            slice_record.result_data = result
            flag_modified(slice_record, "result_data")
            db.commit()

        # 初始化
        stage2["status"] = "processing"
        stage2["started_at"] = stage2.get("started_at") or now_iso()
        stage2["updated_at"] = now_iso()
        commit_result()

        try:
            return _run_pipeline_body(
                db=db,
                slice_record=slice_record,
                slice_id=slice_id,
                result=result,
                stage2=stage2,
                stage3=stage3,
                commit_result=commit_result,
                top_terms_for_llm=top_terms_for_llm,
                min_cell_mentions=min_cell_mentions,
            )
        except Exception:
            logger.exception(
                "[项目切片] 流水线异常中止: slice_id=%s", slice_id
            )
            # 标记当前阶段为 failed，避免永远卡在 processing
            if stage2.get("status") == "processing":
                stage2["status"] = "failed"
                stage2["error"] = "pipeline_exception"
                stage2["updated_at"] = now_iso()
            elif stage3.get("status") == "processing":
                stage3["status"] = "failed"
                stage3["error"] = "pipeline_exception"
                stage3["updated_at"] = now_iso()
            try:
                commit_result()
            except Exception:
                logger.exception(
                    "[项目切片] 异常恢复写入失败: slice_id=%s", slice_id
                )
            return {
                "status": "failed",
                "error": "pipeline_exception",
                "slice_id": slice_id,
            }
    finally:
        db.close()


def _run_pipeline_body(
    *,
    db,
    slice_record,
    slice_id: int,
    result: dict,
    stage2: dict,
    stage3: dict,
    commit_result,
    top_terms_for_llm: int,
    min_cell_mentions: int,
) -> dict:
    """流水线主体逻辑（从 run_monitor_slice_pipeline_sync 提取，便于统一异常处理）。"""

    foundation = (
        result.get("foundation")
        if isinstance(result.get("foundation"), dict)
        else {}
    )
    top_entities = foundation.get("aligned_entities") or []
    top_topics = foundation.get("aligned_topics") or []
    if not isinstance(top_entities, list) or not top_entities:
        stage2.update(
            {
                "status": "skipped",
                "reason": "no_top_entities",
                "generated_at": now_iso(),
            }
        )
        commit_result()
        return {"status": "skipped", "slice_id": slice_id}

    scope = (result.get("meta") or {}).get("scope") or {}
    task_keywords = (
        scope.get("keywords") if isinstance(scope.get("keywords"), list) else []
    )
    subject = (result.get("meta") or {}).get("subject")
    competitors = (result.get("meta") or {}).get("competitors")
    if not isinstance(competitors, list):
        competitors = []

    # ========== 并行：实体归一 + 观点归一 ==========
    # 1. 先创建两个 AnalysisJob（串行，很快）
    set_step(stage2, "entity_normalization", "processing")
    set_step(stage2, "opinion_normalization", "processing")
    commit_result()

    # 注意：source_count 会在归一化完成后根据实际程序聚类后的数量更新
    entity_job = create_analysis_job_sync(
        db=db,
        social_monitor_id=slice_record.monitor_id,
        task_id=None,
        user_id=slice_record.user_id,
        analysis_type=AnalysisType.ENTITY_NORMALIZATION.value,
        source_count=0,  # 稍后更新为程序归一后的数量
        analysis_config={
            "slice_id": slice_id,
            "step": "entity_normalization",
        },
        status="processing",
    )
    entity_job.source_task_ids = slice_record.included_task_ids
    db.commit()

    opinion_job = create_analysis_job_sync(
        db=db,
        social_monitor_id=slice_record.monitor_id,
        task_id=None,
        user_id=slice_record.user_id,
        analysis_type=AnalysisType.OPINION_NORMALIZATION.value,
        source_count=0,  # 稍后更新为程序归一后的数量
        analysis_config={
            "slice_id": slice_id,
            "step": "opinion_normalization",
        },
        status="processing",
    )
    opinion_job.source_task_ids = slice_record.included_task_ids
    db.commit()

    stage2["jobs"]["entity_normalization_job_id"] = entity_job.id
    stage2["jobs"]["opinion_normalization_job_id"] = opinion_job.id
    stage2["steps"]["entity_normalization"]["job_id"] = entity_job.id
    stage2["steps"]["opinion_normalization"]["job_id"] = opinion_job.id
    commit_result()

    # 2. 并行执行两个归一化任务
    def run_entity_normalization():
        return normalize_entity_aliases(
            top_entities=[e for e in top_entities if isinstance(e, dict)],
            task_keywords=[str(x) for x in task_keywords if x],
            subject=str(subject) if subject is not None else None,
            competitors=[str(x) for x in competitors if x],
        )

    def run_opinion_normalization():
        return normalize_opinion_aliases_by_category(
            top_topics=[t for t in top_topics if isinstance(t, dict)],
        )

    logger.info("[项目切片] 并行启动实体归一和观点归一: slice_id=%s", slice_id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_entity = executor.submit(run_entity_normalization)
        future_opinion = executor.submit(run_opinion_normalization)

    # .result() 会重新抛出线程内的异常，由外层 try/except 统一处理
    ent_norm_result = future_entity.result()
    logger.info("[项目切片] 实体归一完成: slice_id=%s", slice_id)
    op_norm_result = future_opinion.result()
    logger.info("[项目切片] 观点归一完成: slice_id=%s", slice_id)

    # 3. 处理实体归一结果
    ent_input_count = ent_norm_result.get("input_count") or len(
        [e for e in top_entities if isinstance(e, dict)]
    )
    ent_program_count = (
        ent_norm_result.get("program_clustered_count") or ent_input_count
    )

    stage2.setdefault("alias_normalization", {})
    stage2["alias_normalization"]["entities"] = {
        "used": bool(ent_norm_result.get("used")),
        "token_stats": ent_norm_result.get("token_stats"),
        "entity_mapping": ent_norm_result.get("entity_mapping") or {},
        "tags_mapping": ent_norm_result.get("tags_mapping") or {},
        "input_count": ent_input_count,
        "program_clustered_count": ent_program_count,
        "after_count": None,
    }
    entities_aligned = build_entities_aligned(
        top_entities=[e for e in top_entities if isinstance(e, dict)],
        entity_mapping=ent_norm_result.get("entity_mapping") or {},
        tags_mapping=ent_norm_result.get("tags_mapping") or {},
    )
    stage2["alias_normalization"]["entities"]["after_count"] = len(entities_aligned)
    set_step(
        stage2,
        "entity_normalization",
        "completed",
        llm_used=bool(ent_norm_result.get("used")),
    )

    # 更新 job 的 source_count（程序归一后送入 LLM 的数量）
    entity_job.source_count = ent_program_count
    db.commit()

    token_usage_entity = ent_norm_result.get("token_stats") or {
        "summary": {
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_cny": 0.0,
            "total_duration_seconds": 0.0,
        },
        "call_details": [],
    }
    complete_analysis_job_sync(
        db=db,
        job=entity_job,
        analyzed_count=len(entities_aligned),
        token_usage=token_usage_entity,
        result_data={
            "slice_id": slice_id,
            "input_count": ent_input_count,
            "program_clustered_count": ent_program_count,
            "after_count": len(entities_aligned),
            "llm_used": bool(ent_norm_result.get("used")),
        },
        error_message=None,
    )

    # 4. 处理观点归一结果
    op_input_count = op_norm_result.get("input_count") or len(
        [t for t in top_topics if isinstance(t, dict)]
    )
    op_program_count = (
        op_norm_result.get("program_clustered_count") or op_input_count
    )

    topics_for_norm = op_norm_result.get("topics_for_norm") or []
    stage2["category_alignment"] = op_norm_result.get("category_alignment") or {}
    stage2["alias_normalization"]["topics"] = {
        "used": bool(op_norm_result.get("used")),
        "token_stats_list": op_norm_result.get("token_stats_list") or [],
        "topic_mapping_by_category": op_norm_result.get("topic_mapping_by_category")
        or {},
        "input_count": op_input_count,
        "program_clustered_count": op_program_count,
        "after_count": None,
    }
    topics_aligned = build_topics_aligned(
        topics_for_norm=[t for t in topics_for_norm if isinstance(t, dict)],
        topic_mapping_by_category=op_norm_result.get("topic_mapping_by_category")
        or {},
    )
    stage2["alias_normalization"]["topics"]["after_count"] = len(topics_aligned)
    set_step(
        stage2,
        "opinion_normalization",
        "completed",
        llm_used=bool(op_norm_result.get("used"))
        or bool(stage2.get("category_alignment", {}).get("used")),
    )

    # 更新 job 的 source_count（程序归一后送入 LLM 的数量）
    opinion_job.source_count = op_program_count
    db.commit()

    token_stats_parts: list[dict] = []
    if stage2.get("category_alignment", {}).get("token_stats"):
        token_stats_parts.append(stage2["category_alignment"]["token_stats"])
    token_stats_parts.extend(
        stage2["alias_normalization"]["topics"].get("token_stats_list") or []
    )
    token_usage_opinion = merge_token_usage_stats(token_stats_parts)
    complete_analysis_job_sync(
        db=db,
        job=opinion_job,
        analyzed_count=len(topics_aligned),
        token_usage=token_usage_opinion,
        result_data={
            "slice_id": slice_id,
            "input_count": op_input_count,
            "program_clustered_count": op_program_count,
            "after_count": len(topics_aligned),
            "llm_used": bool(op_norm_result.get("used"))
            or bool(stage2.get("category_alignment", {}).get("used")),
        },
        error_message=None,
    )
    commit_result()

    # ========== Step 3: 程序化衍生分析（严格：基于归一后的实体/观点）==========
    set_step(stage2, "derived_analysis", "processing")
    commit_result()

    drv = build_drivers_from_entities(
        top_entities=entities_aligned,
        top_terms_for_llm=top_terms_for_llm,
        min_cell_mentions=min_cell_mentions,
    )
    # drivers 写入 foundation（衍生的分析数据，不属于执行状态）
    foundation_for_drv = (
        result.get("foundation") if isinstance(result.get("foundation"), dict) else {}
    )
    if drv.get("status") != "completed":
        foundation_for_drv["drivers"] = {"status": "skipped", "reason": drv.get("reason")}
    else:
        stage2["llm"] = drv.get("llm")
        foundation_for_drv["drivers"] = drv.get("drivers")
        set_step(
            stage2,
            "derived_analysis",
            "processing",
            llm_used=bool((drv.get("llm") or {}).get("used")),
        )
    result["foundation"] = foundation_for_drv
    commit_result()

    # Step0-2 输出对齐：把 Stage2 的对齐结果写回 foundation（不破坏旧字段）
    foundation = (
        result.get("foundation")
        if isinstance(result.get("foundation"), dict)
        else {}
    )
    foundation["aligned_entities"] = entities_aligned[:200]
    foundation["aligned_topics"] = topics_aligned[:200]
    result["foundation"] = foundation

    # Step3：分层指标（Landscape/Topic/Focus）——覆盖 Stage1 预计算的层数据
    layers0 = result.get("layers") if isinstance(result.get("layers"), dict) else {}
    land0 = (
        layers0.get("landscape")
        if isinstance(layers0.get("landscape"), dict)
        else {}
    )
    foundation_cur = (
        result.get("foundation") if isinstance(result.get("foundation"), dict) else {}
    )
    layers = build_slice_layers(
        meta=result.get("meta") or {},
        overview=land0.get("overview")
        if isinstance(land0.get("overview"), dict)
        else {},
        freshness=land0.get("freshness")
        if isinstance(land0.get("freshness"), dict)
        else {},
        entities_aligned=entities_aligned,
        topics_aligned=topics_aligned,
        drivers=foundation_cur.get("drivers")
        if isinstance(foundation_cur.get("drivers"), dict)
        else None,
        # Stage 1 预计算数据透传
        time_distribution=land0.get("time_distribution"),
        kol_voices=land0.get("kol_voices")
        if isinstance(land0.get("kol_voices"), list)
        else None,
    )
    result["layers"] = layers

    set_step(stage2, "derived_analysis", "completed")
    stage2["status"] = "completed"
    stage2["generated_at"] = now_iso()
    commit_result()

    # ========== Stage3：LLM 报告生成 ==========
    summary_job = create_analysis_job_sync(
        db=db,
        social_monitor_id=slice_record.monitor_id,
        task_id=None,
        user_id=slice_record.user_id,
        analysis_type=AnalysisType.MONITOR_SLICE_SUMMARY.value,
        source_count=1,
        analysis_config={"slice_id": slice_id, "step": "summary"},
        status="processing",
    )
    summary_job.source_task_ids = slice_record.included_task_ids
    db.commit()
    stage3["job_id"] = summary_job.id
    stage3["status"] = "processing"
    stage3["started_at"] = stage3.get("started_at") or now_iso()
    stage3["updated_at"] = now_iso()
    commit_result()

    meta = result.get("meta") or {}
    foundation_final = result.get("foundation") or {}
    layers = result.get("layers") or {}
    drivers_matrix = (
        ((foundation_final.get("drivers") or {}).get("entity_matrix") or [])
        if isinstance(foundation_final.get("drivers"), dict)
        else []
    )

    rep = generate_project_reports(
        meta=meta,
        foundation=foundation_final,
        layers=layers,
        drivers_matrix=drivers_matrix,
    )
    stage3["status"] = rep.get("status") or "failed"
    stage3["updated_at"] = now_iso()
    # 即使 stage3 判定为 failed，也写入已生成的部分报告（便于前端展示/排障）
    result["reports"] = rep.get("reports") or {}
    if rep.get("status") == "completed":
        stage3["generated_at"] = now_iso()
    else:
        stage3["error"] = rep.get("error") or "unknown_error"
    stage3["llm"] = rep.get("llm") or {}

    token_usage_summary = (rep.get("llm") or {}).get("token_stats") or {
        "summary": {
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_cny": 0.0,
            "total_duration_seconds": 0.0,
        },
        "call_details": [],
    }
    complete_analysis_job_sync(
        db=db,
        job=summary_job,
        analyzed_count=1,
        token_usage=token_usage_summary,
        result_data={"slice_id": slice_id, "status": stage3.get("status")},
        error_message=None
        if stage3.get("status") == "completed"
        else (stage3.get("error") or "reports_failed"),
    )
    commit_result()

    return {
        "status": "completed",
        "slice_id": slice_id,
        "stage2": stage2.get("status"),
        "stage3": stage3.get("status"),
    }
