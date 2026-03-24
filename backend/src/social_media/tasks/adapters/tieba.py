"""百度贴吧平台数据适配器"""

from typing import Any

from .base import PlatformAdapter
from .factory import register_adapter


@register_adapter("tieba")
class TiebaAdapter(PlatformAdapter):
    """百度贴吧数据适配器

    字段映射：
    - note_id -> post_id_on_platform
    - title -> title
    - desc -> content
    - publish_time -> published_at
    - total_replay_num -> comments_count
    - note_url -> url
    - user_nickname -> author_name
    """

    def transform_post(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换贴吧原文数据"""
        return {
            "post_id_on_platform": self.safe_str(raw_data.get("note_id")),
            "post_type": None,  # 贴吧没有类型字段
            "title": self.safe_str(raw_data.get("title")) or None,
            "content": self.safe_str(raw_data.get("desc")) or None,
            "author_id": None,  # 贴吧原文数据中没有用户ID
            "author_name": self.safe_str(raw_data.get("user_nickname")) or None,
            "likes_count": 0,  # 贴吧数据中没有点赞数
            "comments_count": self.safe_int(raw_data.get("total_replay_num")),
            "shares_count": 0,
            "collected_count": 0,
            "views_count": 0,
            "images": None,  # 贴吧原文需要从内容中提取图片
            "videos": None,
            "published_at": self.parse_timestamp(raw_data.get("publish_time")),
            "url": self.safe_str(raw_data.get("note_url")) or None,
            "raw_data": raw_data,
        }

    def transform_comment(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换贴吧评论数据"""
        # 保存原文ID到 raw_data 中供后续关联使用
        note_id = self.safe_str(raw_data.get("note_id"))
        raw_data_with_post_id = {
            **raw_data,
            "post_id_on_platform": note_id,
        }

        return {
            "comment_id_on_platform": self.safe_str(raw_data.get("comment_id")),
            "parent_comment_id": self.safe_str(raw_data.get("parent_comment_id"))
            or None,
            "content": self.safe_str(raw_data.get("content")) or None,
            "author_id": None,  # 贴吧评论数据中没有用户ID
            "author_name": self.safe_str(raw_data.get("user_nickname")) or None,
            "likes_count": 0,  # 贴吧评论没有点赞数
            "sub_comments_count": self.safe_int(raw_data.get("sub_comment_count")),
            "images": None,
            "published_at": self.parse_timestamp(raw_data.get("publish_time")),
            "raw_data": raw_data_with_post_id,
        }

    def get_post_id_from_comment(self, comment_data: dict[str, Any]) -> str | None:
        """从评论数据中获取关联的原文ID"""
        raw_data = comment_data.get("raw_data", {})
        post_id = raw_data.get("post_id_on_platform") or raw_data.get("note_id")
        if post_id:
            return self.safe_str(post_id)
        return self.safe_str(comment_data.get("note_id")) or None
