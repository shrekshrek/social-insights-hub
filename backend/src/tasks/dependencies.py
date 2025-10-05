"""
爬虫任务模块权限依赖
"""

from src.rbac.dependencies import create_permission_dependency

# 爬虫任务权限依赖（共5个权限）
require_crawler_tasks_access = create_permission_dependency("crawler_tasks:access")
require_crawler_tasks_read = create_permission_dependency("crawler_tasks:read")
require_crawler_tasks_write = create_permission_dependency("crawler_tasks:write")
require_crawler_tasks_delete = create_permission_dependency("crawler_tasks:delete")
require_crawler_tasks_execute = create_permission_dependency("crawler_tasks:execute")
