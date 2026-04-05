"""社交媒体数据管理模块

提供社交媒体平台和项目的管理功能。
"""

from .models import Platform, SocialMonitor
from .router import router

# Backward-compat alias

__all__ = ["Platform", "SocialMonitor", "SocialMonitor", "router"]
