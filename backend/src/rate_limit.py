"""
Rate limiting configuration for API endpoints
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config import settings

# Create limiter instance with default configuration
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

# Export commonly used rate limit decorators
# These can be imported and used directly on routes
auth_limiter = limiter.limit("5/minute")  # For login, register endpoints
password_reset_limiter = limiter.limit("3/minute")  # For password reset endpoints
api_limiter = limiter.limit("100/minute")  # For general API endpoints
