"""
RBAC 初始化数据脚本
用于创建基础的权限和角色数据

包含权限模板函数，用于快速创建新模块的标准权限集
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.rbac import models, service, schemas
from src.rbac.models import SystemRoles

# 导入权限模板工具函数
from src.rbac.utils import create_module_permissions


logger = logging.getLogger(__name__)


# ============================================================================
# 系统核心权限（RBAC核心功能，开发者通常不需要修改）
# ============================================================================
CORE_PERMISSIONS = [
    # 用户管理权限
    {
        "target": "user",
        "action": "read",
        "display_name": "查看用户",
        "description": "查看用户信息和列表",
    },
    {
        "target": "user",
        "action": "write",
        "display_name": "编辑用户",
        "description": "创建和编辑用户信息",
    },
    {
        "target": "user",
        "action": "delete",
        "display_name": "删除用户",
        "description": "删除用户账户",
    },
    # 角色管理权限
    {
        "target": "role",
        "action": "read",
        "display_name": "查看角色",
        "description": "查看角色信息和权限配置",
    },
    {
        "target": "role",
        "action": "write",
        "display_name": "编辑角色",
        "description": "创建和编辑角色及权限分配",
    },
    {
        "target": "role",
        "action": "delete",
        "display_name": "删除角色",
        "description": "删除自定义角色",
    },
    # 权限管理权限
    {
        "target": "permission",
        "action": "read",
        "display_name": "查看权限",
        "description": "查看系统权限列表和配置",
    },
    {
        "target": "permission",
        "action": "write",
        "display_name": "编辑权限",
        "description": "临时权限管理（不推荐使用）",
    },
    {
        "target": "permission",
        "action": "delete",
        "display_name": "删除权限",
        "description": "删除临时权限（不推荐使用）",
    },
    # RBAC管理页面访问权限
    {
        "target": "user",
        "action": "access",
        "display_name": "访问用户管理",
        "description": "允许访问用户管理页面",
    },
    {
        "target": "role",
        "action": "access",
        "display_name": "访问角色管理",
        "description": "允许访问角色管理页面",
    },
    {
        "target": "permission",
        "action": "access",
        "display_name": "访问权限管理",
        "description": "允许访问权限管理页面",
    },
]

# ============================================================================
# 业务功能权限（开发者在此直接添加新模块权限）
# ============================================================================
BUSINESS_PERMISSIONS = [
    # 基础业务模块（使用模板函数，1行即可！）
    *create_module_permissions("dashboard", ["access"]),
    # ========================================================================
    # 新模块权限添加示例（开发者只需1行代码！）
    # ========================================================================
    #
    # 📝 使用说明：
    # 1. 取消注释下面对应的行
    # 2. 修改模块名和权限组合
    # 3. 重启服务（`pnpm dev`）自动同步到数据库
    #
    # 🎯 常用模板：
    #
    # 📊 报表模块（页面 + 查看 + 导出）
    # *create_module_permissions("reports", ["access", "read", "export"]),
    #
    # 📈 数据分析（页面 + 查看 + 导出）
    # *create_module_permissions("analytics", ["access", "read", "export"]),
    #
    # 📄 文档管理（完整CRUD）
    # *create_module_permissions("documents", ["access", "read", "write", "delete"]),
    #
    # 🔔 通知系统（自定义权限名称）
    # *create_module_permissions("notifications", ["access", "read", "send"], {
    #     "send": "发送通知"
    # }),
    #
    # 📦 库存管理（完整管理权限）
    # *create_module_permissions("inventory", ["access", "read", "write", "delete", "export", "import"]),
    #
    # ========================================================================
    # 社交媒体监测管理
    # ========================================================================
    *create_module_permissions(
        "social_monitor",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问社媒监测",
            "read": "查看社媒监测",
            "write": "编辑社媒监测",
            "delete": "删除社媒监测",
        },
        descriptions={
            "access": "允许访问社交媒体监测管理页面",
            "read": "允许查看社媒监测详情和列表",
            "write": "允许创建和编辑社媒监测项目",
            "delete": "允许删除社媒监测及其关联数据",
        },
    ),
    # ========================================================================
    # 社交媒体采集任务管理
    # ========================================================================
    *create_module_permissions(
        "social_task",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问社媒采集任务",
            "read": "查看社媒采集任务",
            "write": "编辑社媒采集任务",
            "delete": "删除社媒采集任务",
        },
        descriptions={
            "access": "允许访问社媒数据采集任务管理页面",
            "read": "允许查看社媒任务详情和数据",
            "write": "允许创建社媒任务和上传数据",
            "delete": "允许删除社媒任务及其数据",
        },
    ),
    # ========================================================================
    # 新闻监测管理
    # ========================================================================
    *create_module_permissions(
        "news_monitor",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问新闻监测",
            "read": "查看新闻监测",
            "write": "编辑新闻监测",
            "delete": "删除新闻监测",
        },
        descriptions={
            "access": "允许访问新闻监测管理页面",
            "read": "允许查看新闻监测详情和列表",
            "write": "允许创建和编辑新闻监测项目",
            "delete": "允许删除新闻监测及其关联数据",
        },
    ),
    # ========================================================================
    # 新闻采集任务管理
    # ========================================================================
    *create_module_permissions(
        "news_task",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问新闻采集任务",
            "read": "查看新闻采集任务",
            "write": "编辑新闻采集任务",
            "delete": "删除新闻采集任务",
        },
        descriptions={
            "access": "允许访问新闻数据采集任务管理页面",
            "read": "允许查看新闻任务详情和文章数据",
            "write": "允许创建新闻任务和执行采集",
            "delete": "允许删除新闻任务及其数据",
        },
    ),
    # ========================================================================
    # AI 任务统计（仅管 /jobs 跨渠道任务历史页面；具体分析触发权归各渠道模块）
    # ========================================================================
    *create_module_permissions(
        "jobs",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问AI统计",
            "read": "查看AI任务",
            "write": "管理AI任务",
            "delete": "删除AI任务",
        },
        descriptions={
            "access": "允许访问 AI 统计页面（跨渠道 AnalysisJob 任务历史与成本）",
            "read": "允许查看 AI 任务列表、详情和进度",
            "write": "允许管理 AI 任务（保留对齐，暂未启用）",
            "delete": "允许取消和删除 AI 任务记录",
        },
    ),
    # ========================================================================
    # 策略定义模块
    # ========================================================================
    *create_module_permissions(
        "strategy",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问策略管理",
            "read": "查看策略",
            "write": "编辑策略",
            "delete": "删除策略",
        },
        descriptions={
            "access": "允许访问策略管理模块",
            "read": "允许查看策略详情和列表",
            "write": "允许创建和编辑策略",
            "delete": "允许删除策略",
        },
    ),
    *create_module_permissions(
        "knowledge_base",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问知识库",
            "read": "查看文档",
            "write": "上传文档",
            "delete": "删除文档",
        },
        descriptions={
            "access": "允许访问市场知识库页面",
            "read": "允许查看和检索知识库文档",
            "write": "允许上传文档到知识库",
            "delete": "允许删除知识库文档",
        },
    ),
    # ========================================================================
    # Research Agent 研究分析
    # ========================================================================
    *create_module_permissions(
        "research_agent",
        ["access", "read", "write", "delete"],
        display_names={
            "access": "访问研究分析",
            "read": "查看研究任务",
            "write": "创建研究任务",
            "delete": "删除研究任务",
        },
        descriptions={
            "access": "允许访问研究分析页面",
            "read": "允许查看研究任务和结果",
            "write": "允许创建和重新运行研究任务",
            "delete": "允许删除研究任务",
        },
    ),
    # ========================================================================
    # 审计日志
    # ========================================================================
    *create_module_permissions(
        "audit",
        ["access", "read"],
        display_names={
            "access": "访问操作日志",
            "read": "查看操作日志",
        },
        descriptions={
            "access": "允许访问操作日志页面",
            "read": "允许查看用户操作审计日志",
        },
    ),
]

# 合并所有权限
BASE_PERMISSIONS = CORE_PERMISSIONS + BUSINESS_PERMISSIONS


# ============================================================================
# 基础角色定义 - 基于target+action的权限分配
# ============================================================================

BASE_ROLES = [
    {
        "name": SystemRoles.SUPER_ADMIN,
        "display_name": "超级管理员",
        "description": "超级管理员，拥有所有权限",
        "permission_strategy": "all",
        "permissions": [],  # 智能策略：自动拥有所有权限
    },
    {
        "name": SystemRoles.ADMIN,
        "display_name": "管理员",
        "description": "系统管理员，拥有管理权限但不能删除核心资源",
        "permission_strategy": "admin",
        "permissions": [],  # 智能策略：自动拥有除核心删除外的所有权限
    },
    {
        "name": SystemRoles.USER,
        "display_name": "普通用户",
        "description": "普通用户，只能访问基础功能",
        "permission_strategy": "explicit",
        "permissions": [
            # 明确权限：仅基础页面访问
            {"target": "dashboard", "action": "access"},
        ],
    },
]


async def init_permissions(db: AsyncSession) -> dict[str, models.Permission]:
    """初始化权限数据 - 基于 target:action 格式"""
    permissions = {}

    for perm_data in BASE_PERMISSIONS:
        target = perm_data["target"]
        action = perm_data["action"]
        permission_key = f"{target}:{action}"

        # 检查权限是否已存在（基于target+action）
        existing = await service.get_permission_by_target_action(db, target, action)
        if existing:
            # 更新现有权限的显示名称和描述
            existing.display_name = perm_data["display_name"]
            existing.description = perm_data.get("description")
            await db.commit()
            await db.refresh(existing)
            permissions[permission_key] = existing
            continue

        # 创建新权限
        try:
            permission = await service.create_permission(
                db, schemas.PermissionCreate(**perm_data)
            )
            permissions[permission_key] = permission
        except service.PermissionAlreadyExistsException:
            # 如果在并发情况下权限已被创建，重新获取
            existing = await service.get_permission_by_target_action(db, target, action)
            permissions[permission_key] = existing

    return permissions


async def init_roles(
    db: AsyncSession, permissions: dict[str, models.Permission]
) -> dict[str, models.Role]:
    """初始化角色数据 - 基于target+action的新逻辑"""
    roles = {}

    for role_data in BASE_ROLES:
        # 检查角色是否已存在
        existing = await service.get_role_by_name(db, role_data["name"])
        if existing:
            updated = False
            if (
                role_data.get("display_name")
                and existing.display_name != role_data["display_name"]
            ):
                existing.display_name = role_data["display_name"]
                updated = True
            if (
                role_data.get("description") is not None
                and existing.description != role_data["description"]
            ):
                existing.description = role_data["description"]
                updated = True
            desired_strategy = role_data.get("permission_strategy", "explicit")
            if existing.permission_strategy != desired_strategy:
                existing.permission_strategy = desired_strategy
                updated = True

            if updated:
                await db.commit()
                await db.refresh(existing)

            roles[role_data["name"]] = existing
            continue

        # 根据权限策略处理权限分配
        permission_ids = []
        permission_strategy = role_data.get("permission_strategy", "explicit")

        if permission_strategy == "explicit":
            # 明确权限策略：使用权限列表
            for perm_dict in role_data["permissions"]:
                permission_key = f"{perm_dict['target']}:{perm_dict['action']}"
                if permission_key in permissions:
                    permission_ids.append(permissions[permission_key].id)
        # all和admin策略不需要明确权限，通过智能检查实现

        # 创建角色
        try:
            role_create_data = {
                "name": role_data["name"],
                "display_name": role_data["display_name"],
                "description": role_data["description"],
                "permission_strategy": permission_strategy,
                "permission_ids": permission_ids,
            }

            role = await service.create_role(db, schemas.RoleCreate(**role_create_data))

            roles[role_data["name"]] = role
        except service.RoleAlreadyExistsException:
            # 如果在并发情况下角色已被创建，重新获取
            existing = await service.get_role_by_name(db, role_data["name"])
            roles[role_data["name"]] = existing

    return roles


async def init_rbac_data(db: AsyncSession) -> None:
    """
    初始化RBAC数据 - 完全同步模式
    将代码定义的权限与数据库完全同步：
    - 添加新权限
    - 更新已有权限的显示名称和描述
    - 删除代码中未定义的权限
    """

    # 多 worker 并发启动时，用 PostgreSQL advisory lock 确保只有一个 worker 执行初始化
    lock_acquired = (await db.execute(text("SELECT pg_try_advisory_lock(1000000)"))).scalar()
    if not lock_acquired:
        logger.info("其他 worker 正在执行 RBAC 初始化，跳过")
        return

    try:
        await _do_init_rbac_data(db)
    finally:
        await db.execute(text("SELECT pg_advisory_unlock(1000000)"))


async def _do_init_rbac_data(db: AsyncSession) -> None:
    # 1. 获取代码中定义的所有权限
    defined_permissions = {f"{p['target']}:{p['action']}": p for p in BASE_PERMISSIONS}

    # 2. 获取数据库中现有权限
    result = await db.execute(text("SELECT target, action FROM permissions"))
    db_permissions = {f"{r.target}:{r.action}" for r in result}

    # 3. 计算差异
    to_add = set(defined_permissions.keys()) - db_permissions
    to_delete = db_permissions - set(defined_permissions.keys())
    to_update = set(defined_permissions.keys()) & db_permissions

    logger.info(
        "权限同步分析: 新增=%s, 删除=%s, 更新=%s",
        len(to_add),
        len(to_delete),
        len(to_update),
    )

    # 4. 删除未定义的权限
    if to_delete:
        # 记录被删除权限的影响
        affected = await db.execute(
            text("""
            SELECT p.target, p.action, COUNT(rp.id) as role_count
            FROM permissions p
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE concat(p.target, ':', p.action) = ANY(:perms)
            GROUP BY p.target, p.action
        """),
            {"perms": list(to_delete)},
        )

        for row in affected:
            if row.role_count > 0:
                logger.warning(
                    "删除权限 %s:%s，将移除 %s 个角色分配",
                    row.target,
                    row.action,
                    row.role_count,
                )

        # 执行删除（外键级联会自动删除 role_permissions）
        await db.execute(
            text("""
            DELETE FROM permissions 
            WHERE concat(target, ':', action) = ANY(:perms)
        """),
            {"perms": list(to_delete)},
        )

        logger.info("删除权限: %s", sorted(to_delete))

    # 5. 添加新权限
    if to_add:
        for perm_key in to_add:
            perm_data = defined_permissions[perm_key]
            await db.execute(
                text("""
                INSERT INTO permissions (target, action, display_name, description)
                VALUES (:target, :action, :display_name, :description)
                ON CONFLICT (target, action) DO NOTHING
            """),
                perm_data,
            )

        logger.info("添加权限: %s", sorted(to_add))

    # 6. 更新已有权限
    if to_update:
        for perm_key in to_update:
            perm_data = defined_permissions[perm_key]
            await db.execute(
                text("""
                UPDATE permissions 
                SET display_name = :display_name,
                    description = :description
                WHERE target = :target AND action = :action
            """),
                perm_data,
            )

        logger.info("更新权限: %s 个", len(to_update))

    # 7. 重新获取所有权限用于角色初始化
    updated_permissions = await init_permissions(db)

    # 8. 初始化角色
    await init_roles(db, updated_permissions)

    logger.info("权限同步完成，当前总计: %s 个权限", len(defined_permissions))


# ============================================================================
# 权限分组自动化
# ============================================================================


def auto_generate_permission_groups() -> dict:
    """基于权限定义自动生成权限分组配置"""
    organized_groups = {
        "CORE": {"label": "系统核心权限", "permissions": []},
        "PAGE_ACCESS": {"label": "页面访问权限", "permissions": []},
        "BUSINESS": {"label": "业务功能权限", "permissions": []},
    }

    for permission in BASE_PERMISSIONS:
        target = permission["target"]
        action = permission["action"]
        permission_key = f"{target}:{action}"

        if target in ["user", "role", "permission"]:
            organized_groups["CORE"]["permissions"].append(permission_key)
        elif action == "access":
            organized_groups["PAGE_ACCESS"]["permissions"].append(permission_key)
        else:
            organized_groups["BUSINESS"]["permissions"].append(permission_key)

    return organized_groups
