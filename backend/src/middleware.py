import logging
import time
import uuid
from typing import Callable
from contextvars import ContextVar

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError

from src.exceptions import BaseAPIException
from src.schemas import CustomBaseModel


class ErrorDetail(CustomBaseModel):
    """错误详情"""

    code: str
    message: str


class ErrorResponse(CustomBaseModel):
    """错误响应格式"""

    error: ErrorDetail
    message: str = "Request failed"


# 上下文变量用于存储请求ID
request_id_context: ContextVar[str] = ContextVar("request_id", default="")

# 配置日志
logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    def __init__(
        self, app: ASGIApp, log_requests: bool = True, log_responses: bool = True
    ):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成请求ID
        request_id = str(uuid.uuid4())
        request_id_context.set(request_id)

        # 记录请求开始时间
        start_time = time.time()

        # 提取请求信息
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # 记录请求日志
        if self.log_requests:
            logger.info(
                f"Request started - ID: {request_id} | "
                f"Method: {request.method} | "
                f"URL: {request.url} | "
                f"Client IP: {client_ip} | "
                f"User Agent: {user_agent}"
            )

        # 处理请求
        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 记录响应日志
            if self.log_responses:
                logger.info(
                    f"Request completed - ID: {request_id} | "
                    f"Status: {response.status_code} | "
                    f"Process Time: {process_time:.3f}s"
                )

            # 添加响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"

            return response

        except Exception as e:
            # 计算处理时间
            process_time = time.time() - start_time

            # 记录错误日志
            logger.error(
                f"Request failed - ID: {request_id} | "
                f"Error: {str(e)} | "
                f"Process Time: {process_time:.3f}s",
                exc_info=True,
            )

            # 重新抛出异常，让全局异常处理器处理
            raise e


class GlobalExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """全局异常处理中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response

        except BaseAPIException as e:
            # 处理自定义API异常
            logger.warning(f"API Exception: {e.error_code} - {e.message}")

            error_detail = ErrorDetail(code=e.error_code, message=e.message)

            error_response = ErrorResponse(error=error_detail, message="Request failed")

            return JSONResponse(
                status_code=e.status_code,
                content=error_response.dict(),
                headers={"X-Request-ID": request_id_context.get()},
            )

        except HTTPException as e:
            # 处理FastAPI HTTP异常
            logger.warning(f"HTTP Exception: {e.status_code} - {e.detail}")

            # 如果detail已经是我们的错误格式，直接返回
            if isinstance(e.detail, dict) and "error" in e.detail:
                return JSONResponse(
                    status_code=e.status_code,
                    content=e.detail,
                    headers={"X-Request-ID": request_id_context.get()},
                )

            # 否则包装为统一格式
            error_detail = ErrorDetail(code="HTTP_EXCEPTION", message=str(e.detail))
            error_response = ErrorResponse(error=error_detail)

            return JSONResponse(
                status_code=e.status_code,
                content=error_response.dict(),
                headers={"X-Request-ID": request_id_context.get()},
            )

        except ValidationError as e:
            # 处理Pydantic验证错误
            logger.warning(f"Validation Error: {e}")

            # 提取第一个验证错误
            first_error = e.errors()[0]
            error_msg = f"Validation failed for {'.'.join(str(x) for x in first_error['loc'])}: {first_error['msg']}"

            error_detail = ErrorDetail(code="VALIDATION_ERROR", message=error_msg)
            error_response = ErrorResponse(error=error_detail)

            return JSONResponse(
                status_code=422,
                content=error_response.dict(),
                headers={"X-Request-ID": request_id_context.get()},
            )

        except SQLAlchemyError as e:
            # 处理数据库错误
            logger.error(f"Database Error: {e}", exc_info=True)

            error_detail = ErrorDetail(
                code="DATABASE_ERROR", message="Database operation failed"
            )
            error_response = ErrorResponse(error=error_detail)

            return JSONResponse(
                status_code=500,
                content=error_response.dict(),
                headers={"X-Request-ID": request_id_context.get()},
            )

        except Exception as e:
            # 处理未知异常
            logger.error(f"Unexpected Error: {e}", exc_info=True)

            error_detail = ErrorDetail(
                code="INTERNAL_SERVER_ERROR", message="An unexpected error occurred"
            )
            error_response = ErrorResponse(error=error_detail)

            return JSONResponse(
                status_code=500,
                content=error_response.dict(),
                headers={"X-Request-ID": request_id_context.get()},
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


def get_request_id() -> str:
    """获取当前请求ID"""
    return request_id_context.get()


def log_with_request_id(level: str, message: str, **kwargs):
    """带请求ID的日志记录"""
    request_id = get_request_id()
    log_message = f"[{request_id}] {message}"

    log_func = getattr(logger, level.lower())
    log_func(log_message, **kwargs)
