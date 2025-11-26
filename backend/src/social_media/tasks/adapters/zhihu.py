"""知乎平台数据适配器"""

from typing import Any

from .base import PlatformAdapter
from .factory import register_adapter


@register_adapter("zhihu")
class ZhihuAdapter(PlatformAdapter):
    """知乎数据适配器

    字段映射：
    - content_id -> post_id_on_platform
    - content_type -> post_type
    - title -> title
    - content_text -> content
    - created_time -> published_at
    - voteup_count -> likes_count
    - comment_count -> comments_count
    - content_url -> url
    - user_id -> author_id
    - user_nickname -> author_name
    """

    def transform_post(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换知乎内容数据"""
        # 知乎内容可能是回答、文章或视频
        content_type = self.safe_str(raw_data.get("content_type"))

        # 内容字段
        content = self.safe_str(raw_data.get("content_text"))
        if not content:
            content = self.safe_str(raw_data.get("desc"))

        return {
            "post_id_on_platform": self.safe_str(raw_data.get("content_id")),
            "post_type": content_type or None,
            "title": self.safe_str(raw_data.get("title")) or None,
            "content": content or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("user_nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("voteup_count")),
            "comments_count": self.safe_int(raw_data.get("comment_count")),
            "shares_count": 0,  # 知乎数据中没有分享数
            "collected_count": 0,  # 知乎数据中没有收藏数
            "views_count": 0,  # 知乎数据中没有浏览量
            "images": None,  # 知乎内容需要从 content_text 中提取图片
            "videos": None,
            "published_at": self.parse_timestamp(raw_data.get("created_time")),
            "url": self.safe_str(raw_data.get("content_url")) or None,
            "raw_data": raw_data,
        }

    def transform_comment(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换知乎评论数据"""
        # 保存帖子ID到 raw_data 中供后续关联使用
        content_id = self.safe_str(raw_data.get("content_id"))
        raw_data_with_post_id = {
            **raw_data,
            "post_id_on_platform": content_id,
        }

        return {
            "comment_id_on_platform": self.safe_str(raw_data.get("comment_id")),
            "parent_comment_id": self.safe_str(raw_data.get("parent_comment_id")) or None,
            "content": self.safe_str(raw_data.get("content")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("user_nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("like_count")),
            "sub_comments_count": self.safe_int(raw_data.get("sub_comment_count")),
            "images": None,
            "published_at": self.parse_timestamp(raw_data.get("publish_time")),
            "raw_data": raw_data_with_post_id,
        }

    def get_post_id_from_comment(self, comment_data: dict[str, Any]) -> str | None:
        """从评论数据中获取关联的帖子ID"""
        raw_data = comment_data.get("raw_data", {})
        post_id = raw_data.get("post_id_on_platform") or raw_data.get("content_id")
        if post_id:
            return self.safe_str(post_id)
        return self.safe_str(comment_data.get("content_id")) or None
