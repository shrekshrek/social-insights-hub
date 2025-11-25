"""AI初筛任务 - 批量API调用模式（同步DB + gevent协程）

优化后的架构：
1. 协调器：将帖子分批（每批5个），分发批次任务
2. 子任务：批量分析一批帖子（一次LLM调用处理5个帖子）
3. Worker Pool：gevent协程池自动调度，完成一批取下一批

技术栈：
- Celery + gevent pool（100协程）
- 同步DB（psycopg2）避免事件循环冲突
- LangChain同步调用（invoke代替ainvoke）
- 批量API调用：减少80%的API请求次数

优化效果：
- 500个帖子：从500次API调用 → 100次API调用
- 降低成本：减少80%的LLM API调用费用
- 提升速度：减少网络往返次数
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
from src.social_media.analysis.models import PostAnalysis, AnalysisJob
from src.social_media.tasks.models import SocialPost
from src.social_media.analysis.celery_tasks.progress_manager import AnalysisProgressManager
from src.social_media.analysis.celery_tasks.llm_utils import invoke_llm_with_stats_sync

logger = logging.getLogger(__name__)


def _analyze_batch_posts(
    result_id: int,
    task_id: int,
    post_ids: list[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """批量分析多个帖子（同步实现，减少API调用次数）

    Args:
        result_id: 分析结果ID
        task_id: 任务ID
        post_ids: 要分析的帖子ID列表（通常5个一批）
        project_keywords: 项目关键词

    Returns:
        批量分析结果
    """
    try:
        llm = get_llm(llm_type="chat")
        db = SyncSessionLocal()

        try:
            # 1. 批量获取帖子数据
            stmt = select(SocialPost).where(SocialPost.id.in_(post_ids))
            result = db.execute(stmt)
            posts = {post.id: post for post in result.scalars().all()}

            if not posts:
                logger.warning(f"批次帖子均不存在: {post_ids}")
                return {"success": False, "analyzed": 0, "failed": len(post_ids)}

            # 2. 构建批量提示词
            posts_content = []
            for i, post_id in enumerate(post_ids, 1):
                post = posts.get(post_id)
                if post:
                    posts_content.append(f"""
帖子{i}（ID:{post_id}）：
标题：{post.title or '无'}
正文：{post.content}
""")

            prompt = f"""请对以下社交媒体帖子进行批量初筛评分：

项目关键词：{project_keywords}

{''.join(posts_content)}

请从以下维度评分（0-10分）：
1. 垃圾分（spam_score）：是否为垃圾、广告、灌水内容
2. 价值分（value_score）：内容的信息价值和质量
3. 相关度分（relevance_score）：与项目关键词的相关程度
4. 情感倾向（sentiment）：-1（负面）、0（中性）、1（正面）

