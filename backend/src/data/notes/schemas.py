"""Note schemas for API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NoteBase(BaseModel):
    """笔记基础字段."""

    platform: str = Field(..., description="平台类型")
    note_id: str = Field(..., description="平台笔记ID")
    title: str = Field(..., description="笔记标题")
    content: Optional[str] = Field(None, description="笔记内容")
    note_type: Optional[str] = Field(None, description="笔记类型")
    author_id: Optional[str] = Field(None, description="作者ID")
    author_name: Optional[str] = Field(None, description="作者昵称")


class NoteCreate(NoteBase):
    """创建笔记."""

    liked_count: int = Field(default=0, description="点赞数")
    collected_count: int = Field(default=0, description="收藏数")
    comment_count: int = Field(default=0, description="评论数")
    shared_count: int = Field(default=0, description="分享数")
    view_count: int = Field(default=0, description="浏览数")
    images: Optional[str] = Field(None, description="图片URL列表(JSON)")
    video_url: Optional[str] = Field(None, description="视频URL")
    note_url: Optional[str] = Field(None, description="笔记链接")
    ip_location: Optional[str] = Field(None, description="IP属地")
    tags: Optional[str] = Field(None, description="标签列表(JSON)")
    published_at: Optional[datetime] = Field(None, description="笔记发布时间")
    last_modified_at: Optional[datetime] = Field(None, description="笔记最后修改时间")


class NoteUpdate(BaseModel):
    """更新笔记."""

    title: Optional[str] = None
    content: Optional[str] = None
    liked_count: Optional[int] = None
    collected_count: Optional[int] = None
    comment_count: Optional[int] = None
    shared_count: Optional[int] = None
    view_count: Optional[int] = None
    last_modified_at: Optional[datetime] = None


class NoteInDB(NoteBase):
    """数据库中的笔记."""

    id: int
    liked_count: int
    collected_count: int
    comment_count: int
    shared_count: int
    view_count: int
    images: Optional[str]
    video_url: Optional[str]
    note_url: Optional[str]
    ip_location: Optional[str]
    tags: Optional[str]
    published_at: Optional[datetime]
    last_modified_at: Optional[datetime]
    crawled_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Note(NoteInDB):
    """API 返回的笔记."""

    pass


class TaskNoteCreate(BaseModel):
    """创建任务-笔记关联."""

    task_id: int
    note_id: int
    keyword: Optional[str] = None


class NoteListResponse(BaseModel):
    """笔记列表响应."""

    items: list[Note]
    total: int
    page: int
    page_size: int
