"""AI深度分析任务（协调器模式）

实现任务级的原文和评论深度分析，使用协调器模式确保高可靠性：
- 实体识别（品牌/产品/服务）
- 观点提取
- 内容总结

架构：coordinator → subtasks → finalizer
- 每个原文/评论一个独立的Celery subtask
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
            logger.warning("过滤掉 %s 个无效实体（name或type为空）", filtered_count)
    return data


# ============================================================================
# 原文深度分析 - 单个原文分析
# ============================================================================


def _analyze_single_post(
    result_id: int,
    task_id: int,
    post_id: int,
    analysis_focus: Optional[str] = None,
) -> Dict[str, Any]:
    """分析单个原文的深度内容（同步，内部函数）

    采用 读取→LLM→写回 三阶段模式，避免 LLM 调用期间长时间占用数据库连接。
    """
    # Phase 1: 读取数据（毫秒级，快速释放连接）
    with SyncSessionLocal() as db:
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        if not post:
            logger.warning("原文 %s 不存在", post_id)
            return {"success": False, "error": "post_not_found"}
        content = f"标题：{post.title or '无'}\n正文：{post.content}"

    # Phase 2: 调用LLM进行深度分析（秒级，不占数据库连接）
    try:
        chain = create_post_extraction_chain()
        response, token_stats = invoke_chain_with_stats_sync(
            chain=chain, input_dict={"content": content}, llm_type="chat"
        )
    except Exception as e:
        logger.error("深度分析原文 %s LLM调用失败: %s", post_id, e, exc_info=True)
        return {"success": False, "error": str(e)}

    # Phase 3: 解析响应（纯CPU，无需连接）
    response_content = response.content
    try:
        json_match = re.search(r"\{[\s\S]*\}", response_content)
        if json_match:
            json_str = json_match.group()
            extraction_data = json.loads(json_str)
        else:
            extraction_data = json.loads(response_content)

        extraction_data = _filter_invalid_entities(extraction_data)
        extraction_data = _fix_sentiment_in_result(extraction_data)

        validated_result = PostDeepResult(**extraction_data)
        extraction_dict = validated_result.model_dump()

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("解析AI响应失败: %s\nResponse: %s", e, response_content)
        return {"success": False, "error": f"parse_error: {str(e)}"}

    # Phase 4: 写回结果（毫秒级，快速释放连接）
    try:
        with SyncSessionLocal() as db:
            post_analysis = (
                db.query(PostAnalysis).filter(PostAnalysis.post_id == post_id).first()
            )

            if post_analysis:
                post_analysis.post_deep_result = extraction_dict
                post_analysis.analyzed_at = datetime.now(timezone.utc)
                post_analysis.analysis_model = "deepseek-chat"
            else:
                post_analysis = PostAnalysis(
                    task_id=task_id,
                    post_id=post_id,
                    post_deep_result=extraction_dict,
                    analyzed_at=datetime.now(timezone.utc),
                    analysis_model="deepseek-chat",
                )
                db.add(post_analysis)

            db.commit()
    except Exception as e:
        logger.error("深度分析原文 %s 保存结果失败: %s", post_id, e, exc_info=True)
        return {"success": False, "error": str(e)}

    logger.info("原文 %s 深度分析完成", post_id)
    return {
        "success": True,
        "post_id": post_id,
        "token_stats": token_stats,
    }


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
    """Celery子任务：分析单个原文的深度内容

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_id: 要分析的原文ID
        analysis_focus: 分析重点（保留扩展性）

    Returns:
        分析结果

    注意：为保证 chord callback 能被调用，重试耗尽后返回失败结果而非抛出异常
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
        logger.error("Celery任务执行失败 (post_id=%s): %s", post_id, e, exc_info=True)
        progress_mgr = AnalysisProgressManager(result_id)
        progress_mgr.increment_failed()

        # 检查是否还有重试机会
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        # 重试耗尽：返回失败结果而非抛出异常，保证 chord callback 能被调用
        logger.warning("原文 %s 深度分析重试耗尽，返回失败结果", post_id)
        return {"success": False, "error": str(e), "post_id": post_id}


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
            logger.info("[Finalizer] 所有子任务已完成: %s/%s", completed, total_count)
            break

        logger.info(
            "[Finalizer] 等待子任务完成: %s/%s, 已等待 %ss",
            completed,
            total_count,
            int(time.time() - start_time),
        )
        time.sleep(poll_interval)
    else:
        logger.warning("[Finalizer] 等待超时，部分任务可能未完成")

    # 2. 最终同步 Redis → DB
    try:
        progress_mgr.finalize()
        logger.info("[Finalizer] 进度已同步到数据库")
    except Exception as e:
        logger.error("[Finalizer] 同步进度到数据库失败: %s", e, exc_info=True)

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
    1. 为每个原文创建一个独立的子任务（group）
    2. 所有子任务完成后，调用 finalizer 进行最终化（callback）

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_ids: 要分析的原文ID列表
        analysis_focus: 分析重点

    Returns:
        任务分发结果
    """
    if not post_ids:
        logger.warning("原文列表为空，跳过深度分析")
        return {"status": "skipped", "reason": "no_posts"}

    logger.info(
        "[Coordinator] 启动原文深度分析: result_id=%s, 原文数=%s",
        result_id,
        len(post_ids),
    )

    # 1. 初始化 Redis 进度管理
    progress_mgr = AnalysisProgressManager(result_id)
    progress_mgr.initialize(total_count=len(post_ids))

    # 2. 为每个原文创建一个子任务
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
        "[Coordinator] 已分发 %s 个子任务，chord_id=%s",
        len(post_ids),
        workflow.id,
    )

    return {
        "status": "dispatched",
        "chord_id": workflow.id,
        "total_tasks": len(post_ids),
    }


# ============================================================================
# 评论深度分析 - 单个原文的评论分析
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
    """分析单个原文下的所有评论（同步，内部函数）

    策略：
    - 获取该原文下点赞最高的前N条评论（配置可调）
    - 批量调用LLM进行评论聚合分析
    - 根据评论点赞数计算 support_score（支持度）
    - 结果存储在 PostAnalysis.comment_deep_result 中

    采用 读取→LLM→写回 三阶段模式，避免 LLM 调用期间长时间占用数据库连接。
    """
    max_comments = settings.CELERY_TASK_MAX_COMMENTS_PER_POST_FOR_DEEP_ANALYSIS

    # Phase 1: 读取数据（毫秒级，快速释放连接）
    with SyncSessionLocal() as db:
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        if not post:
            logger.warning("原文 %s 不存在", post_id)
            return {"success": False, "error": "post_not_found"}

        context = ""
        existing_analysis = (
            db.query(PostAnalysis).filter(PostAnalysis.post_id == post_id).first()
        )
        if existing_analysis and existing_analysis.post_deep_result:
            summary = existing_analysis.post_deep_result.get("summary", "")
            if summary:
                context = f"背景上下文：{summary}"

        comments = (
            db.query(SocialComment)
            .filter(SocialComment.post_id == post_id)
            .order_by(SocialComment.likes_count.desc())
            .limit(max_comments)
            .all()
        )

        if not comments:
            logger.info("原文 %s 没有评论，跳过", post_id)
            return {"success": False, "error": "no_comments"}

        valid_comments = [
            (i + 1, c.content, int(c.likes_count or 0))
            for i, c in enumerate(comments)
            if c.content
        ]

    if not valid_comments:
        return {"success": False, "error": "no_valid_comments"}

    likes_map: Dict[int, int] = {idx: likes for idx, _, likes in valid_comments}

    # Phase 2: 调用LLM进行评论分析（秒级，不占数据库连接）
    formatted_comments = "\n".join(
        [f"评论[{idx}]: {content}" for idx, content, _ in valid_comments]
    )
    context_text = f"背景上下文：\n{context}"

    try:
        chain = create_comment_extraction_chain()
        response, token_stats = invoke_chain_with_stats_sync(
            chain=chain,
            input_dict={
                "context": context_text,
                "comments": formatted_comments,
            },
            llm_type="chat",
        )
    except Exception as e:
        logger.error("分析原文 %s 评论LLM调用失败: %s", post_id, e, exc_info=True)
        return {"success": False, "error": str(e)}

    # Phase 3: 解析响应（纯CPU，无需连接）
    response_content = response.content
    try:
        json_match = re.search(r"\{[\s\S]*\}", response_content)
        if json_match:
            json_str = json_match.group()
            extraction_data = json.loads(json_str)
        else:
            extraction_data = json.loads(response_content)

        extraction_data = _filter_invalid_entities(extraction_data)
        extraction_data = _fix_sentiment_in_result(extraction_data)
        extraction_data = _enrich_with_support_score(extraction_data, likes_map)

        validated_result = CommentDeepResult(**extraction_data)
        extraction_dict = validated_result.model_dump()

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("解析评论AI响应失败: %s\nResponse: %s", e, response_content)
        return {"success": False, "error": f"parse_error: {str(e)}"}

    # Phase 4: 写回结果（毫秒级，快速释放连接）
    try:
        with SyncSessionLocal() as db:
            post_analysis = (
                db.query(PostAnalysis).filter(PostAnalysis.post_id == post_id).first()
            )

            if post_analysis:
                post_analysis.comment_deep_result = extraction_dict
                post_analysis.analyzed_at = datetime.now(timezone.utc)
                post_analysis.analysis_model = "deepseek-chat"
            else:
                post_analysis = PostAnalysis(
                    task_id=task_id,
                    post_id=post_id,
                    comment_deep_result=extraction_dict,
                    analyzed_at=datetime.now(timezone.utc),
                    analysis_model="deepseek-chat",
                )
                db.add(post_analysis)

            db.commit()
    except Exception as e:
        logger.error("分析原文 %s 评论保存结果失败: %s", post_id, e, exc_info=True)
        return {"success": False, "error": str(e)}

    logger.info(
        "原文 %s 的评论深度分析完成（分析了%s条评论）",
        post_id,
        len(valid_comments),
    )
    return {
        "success": True,
        "post_id": post_id,
        "comments_analyzed": len(valid_comments),
        "token_stats": token_stats,
    }


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
    """Celery子任务：分析单个原文的所有评论

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_id: 要分析其评论的原文ID
        analysis_focus: 分析重点

    Returns:
        分析结果

    注意：为保证 chord callback 能被调用，重试耗尽后返回失败结果而非抛出异常
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
            "Celery任务执行失败 (评论分析, post_id=%s): %s", post_id, e, exc_info=True
        )
        progress_mgr = AnalysisProgressManager(result_id)
        progress_mgr.increment_failed()

        # 检查是否还有重试机会
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        # 重试耗尽：返回失败结果而非抛出异常，保证 chord callback 能被调用
        logger.warning("原文 %s 评论深度分析重试耗尽，返回失败结果", post_id)
        return {"success": False, "error": str(e), "post_id": post_id}


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
        total_count: 总任务数（原文数）

    Returns:
        最终统计结果

    注意：聚合分析已移至独立 API (POST /tasks/{task_id}/aggregation)
    """
    logger.info(
        "[Finalizer] 评论深度分析任务开始最终化: result_id=%s, total=%s",
        result_id,
        total_count,
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
                "[Finalizer] 所有评论分析子任务已完成: %s/%s",
                completed,
                total_count,
            )
            break

        logger.info(
            "[Finalizer] 等待评论分析完成: %s/%s, 已等待 %ss",
            completed,
            total_count,
            int(time.time() - start_time),
        )
        time.sleep(poll_interval)
    else:
        logger.warning("[Finalizer] 等待超时，部分评论分析任务可能未完成")

    # 2. 最终同步
    try:
        progress_mgr.finalize()
        logger.info("[Finalizer] 评论分析进度已同步到数据库")
    except Exception as e:
        logger.error("[Finalizer] 同步评论分析进度失败: %s", e, exc_info=True)

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
    - 为每个原文创建一个独立的评论分析子任务
    - 每个子任务会分析该原文下的所有（或前N条）评论

    Args:
        result_id: AnalysisJob的ID
        task_id: DataTask的ID
        post_ids: 要分析其评论的原文ID列表
        analysis_focus: 分析重点

    Returns:
        任务分发结果
    """
    if not post_ids:
        logger.warning("原文列表为空，跳过评论深度分析")
        return {"status": "skipped", "reason": "no_posts"}

    logger.info(
        "[Coordinator] 启动评论深度分析: result_id=%s, 原文数=%s",
        result_id,
        len(post_ids),
    )

    # 1. 初始化进度
    progress_mgr = AnalysisProgressManager(result_id)
    progress_mgr.initialize(total_count=len(post_ids))

    # 2. 为每个原文创建评论分析子任务
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
        "[Coordinator] 已分发 %s 个评论分析子任务，chord_id=%s",
        len(post_ids),
        workflow.id,
    )

    return {
        "status": "dispatched",
        "chord_id": workflow.id,
        "total_tasks": len(post_ids),
    }
