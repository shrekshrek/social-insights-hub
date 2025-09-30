"""
RBAC 模块异常定义
只包含实际使用的异常类
"""

from fastapi import HTTPException, status


class RoleAlreadyExistsException(HTTPException):
    """角色已存在异常"""

    def __init__(self, role_name: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role '{role_name}' already exists",
        )


class RoleNotDeletableException(HTTPException):
    """角色不可删除异常"""

    def __init__(self, role_name: str, reason: str = "System role cannot be deleted"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role_name}' cannot be deleted: {reason}",
        )


class PermissionAlreadyExistsException(HTTPException):
    """权限已存在异常（内部初始化使用）"""

    def __init__(self, permission_key: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Permission '{permission_key}' already exists",
        )


class InsufficientPermissionsException(HTTPException):
    """权限不足异常"""

    def __init__(self, required_permission: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: {required_permission} required",
        )
