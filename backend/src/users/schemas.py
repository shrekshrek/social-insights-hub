from pydantic import EmailStr, Field
from typing import Optional, List
from src.auth.schemas import UserRead
from src.schemas import CustomBaseModel, PaginatedResponse


class UserUpdate(CustomBaseModel):
    """用户更新模型"""

    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


# 使用统一的分页响应格式
UserListResponse = PaginatedResponse[UserRead]


class UserAdminCreate(CustomBaseModel):
    """管理员创建用户请求模型"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    password: str = Field(..., min_length=8, description="密码")
    role_ids: Optional[List[int]] = Field(
        default=None, description="需要分配的角色ID列表"
    )
