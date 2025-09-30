# Auth module constants

# Token settings
DEFAULT_TOKEN_EXPIRE_MINUTES = 30
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1

# Password requirements
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# Username requirements
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 50

# Redis key prefixes
REDIS_BLACKLIST_PREFIX = "blacklist:"
REDIS_PASSWORD_RESET_PREFIX = "password_reset:"

# Error messages
ERROR_USER_NOT_FOUND = "User not found"
ERROR_INVALID_CREDENTIALS = "Invalid credentials"
ERROR_TOKEN_EXPIRED = "Token has expired"
ERROR_TOKEN_INVALID = "Invalid token"
ERROR_USER_ALREADY_EXISTS = "User already exists"
ERROR_INSUFFICIENT_PERMISSIONS = "Insufficient permissions"
