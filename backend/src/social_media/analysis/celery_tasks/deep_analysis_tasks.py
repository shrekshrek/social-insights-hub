"""AI深度分析任务（协调器模式）

实现任务级的帖子和评论深度分析，使用协调器模式确保高可靠性：
- 实体识别（品牌/产品/服务）
- 观点提取
- 内容总结

架构：coordinator → subtasks → finalizer
- 每个帖子/评论一个独立的Celery subtask
- 使用Redis进行进度管理和结果同步
- 支持细粒度失败隔离和重试
"""

import logging
import json
import re
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from celery import chord, group

from src.celery_app import celery_app
from src.config import get_settings
from src.database import SyncSessionLocal
from src.social_media.analysis.models import PostAnalysis
from src.social_media.analysis.schemas import PostDeepResult, CommentDeepResult
from src.social_media.tasks.models import SocialPost, SocialComment
from src.social_media.analysis.celery_tasks.progress_manager import (
    AnalysisProgressManager,
)
from src.social_media.analysis.celery_tasks.llm_utils import (
    invoke_chain_with_stats_sync,
)
from src.langchain.chains.post_extraction_chain import create_post_extraction_chain
from src.langchain.chains.comment_extraction_chain import (
    create_comment_extraction_chain,
)

settings = get_settings()

logger = logging.getLogger(__name__)


# ============================================================================
# 辅助函数
# ============================================================================


def _fix_sentiment_in_result(data: dict) -> dict:
    """修复 sentiment 字段，确保所有实体和观点都有 sentiment 值"""
    if "general_opinions" in data:
        for op in data["general_opinions"]:
            if "sentiment" not in op:
                op["sentiment"] = 0
    if "entities" in data:
        for ent in data["entities"]:
            if "sentiment" not in ent:
                ent["sentiment"] = 0
    return data


def _filter_invalid_entities(data: dict) -> dict:
    """过滤掉无效的实体（name或type为空的实体）

    LLM 有时会返回空值的 entity，这些 entity 没有业务价值且会导致 Pydantic 验证失败。
    """
    if "entities" in data and isinstance(data["entities"], list):
        valid_types = {"品牌", "产品", "服务", "人物", "其他"}
        original_count = len(data["entities"])
        data["entities"] = [
            ent
            for ent in data["entities"]
            if ent.get("name") and ent.get("type") in valid_types
        ]
        filtered_count = original_count - len(data["entities"])
        if filtered_count > 0:
            logger.warning(f"过滤掉 {filtered_count} 个无效实体（name或type为空）")
    return data


# ============================================================================
# 原文深度分析 - 单个帖子分析
# ============================================================================


def _analyze_single_post(
    result_id: int,
    task_id: int,
    post_id: int,
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """分析单个帖子的深度内容（同步，内部函数）"""
    with SyncSessionLocal() as db:
        try:
            # 1. 获取帖子数据
            post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
            if not post:
                logger.warning(f"帖子 {post_id} 不存在")
                return {"success": False, "error": "post_not_found"}

            # 2. 准备输入内容
            content = f"标题：{post.title or '无'}\n正文：{post.content}"

            # 3. 调用LLM进行深度分析（使用chain）
            chain = create_post_extraction_chain()
            response, token_stats = invoke_chain_with_stats_sync(
                chain=chain, input_dict={"content": content}, llm_type="chat"
            )

            # 4. 解析响应
            response_content = response.content
            try:
                json_match = re.search(r"\{[\s\S]*\}", response_content)
                if json_match:
                    json_str = json_match.group()
                    extraction_data = json.loads(json_str)
                else:
                    extraction_data = json.loads(response_content)

                # 数据清洗：过滤无效实体、修复 sentiment 字段
                extraction_data = _filter_invalid_entities(extraction_data)
                extraction_data = _fix_sentiment_in_result(extraction_data)

                # 验证数据结构
                validated_result = PostDeepResult(**extraction_data)
                extraction_dict = validated_result.model_dump()

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"解析AI响应失败: {e}\nResponse: {response_content}")
                return {"success": False, "error": f"parse_error: {str(e)}"}

            # 5. 保存分析结果到数据库
            post_analysis = (
                db.query(PostAnalysis).filter(PostAnalysis.post_id == post_id).first()
            )

            if post_analysis:
                # 更新现有记录
                post_analysis.post_deep_result = extraction_dict
                post_analysis.analyzed_at = datetime.now(timezone.utc)
                post_analysis.analysis_model = "deepseek-chat"
            else:
                # 创建新记录
                post_analysis = PostAnalysis(
                    task_id=task_id,
                    post_id=post_id,
                    post_deep_result=extraction_dict,
                    analyzed_at=datetime.now(timezone.utc),
                    analysis_model="deepseek-chat",
                )
                db.add(post_analysis)

            db.commit()

            logger.info(f"帖子 {post_id} 深度分析完成")
            return {
                "success": True,
                "post_id": post_id,
                "token_stats": token_stats,
            }

        except Exception as e:
            logger.error(f"深度分析帖子 {post_id} 失败: {e}", exc_info=True)
            db.rollback()
            return {"success": False, "error": str(e)}


