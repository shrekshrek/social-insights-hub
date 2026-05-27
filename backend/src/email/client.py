"""
腾讯云 SES 邮件客户端

仅暴露两类业务邮件：
- send_invite_email：管理员邀请用户注册（A 方案邀请制）
- send_password_reset_email：管理员触发的密码重置（A2 方案）

所有 HTML 模板对用户输入做 escape，避免 XSS。
SES SDK 是同步阻塞的，通过 asyncio.to_thread 让出事件循环。
"""

import asyncio
import html
import logging

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.ses.v20201002 import ses_client, models

from src.config import settings

logger = logging.getLogger(__name__)


def _build_client() -> ses_client.SesClient:
    cred = credential.Credential(settings.SES_SECRET_ID, settings.SES_SECRET_KEY)
    return ses_client.SesClient(cred, settings.SES_REGION)


def _app_name() -> str:
    return settings.APP_NAME or "Social Insights Hub"


async def send_invite_email(
    to_email: str,
    invite_token: str,
    inviter_username: str | None = None,
) -> bool:
    """发送邀请注册邮件（管理员触发）"""
    register_url = f"{settings.FRONTEND_URL}/register?token={invite_token}"
    app = html.escape(_app_name())
    inviter = html.escape(inviter_username) if inviter_username else None
    inviter_line = (
        f"<p>{inviter} 邀请您加入 <strong>{app}</strong>。</p>"
        if inviter
        else f"<p>您被邀请加入 <strong>{app}</strong>。</p>"
    )

    subject = f"您被邀请加入 {_app_name()}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">欢迎加入 {app}</h2>
        {inviter_line}
        <p>请点击下方按钮完成注册，设置您的用户名和密码：</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{register_url}"
               style="background-color: #4F46E5; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-size: 16px;">
                完成注册
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            邀请链接 7 天内有效。如非本人申请，请忽略此邮件。
        </p>
        <p style="color: #999; font-size: 12px;">
            如按钮无法点击，请复制以下链接到浏览器：<br>
            <a href="{register_url}">{register_url}</a>
        </p>
    </div>
    """
    return await _send(to_email, subject, html_body)


async def send_password_reset_email(
    to_email: str,
    username: str,
    reset_token: str,
) -> bool:
    """发送密码重置邮件（管理员触发）"""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    app = html.escape(_app_name())
    safe_username = html.escape(username)

    subject = f"重置您的密码 - {_app_name()}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">密码重置</h2>
        <p>Hi {safe_username}，</p>
        <p>管理员为您发起了密码重置，请点击下方按钮设置新密码：</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background-color: #4F46E5; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-size: 16px;">
                重置密码
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            链接有效期为 1 小时。如非本人申请，请联系管理员确认。
        </p>
        <p style="color: #999; font-size: 12px;">
            如按钮无法点击，请复制以下链接到浏览器：<br>
            <a href="{reset_url}">{reset_url}</a>
        </p>
        <p style="color: #999; font-size: 12px; margin-top: 12px;">
            发件方：{app}
        </p>
    </div>
    """
    return await _send(to_email, subject, html_body)


async def _send(to_email: str, subject: str, html_body: str) -> bool:
    """实际调用腾讯云 SES SDK 发送邮件。SDK 同步阻塞 → 走 to_thread。"""
    if not settings.SES_SECRET_ID or not settings.SES_SECRET_KEY:
        logger.error("SES 凭证未配置，邮件未发送：to=%s, subject=%s", to_email, subject)
        return False

    def _do_send() -> None:
        client = _build_client()
        req = models.SendEmailRequest()
        req.FromEmailAddress = settings.SES_FROM_EMAIL
        req.Destination = [to_email]
        req.Subject = subject
        req.Simple = models.Simple()
        req.Simple.Html = html_body
        client.SendEmail(req)

    try:
        await asyncio.to_thread(_do_send)
        logger.info("邮件已发送：to=%s, subject=%s", to_email, subject)
        return True
    except TencentCloudSDKException as e:
        logger.error("SES 发送失败：%s, to=%s", e.message, to_email)
        return False
    except Exception as e:
        logger.error("邮件发送异常：%s, to=%s", e, to_email)
        return False
