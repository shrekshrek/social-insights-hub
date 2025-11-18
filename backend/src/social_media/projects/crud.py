"""社交媒体数据模块的CRUD操作"""

from typing import Optional, List
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Platform, SocialProject, social_project_participants
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
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> tuple[List[Platform], int]:
    """获取平台列表（带分页）"""
    # 查询总数
    count_result = await db.execute(select(func.count()).select_from(Platform))
    total = count_result.scalar_one()

    # 查询数据
    result = await db.execute(
        select(Platform)
        .offset(skip)
        .limit(limit)
        .order_by(Platform.id)
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


# ==================== SocialProject CRUD ====================

async def get_project_by_id(
    db: AsyncSession,
    project_id: int,
    load_relations: bool = True
) -> Optional[SocialProject]:
    """根据ID获取项目"""
    query = select(SocialProject).where(SocialProject.id == project_id)

    if load_relations:
        query = query.options(
            selectinload(SocialProject.participants),
            selectinload(SocialProject.owner)
        )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_project_by_name(db: AsyncSession, name: str) -> Optional[SocialProject]:
    """根据名称获取项目"""
    result = await db.execute(select(SocialProject).where(SocialProject.name == name))
    return result.scalar_one_or_none()


async def get_projects(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    owner_id: Optional[int] = None,
    participant_id: Optional[int] = None,
    search: Optional[str] = None
) -> tuple[List[SocialProject], int]:
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
        conditions.append(SocialProject.owner_id == owner_id)

    if participant_id is not None:
        # 参与者包括owner和participants
        conditions.append(
            or_(
                SocialProject.owner_id == participant_id,
                SocialProject.participants.any(User.id == participant_id)
            )
        )

    if search:
        search_pattern = f"%{search}%"
        conditions.append(SocialProject.name.ilike(search_pattern))

    # 构建基础查询
    base_query = select(SocialProject)
    if conditions:
        base_query = base_query.where(and_(*conditions))

    # 查询总数
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # 查询数据（加载关联）
    query = base_query.options(
        selectinload(SocialProject.owner)
    ).offset(skip).limit(limit).order_by(SocialProject.created_at.desc())

    result = await db.execute(query)
    projects = result.scalars().all()

    return list(projects), total


async def create_project(
    db: AsyncSession,
    project_data: dict,
    owner_id: int,
    participant_ids: List[int] = None
) -> SocialProject:
    """创建项目"""
    from .models import social_project_participants

    # 创建项目
    project = SocialProject(**project_data, owner_id=owner_id)
    db.add(project)
    await db.flush()  # 获取项目ID

    # 关联参与者 - 直接插入关联表
    if participant_ids:
        for user_id in participant_ids:
            await db.execute(
                social_project_participants.insert().values(
                    project_id=project.id,
                    user_id=user_id
                )
            )

    await db.commit()
    # 重新查询以获取完整的关系数据
    result = await db.execute(
        select(SocialProject)
        .options(
            selectinload(SocialProject.participants),
            selectinload(SocialProject.owner)
        )
        .where(SocialProject.id == project.id)
    )
    return result.scalar_one()



async def update_project(
    db: AsyncSession,
    project: SocialProject,
    update_data: dict
) -> SocialProject:
    """更新项目"""
    for key, value in update_data.items():
        if value is not None:
            setattr(project, key, value)

    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project: SocialProject) -> None:
    """删除项目"""
    await db.delete(project)
    await db.commit()


# ==================== Project-Participant Relations ====================

async def add_participants_to_project(
    db: AsyncSession,
    project: SocialProject,
    user_ids: List[int]
) -> SocialProject:
    """为项目添加参与者"""
    users = await db.execute(
        select(User).where(User.id.in_(user_ids))
    )
    new_participants = users.scalars().all()

    # 只添加未关联的参与者
    existing_ids = {u.id for u in project.participants}
    for user in new_participants:
        if user.id not in existing_ids and user.id != project.owner_id:
            project.participants.append(user)

    await db.commit()
    await db.refresh(project, ["participants"])
    return project


async def remove_participant_from_project(
    db: AsyncSession,
    project: SocialProject,
    user_id: int
) -> SocialProject:
    """从项目移除参与者"""
    project.participants = [u for u in project.participants if u.id != user_id]
    await db.commit()
    await db.refresh(project, ["participants"])
    return project


# ==================== Permission Helpers ====================

async def check_project_access(
    db: AsyncSession,
    project_id: int,
    user_id: int
) -> bool:
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

    stmt = select(User).where(User.id == user_id).options(
        selectinload(User.user_roles).selectinload(UserRole.role)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return False

    # 检查是否是管理员或超级管理员
    role_names = [ur.role.name for ur in user.user_roles]
    if 'admin' in role_names or 'super_admin' in role_names:
        return True

    # 获取项目信息
    project = await get_project_by_id(db, project_id, load_relations=True)
    if not project:
        return False

    # 检查是否是owner
    if project.owner_id == user_id:
        return True

    # 检查是否是participant
    participant_ids = [p.id for p in project.participants]
    return user_id in participant_ids
