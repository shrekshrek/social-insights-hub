"""
爬虫任务数据模型
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.database import Base

if TYPE_CHECKING:
    from src.data.notes.models import TaskNote


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class PlatformType(str, Enum):
    """平台类型"""

    XHS = "xhs"  # 小红书
    WEIBO = "weibo"  # 微博
    DOUYIN = "douyin"  # 抖音
    KUAISHOU = "kuaishou"  # 快手
    BILIBILI = "bilibili"  # 哔哩哔哩
    TIEBA = "tieba"  # 百度贴吧
    ZHIHU = "zhihu"  # 知乎


class CrawlerType(str, Enum):
    """爬取模式"""

    SEARCH = "search"  # 关键词搜索
    DETAIL = "detail"  # 帖子详情
    CREATOR = "creator"  # 创作者主页
    HOMEFEED = "homefeed"  # 首页推荐


class CrawlerTask(Base):
    """爬虫任务表"""

    __tablename__ = "crawler_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, comment="任务名称")
    platform = Column(
        SQLEnum(
            PlatformType,
            name="platformtype",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        index=True,
        comment="爬取平台",
    )
    crawler_type = Column(
        SQLEnum(
            CrawlerType,
            name="crawlertype",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        comment="爬取模式",
    )
    status = Column(
        SQLEnum(
            TaskStatus,
            name="taskstatus",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
        comment="任务状态",
    )

    # 任务配置
    config = Column(JSON, nullable=False, comment="爬取配置(关键词、URL、数量等)")
    # 示例配置结构:
    # {
    #   "keywords": "deepseek,chatgpt",  # 关键词(search模式)
    #   "urls": ["url1", "url2"],        # 指定URL列表(detail/creator模式)
    #   "max_count": 100,                # 最大爬取数量
    #   "enable_comments": true,         # 是否爬评论
    #   "enable_sub_comments": false,    # 是否爬二级评论
    #   "sort_type": "popularity",       # 排序方式
    #   "account_ids": [1, 2],           # 指定使用的账号ID列表
    #   "proxy_enabled": true,           # 是否使用代理
    # }

    # 执行信息
    progress = Column(Integer, default=0, comment="进度(0-100)")
    crawled_count = Column(Integer, default=0, comment="已爬取数量")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    # 断点续爬支持
    checkpoint_id = Column(String(255), nullable=True, comment="检查点ID")
    checkpoint_data = Column(JSON, nullable=True, comment="检查点数据")

    # 关联信息
    created_by = Column(
        Integer, ForeignKey("users.id"), nullable=True, comment="创建人ID"
    )
    created_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )

    # 关系
    creator = relationship("User", backref="crawler_tasks")
    note_associations = relationship("TaskNote", back_populates="task", cascade="all, delete-orphan")


class TaskLog(Base):
    """任务执行日志表"""

    __tablename__ = "crawler_task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer, ForeignKey("crawler_tasks.id", ondelete="CASCADE"), nullable=False
    )
    level = Column(String(20), nullable=False, comment="日志级别: INFO/WARNING/ERROR")
    message = Column(Text, nullable=False, comment="日志内容")
    detail = Column(JSON, nullable=True, comment="详细信息(JSON)")
    created_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, comment="记录时间"
    )

    # 关系
    task = relationship("CrawlerTask", backref="logs")
