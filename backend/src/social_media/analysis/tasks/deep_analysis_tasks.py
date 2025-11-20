"""AI深度分析任务

实现任务级的帖子和评论深度分析，包括：
- 实体识别（品牌/产品/服务）
- 观点提取
- 内容总结
"""

import logging
import asyncio
import json
import re
from typing import List, Dict, Any
from datetime import datetime, timezone

from src.celery_app import celery_app
from src.social_media.analysis.base_task import AnalysisTaskBase
from src.database import AsyncSessionLocal
from src.langchain.utils import invoke_llm_with_stats
from src.social_media.analysis.models import PostAnalysis
from src.social_media.analysis.schemas import PostDeepResult, CommentDeepResult
# Import related models to ensure SQLAlchemy mapper initialization
from src.social_media.tasks.models import DataTask, SocialPost, SocialComment

logger = logging.getLogger(__name__)


def run_async(coro):
    """运行异步函数的辅助函数，兼容eventlet"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _run_post_deep_analysis_async(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    analysis_focus: List[str] = None,
) -> Dict[str, Any]:
    """运行帖子AI深度分析（异步实现）"""
    try:
        # 更新状态为处理中
        await self.update_task_result(result_id, status="processing")

        analyzed_count = 0
        failed_count = 0
        stats = self.get_stats()

        # 创建LangChain链
        from src.langchain.chains.post_extraction_chain import create_post_extraction_chain
        chain = create_post_extraction_chain()

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from src.social_media.tasks.models import SocialPost

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

                    # 准备输入内容
                    content = f"标题：{post.title or '无'}\n正文：{post.content}"

                    # 调用LLM进行分析
                    from src.langchain.chains.post_extraction_chain import (
                        POST_EXTRACTION_SYSTEM_TEMPLATE,
                        POST_EXTRACTION_USER_TEMPLATE
                    )

                    messages = [
                        {"role": "system", "content": POST_EXTRACTION_SYSTEM_TEMPLATE},
                        {"role": "user", "content": POST_EXTRACTION_USER_TEMPLATE.format(content=content)}
                    ]

                    # 获取 LLM 实例
                    from src.langchain.llm import get_llm
                    llm = get_llm(llm_type="chat")

                    response, token_stats = await invoke_llm_with_stats(
                        llm=llm,
                        messages=messages,
                        llm_type="chat"
                    )

                    # 累积统计
                    stats.add_stats(token_stats, llm_type="chat")

                    # 解析响应
                    response_content = response.content
                    try:
                        # 尝试直接解析 JSON
                        json_match = re.search(r'\{[\s\S]*\}', response_content)
                        if json_match:
                            json_str = json_match.group()
                            extraction_data = json.loads(json_str)
                        else:
                            # 尝试修复常见 JSON 错误或直接解析整个内容
                            extraction_data = json.loads(response_content)

                        # 验证数据结构
                        validated_result = PostDeepResult(**extraction_data)
                        extraction_dict = validated_result.model_dump()

                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f"解析AI响应失败: {e}\nResponse: {response_content}")
                        raise ValueError(f"无法解析AI响应: {e}")

                    # 保存分析结果
                    # 检查是否已存在记录
                    stmt = select(PostAnalysis).where(PostAnalysis.post_id == post_id)
                    result = await db.execute(stmt)
                    post_analysis = result.scalar_one_or_none()

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

                    await db.commit()

                    analyzed_count += 1
                    logger.debug(f"帖子 {post_id} 深度分析完成")

                except Exception as e:
                    logger.error(f"深度分析帖子 {post_id} 失败: {e}", exc_info=True)
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

        logger.info(f"帖子深度分析任务完成: {analyzed_count}/{len(post_ids)} 成功")

        return {
            "status": "success",
            "analyzed": analyzed_count,
            "failed": failed_count,
            "token_usage": stats.to_dict(),
        }

    except Exception as e:
        logger.error(f"帖子深度分析任务失败: {e}", exc_info=True)
        await self.update_task_result(
            result_id=result_id,
            status="failed",
            error_message=str(e),
        )
        raise


async def _run_comment_deep_analysis_async(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    analysis_focus: List[str] = None,
) -> Dict[str, Any]:
    """运行评论AI深度分析（异步实现）

    策略：以帖子为单位，批量分析该帖子下的评论，结果聚合存储在PostAnalysis.comment_deep_result中。
    """
    try:
        # 更新状态
        await self.update_task_result(result_id, status="processing")

        analyzed_count = 0
        failed_count = 0
        stats = self.get_stats()

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from src.social_media.tasks.models import SocialPost, SocialComment
            from src.social_media.analysis.models import PostAnalysis

            for post_id in post_ids:
                try:
                    # 1. 获取帖子信息和之前的分析结果(作为上下文)
                    stmt = select(SocialPost).where(SocialPost.id == post_id)
                    result = await db.execute(stmt)
                    post = result.scalar_one_or_none()

                    if not post:
                        continue

                    # 尝试获取帖子的深度分析结果作为上下文
                    stmt = select(PostAnalysis).where(PostAnalysis.post_id == post_id)
                    result = await db.execute(stmt)
                    post_analysis = result.scalar_one_or_none()

                    context = f"帖子标题：{post.title or '无'}\n帖子内容：{post.content}"
                    if post_analysis and post_analysis.post_deep_result:
                        summary = post_analysis.post_deep_result.get('summary', '')
                        if summary:
                            context += f"\n\nAI对帖子的总结：{summary}"

                    # 2. 获取帖子下的评论
                    # 选取点赞最高的前100条评论
                    stmt = select(SocialComment).where(
                        SocialComment.post_id == post_id
                    ).order_by(SocialComment.likes_count.desc()).limit(100)

                    result = await db.execute(stmt)
                    comments = result.scalars().all()

                    if not comments:
                        continue

                    # 准备评论文本列表
                    comment_texts = [c.content for c in comments if c.content]
                    if not comment_texts:
                        continue

                    # 3. 调用LLM进行分析
                    from src.langchain.chains.comment_extraction_chain import (
                        COMMENT_ANALYSIS_SYSTEM_TEMPLATE,
                        COMMENT_ANALYSIS_USER_TEMPLATE
                    )

                    formatted_comments = "\n".join(
                        [f"评论{i+1}: {comment}" for i, comment in enumerate(comment_texts)]
                    )

                    context_text = f"背景上下文：\n{context}"

                    messages = [
                        {"role": "system", "content": COMMENT_ANALYSIS_SYSTEM_TEMPLATE},
                        {"role": "user", "content": COMMENT_ANALYSIS_USER_TEMPLATE.format(
                            context=context_text,
                            comments=formatted_comments
                        )}
                    ]

                    from src.langchain.llm import get_llm
                    llm = get_llm(llm_type="chat")

                    response, token_stats = await invoke_llm_with_stats(
                        llm=llm,
                        messages=messages,
                        llm_type="chat"
                    )

                    stats.add_stats(token_stats, llm_type="chat")

                    # 4. 解析和保存结果
                    response_content = response.content
                    try:
                        json_match = re.search(r'\{[\s\S]*\}', response_content)
                        if json_match:
                            json_str = json_match.group()
                            extraction_data = json.loads(json_str)
                        else:
                            extraction_data = json.loads(response_content)

                        # 修复 sentiment 字段
                        if "general_opinions" in extraction_data:
                            for op in extraction_data["general_opinions"]:
                                if "sentiment" not in op:
                                    op["sentiment"] = 0
                        if "entities" in extraction_data:
                            for ent in extraction_data["entities"]:
                                if "sentiment" not in ent:
                                    ent["sentiment"] = 0

                        validated_result = CommentDeepResult(**extraction_data)
                        extraction_dict = validated_result.model_dump()

                        # 保存/更新 PostAnalysis.comment_deep_result
                        if not post_analysis:
                            # 如果还没有PostAnalysis记录，创建一个
                            post_analysis = PostAnalysis(
                                task_id=task_id,
                                post_id=post_id,
                                comment_deep_result=extraction_dict,
                                analyzed_at=datetime.now(timezone.utc),
                                analysis_model="deepseek-chat",
                            )
                            db.add(post_analysis)
                        else:
                            # 更新现有记录
                            post_analysis.comment_deep_result = extraction_dict
                            post_analysis.analyzed_at = datetime.now(timezone.utc)
                            post_analysis.analysis_model = "deepseek-chat"

                        await db.commit()
                        analyzed_count += 1  # 这里计数是指完成了多少个帖子的评论分析

                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f"解析评论AI响应失败: {e}\nResponse: {response_content}")
                        raise ValueError(f"无法解析AI响应: {e}")

                except Exception as e:
                    logger.error(f"分析帖子 {post_id} 的评论失败: {e}", exc_info=True)
                    failed_count += 1
                    await db.rollback()

        # 更新任务结果
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

        return {
            "status": "success",
            "analyzed": analyzed_count,
            "failed": failed_count,
            "token_usage": stats.to_dict(),
        }

    except Exception as e:
        logger.error(f"评论深度分析任务失败: {e}", exc_info=True)
        await self.update_task_result(
            result_id=result_id,
            status="failed",
            error_message=str(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.deep.posts",
    max_retries=3,
    default_retry_delay=60,
)
def run_post_deep_analysis(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    analysis_focus: List[str] = None,
) -> Dict[str, Any]:
    """运行帖子AI深度分析

    Args:
        self: Celery任务实例（自动注入）
        result_id: TaskAnalysisResult的ID
        task_id: DataTask的ID
        post_ids: 要分析的帖子ID列表
        analysis_focus: 分析重点（暂未在Chain中使用，保留扩展性）

    Returns:
        分析结果统计
    """
    return run_async(_run_post_deep_analysis_async(self, result_id, task_id, post_ids, analysis_focus))


@celery_app.task(
    bind=True,
    base=AnalysisTaskBase,
    name="analysis.deep.comments",
    max_retries=3,
    default_retry_delay=60,
)
def run_comment_deep_analysis(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    analysis_focus: List[str] = None,
) -> Dict[str, Any]:
    """运行评论AI深度分析

    策略：以帖子为单位，批量分析该帖子下的评论，结果聚合存储在PostAnalysis.comment_deep_result中。

    Args:
        self: Celery任务实例
        result_id: TaskAnalysisResult的ID
        task_id: DataTask的ID
        post_ids: 要分析其评论的帖子ID列表
        analysis_focus: 分析重点
    """
    return run_async(_run_comment_deep_analysis_async(self, result_id, task_id, post_ids, analysis_focus))
