"""分析任务进度管理器 - 基于Redis缓存 + 批量DB同步

架构设计：
1. 实时进度存储在Redis中（高性能，原子操作）
2. 每N个任务完成后批量同步到PostgreSQL（减少DB写入压力）
3. 前端从Redis读取实时进度
4. 最终结果持久化到PostgreSQL
"""

import logging
import json
from typing import Dict, Any
from datetime import datetime, timezone

from src.redis_sync_client import get_sync_redis
from src.database import SyncSessionLocal
from src.jobs.models import AnalysisJob
from src.config import get_settings
from sqlalchemy import select

logger = logging.getLogger(__name__)
settings = get_settings()


class AnalysisProgressManager:
    """分析进度管理器（Redis缓存 + 批量DB同步）"""

    def __init__(self, result_id: int):
        self.result_id = result_id
        self.redis_client = get_sync_redis()

        # Redis key设计
        self.key_analyzed = f"analysis:result:{result_id}:analyzed_count"
        self.key_failed = f"analysis:result:{result_id}:failed_count"
        self.key_token_usage = f"analysis:result:{result_id}:token_usage"
        self.key_call_details = f"analysis:result:{result_id}:call_details"
        self.key_last_sync = f"analysis:result:{result_id}:last_sync"

        # 批量同步阈值（从配置读取）
        self.batch_threshold = settings.DB_COMMIT_AFTER_BATCH_COUNT

    def initialize(self, total_count: int):
        """初始化进度计数器

        Args:
            total_count: 待分析的总数量
        """
        try:
            # 重置计数器
            self.redis_client.set(self.key_analyzed, 0)
            self.redis_client.set(self.key_failed, 0)
            self.redis_client.delete(self.key_token_usage)
            self.redis_client.delete(self.key_call_details)

            # 存储总数以便计算进度
            self.redis_client.set(
                f"analysis:result:{self.result_id}:total_count", total_count
            )

            # 更新数据库：设置状态为processing和started_at
            db = SyncSessionLocal()
            try:
                stmt = (
                    select(AnalysisJob)
                    .where(AnalysisJob.id == self.result_id)
                    .with_for_update()
                )

                result = db.execute(stmt)
                analysis_job = result.scalar_one_or_none()

                if analysis_job:
                    analysis_job.status = "running"
                    analysis_job.started_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.info(
                        "初始化分析进度: result_id=%s, total_count=%s, started_at已设置",
                        self.result_id,
                        total_count,
                    )
            finally:
                db.close()

        except Exception as e:
            logger.error("初始化Redis进度失败: %s", e)

    def increment_analyzed(self, token_stats: Dict[str, Any]) -> int:
        """
        增加已分析计数（Redis原子操作）- 单条记录版本

        Args:
            token_stats: Token使用统计

        Returns:
            int: 当前已分析数量
        """
        return self.increment_analyzed_batch(1, token_stats)

    def increment_analyzed_batch(self, count: int, token_stats: Dict[str, Any]) -> int:
        """
        批量增加已分析计数（一次API调用处理多条记录）

        Args:
            count: 本批次处理的记录数量
            token_stats: 本次API调用的Token使用统计（整个批次的总量）

        Returns:
            int: 当前已分析数量
        """
        try:
            # 1. 原子递增计数（按实际处理数量）
            current_count = self.redis_client.incrby(self.key_analyzed, count)

            # 2. 追加调用详情到列表（一次API调用记录一条）
            # token_stats 格式: { 'summary': { 'total_input_tokens': ..., ... }, 'call_details': [...] }
            summary = token_stats.get("summary", {})
            input_tokens = summary.get("total_input_tokens", 0)
            output_tokens = summary.get("total_output_tokens", 0)
            total_tokens = summary.get("total_tokens", 0)
            cost_cny = summary.get("total_cost_cny", 0.0)
            duration_seconds = summary.get("total_duration_seconds", 0.0)

            call_detail = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost_cny": cost_cny,
                "duration_seconds": duration_seconds,
                "batch_size": count,  # 记录本批次处理了多少条
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.redis_client.rpush(self.key_call_details, json.dumps(call_detail))

            # 3. 累积Token统计（使用Hash）- API调用次数只加1
            self.redis_client.hincrby(self.key_token_usage, "total_calls", 1)
            self.redis_client.hincrbyfloat(
                self.key_token_usage, "total_input_tokens", input_tokens
            )
            self.redis_client.hincrbyfloat(
                self.key_token_usage, "total_output_tokens", output_tokens
            )
            self.redis_client.hincrbyfloat(
                self.key_token_usage, "total_tokens", total_tokens
            )
            self.redis_client.hincrbyfloat(
                self.key_token_usage, "total_cost_cny", cost_cny
            )
            self.redis_client.hincrbyfloat(
                self.key_token_usage, "total_duration_seconds", duration_seconds
            )

            # 4. 检查是否需要批量同步到DB
            if current_count % self.batch_threshold == 0:
                logger.info("达到批量同步阈值 (%s)，同步到数据库...", current_count)
                self._sync_to_db()

            return current_count

        except Exception as e:
            logger.error("Redis操作失败，降级到直接DB操作: %s", e)
            # 降级：直接写入数据库
            return self._fallback_increment_analyzed_batch(count, token_stats)

    def increment_failed(self) -> int:
        """增加失败计数（Redis原子操作）"""
        try:
            current_count = self.redis_client.incr(self.key_failed)

            # 检查是否需要同步
            if current_count % self.batch_threshold == 0:
                self._sync_to_db()

            return current_count

        except Exception as e:
            logger.error("Redis操作失败: %s", e)
            return self._fallback_increment_failed()

    def get_progress(self) -> Dict[str, Any]:
        """
        获取当前进度（从Redis读取，极快）

        Returns:
            Dict: 进度信息
        """
        try:
            analyzed_count = int(self.redis_client.get(self.key_analyzed) or 0)
            failed_count = int(self.redis_client.get(self.key_failed) or 0)

            # 获取Token统计
            token_usage = self.redis_client.hgetall(self.key_token_usage)

            return {
                "analyzed_count": analyzed_count,
                "failed_count": failed_count,
                "token_usage": {
                    k: float(v) if "." in v else int(v) for k, v in token_usage.items()
                }
                if token_usage
                else {},
            }

        except Exception as e:
            logger.error("获取Redis进度失败: %s", e)
            return {"analyzed_count": 0, "failed_count": 0, "token_usage": {}}

    def _sync_to_db(self):
        """批量同步Redis数据到PostgreSQL"""
        db = SyncSessionLocal()
        try:
            # 从Redis读取所有数据
            analyzed_count = int(self.redis_client.get(self.key_analyzed) or 0)
            failed_count = int(self.redis_client.get(self.key_failed) or 0)

            # 获取所有调用详情
            call_details_raw = self.redis_client.lrange(self.key_call_details, 0, -1)
            call_details = []
            for idx, detail_json in enumerate(call_details_raw):
                detail = json.loads(detail_json)
                detail["call_index"] = idx
                call_details.append(detail)

            # 获取汇总统计
            token_stats = self.redis_client.hgetall(self.key_token_usage)
            summary = (
                {k: float(v) if "." in v else int(v) for k, v in token_stats.items()}
                if token_stats
                else {}
            )

            # 计算平均值
            if summary.get("total_calls", 0) > 0:
                summary["avg_tokens_per_call"] = (
                    summary["total_tokens"] / summary["total_calls"]
                )
                summary["avg_cost_per_call"] = (
                    summary["total_cost_cny"] / summary["total_calls"]
                )

            # 更新数据库
            stmt = (
                select(AnalysisJob)
                .where(AnalysisJob.id == self.result_id)
                .with_for_update()
            )

            result = db.execute(stmt)
            analysis_job = result.scalar_one_or_none()

            if analysis_job:
                analysis_job.analyzed_count = analyzed_count
                analysis_job.failed_count = failed_count
                analysis_job.token_usage = {
                    "summary": summary,
                    "call_details": call_details,
                }
                analysis_job.updated_at = datetime.now(timezone.utc)

                db.commit()

                # 更新最后同步时间
                self.redis_client.set(
                    self.key_last_sync, datetime.now(timezone.utc).isoformat()
                )

                logger.info(
                    "批量同步完成: analyzed=%s, failed=%s, calls=%s",
                    analyzed_count,
                    failed_count,
                    len(call_details),
                )

        except Exception as e:
            logger.error("同步到数据库失败: %s", e, exc_info=True)
            db.rollback()
        finally:
            db.close()

    def finalize(self):
        """
        完成分析任务时调用，执行最终同步并清理Redis

        应在所有子任务完成后由Coordinator调用
        """
        try:
            # 最终同步
            logger.info("执行最终同步...")
            self._sync_to_db()

            # 更新任务状态为completed，并计算processing_time
            db = SyncSessionLocal()
            try:
                stmt = (
                    select(AnalysisJob)
                    .where(AnalysisJob.id == self.result_id)
                    .with_for_update()
                )

                result = db.execute(stmt)
                analysis_job = result.scalar_one_or_none()

                if analysis_job:
                    completed_at = datetime.now(timezone.utc)
                    analysis_job.status = "completed"
                    analysis_job.completed_at = completed_at

                    # 计算处理耗时（秒）
                    if analysis_job.started_at:
                        # 确保 started_at 有时区信息
                        started_at = analysis_job.started_at
                        if started_at.tzinfo is None:
                            started_at = started_at.replace(tzinfo=timezone.utc)
                        analysis_job.processing_time = int(
                            (completed_at - started_at).total_seconds()
                        )
                        logger.info(
                            "任务完成，耗时: %s秒", analysis_job.processing_time
                        )

                    db.commit()

            finally:
                db.close()

            # 清理Redis缓存（可选，保留一段时间供查询）
            # 设置过期时间（24小时后自动清除）
            expire_seconds = 86400
            self.redis_client.expire(self.key_analyzed, expire_seconds)
            self.redis_client.expire(self.key_failed, expire_seconds)
            self.redis_client.expire(self.key_token_usage, expire_seconds)
            self.redis_client.expire(self.key_call_details, expire_seconds)
            self.redis_client.expire(self.key_last_sync, expire_seconds)

            logger.info("任务完成，Redis缓存将在24小时后过期")

        except Exception as e:
            logger.error("最终同步失败: %s", e, exc_info=True)

    def mark_failed(self, error_message: str = "") -> None:
        """将 AnalysisJob 标记为失败（用于异常中断快速兜底）

        不使用 with_for_update，避免在同进程已持有锁时死锁（软超时场景）。
        """
        db = SyncSessionLocal()
        try:
            stmt = select(AnalysisJob).where(AnalysisJob.id == self.result_id)
            result = db.execute(stmt)
            analysis_job = result.scalar_one_or_none()
            if analysis_job and analysis_job.status == "running":
                analysis_job.status = "failed"
                analysis_job.completed_at = datetime.now(timezone.utc)
                analysis_job.error_message = (
                    error_message[:500] if error_message else "任务异常中断"
                )
                db.commit()
                logger.info(
                    "AnalysisJob %s 已标记为失败: %s", self.result_id, error_message
                )
            else:
                logger.debug(
                    "AnalysisJob %s 状态为 %s，跳过失败标记",
                    self.result_id,
                    analysis_job.status if analysis_job else "不存在",
                )
        except Exception as e:
            logger.error("标记 AnalysisJob 失败时出错: %s", e)
            db.rollback()
        finally:
            db.close()

    def _fallback_increment_analyzed(self, token_stats: Dict[str, Any]) -> int:
        """降级方案：直接写入数据库（Redis不可用时）- 单条版本"""
        return self._fallback_increment_analyzed_batch(1, token_stats)

    def _fallback_increment_analyzed_batch(
        self, count: int, token_stats: Dict[str, Any]
    ) -> int:
        """降级方案：直接写入数据库（Redis不可用时）- 批量版本"""
        db = SyncSessionLocal()
        try:
            stmt = (
                select(AnalysisJob)
                .where(AnalysisJob.id == self.result_id)
                .with_for_update()
            )

            result = db.execute(stmt)
            analysis_job = result.scalar_one_or_none()

            if analysis_job:
                current_usage = analysis_job.token_usage or {
                    "summary": {},
                    "call_details": [],
                }

                # token_stats 格式: { 'summary': { 'total_input_tokens': ..., ... }, 'call_details': [...] }
                stats_summary = token_stats.get("summary", {})
                input_tokens = stats_summary.get("total_input_tokens", 0)
                output_tokens = stats_summary.get("total_output_tokens", 0)
                total_tokens = stats_summary.get("total_tokens", 0)
                cost_cny = stats_summary.get("total_cost_cny", 0.0)
                duration_seconds = stats_summary.get("total_duration_seconds", 0.0)

                new_call_detail = {
                    "call_index": len(current_usage.get("call_details", [])),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cost_cny": cost_cny,
                    "duration_seconds": duration_seconds,
                    "batch_size": count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                current_usage.setdefault("call_details", []).append(new_call_detail)

                summary = current_usage.setdefault("summary", {})
                summary["total_calls"] = (
                    summary.get("total_calls", 0) + 1
                )  # 一次API调用
                summary["total_input_tokens"] = (
                    summary.get("total_input_tokens", 0) + input_tokens
                )
                summary["total_output_tokens"] = (
                    summary.get("total_output_tokens", 0) + output_tokens
                )
                summary["total_tokens"] = summary.get("total_tokens", 0) + total_tokens
                summary["total_cost_cny"] = (
                    summary.get("total_cost_cny", 0.0) + cost_cny
                )
                summary["total_duration_seconds"] = (
                    summary.get("total_duration_seconds", 0.0) + duration_seconds
                )

                if summary["total_calls"] > 0:
                    summary["avg_tokens_per_call"] = (
                        summary["total_tokens"] / summary["total_calls"]
                    )
                    summary["avg_cost_per_call"] = (
                        summary["total_cost_cny"] / summary["total_calls"]
                    )

                analysis_job.analyzed_count += count  # 按实际处理数量增加
                analysis_job.token_usage = current_usage
                analysis_job.updated_at = datetime.now(timezone.utc)

                db.commit()
                return analysis_job.analyzed_count

        finally:
            db.close()

        return 0

    def _fallback_increment_failed(self) -> int:
        """降级方案：直接写入数据库（Redis不可用时）"""
        db = SyncSessionLocal()
        try:
            stmt = (
                select(AnalysisJob)
                .where(AnalysisJob.id == self.result_id)
                .with_for_update()
            )

            result = db.execute(stmt)
            analysis_job = result.scalar_one_or_none()

            if analysis_job:
                analysis_job.failed_count += 1
                analysis_job.updated_at = datetime.now(timezone.utc)
                db.commit()
                return analysis_job.failed_count

        finally:
            db.close()

        return 0