@celery_app.task(
    name="analysis.deep.single_post",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def analyze_single_post_deep(
    self,
    result_id: int,
    task_id: int,
    post_id: int,
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """Celery子任务：分析单个帖子的深度内容

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_id: 要分析的帖子ID
        analysis_focus: 分析重点（保留扩展性）

    Returns:
        分析结果
    """
    try:
        result = _analyze_single_post(result_id, task_id, post_id, analysis_focus)

        # 更新Redis进度（成功或失败都更新）
        progress_mgr = AnalysisProgressManager(result_id)
        if result["success"]:
            progress_mgr.increment_analyzed(result.get("token_stats", {}))
        else:
            progress_mgr.increment_failed()

        return result

    except Exception as e:
        logger.error(f"Celery任务执行失败 (post_id={post_id}): {e}", exc_info=True)
        # 更新失败计数
        progress_mgr = AnalysisProgressManager(result_id)
        progress_mgr.increment_failed()
        raise self.retry(exc=e)


# ============================================================================
# 原文深度分析 - Finalizer
# ============================================================================


@celery_app.task(
    name="analysis.deep.posts.finalizer",
    bind=True,
)
def finalize_post_deep_analysis(
    self,
    subtask_results: List[Dict[str, Any]],
    result_id: int,
    total_count: int,
) -> Dict[str, Any]:
    """Finalizer：等待所有原文深度分析子任务完成，同步Redis进度到数据库

    Args:
        subtask_results: 所有子任务的返回结果列表
        result_id: AnalysisJob的ID
        total_count: 总任务数

    Returns:
        最终统计结果

    注意：聚合分析已移至独立 API (POST /tasks/{task_id}/aggregation)
    """
    logger.info(
        f"[Finalizer] 原文深度分析任务开始最终化: result_id={result_id}, total={total_count}"
    )

    progress_mgr = AnalysisProgressManager(result_id)

    # 1. 等待所有子任务完成（最多2小时）
    max_wait_time = 7200  # 2小时
    poll_interval = 5  # 每5秒检查一次
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        current_progress = progress_mgr.get_progress()
        completed = (
            current_progress["analyzed_count"] + current_progress["failed_count"]
        )

        if completed >= total_count:
            logger.info(f"[Finalizer] 所有子任务已完成: {completed}/{total_count}")
            break

        logger.info(
            f"[Finalizer] 等待子任务完成: {completed}/{total_count}, 已等待 {int(time.time() - start_time)}s"
        )
        time.sleep(poll_interval)
    else:
        logger.warning("[Finalizer] 等待超时，部分任务可能未完成")

    # 2. 最终同步 Redis → DB
    try:
        progress_mgr.finalize()
        logger.info("[Finalizer] 进度已同步到数据库")
    except Exception as e:
        logger.error(f"[Finalizer] 同步进度到数据库失败: {e}", exc_info=True)

    # 3. 返回最终统计
    final_progress = progress_mgr.get_progress()
    return {
        "status": "completed",
        "analyzed": final_progress["analyzed_count"],
        "failed": final_progress["failed_count"],
        "total": total_count,
    }


# ============================================================================
# 原文深度分析 - 协调器
# ============================================================================


@celery_app.task(
    name="analysis.deep.posts.run",
    bind=True,
)
def run_post_deep_task(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """原文深度分析协调器

    使用 Celery chord 模式：
    1. 为每个帖子创建一个独立的子任务（group）
    2. 所有子任务完成后，调用 finalizer 进行最终化（callback）

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_ids: 要分析的帖子ID列表
        analysis_focus: 分析重点

    Returns:
        任务分发结果
    """
    if not post_ids:
        logger.warning("帖子列表为空，跳过深度分析")
        return {"status": "skipped", "reason": "no_posts"}

    logger.info(
        f"[Coordinator] 启动原文深度分析: result_id={result_id}, 帖子数={len(post_ids)}"
    )

    # 1. 初始化 Redis 进度管理
    progress_mgr = AnalysisProgressManager(result_id)
    progress_mgr.initialize(total_count=len(post_ids))

    # 2. 为每个帖子创建一个子任务
    subtasks = group(
        [
            analyze_single_post_deep.s(
                result_id=result_id,
                task_id=task_id,
                post_id=post_id,
                analysis_focus=analysis_focus,
            )
            for post_id in post_ids
        ]
    )

    # 3. 使用 chord 编排：subtasks 完成后调用 finalizer
    workflow = chord(subtasks)(
        finalize_post_deep_analysis.s(
            result_id=result_id,
            total_count=len(post_ids),
        )
    )

    logger.info(
        f"[Coordinator] 已分发 {len(post_ids)} 个子任务，chord_id={workflow.id}"
    )

    return {
        "status": "dispatched",
        "chord_id": workflow.id,
        "total_tasks": len(post_ids),
    }


# ============================================================================
# 评论深度分析 - 单个帖子的评论分析
# ============================================================================


def _calculate_support_score(
    source_comments: List[int],
    likes_map: Dict[int, int],
) -> int:
    """根据来源评论编号计算支持度分数

    Args:
        source_comments: 来源评论编号列表（1-indexed）
        likes_map: 评论编号到点赞数的映射 {1: 235, 2: 89, ...}

    Returns:
        int: 支持度分数（来源评论点赞数之和）
    """
    if not source_comments:
        return 0
    # 去重与容错：
    # - LLM 可能输出重复编号（如 [1, 1, 2]），避免重复累加同一条评论的点赞
    # - 防御性过滤非 int / 非正数编号
    unique_indices = set()
    for idx in source_comments:
        try:
            idx_int = int(idx)
        except Exception:
            continue
        if idx_int > 0:
            unique_indices.add(idx_int)

    return sum(int(likes_map.get(idx, 0) or 0) for idx in unique_indices)


def _enrich_with_support_score(
    extraction_data: Dict[str, Any],
    likes_map: Dict[int, int],
) -> Dict[str, Any]:
    """为提取结果中的实体和观点计算 support_score

    Args:
        extraction_data: LLM 提取的原始数据
        likes_map: 评论编号到点赞数的映射

    Returns:
        dict: 补充了 support_score 的数据
    """
    # 处理实体
    for entity in extraction_data.get("entities", []):
        source_comments = entity.get("source_comments", [])
        entity["support_score"] = _calculate_support_score(source_comments, likes_map)

    # 处理观点
    for opinion in extraction_data.get("general_opinions", []):
        source_comments = opinion.get("source_comments", [])
        opinion["support_score"] = _calculate_support_score(source_comments, likes_map)

    return extraction_data


def _analyze_single_post_comments(
    result_id: int,
    task_id: int,
    post_id: int,
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """分析单个帖子下的所有评论（同步，内部函数）

    策略：
    - 获取该帖子下点赞最高的前N条评论（配置可调）
    - 批量调用LLM进行评论聚合分析
    - 根据评论点赞数计算 support_score（支持度）
    - 结果存储在 PostAnalysis.comment_deep_result 中
    """
    max_comments = settings.CELERY_TASK_MAX_COMMENTS_PER_POST_FOR_DEEP_ANALYSIS

    with SyncSessionLocal() as db:
        try:
            # 1. 获取帖子信息
            post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
            if not post:
                logger.warning(f"帖子 {post_id} 不存在")
                return {"success": False, "error": "post_not_found"}

            # 2. 获取PostAnalysis以便添加上下文（仅使用AI总结）
            post_analysis = (
                db.query(PostAnalysis).filter(PostAnalysis.post_id == post_id).first()
            )

            context = ""
            if post_analysis and post_analysis.post_deep_result:
                summary = post_analysis.post_deep_result.get("summary", "")
                if summary:
                    context = f"背景上下文：{summary}"

            # 3. 获取评论（点赞最高的前N条）
            comments = (
                db.query(SocialComment)
                .filter(SocialComment.post_id == post_id)
                .order_by(SocialComment.likes_count.desc())
                .limit(max_comments)
                .all()
            )

            if not comments:
                logger.info(f"帖子 {post_id} 没有评论，跳过")
                return {"success": False, "error": "no_comments"}

            # 4. 构建评论数据：编号、内容、点赞数映射
            # 编号从 1 开始，与 LLM 输出的 source_comments 对应
            valid_comments = [
                (i + 1, c.content, int(c.likes_count or 0))
                for i, c in enumerate(comments)
                if c.content
            ]
            if not valid_comments:
                return {"success": False, "error": "no_valid_comments"}

            # 构建编号到点赞数的映射
            likes_map: Dict[int, int] = {idx: likes for idx, _, likes in valid_comments}

            # 5. 调用LLM进行评论分析（使用chain）
            # 格式：评论[编号]: 内容
            formatted_comments = "\n".join(
                [f"评论[{idx}]: {content}" for idx, content, _ in valid_comments]
            )
            context_text = f"背景上下文：\n{context}"

            chain = create_comment_extraction_chain()
            response, token_stats = invoke_chain_with_stats_sync(
                chain=chain,
                input_dict={
                    "context": context_text,
                    "comments": formatted_comments,
                },
                llm_type="chat",
            )

            # 6. 解析响应
            response_content = response.content
            try:
                json_match = re.search(r"\{[\s\S]*\}", response_content)
                if json_match:
                    json_str = json_match.group()
                    extraction_data = json.loads(json_str)
                else:
                    extraction_data = json.loads(response_content)

                # 数据清洗：过滤无效实体、修复 sentiment 字段
                extraction_data = _filter_invalid_entities(extraction_data)
                extraction_data = _fix_sentiment_in_result(extraction_data)

                # 根据 source_comments 计算 support_score
                extraction_data = _enrich_with_support_score(extraction_data, likes_map)

                # 验证数据结构
                validated_result = CommentDeepResult(**extraction_data)
                extraction_dict = validated_result.model_dump()

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"解析评论AI响应失败: {e}\nResponse: {response_content}")
                return {"success": False, "error": f"parse_error: {str(e)}"}

            # 6. 保存到 PostAnalysis.comment_deep_result
            if not post_analysis:
                post_analysis = PostAnalysis(
                    task_id=task_id,
                    post_id=post_id,
                    comment_deep_result=extraction_dict,
                    analyzed_at=datetime.now(timezone.utc),
                    analysis_model="deepseek-chat",
                )
                db.add(post_analysis)
            else:
                post_analysis.comment_deep_result = extraction_dict
                post_analysis.analyzed_at = datetime.now(timezone.utc)
                post_analysis.analysis_model = "deepseek-chat"

            db.commit()

            logger.info(
                f"帖子 {post_id} 的评论深度分析完成（分析了{len(valid_comments)}条评论）"
            )
            return {
                "success": True,
                "post_id": post_id,
                "comments_analyzed": len(valid_comments),
                "token_stats": token_stats,
            }

        except Exception as e:
            logger.error(f"分析帖子 {post_id} 的评论失败: {e}", exc_info=True)
            db.rollback()
            return {"success": False, "error": str(e)}


@celery_app.task(
    name="analysis.deep.single_post_comments",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def analyze_single_post_comments_deep(
    self,
    result_id: int,
    task_id: int,
    post_id: int,
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """Celery子任务：分析单个帖子的所有评论

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_id: 要分析其评论的帖子ID
        analysis_focus: 分析重点

    Returns:
        分析结果
    """
    try:
        result = _analyze_single_post_comments(
            result_id, task_id, post_id, analysis_focus
        )

        # 更新Redis进度
        progress_mgr = AnalysisProgressManager(result_id)
        if result["success"]:
            progress_mgr.increment_analyzed(result.get("token_stats", {}))
        else:
            progress_mgr.increment_failed()

        return result

    except Exception as e:
        logger.error(
            f"Celery任务执行失败 (评论分析, post_id={post_id}): {e}", exc_info=True
        )
        progress_mgr = AnalysisProgressManager(result_id)
        progress_mgr.increment_failed()
        raise self.retry(exc=e)


# ============================================================================
# 评论深度分析 - Finalizer
# ============================================================================


@celery_app.task(
    name="analysis.deep.comments.finalizer",
    bind=True,
)
def finalize_comment_deep_analysis(
    self,
    subtask_results: List[Dict[str, Any]],
    result_id: int,
    total_count: int,
) -> Dict[str, Any]:
    """Finalizer：等待所有评论深度分析子任务完成

    Args:
        subtask_results: 所有子任务的返回结果列表
        result_id: AnalysisJob的ID
        total_count: 总任务数（帖子数）

    Returns:
        最终统计结果

    注意：聚合分析已移至独立 API (POST /tasks/{task_id}/aggregation)
    """
    logger.info(
        f"[Finalizer] 评论深度分析任务开始最终化: result_id={result_id}, total={total_count}"
    )

    progress_mgr = AnalysisProgressManager(result_id)

    # 1. 等待所有子任务完成（最多2小时）
    max_wait_time = 7200
    poll_interval = 5
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        current_progress = progress_mgr.get_progress()
        completed = (
            current_progress["analyzed_count"] + current_progress["failed_count"]
        )

        if completed >= total_count:
            logger.info(
                f"[Finalizer] 所有评论分析子任务已完成: {completed}/{total_count}"
            )
            break

        logger.info(
            f"[Finalizer] 等待评论分析完成: {completed}/{total_count}, 已等待 {int(time.time() - start_time)}s"
        )
        time.sleep(poll_interval)
    else:
        logger.warning("[Finalizer] 等待超时，部分评论分析任务可能未完成")

    # 2. 最终同步
    try:
        progress_mgr.finalize()
        logger.info("[Finalizer] 评论分析进度已同步到数据库")
    except Exception as e:
        logger.error(f"[Finalizer] 同步评论分析进度失败: {e}", exc_info=True)

    # 3. 返回最终统计
    final_progress = progress_mgr.get_progress()
    return {
        "status": "completed",
        "analyzed": final_progress["analyzed_count"],
        "failed": final_progress["failed_count"],
        "total": total_count,
    }


# ============================================================================
# 评论深度分析 - 协调器
# ============================================================================


@celery_app.task(
    name="analysis.deep.comments.run",
    bind=True,
)
def run_comment_deep_task(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """评论深度分析协调器

    策略：
    - 为每个帖子创建一个独立的评论分析子任务
    - 每个子任务会分析该帖子下的所有（或前N条）评论

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_ids: 要分析其评论的帖子ID列表
        analysis_focus: 分析重点

    Returns:
        任务分发结果
    """
    if not post_ids:
        logger.warning("帖子列表为空，跳过评论深度分析")
        return {"status": "skipped", "reason": "no_posts"}

    logger.info(
        f"[Coordinator] 启动评论深度分析: result_id={result_id}, 帖子数={len(post_ids)}"
    )

    # 1. 初始化进度
    progress_mgr = AnalysisProgressManager(result_id)
    progress_mgr.initialize(total_count=len(post_ids))

    # 2. 为每个帖子创建评论分析子任务
    subtasks = group(
        [
            analyze_single_post_comments_deep.s(
                result_id=result_id,
                task_id=task_id,
                post_id=post_id,
                analysis_focus=analysis_focus,
            )
            for post_id in post_ids
        ]
    )

    # 3. 使用 chord 编排
    workflow = chord(subtasks)(
        finalize_comment_deep_analysis.s(
            result_id=result_id,
            total_count=len(post_ids),
        )
    )

    logger.info(
        f"[Coordinator] 已分发 {len(post_ids)} 个评论分析子任务，chord_id={workflow.id}"
    )

    return {
        "status": "dispatched",
        "chord_id": workflow.id,
        "total_tasks": len(post_ids),
    }
