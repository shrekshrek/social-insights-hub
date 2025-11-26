"""B站平台数据适配器"""

from typing import Any

from .base import PlatformAdapter
from .factory import register_adapter


@register_adapter("bili")
class BilibiliAdapter(PlatformAdapter):
    """B站数据适配器

    字段映射：
    - video_id (aid) / bvid -> post_id_on_platform
    - video_type -> post_type
    - title -> title
    - desc -> content
    - create_time -> published_at
    - liked_count -> likes_count
    - video_comment -> comments_count
    - video_play_count -> views_count
    - video_danmaku -> danmaku_count
    - video_url -> url
    - video_cover_url -> images
    - user_id -> author_id
    - nickname -> author_name
    """

    def transform_post(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换B站视频数据"""
        # 优先使用 bvid，其次用 video_id (aid)
        post_id = self.safe_str(raw_data.get("bvid")) or self.safe_str(raw_data.get("video_id"))

        # 处理封面图
        cover_url = self.safe_str(raw_data.get("video_cover_url"))
        images = [cover_url] if cover_url else None

        return {
            "post_id_on_platform": post_id,
            "post_type": self.safe_str(raw_data.get("video_type")) or None,
            "title": self.safe_str(raw_data.get("title")) or None,
            "content": self.safe_str(raw_data.get("desc")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("liked_count")),
            "comments_count": self.safe_int(raw_data.get("video_comment")),
            "shares_count": 0,  # B站数据中没有分享数
            "collected_count": 0,  # B站数据中没有收藏数
            "views_count": self.safe_int(raw_data.get("video_play_count")),
            "danmaku_count": self.safe_int(raw_data.get("video_danmaku")),
            "images": images,
            "videos": None,  # B站视频链接需要特殊处理，暂不存储
            "published_at": self.parse_timestamp(raw_data.get("create_time")),
            "url": self.safe_str(raw_data.get("video_url")) or None,
            "raw_data": raw_data,
        }

    def transform_comment(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换B站评论数据"""
        # 保存帖子ID到 raw_data 中供后续关联使用
        # B站评论中 video_id 是关联字段
        video_id = self.safe_str(raw_data.get("video_id"))
        raw_data_with_post_id = {
            **raw_data,
            "post_id_on_platform": video_id,
        }

        return {
            "comment_id_on_platform": self.safe_str(raw_data.get("comment_id")),
            "parent_comment_id": self.safe_str(raw_data.get("parent_comment_id")) or None,
            "content": self.safe_str(raw_data.get("content")) or None,
            "author_id": self.safe_str(raw_data.get("user_id")) or None,
            "author_name": self.safe_str(raw_data.get("nickname")) or None,
            "likes_count": self.safe_int(raw_data.get("like_count")),
            "sub_comments_count": self.safe_int(raw_data.get("sub_comment_count")),
            "images": None,  # B站评论没有图片
            "published_at": self.parse_timestamp(raw_data.get("create_time")),
            "raw_data": raw_data_with_post_id,
        }

    def get_post_id_from_comment(self, comment_data: dict[str, Any]) -> str | None:
        """从评论数据中获取关联的帖子ID"""
        raw_data = comment_data.get("raw_data", {})
        post_id = raw_data.get("post_id_on_platform") or raw_data.get("video_id")
        if post_id:
            return self.safe_str(post_id)
        return self.safe_str(comment_data.get("video_id")) or None
