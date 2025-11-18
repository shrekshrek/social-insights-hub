"""Celery任务基类

提供带有统计收集功能的Celery任务基类，自动跟踪：
- 任务执行时间
- Token使用量和成本
- 任务状态更新
- 错误处理
"""

import logging
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from src.celery_app import celery_app
from src.database import AsyncSessionLocal
from src.langchain_module.utils import TaskAnalysisStats
from src.analysis.models import TaskAnalysisResult, ProjectAnalysisResult

logger = logging.getLogger(__name__)


class AnalysisTaskBase(Task):
    """分析任务基类

    所有AI分析任务都应继承此基类，自动获得：
    - 统计收集功能
    - 数据库状态更新
    - 错误处理和重试
    """

    def __init__(self):
        super().__init__()
        self._stats: Optional[TaskAnalysisStats] = None
        self._start_time: Optional[float] = None
        self._db_session: Optional[AsyncSession] = None

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """任务开始前的钩子"""
        super().before_start(task_id, args, kwargs)
        self._start_time = time.time()
        self._stats = TaskAnalysisStats()
        logger.info(f"任务 {task_id} 开始执行")

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """任务成功完成的钩子"""
        super().on_success(retval, task_id, args, kwargs)
        processing_time = int(time.time() - self._start_time) if self._start_time else 0
        logger.info(f"任务 {task_id} 成功完成，耗时 {processing_time}秒")

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo) -> None:
        """任务失败的钩子"""
        super().on_failure(exc, task_id, args, kwargs, einfo)
        logger.error(f"任务 {task_id} 失败: {str(exc)}", exc_info=True)

    def on_retry(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo) -> None:
        """任务重试的钩子"""
        super().on_retry(exc, task_id, args, kwargs, einfo)
        logger.warning(f"任务 {task_id} 重试: {str(exc)}")

    def get_stats(self) -> TaskAnalysisStats:
        """获取当前任务的统计信息"""
        if self._stats is None:
            self._stats = TaskAnalysisStats()
        return self._stats

    def get_processing_time(self) -> int:
        """获取当前处理时间（秒）"""
        if self._start_time is None:
            return 0
        return int(time.time() - self._start_time)

    async def update_task_result(
        self,
        result_id: int,
        status: str,
        result_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        analyzed_count: Optional[int] = None,
        failed_count: Optional[int] = None,
    ) -> None:
        """更新任务级分析结果记录

        Args:
            result_id: TaskAnalysisResult的ID
            status: 任务状态 (pending/processing/completed/failed)
            result_data: 结果数据
            error_message: 错误信息
            analyzed_count: 成功分析数量
            failed_count: 失败数量
        """
        async with AsyncSessionLocal() as db:
            try:
                from sqlalchemy import select, update

                # 构建更新数据
                update_data = {
                    "status": status,
                    "processing_time": self.get_processing_time(),
                    "updated_at": datetime.now(timezone.utc),
                }

                if status == "processing" and not result_data:
                    update_data["started_at"] = datetime.now(timezone.utc)

                if status in ("completed", "failed"):
                    update_data["completed_at"] = datetime.now(timezone.utc)
                    update_data["token_usage"] = self.get_stats().to_dict()

                if result_data is not None:
                    update_data["result_data"] = result_data

                if error_message is not None:
                    update_data["error_message"] = error_message

                if analyzed_count is not None:
                    update_data["analyzed_count"] = analyzed_count

                if failed_count is not None:
                    update_data["failed_count"] = failed_count

                # 执行更新
                stmt = (
                    update(TaskAnalysisResult)
                    .where(TaskAnalysisResult.id == result_id)
                    .values(**update_data)
                )
                await db.execute(stmt)
                await db.commit()

                logger.debug(f"更新TaskAnalysisResult#{result_id}: status={status}")

            except Exception as e:
                logger.error(f"更新TaskAnalysisResult失败: {e}", exc_info=True)
                await db.rollback()

    async def update_project_result(
        self,
        result_id: int,
        status: str,
        result_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """更新项目级分析结果记录

        Args:
            result_id: ProjectAnalysisResult的ID
            status: 任务状态 (pending/processing/completed/failed)
            result_data: 结果数据
            error_message: 错误信息
        """
        async with AsyncSessionLocal() as db:
            try:
                from sqlalchemy import update

                # 构建更新数据
                update_data = {
                    "status": status,
                    "processing_time": self.get_processing_time(),
                    "updated_at": datetime.now(timezone.utc),
                }

                if status in ("completed", "failed"):
                    update_data["completed_at"] = datetime.now(timezone.utc)
                    update_data["token_usage"] = self.get_stats().to_dict()

                if result_data is not None:
                    update_data["result_data"] = result_data

                if error_message is not None:
                    update_data["error_message"] = error_message

                # 执行更新
                stmt = (
                    update(ProjectAnalysisResult)
                    .where(ProjectAnalysisResult.id == result_id)
                    .values(**update_data)
                )
                await db.execute(stmt)
                await db.commit()

                logger.debug(f"更新ProjectAnalysisResult#{result_id}: status={status}")

            except Exception as e:
                logger.error(f"更新ProjectAnalysisResult失败: {e}", exc_info=True)
                await db.rollback()


# 注册基类到Celery应用
celery_app.Task = AnalysisTaskBase
