"""
腾讯云 SES 邮件服务
用于发送验证邮件和密码重置邮件
"""
import logging
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.ses.v20201002 import ses_client, models as ses_models

from src.config import settings

logger = logging.getLogger(__name__)


def _get_ses_client() -> ses_client.SesClient:
    cred = credential.Credential(settings.SES_SECRET_ID, settings.SES_SECRET_KEY)
    return ses_client.SesClient(cred, settings.SES_REGION)


async def send_email_verification(to_email: str, username: str, token: str) -> bool:
    """发送邮箱验证邮件"""
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "请验证您的邮箱 - Social Insights Hub"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">欢迎注册 Social Insights Hub</h2>
        <p>Hi {username}，</p>
        <p>感谢您的注册！请点击下方按钮验证您的邮箱地址：</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}"
               style="background-color: #4F46E5; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-size: 16px;">
                验证邮箱
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            链接有效期为 24 小时。如非本人操作，请忽略此邮件。
        </p>
        <p style="color: #999; font-size: 12px;">
            如按钮无法点击，请复制以下链接到浏览器：<br>
            <a href="{verify_url}">{verify_url}</a>
        </p>
    </div>
    """
    return await _send(to_email, subject, html_body)


async def send_password_reset(to_email: str, username: str, token: str) -> bool:
    """发送密码重置邮件"""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = "重置您的密码 - Social Insights Hub"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">密码重置请求</h2>
        <p>Hi {username}，</p>
        <p>我们收到了您的密码重置请求，请点击下方按钮设置新密码：</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background-color: #4F46E5; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-size: 16px;">
                重置密码
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            链接有效期为 1 小时。如非本人操作，请忽略此邮件，您的账号密码不会发生变化。
        </p>
        <p style="color: #999; font-size: 12px;">
            如按钮无法点击，请复制以下链接到浏览器：<br>
            <a href="{reset_url}">{reset_url}</a>
        </p>
    </div>
    """
    return await _send(to_email, subject, html_body)


async def _send(to_email: str, subject: str, html_body: str) -> bool:
    """实际调用腾讯云 SES API 发送邮件"""
    try:
        client = _get_ses_client()
        req = ses_models.SendEmailRequest()
        req.FromEmailAddress = settings.SES_FROM_EMAIL
        req.Destination = [to_email]
        req.Subject = subject
        req.Template = None
        req.Simple = ses_models.Simple()
        req.Simple.Subject = subject
        req.Simple.Html = html_body
        client.SendEmail(req)
        logger.info(f"邮件已发送至 {to_email}，主题：{subject}")
        return True
    except TencentCloudSDKException as e:
        logger.error(f"SES 发送失败：{e.message}，to={to_email}")
        return False
    except Exception as e:
        logger.error(f"邮件发送异常：{e}，to={to_email}")
        return False
