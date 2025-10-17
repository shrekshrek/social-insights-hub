"""Comment schemas for API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CommentBase(BaseModel):
    """评论基础字段."""

    platform: str = Field(..., description="平台类型")
    comment_id: str = Field(..., description="平台评论ID")
    content: str = Field(..., description="评论内容")
    note_id: str = Field(..., description="所属笔记ID")
    note_title: Optional[str] = Field(None, description="笔记标题")
    parent_comment_id: Optional[str] = Field(None, description="父评论ID")
    author_id: str = Field(..., description="评论者ID")
    author_name: Optional[str] = Field(None, description="评论者昵称")
    author_avatar: Optional[str] = Field(None, description="评论者头像URL")


class CommentCreate(CommentBase):
    """创建评论."""

    sub_comment_count: int = Field(default=0, description="子评论数量")
    liked_count: int = Field(default=0, description="点赞数")
    reply_count: int = Field(default=0, description="回复数")
    ip_location: Optional[str] = Field(None, description="IP属地")
    published_at: Optional[datetime] = Field(None, description="评论发布时间")


class CommentUpdate(BaseModel):
    """更新评论."""

    content: Optional[str] = None
    sub_comment_count: Optional[int] = None
    liked_count: Optional[int] = None
    reply_count: Optional[int] = None


class CommentInDB(CommentBase):
    """数据库中的评论."""

    id: int
    sub_comment_count: int
    liked_count: int
    reply_count: int
    ip_location: Optional[str]
    published_at: Optional[datetime]
    crawled_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Comment(CommentInDB):
    """API 返回的评论."""

    pass


class TaskCommentCreate(BaseModel):
    """创建任务-评论关联."""

    task_id: int
    comment_id: int
    keyword: Optional[str] = None


class TaskCommentResponse(BaseModel):
    """任务-评论关联响应."""

    id: int
    task_id: int
    comment_id: int
    keyword: Optional[str]
    crawled_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    """评论列表响应."""

    items: list[Comment]
    total: int
    page: int
    page_size: int
