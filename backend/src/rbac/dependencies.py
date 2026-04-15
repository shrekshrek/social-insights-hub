from typing import Callable, List

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.rbac import service
from src.rbac.exceptions import InsufficientPermissionsException


async def require_permission(
    permission: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """
    权限检查依赖函数

    Args:
        permission: 需要的权限，如 "user:read"
        db: 数据库会话
        current_user: 当前用户

    Returns:
        当前用户（如果有权限）

    Raises:
        HTTPException: 如果没有权限
    """
    has_permission = await service.check_user_permission_cached(
        db, current_user.id, permission
    )
    if not has_permission:
        raise InsufficientPermissionsException(permission)
    return current_user


def create_permission_dependency(permission: str) -> Callable:
    """
    创建特定权限的依赖函数

    Args:
        permission: 权限名称

    Returns:
        依赖函数
    """

    async def permission_dependency(
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ) -> User:
        return await require_permission(permission, db, current_user)

    return permission_dependency


# 数据操作权限依赖
require_user_read = create_permission_dependency("user:read")
require_user_write = create_permission_dependency("user:write")
require_user_delete = create_permission_dependency("user:delete")
require_role_read = create_permission_dependency("role:read")
require_role_write = create_permission_dependency("role:write")
require_role_delete = create_permission_dependency("role:delete")
require_permission_read = create_permission_dependency("permission:read")

# 页面访问权限依赖
require_dashboard_access = create_permission_dependency("dashboard:access")
require_user_mgmt_access = create_permission_dependency("user_mgmt:access")
require_role_mgmt_access = create_permission_dependency("role_mgmt:access")
require_perm_mgmt_access = create_permission_dependency("perm_mgmt:access")

# 社媒监测权限依赖
require_social_monitor_read = create_permission_dependency("social_monitor:read")
require_social_monitor_write = create_permission_dependency("social_monitor:write")
require_social_monitor_delete = create_permission_dependency("social_monitor:delete")

# 社媒采集任务权限依赖
require_social_task_read = create_permission_dependency("social_task:read")
require_social_task_write = create_permission_dependency("social_task:write")
require_social_task_delete = create_permission_dependency("social_task:delete")

# 新闻监测权限依赖
require_news_monitor_read = create_permission_dependency("news_monitor:read")
require_news_monitor_write = create_permission_dependency("news_monitor:write")
require_news_monitor_delete = create_permission_dependency("news_monitor:delete")

# 新闻采集任务权限依赖
require_news_task_read = create_permission_dependency("news_task:read")
require_news_task_write = create_permission_dependency("news_task:write")
require_news_task_delete = create_permission_dependency("news_task:delete")

# 策略研究权限依赖
require_strategy_read = create_permission_dependency("strategy:read")
require_strategy_write = create_permission_dependency("strategy:write")
require_strategy_delete = create_permission_dependency("strategy:delete")

# 知识库权限依赖
require_kb_read = create_permission_dependency("knowledge_base:read")
require_kb_write = create_permission_dependency("knowledge_base:write")
require_kb_delete = create_permission_dependency("knowledge_base:delete")

# Research Agent 权限依赖
require_research_agent_read = create_permission_dependency("research_agent:read")
require_research_agent_write = create_permission_dependency("research_agent:write")
require_research_agent_delete = create_permission_dependency("research_agent:delete")

# 分析权限依赖
require_analysis_task_run_screening = create_permission_dependency("analysis:task.run_screening")
require_analysis_task_run_deep = create_permission_dependency("analysis:task.run_deep")
require_analysis_task_view_results = create_permission_dependency("analysis:task.view_results")
require_analysis_task_delete_results = create_permission_dependency("analysis:task.delete_results")
require_analysis_monitor_run_clustering = create_permission_dependency("analysis:monitor.run_clustering")
require_analysis_monitor_view_results = create_permission_dependency("analysis:monitor.view_results")
require_analysis_monitor_delete_results = create_permission_dependency("analysis:monitor.delete_results")
require_analysis_read = create_permission_dependency("analysis:read")
require_analysis_stats_view = create_permission_dependency("analysis:stats.view")
require_analysis_results_export = create_permission_dependency("analysis:results.export")


async def get_current_user_permissions(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """
    获取当前用户的所有权限

    Returns:
        权限对象列表 (结构化格式)
    """
    permissions_objs = await service.get_user_permissions_db(db, current_user.id)
    return [
        {
            "target": p.target,
            "action": p.action,
            "display_name": p.display_name,
            "description": p.description,
        }
        for p in permissions_objs
    ]


async def get_current_user_roles(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """
    获取当前用户的所有角色

    Returns:
        角色信息列表
    """
    roles = await service.get_user_roles(db, current_user.id)
    return [{"id": r.id, "name": r.name, "display_name": r.display_name} for r in roles]
