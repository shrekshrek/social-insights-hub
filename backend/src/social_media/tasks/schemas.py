"""社交媒体数据任务Pydantic模型"""

from datetime import datetime
from typing import Optional, List
from pydantic import Field, field_validator

from src.schemas import CustomBaseModel


# ==================== DataTask Schemas ====================

class DataTaskBase(CustomBaseModel):
    """任务基础模型"""
    name: str = Field(..., min_length=1, max_length=255, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    platform_id: int = Field(..., gt=0, description="平台ID")
    task_type: str = Field(
        ...,
        pattern="^(search|detail|creator|homefeed)$",
        description="任务类型: search/detail/creator/homefeed"
    )
    keywords: Optional[str] = Field(None, description="搜索关键词（仅search类型）")
    task_params: Optional[dict] = Field(None, description="任务参数")


class DataTaskCreate(DataTaskBase):
    """创建任务"""
    project_id: int = Field(..., gt=0, description="项目ID")
    data_source: str = Field(
        ...,
        pattern="^(remote_crawler|local_upload)$",
        description="数据源: remote_crawler/local_upload"
    )


class DataTaskUpdate(CustomBaseModel):
    """更新任务"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    keywords: Optional[str] = None
    task_params: Optional[dict] = None
    status: Optional[str] = Field(
        None,
        pattern="^(pending|running|completed|failed)$"
    )


class DataTaskRead(DataTaskBase):
    """任务详情返回"""
    id: int
    project_id: int
    creator_id: int
    data_source: str
    status: str
    posts_count: int
    comments_count: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class DataTaskReadWithRelations(DataTaskRead):
    """任务详情（包含关联信息）"""
    project_name: Optional[str] = None
    platform_name: Optional[str] = None
    platform_code: Optional[str] = None
    creator_username: Optional[str] = None


class DataTaskListResponse(CustomBaseModel):
    """任务列表响应"""
    items: List[DataTaskReadWithRelations]
    total: int
    page: int
    page_size: int

    @classmethod
    def create(cls, items: List[DataTaskReadWithRelations], total: int, page: int, page_size: int):
        """创建分页响应"""
        return cls(items=items, total=total, page=page, page_size=page_size)


# ==================== SocialPost Schemas ====================

class SocialPostBase(CustomBaseModel):
    """原文基础模型"""
    post_id_on_platform: str = Field(..., min_length=1, max_length=255, description="平台上的帖子ID")
    post_type: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = None
    content: Optional[str] = None
    author_id: Optional[str] = Field(None, max_length=255)
    author_name: Optional[str] = Field(None, max_length=255)
    likes_count: int = Field(0, ge=0, description="点赞数")
    comments_count: int = Field(0, ge=0, description="评论数")
    shares_count: int = Field(0, ge=0, description="分享/转发数")
    collected_count: int = Field(0, ge=0, description="收藏数")
    views_count: int = Field(0, ge=0, description="播放/浏览数")
    images: Optional[List[str]] = None
    videos: Optional[List[str]] = None
    published_at: Optional[datetime] = None
    url: Optional[str] = None
    raw_data: Optional[dict] = None


class SocialPostCreate(SocialPostBase):
    """创建原文（用于JSON上传）"""
    pass


class SocialPostRead(SocialPostBase):
    """原文详情返回"""
    id: int
    task_id: int
    platform_id: int
    collected_at: datetime
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class SocialPostWithComments(SocialPostRead):
    """原文详情（包含评论）"""
    comments: List["SocialCommentRead"] = []


class SocialPostListResponse(CustomBaseModel):
    """原文列表响应"""
    items: List[SocialPostRead]
    total: int
    page: int
    page_size: int

    @classmethod
    def create(cls, items: List[SocialPostRead], total: int, page: int, page_size: int):
        """创建分页响应"""
        return cls(items=items, total=total, page=page, page_size=page_size)


# ==================== SocialComment Schemas ====================

class SocialCommentBase(CustomBaseModel):
    """评论基础模型"""
    comment_id_on_platform: str = Field(..., min_length=1, max_length=255, description="平台上的评论ID")
    parent_comment_id: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    author_id: Optional[str] = Field(None, max_length=255)
    author_name: Optional[str] = Field(None, max_length=255)
    likes_count: int = Field(0, ge=0)
    sub_comments_count: int = Field(0, ge=0)
    images: Optional[List[str]] = None
    published_at: Optional[datetime] = None
    raw_data: Optional[dict] = None


class SocialCommentCreate(SocialCommentBase):
    """创建评论（用于JSON上传）"""
    pass


class SocialCommentRead(SocialCommentBase):
    """评论详情返回"""
    id: int
    task_id: int
    post_id: int
    platform_id: int
    collected_at: datetime
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class SocialCommentListResponse(CustomBaseModel):
    """评论列表响应"""
    items: List[SocialCommentRead]
    total: int
    page: int
    page_size: int

    @classmethod
    def create(cls, items: List[SocialCommentRead], total: int, page: int, page_size: int):
        """创建分页响应"""
        return cls(items=items, total=total, page=page, page_size=page_size)


# ==================== JSON Upload Schemas ====================

class RawPostData(CustomBaseModel):
    """原始帖子数据（宽松验证，由适配器负责转换）

    支持各平台原始字段名，如：
    - 抖音: aweme_id, liked_count, comment_count, ...
    - 微博: note_id, liked_count, comments_count, ...
    - 小红书: note_id, liked_count, collected_count, ...
    等等
    """
    model_config = {"extra": "allow"}  # 允许任意额外字段


class RawCommentData(CustomBaseModel):
    """原始评论数据（宽松验证，由适配器负责转换）"""
    model_config = {"extra": "allow"}  # 允许任意额外字段


class JSONUploadData(CustomBaseModel):
    """JSON上传数据格式

    接受各平台原始格式的数据，后端适配器会自动转换为统一格式。
    """
    contents: List[RawPostData] = Field(..., description="原文列表（支持平台原始格式）")
    comments: List[RawCommentData] = Field(default_factory=list, description="评论列表（支持平台原始格式）")

    @field_validator('contents')
    @classmethod
    def validate_contents_not_empty(cls, v):
        """验证原文列表不为空"""
        if not v:
            raise ValueError("原文列表不能为空")
        return v


class JSONUploadRequest(CustomBaseModel):
    """JSON上传请求"""
    task_id: int = Field(..., gt=0, description="任务ID")
    data: JSONUploadData = Field(..., description="上传的数据")


class JSONUploadResponse(CustomBaseModel):
    """JSON上传响应"""
    task_id: int
    posts_imported: int
    comments_imported: int
    message: str


# ==================== WebSocket Crawler Schemas ====================

class CrawlerTaskRequest(CustomBaseModel):
    """爬虫任务请求"""
    task_id: int
    platform_code: str
    task_type: str
    keywords: Optional[str] = None
    params: Optional[dict] = None


class CrawlerTaskStatus(CustomBaseModel):
    """爬虫任务状态"""
    task_id: int
    status: str  # connecting/running/completed/failed
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    posts_count: int = 0
    comments_count: int = 0
    message: Optional[str] = None


# ==================== Query Schemas ====================

class CrossTaskPostQuery(CustomBaseModel):
    """跨任务查询同一帖子"""
    platform_id: int
    post_id_on_platform: str
    project_id: Optional[int] = None


class PostQueryResponse(CustomBaseModel):
    """帖子查询响应"""
    posts: List[SocialPostRead]
    total_tasks: int
    message: str


# 解决循环引用
SocialPostWithComments.model_rebuild()
