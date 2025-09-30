from fastapi import status
from typing import Any, Dict, Optional


class BaseAPIException(Exception):
    """基础API异常类"""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {"error": {"code": self.error_code, "message": self.message}}


# 常用异常类
class ValidationException(BaseAPIException):
    """数据验证异常"""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
        )


class NotFoundException(BaseAPIException):
    """资源不存在异常"""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
        )


class ConflictException(BaseAPIException):
    """资源冲突异常"""

    def __init__(self, message: str):
        super().__init__(
            message=message, status_code=status.HTTP_409_CONFLICT, error_code="CONFLICT"
        )


class UnauthorizedException(BaseAPIException):
    """未授权异常"""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )


class ForbiddenException(BaseAPIException):
    """禁止访问异常"""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )


# ============================================================================
# 业务异常类（符合FastAPI最佳实践的统一异常体系）
# ============================================================================


class UserException(BaseAPIException):
    """用户相关异常基类"""

    pass


class UserNotFound(UserException):
    """用户不存在异常"""

    def __init__(self, identifier: str):
        super().__init__(
            message=f"User {identifier} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND",
        )


class UserAlreadyExists(UserException):
    """用户已存在异常"""

    def __init__(self, field: str, value: str):
        super().__init__(
            message=f"User with {field} '{value}' already exists",
            status_code=status.HTTP_409_CONFLICT,
            error_code="USER_ALREADY_EXISTS",
        )


class WeakPasswordException(UserException):
    """弱密码异常"""

    def __init__(self, message: str):
        super().__init__(
            message=f"Password validation failed: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="WEAK_PASSWORD",
        )


class InvalidCredentialsException(UserException):
    """无效凭据异常"""

    def __init__(self):
        super().__init__(
            message="Invalid username or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_CREDENTIALS",
        )
