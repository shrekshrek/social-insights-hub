"""社交媒体模块初始化数据

初始化7个社交媒体平台的基础数据
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .models import Platform

logger = logging.getLogger(__name__)


# 7个平台的基础数据（根据CRAWLER_DATA_STRUCTURE.md）
PLATFORM_DATA = [
    {
        "name": "Bilibili",
        "code": "bili",
        "description": "B站视频平台",
        "base_url": "https://www.bilibili.com",
    },
    {
        "name": "Douyin",
        "code": "dy",
        "description": "抖音短视频平台",
        "base_url": "https://www.douyin.com",
    },
    {
        "name": "Kuaishou",
        "code": "ks",
        "description": "快手短视频平台",
        "base_url": "https://www.kuaishou.com",
    },
    {
        "name": "Tieba",
        "code": "tieba",
        "description": "百度贴吧论坛社区",
        "base_url": "https://tieba.baidu.com",
    },
    {
        "name": "Weibo",
        "code": "wb",
        "description": "微博社交媒体平台",
        "base_url": "https://weibo.com",
    },
    {
        "name": "XiaoHongShu",
        "code": "xhs",
        "description": "小红书生活方式分享平台",
        "base_url": "https://www.xiaohongshu.com",
    },
    {
        "name": "Zhihu",
        "code": "zhihu",
        "description": "知乎问答社区平台",
        "base_url": "https://www.zhihu.com",
    },
]


async def init_platforms(db: AsyncSession) -> None:
    """初始化社交媒体平台数据

    如果平台已存在（根据code判断），则跳过。
    只在首次运行时创建平台数据。

    Args:
        db: 数据库会话
    """
    logger.info("开始初始化社交媒体平台数据...")

    created_count = 0
    existing_count = 0

    for platform_data in PLATFORM_DATA:
        # 检查平台是否已存在
        result = await db.execute(
            select(Platform).where(Platform.code == platform_data["code"])
        )
        existing_platform = result.scalar_one_or_none()

        if existing_platform:
            logger.debug(f"平台 {platform_data['name']} 已存在，跳过")
            existing_count += 1
            continue

        # 创建新平台
        platform = Platform(**platform_data)
        db.add(platform)
        created_count += 1
        logger.info(f"创建平台: {platform_data['name']} ({platform_data['code']})")

    if created_count > 0:
        await db.commit()
        logger.info(f"✅ 成功创建 {created_count} 个平台")

    if existing_count > 0:
        logger.info(f"跳过 {existing_count} 个已存在的平台")

    logger.info("社交媒体平台数据初始化完成")


async def init_social_media_data(db: AsyncSession) -> None:
    """初始化social_media模块的所有数据

    这是统一的入口函数，可以在main.py的lifespan中调用。

    Args:
        db: 数据库会话
    """
    await init_platforms(db)
