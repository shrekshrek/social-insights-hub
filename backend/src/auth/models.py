from typing import TYPE_CHECKING
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from src.database import Base

if TYPE_CHECKING:
    from src.rbac.models import UserRole
    from src.social_media.projects.models import SocialProject, social_project_participants


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(
        String(100), unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[str] = mapped_column(String)

    # 时间戳字段
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    user_roles: Mapped[list["UserRole"]] = relationship(
        "src.rbac.models.UserRole", back_populates="user", cascade="all, delete-orphan"
    )

    # 社交媒体项目关系（作为owner）
    owned_projects: Mapped[list["SocialProject"]] = relationship(
        "src.social_media.projects.models.SocialProject",
        foreign_keys="SocialProject.owner_id",
        back_populates="owner"
    )

    # 社交媒体项目关系（作为participant）
    participating_projects: Mapped[list["SocialProject"]] = relationship(
        "src.social_media.projects.models.SocialProject",
        secondary="social_project_participants",
        back_populates="participants"
    )
