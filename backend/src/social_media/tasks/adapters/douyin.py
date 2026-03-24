"""抖音平台数据适配器"""

from typing import Any

from .base import PlatformAdapter
from .factory import register_adapter


@register_adapter("dy")
class DouyinAdapter(PlatformAdapter):
    """抖音数据适配器

    字段映射：
    - aweme_id -> post_id_on_platform
    - aweme_type -> post_type
    - title -> title
    - desc -> content
    - create_time -> published_at
    - liked_count -> likes_count
    - comment_count -> comments_count
    - share_count -> shares_count
    - collected_count -> collected_count
    - play_count -> views_count
    - aweme_url -> url
    - cover_url -> images
    - video_download_url -> videos
    - user_id -> author_id
    - nickname -> author_name
    """

    def transform_post(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换抖音视频数据"""
        # 处理封面图
        cover_url = self.safe_str(raw_data.get("cover_url"))
        images = [cover_url] if cover_url else None

        # 处理视频链接
        video_url = self.safe_str(raw_data.get("video_download_url"))
        videos = [video_url] if video_url else None

        return {
            "post_id_on_platform": self.safe_str(raw_data.get("aweme_id")),
            "post_type": self.safe_str(raw_data.get("aweme_type")) or None,
            "title": self.safe_str(raw_data.get("title")) or None,
            "content": self.safe_str(raw_data.get("desc")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("liked_count")),
            "comments_count": self.safe_int(raw_data.get("comment_count")),
            "shares_count": self.safe_int(raw_data.get("share_count")),
            "collected_count": self.safe_int(raw_data.get("collected_count")),
            "views_count": self.safe_int(raw_data.get("play_count")),
            "images": images,
            "videos": videos,
            "published_at": self.parse_timestamp(raw_data.get("create_time")),
            "url": self.safe_str(raw_data.get("aweme_url")) or None,
            "raw_data": raw_data,
        }

    def transform_comment(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换抖音评论数据"""
        # 处理评论图片
        pictures = self.safe_str(raw_data.get("pictures"))
        images = self.parse_list(pictures) if pictures else None

        # 保存原文ID到 raw_data 中供后续关联使用
        raw_data_with_post_id = {
            **raw_data,
            "post_id_on_platform": self.safe_str(raw_data.get("aweme_id")),
        }

        return {
            "comment_id_on_platform": self.safe_str(raw_data.get("comment_id")),
            "parent_comment_id": self.safe_str(raw_data.get("parent_comment_id"))
            or None,
            "content": self.safe_str(raw_data.get("content")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("like_count")),
            "sub_comments_count": self.safe_int(raw_data.get("sub_comment_count")),
            "images": images,
            "published_at": self.parse_timestamp(raw_data.get("create_time")),
            "raw_data": raw_data_with_post_id,
        }

    def get_post_id_from_comment(self, comment_data: dict[str, Any]) -> str | None:
        """从评论数据中获取关联的原文ID"""
        # 优先从 raw_data 中获取
        raw_data = comment_data.get("raw_data", {})
        post_id = raw_data.get("post_id_on_platform") or raw_data.get("aweme_id")
        if post_id:
            return self.safe_str(post_id)

        # 直接从评论数据获取
        return self.safe_str(comment_data.get("aweme_id")) or None
