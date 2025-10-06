"""Permissions for crawler resources module."""

from src.rbac.dependencies import create_permission_dependency

require_resources_access = create_permission_dependency("crawler_resources:access")
require_resources_read = create_permission_dependency("crawler_resources:read")
require_resources_write = create_permission_dependency("crawler_resources:write")
require_resources_delete = create_permission_dependency("crawler_resources:delete")
