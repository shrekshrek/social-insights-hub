"""Permissions for crawler comments data module."""

from src.rbac.dependencies import create_permission_dependency

require_comments_access = create_permission_dependency("crawler_data_comments:access")
require_comments_read = create_permission_dependency("crawler_data_comments:read")
require_comments_write = create_permission_dependency("crawler_data_comments:write")
require_comments_delete = create_permission_dependency("crawler_data_comments:delete")
