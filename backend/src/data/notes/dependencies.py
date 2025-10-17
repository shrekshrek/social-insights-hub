"""Permissions for crawler notes data module."""

from src.rbac.dependencies import create_permission_dependency

require_notes_access = create_permission_dependency("crawler_data_notes:access")
require_notes_read = create_permission_dependency("crawler_data_notes:read")
require_notes_write = create_permission_dependency("crawler_data_notes:write")
require_notes_delete = create_permission_dependency("crawler_data_notes:delete")
