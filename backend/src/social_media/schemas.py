"""社交媒体数据模块的Pydantic schemas"""

from pydantic import Field, model_validator
from datetime import datetime
from typing import Optional, List, Literal
from src.schemas import CustomBaseModel, PaginatedResponse


# ==================== Platform Schemas ====================

class PlatformBase(CustomBaseModel):
    """平台基础模型"""

    name: str = Field(..., max_length=100, description="平台名称")
    code: str = Field(..., max_length=20, description="平台代码（如: xhs, dy, bili等）")
    description: Optional[str] = Field(None, max_length=500, description="平台描述")
    base_url: Optional[str] = Field(None, max_length=512, description="平台基础URL")
    icon_url: Optional[str] = Field(None, max_length=512, description="平台图标URL")


class PlatformRead(PlatformBase):
    """平台读取模型（返回给客户端）"""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


PlatformListResponse = PaginatedResponse[PlatformRead]


# ==================== SocialProject Schemas ====================

class SocialProjectBase(CustomBaseModel):
    """社交项目基础模型"""

    name: str = Field(..., min_length=1, max_length=255, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    project_start_date: Optional[datetime] = Field(None, description="项目开始时间")
    project_end_date: Optional[datetime] = Field(None, description="项目结束时间")


class QuickTaskCreate(CustomBaseModel):
    """快速创建任务配置（仅支持search和homefeed）"""

    platform_ids: List[int] = Field(..., min_length=1, description="平台ID列表")
    task_type: Literal["search", "homefeed"] = Field(..., description="任务类型（仅支持search和homefeed）")
    data_source: Literal["local_upload", "remote_crawler"] = Field(..., description="数据源")
    keywords: Optional[str] = Field(None, description="搜索关键词（search类型必填）")

    @model_validator(mode='after')
    def validate_keywords(self):
        """验证search任务必须提供关键词"""
        if self.task_type == "search" and not self.keywords:
            raise ValueError("keywords is required for search tasks")
        return self


class SocialProjectCreate(SocialProjectBase):
    """创建社交项目请求模型"""

    participant_ids: List[int] = Field(default_factory=list, description="参与者用户ID列表")
    quick_tasks: Optional[QuickTaskCreate] = Field(None, description="同时创建任务（可选）")


class SocialProjectUpdate(CustomBaseModel):
    """更新社交项目请求模型"""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    project_start_date: Optional[datetime] = Field(None, description="项目开始时间")
    project_end_date: Optional[datetime] = Field(None, description="项目结束时间")


class SocialProjectRead(SocialProjectBase):
    """社交项目读取模型（返回给客户端）"""

    id: int
    owner_id: int
    deep_analysis_settings: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    # 关联数据
    participant_ids: List[int] = Field(default_factory=list, description="参与者ID列表")

    model_config = {"from_attributes": True}


class SocialProjectReadWithOwner(SocialProjectRead):
    """带owner信息的项目读取模型"""

    owner_username: str = Field(..., description="项目创建者用户名")
    participant_usernames: List[str] = Field(default_factory=list, description="参与者用户名列表")


SocialProjectListResponse = PaginatedResponse[SocialProjectReadWithOwner]


class SocialProjectCreateResponse(CustomBaseModel):
    """创建项目响应（包含项目和可选的批量创建任务）"""

    project: SocialProjectRead = Field(..., description="创建的项目")
    created_tasks: List[dict] = Field(default_factory=list, description="批量创建的任务列表")


# ==================== Project-Participant Management ====================

class ProjectParticipantAssignment(CustomBaseModel):
    """项目-参与者关联模型"""

    user_ids: List[int] = Field(..., min_length=1, description="要添加的参与者用户ID列表")


# ==================== Deep Analysis Settings ====================

class DeepAnalysisSettings(CustomBaseModel):
    """深度分析阈值配置"""

    spam_score_max: Optional[float] = Field(None, ge=0, le=1, description="垃圾信息分数上限")
    value_score_min: Optional[float] = Field(None, ge=0, le=1, description="价值分数下限")
    relevance_score_min: Optional[float] = Field(None, ge=0, le=1, description="相关性分数下限")


class UpdateDeepAnalysisSettings(CustomBaseModel):
    """更新深度分析配置请求"""

    settings: DeepAnalysisSettings = Field(..., description="深度分析阈值配置")
