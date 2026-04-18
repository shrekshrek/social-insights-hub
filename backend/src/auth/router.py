from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from src.auth import schemas, service, models, security
from src.schemas import MessageResponse
from src.auth.dependencies import get_current_user, oauth2_scheme
from src.auth.blacklist import add_token_to_blacklist
from src.users import service as user_service
from src.config import settings
from src.database import get_async_db
from src.rate_limit import auth_limiter
from src.redis_client import get_redis_client
from src.feishu.oauth import (
    generate_state,
    build_authorize_url,
    exchange_code_for_token,
    get_feishu_user_info,
    OAUTH_STATE_PREFIX,
    OAUTH_STATE_TTL_SECONDS,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
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
    return await user_service.user_to_schema(db, db_user)


@router.post(
    "/token",
    response_model=schemas.Token,
    status_code=status.HTTP_200_OK,
    summary="用户登录",
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
    # 记录尝试登录的用户名，供审计中间件读取（失败登录也需要）
    request.state.audit_username = form_data.username

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
    summary="用户登出",
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
    summary="修改密码",
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


@router.get(
    "/feishu/authorize",
    response_model=schemas.FeishuAuthUrlResponse,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    summary="获取飞书授权URL",
)
async def feishu_authorize(
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """生成飞书 OAuth 授权页面 URL，含 CSRF state 参数。"""
    if not settings.FEISHU_APP_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="飞书登录未配置",
        )

    state = generate_state()
    # 存入 Redis，回调时校验
    await redis_client.set(
        f"{OAUTH_STATE_PREFIX}{state}", "1", ex=OAUTH_STATE_TTL_SECONDS
    )
    authorize_url = build_authorize_url(state)
    return schemas.FeishuAuthUrlResponse(authorize_url=authorize_url, state=state)


@router.post(
    "/feishu/callback",
    response_model=schemas.Token,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    summary="飞书扫码登录回调",
)
@auth_limiter
async def feishu_callback(
    request: Request,
    body: schemas.FeishuCallbackRequest,
    db: AsyncSession = Depends(get_async_db),
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """
    处理飞书 OAuth 回调：校验 state → code 兑换 token → 获取用户信息 → 查找/创建本地用户 → 签发 JWT。
    """
    # 1. 校验 state 防 CSRF
    state_key = f"{OAUTH_STATE_PREFIX}{body.state}"
    state_valid = await redis_client.get(state_key)
    if not state_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效或过期的 state 参数",
        )
    # state 一次性，立即删除
    await redis_client.delete(state_key)

    # 2. 用 code 兑换 access_token
    try:
        token_data = await exchange_code_for_token(body.code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"飞书授权码兑换失败: {exc}",
        )

    feishu_access_token = token_data.get("access_token")
    if not feishu_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="飞书未返回有效的 access_token",
        )

    # 3. 获取飞书用户信息
    try:
        user_info = await get_feishu_user_info(feishu_access_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取飞书用户信息失败: {exc}",
        )

    open_id = user_info.get("open_id")
    if not open_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="飞书用户信息缺少 open_id",
        )

    # 4. 查找或创建本地用户
    user = await service.get_or_create_feishu_user(
        db=db,
        open_id=open_id,
        name=user_info.get("name", "feishu_user"),
        avatar_url=user_info.get("avatar_url"),
        email=user_info.get("email"),
    )

    # 供审计中间件读取
    request.state.audit_username = user.username

    # 5. 签发 JWT
    access_token = security.create_access_token(subject=user.username)
    return {"access_token": access_token, "token_type": "bearer"}
