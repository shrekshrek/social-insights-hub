"""修复原文的评论计数

这个脚本会遍历所有原文，统计每个原文的评论数量，并更新 comments_count 字段。
"""

import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_engine, AsyncSessionLocal
from src.task_manager.models import SocialPost, SocialComment


async def fix_comments_count():
    """修复所有原文的评论计数"""
    async with AsyncSessionLocal() as db:
        # 获取所有原文
        result = await db.execute(
            select(SocialPost).where(SocialPost.is_deleted == False)
        )
        posts = result.scalars().all()

        print(f"找到 {len(posts)} 个原文，开始修复评论计数...")

        fixed_count = 0
        for post in posts:
            # 统计该原文的评论数量
            count_result = await db.execute(
                select(func.count()).select_from(SocialComment).where(
                    SocialComment.post_id == post.id,
                    SocialComment.is_deleted == False
                )
            )
            actual_count = count_result.scalar_one()

            # 如果计数不一致，更新
            if post.comments_count != actual_count:
                print(f"原文 {post.id} (platform_id: {post.post_id_on_platform}): "
                      f"{post.comments_count} -> {actual_count}")
                post.comments_count = actual_count
                fixed_count += 1

        await db.commit()
        print(f"\n修复完成！共修复了 {fixed_count} 个原文的评论计数。")


if __name__ == "__main__":
    asyncio.run(fix_comments_count())
