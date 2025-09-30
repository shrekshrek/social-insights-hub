import re
from datetime import datetime, timezone
from typing import Optional

from src.auth.constants import (
    MIN_PASSWORD_LENGTH,
    MAX_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
    MAX_USERNAME_LENGTH,
)


def validate_password(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"

    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"

    if len(password) > MAX_PASSWORD_LENGTH:
        return (
            False,
            f"Password must be no more than {MAX_PASSWORD_LENGTH} characters long",
        )

    # Check for at least one digit
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    # Check for at least one letter
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one letter"

    return True, None


def validate_username(username: str) -> tuple[bool, Optional[str]]:
    """
    Validate username format.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not username:
        return False, "Username is required"

    if len(username) < MIN_USERNAME_LENGTH:
        return False, f"Username must be at least {MIN_USERNAME_LENGTH} characters long"

    if len(username) > MAX_USERNAME_LENGTH:
        return (
            False,
            f"Username must be no more than {MAX_USERNAME_LENGTH} characters long",
        )

    # Check for valid characters (alphanumeric and underscore)
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores"

    # Username cannot start with a number
    if username[0].isdigit():
        return False, "Username cannot start with a number"

    return True, None


def is_token_expired(exp_timestamp: int) -> bool:
    """
    Check if a token has expired based on its expiration timestamp.

    Args:
        exp_timestamp: Unix timestamp of token expiration

    Returns:
        bool: True if token has expired, False otherwise
    """
    current_timestamp = datetime.now(timezone.utc).timestamp()
    return current_timestamp >= exp_timestamp


def format_user_display_name(user) -> str:
    """
    Format a user's display name.

    Args:
        user: User model instance

    Returns:
        str: Formatted display name
    """
    if hasattr(user, "full_name") and user.full_name:
        return user.full_name
    elif hasattr(user, "username") and user.username:
        return user.username
    elif hasattr(user, "email") and user.email:
        return user.email.split("@")[0]  # Use email prefix as fallback
    else:
        return "Unknown User"


def sanitize_user_input(input_str: str) -> str:
    """
    Sanitize user input by removing potentially dangerous characters.

    Args:
        input_str: Raw user input

    Returns:
        str: Sanitized string
    """
    if not input_str:
        return ""

    # Remove leading/trailing whitespace
    sanitized = input_str.strip()

    # Remove null bytes
    sanitized = sanitized.replace("\x00", "")

    return sanitized
