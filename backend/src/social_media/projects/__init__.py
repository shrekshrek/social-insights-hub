"""社交媒体数据管理模块

提供社交媒体平台和项目的管理功能。
"""

from .models import Platform, SocialProject
from .router import router

__all__ = ["Platform", "SocialProject", "router"]
