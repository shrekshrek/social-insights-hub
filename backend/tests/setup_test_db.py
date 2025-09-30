#!/usr/bin/env python3
"""
测试数据库初始化脚本
确保测试数据库存在并准备就绪
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

# 加载测试环境变量
env_path = Path(__file__).parent.parent / ".env.test"
load_dotenv(dotenv_path=env_path, override=True)


async def create_test_database():
    """创建测试数据库（如果不存在）"""
    # 连接到默认的 postgres 数据库
    admin_db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    admin_engine = create_async_engine(admin_db_url, isolation_level="AUTOCOMMIT")

    async with admin_engine.connect() as conn:
        # 检查测试数据库是否存在
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'test_db'")
        )
        exists = result.scalar() is not None

        if not exists:
            print("Creating test database...")
            await conn.execute(text("CREATE DATABASE test_db"))
            print("Test database created successfully!")
        else:
            print("Test database already exists.")

    await admin_engine.dispose()

    # 确保可以连接到测试数据库
    test_db_url = os.getenv("DATABASE_URL")
    test_engine = create_async_engine(test_db_url)

    try:
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            print("Successfully connected to test database!")
    finally:
        await test_engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(create_test_database())
    except Exception as e:
        print(f"Error setting up test database: {e}")
        sys.exit(1)
