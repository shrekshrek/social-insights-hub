"""社交媒体数据任务管理模块

提供社交媒体数据获取任务的创建、管理和数据导入功能。
支持两种数据源：
1. 远程爬虫（通过WebSocket通信）
2. 本地JSON文件上传
"""

from .models import SocialTask, SocialPost, SocialComment
from .router import router

# Backward-compat alias

__all__ = ["SocialTask", "SocialTask", "SocialPost", "SocialComment", "router"]
