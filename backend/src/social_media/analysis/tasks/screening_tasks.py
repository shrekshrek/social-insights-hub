"""AI初筛任务

实现任务级的帖子初筛分析，包括：
- 垃圾分（spam_score）
- 价值分（value_score）
- 相关度分（relevance_score）
- 情感倾向（sentiment）

注意：评论不需要初筛分析，只对帖子进行初筛。
"""

import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone

from src.celery_app import celery_app
from src.social_media.analysis.base_task import AnalysisTaskBase
from src.database import AsyncSessionLocal
from src.langchain.llm import get_llm
from src.langchain.utils import invoke_llm_with_stats
from src.social_media.analysis.models import PostAnalysis
# Import related models to ensure SQLAlchemy mapper initialization
from src.social_media.tasks.models import DataTask, SocialPost

logger = logging.getLogger(__name__)


def run_async(coro):
    """运行异步函数的辅助函数，兼容eventlet"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _run_post_screening_async(
    self,
    result_id: int,
    task_id: int,
    post_ids: List[int],
    project_keywords: str,
) -> Dict[str, Any]:
    """运行帖子AI初筛分析（异步实现）"""
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
                    stats.add_stats(token_stats, llm_type="chat")

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
                    # 检查是否已存在记录
                    stmt = select(PostAnalysis).where(PostAnalysis.post_id == post_id)
                    result = await db.execute(stmt)
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
    name="analysis.screening.posts",
    max_retries=3,
    default_retry_delay=60,
)
def run_post_screening(
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
    return run_async(_run_post_screening_async(self, result_id, task_id, post_ids, project_keywords))
