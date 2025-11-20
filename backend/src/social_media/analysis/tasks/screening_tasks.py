"""AI初筛任务 - 工作队列并发模式（同步DB + gevent协程）

重新设计的架构：
1. 主任务：分发子任务 + 监控进度
2. 子任务：分析单个 post（使用同步DB）
3. Worker Pool：gevent协程池自动调度，完成一个取下一个

技术栈：
- Celery + gevent pool（100协程）
- 同步DB（psycopg2）避免事件循环冲突
- LangChain同步调用（invoke代替ainvoke）
"""

import logging
import json
import re
from typing import Dict, Any
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.social_media.analysis.base_task import AnalysisTaskBase
from src.database import SyncSessionLocal
from src.langchain.llm import get_llm
from src.social_media.analysis.models import PostAnalysis, TaskAnalysisResult
from src.social_media.tasks.models import DataTask, SocialPost
from src.config import get_settings
from src.social_media.analysis.tasks.progress_manager import AnalysisProgressManager

logger = logging.getLogger(__name__)
settings = get_settings()


def invoke_llm_with_stats_sync(llm, messages: list, llm_type: str = "chat"):
    """同步调用LLM并获取token统计（用于gevent环境）

    Args:
        llm: LangChain LLM实例
        messages: 消息列表
        llm_type: LLM类型 ("chat" 或 "reasoner")

    Returns:
        (response, stats_dict): LLM响应和token统计字典
    """
    start_time = datetime.now()

    # 同步调用LLM
    response = llm.invoke(messages)

    # 计算耗时
    duration_seconds = (datetime.now() - start_time).total_seconds()

    # 提取token统计
    real_input_tokens = 0
    real_output_tokens = 0
    real_total_tokens = 0

    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        usage = response.usage_metadata
        real_input_tokens = usage.get('input_tokens', 0)
        real_output_tokens = usage.get('output_tokens', 0)
        real_total_tokens = usage.get('total_tokens', 0)
    elif hasattr(response, 'response_metadata') and response.response_metadata:
        metadata = response.response_metadata
        if 'usage' in metadata:
            usage = metadata['usage']
            real_input_tokens = usage.get('prompt_tokens', usage.get('input_tokens', 0))
            real_output_tokens = usage.get('completion_tokens', usage.get('output_tokens', 0))
            real_total_tokens = usage.get('total_tokens', 0)

    # 计算成本
    if llm_type == "reasoner":
        input_cost = real_input_tokens * settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION / 1_000_000
        output_cost = real_output_tokens * settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION / 1_000_000
    else:
        input_cost = real_input_tokens * settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION / 1_000_000
        output_cost = real_output_tokens * settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION / 1_000_000

    real_cost = input_cost + output_cost

    # 返回简化的统计字典
    stats = {
        'input_tokens': real_input_tokens,
        'output_tokens': real_output_tokens,
        'total_tokens': real_total_tokens,
        'total_cost_cny': real_cost,
        'duration_seconds': duration_seconds,
    }

    return response, stats


def _analyze_single_post(
    result_id: int,
    task_id: int,
    post_id: int,
    project_keywords: str,
) -> Dict[str, Any]:
    """分析单个帖子（同步实现，用于gevent协程池）"""
    try:
        # 获取LLM实例
        llm = get_llm(llm_type="chat")

        # 使用同步DB session
        db = SyncSessionLocal()
        try:
            # 获取帖子数据
            stmt = select(SocialPost).where(SocialPost.id == post_id)
            result = db.execute(stmt)
            post = result.scalar_one_or_none()

            if not post:
                logger.warning(f"帖子 {post_id} 不存在")
                return {"success": False, "error": "Post not found"}

            # 构建提示词
            prompt = f"""请对以下社交媒体帖子进行初筛评分：

项目关键词：{project_keywords}

帖子内容：
标题：{post.title or '无'}
正文：{post.content}

请从以下维度评分（0-10分）：
1. 垃圾分（spam_score）：是否为垃圾、广告、灌水内容
2. 价值分（value_score）：内容的信息价值和质量
3. 相关度分（relevance_score）：与项目关键词的相关程度
4. 情感倾向（sentiment）：-1（负面）、0（中性）、1（正面）

请以JSON格式返回结果：
{{
    "spam_score": 分数,
    "value_score": 分数,
    "relevance_score": 分数,
    "sentiment": -1/0/1
}}"""

            # 同步调用LLM
            response, token_stats = invoke_llm_with_stats_sync(
                llm=llm,
                messages=[{"role": "user", "content": prompt}],
                llm_type="chat"
            )

            # 解析响应
            try:
                scores = json.loads(response.content)
            except json.JSONDecodeError:
                # 如果解析失败，尝试提取JSON
                match = re.search(r'\{[^}]+\}', response.content)
                if match:
                    scores = json.loads(match.group())
                else:
                    raise ValueError("无法解析AI响应")

            # 保存分析结果（upsert）
            stmt = select(PostAnalysis).where(PostAnalysis.post_id == post_id)
            result = db.execute(stmt)
            post_analysis = result.scalar_one_or_none()

            if post_analysis:
                # 更新现有记录
                post_analysis.task_id = task_id
                post_analysis.spam_score = scores.get("spam_score")
                post_analysis.value_score = scores.get("value_score")
                post_analysis.relevance_score = scores.get("relevance_score")
                post_analysis.sentiment = scores.get("sentiment")
                post_analysis.analyzed_at = datetime.now(timezone.utc)
                post_analysis.analysis_model = "deepseek-chat"
            else:
                # 创建新记录
                post_analysis = PostAnalysis(
                    task_id=task_id,
                    post_id=post_id,
                    spam_score=scores.get("spam_score"),
                    value_score=scores.get("value_score"),
                    relevance_score=scores.get("relevance_score"),
                    sentiment=scores.get("sentiment"),
                    analyzed_at=datetime.now(timezone.utc),
                    analysis_model="deepseek-chat",
                )
                db.add(post_analysis)

            db.commit()

            # 更新主任务进度（使用Redis缓存 + 批量同步）
            progress_mgr = AnalysisProgressManager(result_id)
            current_count = progress_mgr.increment_analyzed(token_stats)

            logger.debug(f"帖子 {post_id} 分析完成 ({current_count})")
            return {
                "success": True,
                "post_id": post_id,
                "token_usage": token_stats
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"分析帖子 {post_id} 失败: {e}", exc_info=True)
        # 更新失败计数（使用Redis缓存）
        progress_mgr = AnalysisProgressManager(result_id)
        progress_mgr.increment_failed()
        return {"success": False, "post_id": post_id, "error": str(e)}


