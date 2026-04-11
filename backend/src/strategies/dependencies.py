"""策略模块依赖注入"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.rbac.utils import is_admin_or_super_admin

from . import service
from .models import Strategy


async def validate_strategy_exists(
    strategy_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db),
) -> Strategy:
    """验证策略是否存在"""
    strategy = await service.get_strategy_by_id(db, strategy_id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"策略 {strategy_id} 不存在",
        )
    return strategy


async def validate_strategy_owner(
    strategy: Strategy = Depends(validate_strategy_exists),
    current_user: User = Depends(get_current_user),
) -> Strategy:
    """验证用户是否有策略管理权限（创建者 or admin）"""
    if is_admin_or_super_admin(current_user):
        return strategy

    if strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有策略创建者或管理员可以执行此操作",
        )
    return strategy
