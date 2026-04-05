"""社交媒体数据模块的CRUD操作"""

from typing import Optional, List
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Platform, SocialMonitor, social_monitor_participants as monitor_participants
from src.auth.models import User


# ==================== Platform CRUD ====================


async def get_platform_by_id(db: AsyncSession, platform_id: int) -> Optional[Platform]:
    """根据ID获取平台"""
    result = await db.execute(select(Platform).where(Platform.id == platform_id))
    return result.scalar_one_or_none()


async def get_platform_by_code(db: AsyncSession, code: str) -> Optional[Platform]:
    """根据代码获取平台"""
    result = await db.execute(select(Platform).where(Platform.code == code))
    return result.scalar_one_or_none()


async def get_platforms(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> tuple[List[Platform], int]:
    """获取平台列表（带分页）"""
    # 查询总数
    count_result = await db.execute(select(func.count()).select_from(Platform))
    total = count_result.scalar_one()

    # 查询数据
    result = await db.execute(
        select(Platform).offset(skip).limit(limit).order_by(Platform.id)
    )
    platforms = result.scalars().all()

    return list(platforms), total


async def create_platform(db: AsyncSession, platform_data: dict) -> Platform:
    """创建平台"""
    platform = Platform(**platform_data)
    db.add(platform)
    await db.commit()
    await db.refresh(platform)
    return platform


# ==================== SocialMonitor CRUD ====================


async def get_social_monitor_by_id(
    db: AsyncSession, monitor_id: int, load_relations: bool = True
) -> Optional[SocialMonitor]:
    """根据ID获取项目"""
    query = select(SocialMonitor).where(SocialMonitor.id == monitor_id)

    if load_relations:
        query = query.options(
            selectinload(SocialMonitor.participants), selectinload(SocialMonitor.owner)
        )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_social_monitor_by_name(db: AsyncSession, name: str) -> Optional[SocialMonitor]:
    """根据名称获取项目"""
    result = await db.execute(select(SocialMonitor).where(SocialMonitor.name == name))
    return result.scalar_one_or_none()


async def get_social_monitors(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    owner_id: Optional[int] = None,
    participant_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[List[SocialMonitor], int]:
    """获取项目列表（带过滤和分页）

    Args:
        db: 数据库会话
        skip: 跳过记录数
        limit: 返回记录数
        owner_id: 按所有者过滤
        participant_id: 按参与者过滤（包括owner）
        search: 搜索关键词（匹配name或keywords）
    """
    # 构建查询条件
    conditions = []

    if owner_id is not None:
        conditions.append(SocialMonitor.owner_id == owner_id)

    if participant_id is not None:
        # 参与者包括owner和participants
        conditions.append(
            or_(
                SocialMonitor.owner_id == participant_id,
                SocialMonitor.participants.any(User.id == participant_id),
            )
        )

    if search:
        search_pattern = f"%{search}%"
        conditions.append(SocialMonitor.name.ilike(search_pattern))

    # 构建基础查询
    base_query = select(SocialMonitor)
    if conditions:
        base_query = base_query.where(and_(*conditions))

    # 查询总数
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # 查询数据（加载关联）
    query = (
        base_query.options(selectinload(SocialMonitor.owner))
        .offset(skip)
        .limit(limit)
        .order_by(SocialMonitor.created_at.desc())
    )

    result = await db.execute(query)
    monitors_list = result.scalars().all()

    return list(monitors_list), total


async def create_social_monitor(
    db: AsyncSession,
    monitor_data: dict,
    owner_id: int,
    participant_ids: List[int] = None,
) -> SocialMonitor:
    """创建项目"""

    # 创建项目
    monitor = SocialMonitor(**monitor_data, owner_id=owner_id)
    db.add(monitor)
    await db.flush()  # 获取项目ID

    # 关联参与者 - 直接插入关联表
    if participant_ids:
        for user_id in participant_ids:
            await db.execute(
                monitor_participants.insert().values(
                    monitor_id=monitor.id, user_id=user_id
                )
            )

    await db.commit()
    # 重新查询以获取完整的关系数据
    result = await db.execute(
        select(SocialMonitor)
        .options(
            selectinload(SocialMonitor.participants), selectinload(SocialMonitor.owner)
        )
        .where(SocialMonitor.id == monitor.id)
    )
    return result.scalar_one()


async def update_social_monitor(
    db: AsyncSession, monitor: SocialMonitor, update_data: dict
) -> SocialMonitor:
    """更新项目"""
    for key, value in update_data.items():
        if value is not None:
            setattr(monitor, key, value)

    await db.commit()
    await db.refresh(monitor)
    return monitor


async def delete_social_monitor(db: AsyncSession, monitor: SocialMonitor) -> None:
    """删除项目"""
    await db.delete(monitor)
    await db.commit()


# ==================== SocialMonitor-Participant Relations ====================


async def add_participants_to_monitor(
    db: AsyncSession, monitor: SocialMonitor, user_ids: List[int]
) -> SocialMonitor:
    """为项目添加参与者"""
    users = await db.execute(select(User).where(User.id.in_(user_ids)))
    new_participants = users.scalars().all()

    # 只添加未关联的参与者
    existing_ids = {u.id for u in monitor.participants}
    for user in new_participants:
        if user.id not in existing_ids and user.id != monitor.owner_id:
            monitor.participants.append(user)

    await db.commit()
    await db.refresh(monitor, ["participants"])
    return monitor


async def remove_participant_from_monitor(
    db: AsyncSession, monitor: SocialMonitor, user_id: int
) -> SocialMonitor:
    """从项目移除参与者"""
    monitor.participants = [u for u in monitor.participants if u.id != user_id]
    await db.commit()
    await db.refresh(monitor, ["participants"])
    return monitor


# ==================== Permission Helpers ====================


async def check_monitor_access(db: AsyncSession, monitor_id: int, user_id: int) -> bool:
    """
    检查用户是否有项目访问权限

    访问权限规则：
    1. 管理员和超级管理员：可以访问所有项目
    2. 项目创建者（owner）：可以访问
    3. 项目参与者（participant）：可以访问
    """
    # 获取用户信息和角色
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.auth.models import User
    from src.rbac.models import UserRole

    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return False

    # 检查是否是管理员或超级管理员
    from src.rbac.utils import is_admin_or_super_admin

    if is_admin_or_super_admin(user):
        return True

    # 获取项目信息
    monitor = await get_social_monitor_by_id(db, monitor_id, load_relations=True)
    if not monitor:
        return False

    # 检查是否是owner
    if monitor.owner_id == user_id:
        return True

    # 检查是否是participant
    participant_ids = [p.id for p in monitor.participants]
    return user_id in participant_ids


async def assert_social_monitor_access(
    db: AsyncSession,
    monitor_id: int,
    user_id: int,
    detail: str = "You don't have access to this monitor",
) -> None:
    """验证用户有 monitor 访问权限，无权限时直接抛 HTTP 403。"""
    from fastapi import HTTPException, status as http_status

    has_access = await check_monitor_access(db, monitor_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


# ==================== Backward-compatible aliases ====================

# These aliases keep existing callers working while we migrate all call sites.
get_monitor_by_id = get_social_monitor_by_id
get_monitor_by_name = get_social_monitor_by_name
get_monitors = get_social_monitors
create_monitor = create_social_monitor
update_monitor = update_social_monitor
delete_monitor = delete_social_monitor
assert_monitor_access = assert_social_monitor_access