def _update_task_status(result_id: int, status: str, **kwargs):
    """更新任务状态（同步）"""
    db = SyncSessionLocal()
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
            **kwargs
        }

        stmt = (
            update(TaskAnalysisResult)
            .where(TaskAnalysisResult.id == result_id)
            .values(**update_data)
        )
        db.execute(stmt)
        db.commit()

    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.screening.single_post",
    max_retries=2,
    default_retry_delay=30,
)
def analyze_single_post_screening(
    self,
    result_id: int,
    task_id: int,
    post_id: int,
    project_keywords: str,
) -> Dict[str, Any]:
    """分析单个帖子的初筛任务（子任务）

    这是并发执行的最小单元，每个帖子一个任务
    在gevent协程池中执行，使用同步DB避免事件循环冲突
    """
    return _analyze_single_post(result_id, task_id, post_id, project_keywords)


@celery_app.task(
    bind=True,
    name="analysis.screening.finalizer",
    max_retries=0,
)
def finalize_screening_analysis(result_id: int, total_count: int):
    """
    最终化分析任务（等待所有子任务完成后调用）

    职责：
    1. 执行Redis到DB的最终同步
    2. 更新任务状态为completed
    3. 清理Redis缓存
    """
    import time

    logger.info(f"等待所有 {total_count} 个子任务完成...")

    # 轮询检查进度
    max_wait_time = 3600  # 最多等待1小时
    start_time = time.time()
    progress_mgr = AnalysisProgressManager(result_id)

    while time.time() - start_time < max_wait_time:
        progress = progress_mgr.get_progress()
        current_total = progress['analyzed_count'] + progress['failed_count']

        logger.info(f"当前进度: {current_total}/{total_count}")

        if current_total >= total_count:
            # 所有任务已完成
            logger.info(f"所有子任务已完成，执行最终同步...")
            progress_mgr.finalize()
            return {
                "status": "completed",
                "analyzed": progress['analyzed_count'],
                "failed": progress['failed_count']
            }

        # 等待5秒后再次检查
        time.sleep(5)

    # 超时
    logger.error(f"等待超时，部分任务可能未完成")
    progress_mgr._sync_to_db()  # 至少同步已完成的
    _update_task_status(result_id, status="failed", error_message="任务执行超时")


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.screening.posts.coordinator",
    max_retries=0,
)
def run_post_screening_coordinator(
    self,
    result_id: int,
    task_id: int,
    post_ids: list[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """帖子初筛分析协调器（主任务）

    职责：
    1. 分发子任务到队列
    2. 子任务由 worker pool 自动调度执行
    3. 启动监控任务等待完成并执行最终同步
    """
    try:
        # 更新状态为处理中
        _update_task_status(result_id, status="processing")

        # 批量提交子任务到队列
        from celery import group, chain

        job = group(
            analyze_single_post_screening.s(
                result_id=result_id,
                task_id=task_id,
                post_id=post_id,
                project_keywords=project_keywords
            )
            for post_id in post_ids
        )

        # 链接最终化任务：所有子任务完成 → 执行最终同步
        workflow = chain(job, finalize_screening_analysis.si(result_id, len(post_ids)))

        # 异步执行工作流
        workflow.apply_async()

        logger.info(f"已提交 {len(post_ids)} 个子任务到队列，启动监控任务")

        return {
            "status": "dispatched",
            "subtasks_count": len(post_ids),
            "message": f"已提交 {len(post_ids)} 个分析任务到队列"
        }

    except Exception as e:
        logger.error(f"协调器任务失败: {e}", exc_info=True)
        _update_task_status(
            result_id=result_id,
            status="failed",
            error_message=str(e),
        )
        raise


# 保持原有的任务名以保持兼容性
@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.screening.posts",
    max_retries=0,
)
def run_post_screening(
    self,
    result_id: int,
    task_id: int,
    post_ids: list[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """帖子AI初筛分析（主入口，转发到协调器）"""
    return run_post_screening_coordinator(
        result_id=result_id,
        task_id=task_id,
        post_ids=post_ids,
        project_keywords=project_keywords
    )
