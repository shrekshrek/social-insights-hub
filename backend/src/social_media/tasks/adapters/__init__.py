"""平台数据适配器

将各平台原始数据格式转换为统一的 SocialPost/SocialComment 格式。
"""

from .base import PlatformAdapter
from .factory import get_adapter, PLATFORM_ADAPTERS

__all__ = [
    "PlatformAdapter",
    "get_adapter",
    "PLATFORM_ADAPTERS",
]
