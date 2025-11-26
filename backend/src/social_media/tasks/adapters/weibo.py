"""微博平台数据适配器"""

from typing import Any

from .base import PlatformAdapter
from .factory import register_adapter


@register_adapter("wb")
class WeiboAdapter(PlatformAdapter):
    """微博数据适配器

    字段映射：
    - note_id -> post_id_on_platform
    - content -> content
    - create_time -> published_at
    - liked_count -> likes_count
    - comments_count -> comments_count
    - shared_count -> shares_count
    - note_url -> url
    - image_list -> images
    - video_url -> videos
    - user_id -> author_id
    - nickname -> author_name
    """

    def transform_post(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换微博笔记数据"""
        # 处理图片列表（逗号分隔字符串或 JSON）
        image_list = raw_data.get("image_list")
        images = self.parse_list(image_list) if image_list else None

        # 处理视频链接
        video_url = self.safe_str(raw_data.get("video_url"))
        videos = [video_url] if video_url else None

        return {
            "post_id_on_platform": self.safe_str(raw_data.get("note_id")),
            "post_type": None,  # 微博没有类型字段
            "title": None,  # 微博没有标题
            "content": self.safe_str(raw_data.get("content")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("liked_count")),
            "comments_count": self.safe_int(raw_data.get("comments_count")),
            "shares_count": self.safe_int(raw_data.get("shared_count")),
            "collected_count": 0,  # 微博数据中没有收藏数
            "views_count": 0,  # 微博数据中没有浏览量
            "images": images,
            "videos": videos,
            "published_at": self.parse_timestamp(raw_data.get("create_time")),
            "url": self.safe_str(raw_data.get("note_url")) or None,
            "raw_data": raw_data,
        }

    def transform_comment(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换微博评论数据"""
        # 保存帖子ID到 raw_data 中供后续关联使用
        raw_data_with_post_id = {
            **raw_data,
            "post_id_on_platform": self.safe_str(raw_data.get("note_id")),
        }

        return {
            "comment_id_on_platform": self.safe_str(raw_data.get("comment_id")),
            "parent_comment_id": self.safe_str(raw_data.get("parent_comment_id")) or None,
            "content": self.safe_str(raw_data.get("content")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("like_count")),
            "sub_comments_count": self.safe_int(raw_data.get("sub_comment_count")),
            "images": None,  # 微博评论没有图片字段
            "published_at": self.parse_timestamp(raw_data.get("create_time")),
            "raw_data": raw_data_with_post_id,
        }

    def get_post_id_from_comment(self, comment_data: dict[str, Any]) -> str | None:
        """从评论数据中获取关联的帖子ID"""
        raw_data = comment_data.get("raw_data", {})
        post_id = raw_data.get("post_id_on_platform") or raw_data.get("note_id")
        if post_id:
            return self.safe_str(post_id)
        return self.safe_str(comment_data.get("note_id")) or None
