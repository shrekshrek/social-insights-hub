from pydantic import EmailStr, Field, field_validator
from datetime import datetime
from typing import List
import re
from src.schemas import CustomBaseModel


# --- User Schemas ---


class UserCreate(CustomBaseModel):
    """
    Schema for user creation.
    Used for request body validation when creating a new user.
    """

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr | None = Field(None, description="邮箱地址（可选）")
    password: str = Field(..., min_length=8, description="密码")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """验证用户名格式"""
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """验证密码强度"""
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含数字")
        return v


class UserRead(CustomBaseModel):
    """
    Schema for reading user information.
    Used for response bodies to avoid exposing sensitive data like password.
    """

    id: int
    username: str
    email: EmailStr | None
    created_at: datetime
    updated_at: datetime
    roles: List[str] = Field(default_factory=list)  # 用户的角色名称列表


# --- Token Schemas ---


class Token(CustomBaseModel):
    access_token: str
    token_type: str


class TokenData(CustomBaseModel):
    username: str | None = None


# --- Password Change Schema ---


class ChangePassword(CustomBaseModel):
    """修改密码请求模型"""

    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=8, description="新密码")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """验证新密码强度"""
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("新密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("新密码必须包含数字")
        return v
