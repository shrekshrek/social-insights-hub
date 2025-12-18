from __future__ import annotations

import logging
from sqlalchemy import select

from src.database import SyncSessionLocal
from src.social_media.analysis.models import ProjectAnalysisSnapshot, AnalysisType
from src.social_media.analysis.jobs import create_analysis_job_sync, complete_analysis_job_sync

from .utils import ensure_stage_state, now_iso, set_step, merge_token_usage_stats
from .entity_aggregation import normalize_entity_aliases, build_entities_aligned
from .opinion_aggregation import normalize_opinion_aliases_by_category, build_topics_aligned
from .drivers import build_drivers_from_entities
from .insights import build_topic_aspects_from_topics
from .summary import generate_project_summary

logger = logging.getLogger(__name__)


def run_project_snapshot_pipeline_sync(
    *,
    snapshot_id: int,
    top_terms_for_llm: int = 160,
    min_cell_mentions: int = 5,
) -> dict:
    """项目级快照 Stage2 + Stage3 编排（分步写回 stage2.steps / stage3）"""
    db = SyncSessionLocal()
    try:
        stmt = select(ProjectAnalysisSnapshot).where(ProjectAnalysisSnapshot.id == snapshot_id)
        snapshot = db.execute(stmt).scalar_one_or_none()
        if not snapshot:
            return {"status": "failed", "error": "snapshot_not_found", "snapshot_id": snapshot_id}

        result = snapshot.result_data or {}
        if not isinstance(result, dict):
            result = {}
        stage2, stage3 = ensure_stage_state(result)
        stage2.setdefault("jobs", {})

        # 初始化
        stage2["status"] = "processing"
        stage2["started_at"] = stage2.get("started_at") or now_iso()
        stage2["updated_at"] = now_iso()
        snapshot.result_data = result
        db.commit()

        details = result.get("details") or {}
        top_entities = details.get("top_entities") or []
        top_topics = details.get("top_topics") or []
        if not isinstance(top_entities, list) or not top_entities:
            stage2.update({"status": "skipped", "reason": "no_top_entities", "generated_at": now_iso()})
            result["stage2"] = stage2
            snapshot.result_data = result
            db.commit()
            return {"status": "skipped", "snapshot_id": snapshot_id}

        # Step 1: 实体归一（程序 + LLM）→ 产出 entities_aligned
        set_step(stage2, "entity_normalization", "processing")
        snapshot.result_data = result
        db.commit()
        scope = (result.get("meta") or {}).get("scope") or {}
        task_keywords = scope.get("keywords") if isinstance(scope.get("keywords"), list) else []

        # 为实体归一创建 AI 任务记录（AnalysisJob）
        entity_job = create_analysis_job_sync(
            db=db,
            project_id=snapshot.project_id,
            task_id=None,
            user_id=snapshot.user_id,
            analysis_type=AnalysisType.ENTITY_NORMALIZATION.value,
            source_count=len([e for e in top_entities if isinstance(e, dict)]),
            analysis_config={"snapshot_id": snapshot_id, "step": "entity_normalization"},
            status="processing",
        )
        entity_job.source_task_ids = snapshot.included_task_ids
        db.commit()
        stage2["jobs"]["entity_normalization_job_id"] = entity_job.id
        stage2["steps"]["entity_normalization"]["job_id"] = entity_job.id
        snapshot.result_data = result
        db.commit()

        ent_norm = normalize_entity_aliases(
            top_entities=[e for e in top_entities if isinstance(e, dict)],
            task_keywords=[str(x) for x in task_keywords if x],
        )
        stage2.setdefault("alias_normalization", {})
        stage2["alias_normalization"]["entities"] = {
            "used": bool(ent_norm.get("used")),
            "token_stats": ent_norm.get("token_stats"),
            "entity_mapping": ent_norm.get("entity_mapping") or {},
            "tags_mapping": ent_norm.get("tags_mapping") or {},
            "before_count": len([e for e in top_entities if isinstance(e, dict)]),
            "after_count": None,
        }
        set_step(stage2, "entity_normalization", "completed", llm_used=bool(ent_norm.get("used")))
        # 先基于 entity_mapping 构造 entities_aligned（后续衍生全部用对齐后的）
        entities_aligned = build_entities_aligned(
            top_entities=[e for e in top_entities if isinstance(e, dict)],
            entity_mapping=stage2.get("alias_normalization", {}).get("entities", {}).get("entity_mapping", {}) or {},
            tags_mapping=stage2.get("alias_normalization", {}).get("entities", {}).get("tags_mapping", {}) or {},
        )
        stage2["alias_normalization"]["entities"]["after_count"] = len(entities_aligned)

        # 完成实体归一 job（token_usage 与任务级一致）
        token_usage_entity = ent_norm.get("token_stats") or {"summary": {"total_calls": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0, "total_cost_cny": 0.0, "total_duration_seconds": 0.0}, "call_details": []}
        complete_analysis_job_sync(
            db=db,
            job=entity_job,
            analyzed_count=len(entities_aligned),
            token_usage=token_usage_entity,
            result_data={
                "snapshot_id": snapshot_id,
                "before_count": stage2["alias_normalization"]["entities"]["before_count"],
                "after_count": len(entities_aligned),
                "llm_used": bool(ent_norm.get("used")),
            },
            error_message=None,
        )
        snapshot.result_data = result
        db.commit()

        # Step 2: 观点归一（包含类目对齐 + 程序 + LLM）→ 产出 topics_aligned
        set_step(stage2, "opinion_normalization", "processing")
        snapshot.result_data = result
        db.commit()

        # 为观点归一创建 AI 任务记录（把类目对齐也算入该 job 的 token_usage，保持“任务级一条 opinion_normalization”风格）
        opinion_job = create_analysis_job_sync(
            db=db,
            project_id=snapshot.project_id,
            task_id=None,
            user_id=snapshot.user_id,
            analysis_type=AnalysisType.OPINION_NORMALIZATION.value,
            source_count=len([t for t in top_topics if isinstance(t, dict)]),
            analysis_config={"snapshot_id": snapshot_id, "step": "opinion_normalization"},
            status="processing",
        )
        opinion_job.source_task_ids = snapshot.included_task_ids
        db.commit()
        stage2["jobs"]["opinion_normalization_job_id"] = opinion_job.id
        stage2["steps"]["opinion_normalization"]["job_id"] = opinion_job.id
        snapshot.result_data = result
        db.commit()

        op_norm = normalize_opinion_aliases_by_category(
            top_topics=[t for t in top_topics if isinstance(t, dict)],
        )
        topics_for_norm = op_norm.get("topics_for_norm") or []
        stage2["category_alignment"] = (op_norm.get("category_alignment") or {})
        stage2.setdefault("alias_normalization", {})
        stage2["alias_normalization"]["topics"] = {
            "used": bool(op_norm.get("used")),
            "token_stats_list": op_norm.get("token_stats_list") or [],
            "topic_mapping_by_category": op_norm.get("topic_mapping_by_category") or {},
            "before_count": len([t for t in top_topics if isinstance(t, dict)]),
            "after_count": None,
        }
        set_step(stage2, "opinion_normalization", "completed", llm_used=bool(op_norm.get("used")) or bool((stage2.get("category_alignment") or {}).get("used")))
        topics_aligned = build_topics_aligned(
            topics_for_norm=[t for t in topics_for_norm if isinstance(t, dict)],
            topic_mapping_by_category=stage2.get("alias_normalization", {}).get("topics", {}).get("topic_mapping_by_category", {}) or {},
        )
        stage2["alias_normalization"]["topics"]["after_count"] = len(topics_aligned)

        # opinion job token_usage = category_alignment(token_stats) + topics(token_stats_list)
        token_stats_parts: list[dict] = []
        if (stage2.get("category_alignment") or {}).get("token_stats"):
            token_stats_parts.append((stage2.get("category_alignment") or {}).get("token_stats"))
        token_stats_parts.extend(stage2["alias_normalization"]["topics"].get("token_stats_list") or [])
        token_usage_opinion = merge_token_usage_stats(token_stats_parts)
        complete_analysis_job_sync(
            db=db,
            job=opinion_job,
            analyzed_count=len(topics_aligned),
            token_usage=token_usage_opinion,
            result_data={
                "snapshot_id": snapshot_id,
                "before_count": stage2["alias_normalization"]["topics"]["before_count"],
                "after_count": len(topics_aligned),
                "llm_used": bool(op_norm.get("used")) or bool(stage2.get("category_alignment", {}).get("used")),
            },
            error_message=None,
        )
        snapshot.result_data = result
        db.commit()

        # Step 3: 程序化衍生分析（严格：基于归一后的实体/观点）
        set_step(stage2, "derived_analysis", "processing")
        snapshot.result_data = result
        db.commit()
        drv = build_drivers_from_entities(
            top_entities=entities_aligned,
            top_terms_for_llm=top_terms_for_llm,
            min_cell_mentions=min_cell_mentions,
        )
        if drv.get("status") != "completed":
            stage2["drivers"] = {"status": "skipped", "reason": drv.get("reason")}
            set_step(stage2, "drivers", "completed", llm_used=False)
        else:
            stage2["llm"] = drv.get("llm")
            stage2["drivers"] = drv.get("drivers")
            # derived_analysis 的 llm_used 主要参考 drivers 是否使用了 LLM
            set_step(stage2, "derived_analysis", "processing", llm_used=bool((drv.get("llm") or {}).get("used")))
        snapshot.result_data = result
        db.commit()

        # insights：对齐后的 details + aspects（严格：全部基于 topics_aligned / entities_aligned）
        snapshot.result_data = result
        db.commit()
        aspects_v2 = build_topic_aspects_from_topics(topics_aligned)

        stage2["details_aligned"] = {
            "top_entities": entities_aligned[:60],
            "top_topics": topics_aligned[:60],
            "topic_aspects_aligned_v2": aspects_v2,
        }

        set_step(stage2, "derived_analysis", "completed")
        stage2["status"] = "completed"
        stage2["generated_at"] = now_iso()
        snapshot.result_data = result
        db.commit()

        # Stage3 summary
        set_step(stage2, "summary", "processing")
        # 生成 summary 的同时创建 AI 任务记录（AnalysisJob）
        summary_job = create_analysis_job_sync(
            db=db,
            project_id=snapshot.project_id,
            task_id=None,
            user_id=snapshot.user_id,
            analysis_type=AnalysisType.PROJECT_SNAPSHOT_SUMMARY.value,
            source_count=1,
            analysis_config={"snapshot_id": snapshot_id, "step": "summary"},
            status="processing",
        )
        summary_job.source_task_ids = snapshot.included_task_ids
        db.commit()
        stage2["jobs"]["project_snapshot_summary_job_id"] = summary_job.id
        stage2["steps"]["summary"]["job_id"] = summary_job.id
        snapshot.result_data = result
        db.commit()

        stage3 = result.get("stage3") if isinstance(result.get("stage3"), dict) else {}
        stage3["status"] = "processing"
        stage3["started_at"] = stage3.get("started_at") or now_iso()
        stage3["updated_at"] = now_iso()
        result["stage3"] = stage3
        snapshot.result_data = result
        db.commit()

        meta = result.get("meta") or {}
        overview = result.get("overview") or {}
        charts = result.get("charts") or {}
        drivers_matrix = ((stage2.get("drivers") or {}).get("entity_matrix") or []) if isinstance(stage2.get("drivers"), dict) else []

        summ = generate_project_summary(
            meta=meta,
            overview=overview,
            charts=charts,
            topic_aspects_aligned_v2=aspects_v2,
            entities_aligned=entities_aligned,
            topics_aligned=topics_aligned,
            drivers_matrix=drivers_matrix,
        )
        stage3 = result.get("stage3") if isinstance(result.get("stage3"), dict) else {}
        stage3["status"] = summ.get("status") or "failed"
        stage3["updated_at"] = now_iso()
        if summ.get("status") == "completed":
            stage3["generated_at"] = now_iso()
            stage3["summary"] = summ.get("summary") or {}
        else:
            stage3["error"] = summ.get("error") or "unknown_error"
        stage3["llm"] = summ.get("llm") or {}
        result["stage3"] = stage3
        set_step(stage2, "summary", "completed")
        # 完成 summary job
        token_usage_summary = (summ.get("llm") or {}).get("token_stats") or {"summary": {"total_calls": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0, "total_cost_cny": 0.0, "total_duration_seconds": 0.0}, "call_details": []}
        complete_analysis_job_sync(
            db=db,
            job=summary_job,
            analyzed_count=1,
            token_usage=token_usage_summary,
            result_data={"snapshot_id": snapshot_id, "status": stage3.get("status")},
            error_message=None if stage3.get("status") == "completed" else (stage3.get("error") or "summary_failed"),
        )
        snapshot.result_data = result
        db.commit()

        return {"status": "completed", "snapshot_id": snapshot_id, "stage2": stage2.get("status"), "stage3": stage3.get("status")}
    finally:
        db.close()


