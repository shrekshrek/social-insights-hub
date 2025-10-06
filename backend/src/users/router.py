from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import models as auth_models
from src.auth import schemas as auth_schemas
from src.auth.dependencies import get_current_user
from src.database import get_async_db
from src.users import schemas, service
from src.pagination import get_pagination_params, PaginationParams
from src.rbac.dependencies import (
    require_user_read,
    require_user_delete,
    require_user_write,
)
from src.rbac import service as rbac_service
from src.users.dependencies import (
    require_user_read_or_self,
    require_user_write_or_self,
    require_user_delete_not_self,
)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=auth_schemas.UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current user",
)
async def read_users_me(
    current_user: auth_models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get current logged in user information.

    Returns the user profile information for the currently authenticated user.
    """
    # 获取用户的角色信息
    user_roles = await rbac_service.get_user_roles(db, current_user.id)
    role_names = [role.name for role in user_roles]

    # 使用统一的转换函数
    return service._convert_user_to_schema(current_user, role_names)


@router.get(
    "",
    response_model=schemas.UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get users list",
)
async def read_users(
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    _: auth_models.User = Depends(require_user_read),
):
    """
    Get list of users with pagination.

    Returns a paginated list of users. Only accessible to users with user:read permission.
    """
    users, total = await service.get_users(db, pagination)

    # 批量获取用户和角色信息，避免N+1查询
    user_list = await service.get_users_with_roles_batch(db, users)

    return schemas.UserListResponse.create(
        items=user_list,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "",
    response_model=auth_schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
)
async def create_user_admin(
    user_create: schemas.UserAdminCreate,
    db: AsyncSession = Depends(get_async_db),
    _: auth_models.User = Depends(require_user_write),
):
    """管理员创建用户并可选分配角色"""

    new_user = await service.create_user_admin(db, user_create)
    return new_user


@router.get(
    "/{user_id}",
    response_model=auth_schemas.UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get user by ID",
)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: auth_models.User = Depends(require_user_read_or_self),
):
    """
    Get user by ID.

    Users can access their own information, or users with user:read permission can access any user.
    """

    user_data = await service.get_user_with_roles(db, user_id)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user_data


@router.put(
    "/{user_id}",
    response_model=auth_schemas.UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update user",
)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: auth_models.User = Depends(require_user_write_or_self),
):
    """
    Update user information.
    """

    # 注意：UserUpdate 中不再包含 role 字段，角色管理通过 RBAC API 进行

    user = await service.update_user(db, user_id, user_update)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # 获取更新后的用户信息，包含角色信息
    user_data = await service.get_user_with_roles(db, user_id)
    return user_data


@router.delete(
    "/{user_id}",
    response_model=auth_schemas.UserRead,
    status_code=status.HTTP_200_OK,
    summary="Delete user",
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: auth_models.User = Depends(require_user_delete),
    _: auth_models.User = Depends(require_user_delete_not_self),
):
    """
    Delete user.
    """

    # 先获取要删除的用户信息（包含角色）
    user_data = await service.get_user_with_roles(db, user_id)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # 执行删除操作
    success = await service.delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # 返回被删除的用户信息
    return user_data
