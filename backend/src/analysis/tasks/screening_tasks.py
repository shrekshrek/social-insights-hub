"""AI初筛任务

实现任务级的帖子和评论初筛分析，包括：
- 垃圾分（spam_score）
- 价值分（value_score）
- 相关度分（relevance_score）
- 情感倾向（sentiment）
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from src.celery_app import celery_app
from src.analysis.base_task import AnalysisTaskBase
from src.database import AsyncSessionLocal
from src.langchain_module.utils import invoke_llm_with_stats, get_llm
from src.analysis.models import PostAnalysis, CommentAnalysis

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.screening.posts",
    max_retries=3,
    default_retry_delay=60,
)
async def run_post_screening(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """运行帖子AI初筛分析

    Args:
        self: Celery任务实例（自动注入）
        result_id: TaskAnalysisResult的ID
        task_id: DataTask的ID
        post_ids: 要分析的帖子ID列表
        project_keywords: 项目关键词（用于计算相关度）

    Returns:
        分析结果统计
    """
    try:
        # 更新状态为处理中
        await self.update_task_result(result_id, status="processing")

        analyzed_count = 0
        failed_count = 0
        stats = self.get_stats()

        # 获取LLM实例
        llm = get_llm(llm_type="chat")

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from src.tasks.models import SocialPost

            # 批量处理帖子
            for post_id in post_ids:
                try:
                    # 获取帖子数据
                    stmt = select(SocialPost).where(SocialPost.id == post_id)
                    result = await db.execute(stmt)
                    post = result.scalar_one_or_none()

                    if not post:
                        logger.warning(f"帖子 {post_id} 不存在")
                        failed_count += 1
                        continue

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

                    # 调用LLM进行分析
                    response, token_stats = await invoke_llm_with_stats(
                        llm=llm,
                        messages=[{"role": "user", "content": prompt}],
                        llm_type="chat"
                    )

                    # 累积统计
                    stats.add_call(token_stats)

                    # 解析响应
                    import json
                    try:
                        scores = json.loads(response.content)
                    except json.JSONDecodeError:
                        # 如果解析失败，尝试提取JSON
                        import re
                        match = re.search(r'\{[^}]+\}', response.content)
                        if match:
                            scores = json.loads(match.group())
                        else:
                            raise ValueError("无法解析AI响应")

                    # 保存分析结果
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
                    await db.commit()

                    analyzed_count += 1
                    logger.debug(f"帖子 {post_id} 分析完成")

                except Exception as e:
                    logger.error(f"分析帖子 {post_id} 失败: {e}", exc_info=True)
                    failed_count += 1
                    await db.rollback()

        # 更新为完成状态
        result_data = {
            "analyzed_count": analyzed_count,
            "failed_count": failed_count,
            "success_rate": analyzed_count / len(post_ids) if post_ids else 0,
        }

        await self.update_task_result(
            result_id=result_id,
            status="completed",
            result_data=result_data,
            analyzed_count=analyzed_count,
            failed_count=failed_count,
        )

        logger.info(f"帖子初筛任务完成: {analyzed_count}/{len(post_ids)} 成功")

        return {
            "status": "success",
            "analyzed": analyzed_count,
            "failed": failed_count,
            "token_usage": stats.to_dict(),
        }

    except Exception as e:
        logger.error(f"帖子初筛任务失败: {e}", exc_info=True)
        await self.update_task_result(
            result_id=result_id,
            status="failed",
            error_message=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.screening.comments",
    max_retries=3,
    default_retry_delay=60,
)
async def run_comment_screening(
    self,
    result_id: int,
    task_id: int,
    comment_ids: List[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """运行评论AI初筛分析

    Args:
        self: Celery任务实例（自动注入）
        result_id: TaskAnalysisResult的ID
        task_id: DataTask的ID
        comment_ids: 要分析的评论ID列表
        project_keywords: 项目关键词（用于计算相关度）

    Returns:
        分析结果统计
    """
    try:
        # 更新状态为处理中
        await self.update_task_result(result_id, status="processing")

        analyzed_count = 0
        failed_count = 0
        stats = self.get_stats()

        # 获取LLM实例
        llm = get_llm(llm_type="chat")

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from src.tasks.models import SocialComment

            # 批量处理评论
            for comment_id in comment_ids:
                try:
                    # 获取评论数据
                    stmt = select(SocialComment).where(SocialComment.id == comment_id)
                    result = await db.execute(stmt)
                    comment = result.scalar_one_or_none()

                    if not comment:
                        logger.warning(f"评论 {comment_id} 不存在")
                        failed_count += 1
                        continue

                    # 构建提示词
                    prompt = f"""请对以下社交媒体评论进行初筛评分：

项目关键词：{project_keywords}

评论内容：{comment.content}

请从以下维度评分（0-10分）：
1. 垃圾分（spam_score）：是否为垃圾、广告、灌水内容
2. 价值分（value_score）：评论的信息价值和质量
3. 相关度分（relevance_score）：与项目关键词的相关程度
4. 情感倾向（sentiment）：-1（负面）、0（中性）、1（正面）

请以JSON格式返回结果：
{{
    "spam_score": 分数,
    "value_score": 分数,
    "relevance_score": 分数,
    "sentiment": -1/0/1
}}"""

                    # 调用LLM进行分析
                    response, token_stats = await invoke_llm_with_stats(
                        llm=llm,
                        messages=[{"role": "user", "content": prompt}],
                        llm_type="chat"
                    )

                    # 累积统计
                    stats.add_call(token_stats)

                    # 解析响应
                    import json
                    try:
                        scores = json.loads(response.content)
                    except json.JSONDecodeError:
                        # 如果解析失败，尝试提取JSON
                        import re
                        match = re.search(r'\{[^}]+\}', response.content)
                        if match:
                            scores = json.loads(match.group())
                        else:
                            raise ValueError("无法解析AI响应")

                    # 保存分析结果
                    comment_analysis = CommentAnalysis(
                        task_id=task_id,
                        comment_id=comment_id,
                        spam_score=scores.get("spam_score"),
                        value_score=scores.get("value_score"),
                        relevance_score=scores.get("relevance_score"),
                        sentiment=scores.get("sentiment"),
                        analyzed_at=datetime.now(timezone.utc),
                        analysis_model="deepseek-chat",
                    )

                    db.add(comment_analysis)
                    await db.commit()

                    analyzed_count += 1
                    logger.debug(f"评论 {comment_id} 分析完成")

                except Exception as e:
                    logger.error(f"分析评论 {comment_id} 失败: {e}", exc_info=True)
                    failed_count += 1
                    await db.rollback()

        # 更新为完成状态
        result_data = {
            "analyzed_count": analyzed_count,
            "failed_count": failed_count,
            "success_rate": analyzed_count / len(comment_ids) if comment_ids else 0,
        }

        await self.update_task_result(
            result_id=result_id,
            status="completed",
            result_data=result_data,
            analyzed_count=analyzed_count,
            failed_count=failed_count,
        )

        logger.info(f"评论初筛任务完成: {analyzed_count}/{len(comment_ids)} 成功")

        return {
            "status": "success",
            "analyzed": analyzed_count,
            "failed": failed_count,
            "token_usage": stats.to_dict(),
        }

    except Exception as e:
        logger.error(f"评论初筛任务失败: {e}", exc_info=True)
        await self.update_task_result(
            result_id=result_id,
            status="failed",
            error_message=str(e),
        )
        raise