请以JSON数组格式返回结果（按帖子顺序）：
[
    {{"post_id": {post_ids[0] if post_ids else 0}, "spam_score": 分数, "value_score": 分数, "relevance_score": 分数, "sentiment": -1/0/1}},
    ...
]"""

            # 3. 调用LLM（一次调用分析多个帖子）
            response, token_stats = invoke_llm_with_stats_sync(
                llm=llm,
                messages=[{"role": "user", "content": prompt}],
                llm_type="chat"
            )

            # 4. 解析响应
            try:
                # 尝试提取JSON数组
                json_match = re.search(r'\[[\s\S]*\]', response.content)
                if json_match:
                    results = json.loads(json_match.group())
                else:
                    results = json.loads(response.content)

                if not isinstance(results, list):
                    raise ValueError("响应不是数组格式")

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"解析AI批量响应失败: {e}\nResponse: {response.content}")
                raise ValueError(f"无法解析AI响应: {e}")

            # 5. 批量保存结果
            analyzed_count = 0
            failed_count = 0

            for item in results:
                post_id = item.get("post_id")
                if not post_id or post_id not in posts:
                    continue

                try:
                    # Upsert分析结果
                    stmt = select(PostAnalysis).where(PostAnalysis.post_id == post_id)
                    result = db.execute(stmt)
                    post_analysis = result.scalar_one_or_none()

                    if post_analysis:
                        post_analysis.task_id = task_id
                        post_analysis.spam_score = item.get("spam_score")
                        post_analysis.value_score = item.get("value_score")
                        post_analysis.relevance_score = item.get("relevance_score")
                        post_analysis.sentiment = item.get("sentiment")
                        post_analysis.analyzed_at = datetime.now(timezone.utc)
                        post_analysis.analysis_model = "deepseek-chat"
                    else:
                        post_analysis = PostAnalysis(
                            task_id=task_id,
                            post_id=post_id,
                            spam_score=item.get("spam_score"),
                            value_score=item.get("value_score"),
                            relevance_score=item.get("relevance_score"),
                            sentiment=item.get("sentiment"),
                            analyzed_at=datetime.now(timezone.utc),
                            analysis_model="deepseek-chat",
                        )
                        db.add(post_analysis)

                    analyzed_count += 1

                except Exception as e:
                    logger.error(f"保存帖子 {post_id} 分析结果失败: {e}")
                    failed_count += 1

            db.commit()

            # 6. 更新进度
            progress_mgr = AnalysisProgressManager(result_id)
            if analyzed_count > 0:
                # 将token统计平均分配到每个帖子
                for _ in range(analyzed_count):
                    progress_mgr.increment_analyzed({
                        'input_tokens': token_stats['input_tokens'] // analyzed_count,
                        'output_tokens': token_stats['output_tokens'] // analyzed_count,
                        'total_tokens': token_stats['total_tokens'] // analyzed_count,
                        'total_cost_cny': token_stats['total_cost_cny'] / analyzed_count,
                        'duration_seconds': token_stats['duration_seconds'] / analyzed_count,
                    })

            if failed_count > 0:
                for _ in range(failed_count):
                    progress_mgr.increment_failed()

            logger.info(f"批量分析完成: {analyzed_count}/{len(post_ids)} 成功")
            return {
                "success": True,
                "analyzed": analyzed_count,
                "failed": failed_count,
                "token_usage": token_stats
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"批量分析失败: {e}", exc_info=True)
        progress_mgr = AnalysisProgressManager(result_id)
        for _ in range(len(post_ids)):
            progress_mgr.increment_failed()
        return {"success": False, "analyzed": 0, "failed": len(post_ids), "error": str(e)}


def _update_task_status(result_id: int, status: str, **kwargs):
    """更新分析任务状态（同步）"""
    db = SyncSessionLocal()
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
            **kwargs
        }

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == result_id)
            .values(**update_data)
        )
        db.execute(stmt)
        db.commit()

    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.screening.batch_posts",
    max_retries=2,
    default_retry_delay=30,
)
def analyze_batch_posts_screening(
    self,
    result_id: int,
    task_id: int,
    post_ids: list[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """批量分析帖子的初筛任务（子任务）

    每个子任务处理一批帖子（通常5个），在gevent协程池中执行
    使用同步DB避免事件循环冲突，一次LLM调用处理多个帖子

    Args:
        result_id: 分析结果ID
        task_id: 任务ID
        post_ids: 要分析的帖子ID列表（通常5个一批）
        project_keywords: 项目关键词

    Returns:
        批量分析结果
    """
    return _analyze_batch_posts(result_id, task_id, post_ids, project_keywords)


@celery_app.task(
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
    name="analysis.screening.coordinator",
    max_retries=0,
)
def screening_coordinator(
    self,
    result_id: int,
    task_id: int,
    post_ids: list[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """帖子初筛分析协调器（批量模式）

    职责：
    1. 将帖子分批（每批5个）
    2. 为每批创建一个子任务（减少API调用次数）
    3. 启动监控任务等待完成并执行最终同步

    优化效果：
    - 500个帖子：从500次API调用 → 100次API调用（减少80%）
    """
    try:
        # 更新状态为处理中
        _update_task_status(result_id, status="processing")

        # 将帖子分批，每批5个
        from celery import group, chain

        BATCH_SIZE = 5
        batches = [
            post_ids[i:i + BATCH_SIZE]
            for i in range(0, len(post_ids), BATCH_SIZE)
        ]

        # 为每批创建一个子任务
        job = group(
            analyze_batch_posts_screening.s(
                result_id=result_id,
                task_id=task_id,
                post_ids=batch,
                project_keywords=project_keywords
            )
            for batch in batches
        )

        # 链接最终化任务：所有子任务完成 → 执行最终同步
        # 注意：finalizer需要知道总帖子数（不是批次数）
        workflow = chain(job, finalize_screening_analysis.si(result_id, len(post_ids)))

        # 异步执行工作流
        workflow.apply_async()

        logger.info(
            f"已提交 {len(batches)} 个批次任务（共 {len(post_ids)} 个帖子，"
            f"每批 {BATCH_SIZE} 个）到队列，启动监控任务"
        )

        return {
            "status": "dispatched",
            "subtasks_count": len(batches),
            "total_posts": len(post_ids),
            "batch_size": BATCH_SIZE,
            "message": f"已提交 {len(batches)} 个批次任务（共 {len(post_ids)} 个帖子）到队列"
        }

    except Exception as e:
        logger.error(f"协调器任务失败: {e}", exc_info=True)
        _update_task_status(
            result_id=result_id,
            status="failed",
            error_message=str(e),
        )
        raise
