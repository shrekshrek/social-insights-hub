"""Agent API Schemas"""

from datetime import datetime
from typing import Optional, Any
from pydantic import Field

from src.schemas import CustomBaseModel


# ==================== Task Schemas ====================


class AgentTaskInfo(CustomBaseModel):
    """Agent 任务信息（返回给爬虫客户端）"""

    task_id: int = Field(..., description="任务ID")
    task_name: str = Field(..., description="任务名称")
    platform: str = Field(..., description="平台代码: xhs/dy/bili/ks/wb/tieba/zhihu")
    task_type: str = Field(..., description="任务类型: search/detail/creator/homefeed")
    priority: int = Field(0, description="优先级（越大越优先）")
    keywords: Optional[str] = Field(None, description="搜索关键词")
    task_params: Optional[dict] = Field(None, description="任务参数")
    created_at: datetime = Field(..., description="创建时间")
    preview_count: Optional[int] = Field(
        None,
        description="预览采集数量。>0 时 Agent 采集到该数量后保存断点退出；null 则正常全量采集",
    )
    checkpoint_id: Optional[str] = Field(
        None,
        description="断点 ID。非空时 Agent 从该断点继续采集；null 则从头开始",
    )


class PendingTasksResponse(CustomBaseModel):
    """待执行任务列表响应"""

    tasks: list[AgentTaskInfo] = Field(default_factory=list, description="任务列表")


# ==================== Accept Schemas ====================


class AcceptTaskRequest(CustomBaseModel):
    """接收任务请求"""

    client_id: Optional[str] = Field(
        None, max_length=100, description="客户端标识（可选，用于追溯）"
    )


class AcceptTaskResponse(CustomBaseModel):
    """接收任务响应"""

    ok: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")


# ==================== Progress Schemas ====================


class ProgressUpdateRequest(CustomBaseModel):
    """进度更新请求"""

    status: str = Field(
        ...,
        pattern="^(accepted|running|completed|failed)$",
        description="任务状态",
    )
    crawled_count: Optional[int] = Field(None, ge=0, description="已爬取数量")
    message: Optional[str] = Field(None, max_length=255, description="进度描述")


class ProgressUpdateResponse(CustomBaseModel):
    """进度更新响应"""

    ok: bool = Field(..., description="是否成功")


# ==================== Result Schemas ====================


class ResultStats(CustomBaseModel):
    """结果统计"""

    contents_count: int = Field(0, ge=0, description="内容数量")
    comments_count: int = Field(0, ge=0, description="评论数量")


class UploadResultRequest(CustomBaseModel):
    """上传结果请求"""

    platform: str = Field(..., description="平台代码")
    stats: Optional[ResultStats] = Field(None, description="统计信息")
    data: dict[str, Any] = Field(..., description="采集数据")
    checkpoint_id: Optional[str] = Field(
        None,
        description="断点 ID。预览采集完成后携带，云端持久化后下发续采时回传",
    )


class StoredCounts(CustomBaseModel):
    """已存储数量"""

    posts: int = Field(0, ge=0)
    comments: int = Field(0, ge=0)


class UploadResultResponse(CustomBaseModel):
    """上传结果响应"""

    ok: bool = Field(..., description="是否成功")
    stored: Optional[StoredCounts] = Field(None, description="已存储数量")
    message: Optional[str] = Field(None, description="消息")


# ==================== Task Status Schemas ====================


class TaskStatusResponse(CustomBaseModel):
    """任务状态查询响应（供爬虫轮询）"""

    task_id: int = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")


# ==================== Health Schemas ====================


class HealthResponse(CustomBaseModel):
    """健康检查响应"""

    status: str = Field(..., description="状态")
    timestamp: datetime = Field(..., description="时间戳")
