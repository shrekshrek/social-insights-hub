from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.pagination import get_pagination_params, PaginationParams
from src.rbac import schemas, service
from src.rbac.dependencies import (
    require_role_read,
    require_role_write,
    require_role_delete,
    require_permission_read,
    get_current_user_permissions,
    get_current_user_roles,
)
from src.schemas import MessageResponse

router = APIRouter(
    prefix="/rbac",
    tags=["RBAC"],
)


# Permission endpoints
@router.get(
    "/permissions",
    response_model=schemas.PermissionListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get permissions list",
    description="获取系统权限列表，支持分页。返回所有已定义的权限，包括核心权限和业务权限。",
    responses={200: {"description": "权限列表"}, 403: {"description": "无权限访问"}},
)
async def get_permissions(
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_permission_read),
):
    """
    获取系统中所有权限的列表。

    权限使用 target:action 格式，如 user:read、dashboard:access。
    需要 permission:read 权限才能访问此接口。
    """
    permissions, total = await service.get_permissions(db, pagination)
    return schemas.PermissionListResponse.create(
        items=permissions,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/permissions/{permission_id}",
    response_model=schemas.PermissionRead,
    status_code=status.HTTP_200_OK,
    summary="Get permission by ID",
    description="根据权限ID获取单个权限的详细信息。",
    responses={
        200: {"description": "权限详情"},
        403: {"description": "无权限访问"},
        404: {"description": "权限不存在"},
    },
)
async def get_permission(
    permission_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_permission_read),
):
    """
    根据ID获取权限的详细信息。

    返回包括权限的 target、action、display_name 和 description。
    需要 permission:read 权限才能访问此接口。
    """
    permission = await service.get_permission_by_id(db, permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found"
        )
    return permission


# Role endpoints
@router.get(
    "/roles",
    response_model=schemas.RoleListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get roles list",
    description="获取系统角色列表，支持分页。包括核心角色（super_admin, admin, user）和自定义角色。",
    responses={
        200: {"description": "角色列表，包含每个角色的权限"},
        403: {"description": "无权限访问"},
    },
)
async def get_roles(
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_read),
):
    """
    获取系统中所有角色的列表。

    每个角色包含其所有的权限列表。
    核心角色（super_admin, admin, user）不可删除。
    需要 role:read 权限才能访问此接口。
    """
    roles, total = await service.get_roles(db, pagination)

    # 转换为响应格式
    role_items = service._convert_roles_to_schemas(roles)

    return schemas.RoleListResponse.create(
        items=role_items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "/roles",
    response_model=schemas.RoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create role",
)
async def create_role(
    role: schemas.RoleCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_write),
):
    """
    创建角色
    """
    try:
        db_role = await service.create_role(db, role)

        # 重新获取角色信息（包含权限）
        db_role = await service.get_role_by_id(db, db_role.id)
        return service._convert_role_to_schema(db_role)
    except service.RoleAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/roles/{role_id}",
    response_model=schemas.RoleRead,
    status_code=status.HTTP_200_OK,
    summary="Get role by ID",
)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_read),
):
    """
    根据ID获取角色
    """
    role = await service.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )

    return service._convert_role_to_schema(role)


@router.put(
    "/roles/{role_id}",
    response_model=schemas.RoleRead,
    status_code=status.HTTP_200_OK,
    summary="Update role",
)
async def update_role(
    role_id: int,
    role: schemas.RoleUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_write),
):
    """
    更新角色
    """
    db_role = await service.update_role(db, role_id, role)
    if not db_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )

    # 重新获取角色信息（包含权限）
    db_role = await service.get_role_by_id(db, role_id)
    return service._convert_role_to_schema(db_role)


@router.delete(
    "/roles/{role_id}",
    response_model=schemas.RoleRead,
    status_code=status.HTTP_200_OK,
    summary="Delete role",
)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_delete),
):
    """
    删除角色
    """
    try:
        # 先获取要删除的角色信息（包含权限）
        db_role = await service.get_role_by_id(db, role_id)
        if not db_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
            )

        # 执行删除操作
        success = await service.delete_role(db, role_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
            )

        # 返回被删除的角色信息
        return db_role
    except service.RoleNotDeletableException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Role Permission endpoints
@router.get(
    "/roles/{role_id}/permissions",
    response_model=List[schemas.PermissionRead],
    status_code=status.HTTP_200_OK,
    summary="Get role permissions",
)
async def get_role_permissions(
    role_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_read),
):
    """
    获取角色的权限列表
    """
    permissions = await service.get_role_permissions(db, role_id)
    return permissions


@router.post(
    "/roles/{role_id}/permissions",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign permissions to role",
)
async def assign_role_permissions(
    role_id: int,
    permission_assign: schemas.RolePermissionAssign,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_write),
):
    """
    为角色分配权限（替换式）
    """
    success = await service.assign_role_permissions(
        db, role_id, permission_assign.permission_ids
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return MessageResponse(message="Permissions assigned successfully")


# User Role endpoints
@router.post(
    "/users/{user_id}/roles",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign roles to user",
)
async def assign_user_roles(
    user_id: int,
    role_assign: schemas.UserRoleAssign,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_write),
):
    """
    为用户分配角色
    """
    success = await service.assign_user_roles(db, user_id, role_assign.role_ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return MessageResponse(message="Roles assigned successfully")


@router.get(
    "/users/{user_id}/roles",
    response_model=List[schemas.RoleRead],
    status_code=status.HTTP_200_OK,
    summary="Get user roles",
)
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_read),
):
    """
    获取用户的角色列表
    """
    roles = await service.get_user_roles(db, user_id)

    # 转换为响应格式
    return service._convert_roles_to_schemas(roles)


@router.get(
    "/users/{user_id}/permissions",
    response_model=List[schemas.PermissionRead],
    status_code=status.HTTP_200_OK,
    summary="Get user permissions",
)
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role_read),
):
    """
    获取用户的所有权限
    """
    permissions = await service.get_user_permissions(db, user_id)
    return permissions


# Current user endpoints
@router.get(
    "/me/permissions",
    response_model=List[dict],
    status_code=status.HTTP_200_OK,
    summary="Get current user permissions",
)
async def get_my_permissions(
    permissions: List[dict] = Depends(get_current_user_permissions),
):
    """
    获取当前用户的权限列表（结构化格式）
    """
    return permissions


@router.get(
    "/me/roles",
    response_model=List[dict],
    status_code=status.HTTP_200_OK,
    summary="Get current user roles",
)
async def get_my_roles(roles: List[dict] = Depends(get_current_user_roles)):
    """
    获取当前用户的角色列表
    """
    return roles


# Utility endpoints
@router.get(
    "/permission-groups",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get auto-generated permission groups",
)
async def get_permission_groups():
    """
    获取自动生成的权限分组配置

    供前端权限管理页面使用，基于权限定义自动生成分组
    """
    from .init_data import auto_generate_permission_groups

    return auto_generate_permission_groups()
