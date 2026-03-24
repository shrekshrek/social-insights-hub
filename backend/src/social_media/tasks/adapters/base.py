"""平台数据适配器基类"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class PlatformAdapter(ABC):
    """平台数据适配器基类

    每个平台需要实现自己的适配器，将平台特定的数据格式转换为统一格式。
    """

    # 平台代码，子类必须覆盖
    platform_code: str = ""

    @abstractmethod
    def transform_post(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换原文/内容数据

        Args:
            raw_data: 平台原始数据

        Returns:
            转换后的统一格式数据，包含以下字段：
            - post_id_on_platform: str (必填)
            - post_type: str | None
            - title: str | None
            - content: str | None
            - author_id: str | None
            - author_name: str | None
            - likes_count: int
            - comments_count: int
            - shares_count: int
            - collected_count: int
            - views_count: int
            - images: list[str] | None
            - videos: list[str] | None
            - published_at: datetime | None
            - url: str | None
            - raw_data: dict (原始数据保留)
        """
        pass

    @abstractmethod
    def transform_comment(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """转换评论数据

        Args:
            raw_data: 平台原始数据

        Returns:
            转换后的统一格式数据，包含以下字段：
            - comment_id_on_platform: str (必填)
            - parent_comment_id: str | None
            - content: str | None
            - author_id: str | None
            - author_name: str | None
            - likes_count: int
            - sub_comments_count: int
            - images: list[str] | None
            - published_at: datetime | None
            - raw_data: dict (原始数据保留，需包含 post_id_on_platform)
        """
        pass

    @abstractmethod
    def get_post_id_from_comment(self, comment_data: dict[str, Any]) -> str | None:
        """从评论数据中获取关联的原文ID

        Args:
            comment_data: 评论的原始数据或转换后的数据

        Returns:
            原文在平台上的ID
        """
        pass

    # ==================== 工具方法 ====================

    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        """安全转换为整数"""
        if value is None:
            return default
        try:
            # 处理字符串中可能的逗号分隔符（如 "1,234"）
            if isinstance(value, str):
                value = value.replace(",", "").strip()
                if not value:
                    return default
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def safe_str(value: Any, default: str = "") -> str:
        """安全转换为字符串"""
        if value is None:
            return default
        return str(value).strip()

    @staticmethod
    def parse_timestamp(value: Any) -> datetime | None:
        """解析时间戳为 datetime 对象

        支持：
        - Unix 时间戳（秒或毫秒）
        - ISO 格式字符串
        - 常见日期格式字符串
        """
        if value is None:
            return None

        # 如果已经是 datetime
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        # 尝试解析为时间戳
        try:
            ts = int(value)
            # 判断是秒还是毫秒（13位为毫秒）
            if ts > 10000000000:
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            pass

        # 尝试解析字符串格式
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None

            # 尝试常见格式
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

        return None

    @staticmethod
    def parse_list(value: Any, separator: str = ",") -> list[str] | None:
        """解析列表字段

        支持：
        - 已经是 list 的情况
        - 逗号分隔的字符串
        - JSON 字符串
        """
        if value is None:
            return None

        if isinstance(value, list):
            return [str(v).strip() for v in value if v]

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None

            # 尝试 JSON 解析
            if value.startswith("["):
                try:
                    import json

                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(v).strip() for v in parsed if v]
                except json.JSONDecodeError:
                    pass

            # 分隔符分割
            items = [v.strip() for v in value.split(separator) if v.strip()]
            return items if items else None

        return None

    def _base_transform(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """基础转换，保留原始数据"""
        return {
            "raw_data": raw_data,
        }

    def normalize_content(self, transformed: dict[str, Any]) -> dict[str, Any]:
        """规范化内容字段

        规则：
        1. 当 raw_data.transcript.text 有值时，content = transcript.text
        2. 当 title == content 时，清空 content（避免重复存储）
        """
        raw_data = transformed.get("raw_data")
        if raw_data and isinstance(raw_data, dict):
            transcript = raw_data.get("transcript")
            if transcript and isinstance(transcript, dict):
                transcript_text = transcript.get("text")
                if transcript_text:
                    transformed["content"] = transcript_text

        title = transformed.get("title")
        content = transformed.get("content")
        if title and content and title == content:
            transformed["content"] = None

        return transformed

    def validate_post(self, transformed: dict[str, Any]) -> None:
        """验证转换后的原文数据

        Raises:
            ValueError: 如果必填字段缺失
        """
        post_id = transformed.get("post_id_on_platform")
        if not post_id:
            raw_keys = list(transformed.get("raw_data", {}).keys())[:10]
            raise ValueError(
                f"[{self.platform_code}] Missing required field 'post_id_on_platform'. "
                f"Raw data keys (first 10): {raw_keys}"
            )

    def validate_comment(self, transformed: dict[str, Any]) -> None:
        """验证转换后的评论数据

        Raises:
            ValueError: 如果必填字段缺失
        """
        comment_id = transformed.get("comment_id_on_platform")
        if not comment_id:
            raw_keys = list(transformed.get("raw_data", {}).keys())[:10]
            raise ValueError(
                f"[{self.platform_code}] Missing required field 'comment_id_on_platform'. "
                f"Raw data keys (first 10): {raw_keys}"
            )
