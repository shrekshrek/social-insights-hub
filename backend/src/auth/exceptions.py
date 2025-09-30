"""
Custom exceptions for the auth module.
"""

from fastapi import HTTPException, status


class AuthException(Exception):
    """Base exception for authentication-related errors."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

    def to_http_exception(self) -> HTTPException:
        """Convert to FastAPI HTTPException."""
        return HTTPException(status_code=self.status_code, detail=self.message)


class UserAlreadyExistsException(AuthException):
    """Raised when trying to create a user that already exists."""

    def __init__(self, message: str = "User already exists"):
        super().__init__(message, status.HTTP_400_BAD_REQUEST)


class UserNotFoundException(AuthException):
    """Raised when a user is not found."""

    def __init__(self, message: str = "User not found"):
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class InvalidCredentialsException(AuthException):
    """Raised when authentication credentials are invalid."""

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class TokenExpiredException(AuthException):
    """Raised when a token has expired."""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class TokenInvalidException(AuthException):
    """Raised when a token is invalid."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class TokenRevokedException(AuthException):
    """Raised when a token has been revoked."""

    def __init__(self, message: str = "Token has been revoked"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class InsufficientPermissionsException(AuthException):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class ValidationException(AuthException):
    """Raised when input validation fails."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY)


class PasswordValidationException(ValidationException):
    """Raised when password validation fails."""

    def __init__(self, message: str = "Password validation failed"):
        super().__init__(message)


class UsernameValidationException(ValidationException):
    """Raised when username validation fails."""

    def __init__(self, message: str = "Username validation failed"):
        super().__init__(message)
