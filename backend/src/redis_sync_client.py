"""同步Redis客户端 - 用于Celery任务（gevent环境）

针对高并发场景的Redis连接池优化：
- 100 gevent greenlets 并发执行任务
- 每个任务可能需要多次Redis操作（INCR, HINCRBY, RPUSH等）
- 连接池需要支持足够的并发连接数

连接池配置原则：
1. max_connections >= 并发数 × 1.5（考虑突发流量）
2. socket_timeout/socket_connect_timeout 防止连接卡死
3. socket_keepalive 保持长连接活性
4. retry_on_timeout 提高容错性
"""

import redis
from src.config import settings
import logging
import sys
import socket

logger = logging.getLogger(__name__)

# ==================== 连接池优化配置 ====================
# 基于 gevent pool concurrency=100 的优化参数

# TCP Keepalive 配置（跨平台兼容）
def get_keepalive_options():
    """
    根据平台获取TCP keepalive配置

    注意：socket_keepalive_options 在不同操作系统上的行为不同
    - Linux: 支持完整的 TCP_KEEPIDLE, TCP_KEEPINTVL, TCP_KEEPCNT
    - macOS/BSD: 部分支持或使用不同常量
    - Windows: 不支持这些选项
    """
    if sys.platform.startswith('linux'):
        # Linux 系统，启用完整的 keepalive 配置
        try:
            return {
                socket.TCP_KEEPIDLE: 60,   # 60秒无数据后开始探测
                socket.TCP_KEEPINTVL: 10,  # 每10秒探测一次
                socket.TCP_KEEPCNT: 3,     # 3次失败后断开
            }
        except AttributeError:
            # 某些 Linux 版本可能没有这些常量
            return None
    else:
        # macOS/Windows，只启用基础 keepalive（不设置详细参数）
        return None


REDIS_POOL_CONFIG = {
    # 核心连接池参数
    "max_connections": 150,  # 最大连接数 = 并发数 × 1.5（100 × 1.5）
    "decode_responses": True,  # 自动解码为字符串

    # 超时配置（防止连接卡死）
    "socket_timeout": 5,  # 单次操作超时：5秒
    "socket_connect_timeout": 3,  # 连接建立超时：3秒
    "socket_keepalive": True,  # 启用TCP keepalive

    # 重试配置
    "retry_on_timeout": True,  # 超时后自动重试一次
    "retry_on_error": [redis.exceptions.ConnectionError],  # 连接错误时重试

    # 健康检查
    "health_check_interval": 30,  # 每30秒检查连接健康状态
}

# 添加平台相关的 keepalive 配置
keepalive_opts = get_keepalive_options()
if keepalive_opts:
    REDIS_POOL_CONFIG["socket_keepalive_options"] = keepalive_opts
    logger.debug("TCP keepalive 详细配置已启用（Linux平台）")

# 创建同步Redis连接池（用于Celery + gevent）
sync_redis_pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    **REDIS_POOL_CONFIG
)

logger.info(
    f"✅ Redis连接池初始化完成: "
    f"max_connections={REDIS_POOL_CONFIG['max_connections']}, "
    f"timeout={REDIS_POOL_CONFIG['socket_timeout']}s"
)


def get_sync_redis() -> redis.Redis:
    """
    获取同步Redis客户端（用于Celery任务，gevent友好）

    特性：
    - 从连接池获取连接，支持高并发
    - 自动重试机制（超时/连接错误）
    - TCP keepalive 保持长连接
    - 健康检查自动剔除坏连接

    Returns:
        redis.Redis: 同步Redis客户端实例

    Example:
        redis_client = get_sync_redis()
        redis_client.incr("counter")
    """
    return redis.Redis(connection_pool=sync_redis_pool)


def get_pool_stats() -> dict:
    """
    获取连接池统计信息（用于监控）

    Returns:
        dict: 连接池状态
    """
    pool = sync_redis_pool
    return {
        "max_connections": pool.max_connections,
        "available_connections": len(pool._available_connections),
        "in_use_connections": len(pool._in_use_connections),
    }
