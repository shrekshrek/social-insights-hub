"""Research Agent Celery 任务

同步执行 LangGraph 研究图，通过 AnalysisJob 追踪 token/cost。
Celery gevent worker 中必须使用 sync invoke，不用 asyncio.run。
"""

import logging

from src.celery_app import celery_app
from src.database import SyncSessionLocal
from src.jobs.factory import (
    create_analysis_job_sync,
    start_analysis_job_sync,
    complete_analysis_job_sync,
)
from src.jobs.models import AnalysisJob
from src.research_agent.models import ResearchTask

logger = logging.getLogger(__name__)


@celery_app.task(
    name="research_agent.run_research",
    bind=True,
    max_retries=0,
    time_limit=600,
    soft_time_limit=570,
)
def run_research_task(self, research_task_id: int) -> None:
    """执行研究任务

    流程：
    1. 加载 ResearchTask，创建 AnalysisJob
    2. 同步运行 LangGraph 研究图
    3. 保存结果到 ResearchTask.result_data
    4. 完成 AnalysisJob
    """
    db = SyncSessionLocal()
    try:
        task = db.get(ResearchTask, research_task_id)
        if not task:
            logger.error("ResearchTask %d not found", research_task_id)
            return

        # 创建 AnalysisJob
        job = create_analysis_job_sync(
            db=db,
            user_id=task.user_id,
            analysis_type="research",
            source_count=0,
            celery_task_id=self.request.id or "",
            analysis_config=task.search_config,
        )
        task.job_id = job.id
        task.status = "running"
        db.commit()

        start_analysis_job_sync(db, job)
        db.commit()

        # 执行 LangGraph 研究图（同步）
        from src.research_agent.graph import run_research

        search_config = task.search_config or {}
        result_state = run_research(
            query=task.query,
            research_questions=task.research_questions or [],
            research_type=search_config.get("research_type"),
        )

        # 组装结构化结果
        selected = result_state.get("selected", [])
        sources = [
            {
                "id": f"src_{i}",
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "source": s.get("source", ""),
                "source_tier": s.get("source_tier", "tier3"),
                "content_type": s.get("content_type", "html"),
                "relevance_score": s.get("relevance_score", 0.0),
            }
            for i, s in enumerate(selected)
        ]

        task.result_data = {
            "findings_by_question": result_state.get("findings_by_question", {}),
            "synthesis": result_state.get("synthesis", ""),
            "sources": sources,
            "coverage": result_state.get("coverage", {}),
            "information_gaps": result_state.get("information_gaps", []),
            "findings": result_state.get("findings", []),
        }
        task.stats = {
            "rounds": result_state.get("round", 1),
            "candidates_total": len(result_state.get("candidates", [])),
            "documents_analyzed": len(selected),
            "synthesis_length": len(result_state.get("synthesis", "")),
        }
        task.status = "completed"

        complete_analysis_job_sync(
            db=db,
            job=job,
            analyzed_count=len(selected),
        )
        db.commit()

        logger.info(
            "ResearchTask %d 完成: %d 条来源, %d 字综合分析",
            research_task_id,
            len(selected),
            len(result_state.get("synthesis", "")),
        )

    except Exception as exc:
        logger.error(
            "ResearchTask %d 失败: %s",
            research_task_id,
            exc,
            exc_info=True,
        )
        db.rollback()

        try:
            task = db.get(ResearchTask, research_task_id)
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:500]
                if task.job_id:
                    job = db.get(AnalysisJob, task.job_id)
                    if job:
                        complete_analysis_job_sync(
                            db=db,
                            job=job,
                            error_message=str(exc)[:500],
                        )
                db.commit()
        except Exception as inner_exc:
            logger.error("更新失败状态时出错: %s", inner_exc)
            db.rollback()
    finally:
        db.close()
