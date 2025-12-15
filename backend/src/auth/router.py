from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from src.auth import schemas, service, models, security
from src.schemas import MessageResponse
from src.auth.dependencies import get_current_user, oauth2_scheme
from src.auth.blacklist import add_token_to_blacklist
from src.rbac import service as rbac_service
from src.users import service as user_service
from src.config import settings
from src.database import get_async_db
from src.rate_limit import auth_limiter
from src.redis_client import get_redis_client

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
)
@auth_limiter
async def register(
    request: Request, user: schemas.UserCreate, db: AsyncSession = Depends(get_async_db)
):
    """
    Register a new user.
    """
    # 使用统一异常处理，异常将由全局中间件处理
    db_user = await service.create_user(db=db, user=user)

    # 用户注册成功，补充角色确保响应包含 roles 数组
    user_roles = await rbac_service.get_user_roles(db, db_user.id)
    role_names = [role.name for role in user_roles]
    return user_service._convert_user_to_schema(db_user, role_names)


@router.post(
    "/token",
    response_model=schemas.Token,
    status_code=status.HTTP_200_OK,
    summary="User login",
)
@auth_limiter
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Login and get an access token.
    """
    user = await service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = security.create_access_token(subject=user.username)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="User logout",
)
async def logout(
    current_user: schemas.UserRead = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """
    Logout and invalidate the current token.
    """
    # 计算token剩余有效时间并加入黑名单
    expires_in = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    await add_token_to_blacklist(redis_client, token, expires_in)

    return MessageResponse(message="Successfully logged out")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password",
)
async def change_password_endpoint(
    request: schemas.ChangePassword,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Change user password with current password verification.
    """
    success = await service.change_password(
        db=db,
        user=current_user,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect or new password is the same as current password.",
        )
    return MessageResponse(message="Password has been changed successfully.")
