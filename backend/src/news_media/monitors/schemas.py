"""新闻监测项目 Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class NewsMonitorCreate(CustomBaseModel):
    """创建新闻监测项目"""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    participant_ids: list[int] = Field(default_factory=list, description="参与者用户ID列表")


class NewsMonitorUpdate(CustomBaseModel):
    """更新新闻监测项目"""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


class NewsMonitorRead(CustomBaseModel):
    """新闻监测项目详情"""

    id: int
    name: str
    description: str | None
    owner_id: int
    participant_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class NewsMonitorReadWithOwner(NewsMonitorRead):
    """新闻监测项目详情（含创建者用户名）"""

    owner_username: str
    participant_usernames: list[str] = Field(default_factory=list)

    @classmethod
    def from_orm_full(cls, monitor) -> "NewsMonitorReadWithOwner":
        return cls(
            id=monitor.id,
            name=monitor.name,
            description=monitor.description,
            owner_id=monitor.owner_id,
            participant_ids=[p.id for p in monitor.participants],
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            owner_username=monitor.owner.username if monitor.owner else "",
            participant_usernames=[p.username for p in monitor.participants],
        )


class NewsMonitorParticipantAssignment(CustomBaseModel):
    """新闻监测项目参与者批量添加请求"""

    user_ids: list[int] = Field(..., min_length=1, description="要添加的参与者用户ID列表")
