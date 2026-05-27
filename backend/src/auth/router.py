import logging
from datetime import timedelta

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import models, schemas, security, service
from src.auth.blacklist import add_token_to_blacklist
from src.auth.dependencies import get_current_user, oauth2_scheme
from src.config import settings
from src.database import get_async_db
from src.email.client import send_invite_email, send_password_reset_email
from src.feishu.oauth import (
    OAUTH_STATE_PREFIX,
    OAUTH_STATE_TTL_SECONDS,
    build_authorize_url,
    exchange_code_for_token,
    generate_state,
    get_feishu_user_info,
)
from src.rate_limit import auth_limiter
from src.rbac.dependencies import require_user_write
from src.redis_client import get_redis_client
from src.schemas import MessageResponse
from src.users import service as user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册（邀请制）",
)
@auth_limiter
async def register(
    request: Request,
    user: schemas.UserCreate,
    db: AsyncSession = Depends(get_async_db),
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """
    通过管理员邀请的 invite_token 完成注册。

    - email 由邀请决定，不接受用户自填
    - invite_token 一次性消费
    - 注册成功即视为邮箱已验证（邀请邮件能送达 = 邮箱真实）
    """
    payload = await service.consume_invite_token(redis_client, user.invite_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邀请链接无效或已过期，请联系管理员重新发送",
        )

    email = payload["email"]
    default_role_id = payload.get("default_role_id")
    role_ids = [default_role_id] if default_role_id else None

    db_user = await service.create_user(
        db=db,
        username=user.username,
        email=email,
        password=user.password,
        email_verified=True,
        role_ids=role_ids,
    )

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


@router.post(
    "/invitations",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="管理员发送注册邀请邮件",
)
async def create_invitation(
    body: schemas.InvitationCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    redis_client: redis.Redis = Depends(get_redis_client),
    current_user: models.User = Depends(require_user_write),
):
    """
    管理员邀请用户注册：生成 invite token 并发送邀请邮件。

    - 邮箱已被注册时拒绝
    - SES 失败会回滚 token 让管理员重试
    """
    existing = await service.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册",
        )

    token = await service.create_invite_token(
        redis_client, body.email, body.default_role_id
    )
    sent = await send_invite_email(
        to_email=body.email,
        invite_token=token,
        inviter_username=current_user.username,
    )
    if not sent:
        await redis_client.delete(f"{service.INVITE_TOKEN_PREFIX}{token}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="邀请邮件发送失败，请稍后重试或检查 SES 配置",
        )

    return MessageResponse(message=f"邀请邮件已发送至 {body.email}")


@router.post(
    "/users/{user_id}/send-reset-email",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="管理员触发用户密码重置邮件",
)
async def admin_send_reset_email(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    redis_client: redis.Redis = Depends(get_redis_client),
    current_user: models.User = Depends(require_user_write),
):
    """
    管理员代为发起密码重置：生成 reset token 并将链接发送到目标用户邮箱。

    - 目标用户必须有密码（OAuth-only 用户应通过原渠道找回）
    - 目标用户必须有 email
    - SES 失败会回滚 token
    """
    target_user = await user_service.get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if not target_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户未绑定邮箱，无法发送重置邮件",
        )
    if not target_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户为 OAuth 登录用户，不支持密码重置",
        )

    token = await service.create_password_reset_token(redis_client, target_user.id)
    sent = await send_password_reset_email(
        to_email=target_user.email,
        username=target_user.username,
        reset_token=token,
    )
    if not sent:
        await redis_client.delete(f"{service.PASSWORD_RESET_PREFIX}{token}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="重置邮件发送失败，请稍后重试或检查 SES 配置",
        )

    return MessageResponse(message=f"重置邮件已发送至 {target_user.email}")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="消费 reset token 设置新密码",
)
async def reset_password(
    body: schemas.ResetPasswordRequest,
    db: AsyncSession = Depends(get_async_db),
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """用 admin 发出的 reset token 设置新密码。"""
    user = await service.reset_password_with_token(
        db, redis_client, body.token, body.new_password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="重置链接无效或已过期",
        )
    return MessageResponse(message="密码重置成功，请重新登录。")


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
