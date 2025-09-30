"""initial_data

Revision ID: aa99cf3f13cf
Revises: a3b73ce2274e
Create Date: 2025-09-08 16:51:41.244765

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "aa99cf3f13cf"
down_revision: Union[str, Sequence[str], None] = "a3b73ce2274e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert initial data."""
    connection = op.get_bind()

    # Create basic permissions
    connection.execute(
        text("""
        INSERT INTO permissions (target, action, display_name, description)
        VALUES 
        ('user', 'read', '查看用户', '查看用户信息和列表'),
        ('user', 'write', '编辑用户', '创建和编辑用户信息'),
        ('user', 'delete', '删除用户', '删除用户账户'),
        ('role', 'read', '查看角色', '查看角色信息和权限配置'),
        ('role', 'write', '编辑角色', '创建和编辑角色及权限分配'),
        ('role', 'delete', '删除角色', '删除自定义角色'),
        ('permission', 'read', '查看权限', '查看系统权限列表和配置'),
        ('permission', 'write', '编辑权限', '临时权限管理（不推荐使用）'),
        ('permission', 'delete', '删除权限', '删除临时权限（不推荐使用）'),
        ('user_mgmt', 'access', '访问用户管理', '允许访问用户管理页面'),
        ('role_mgmt', 'access', '访问角色管理', '允许访问角色管理页面'),
        ('perm_mgmt', 'access', '访问权限管理', '允许访问权限管理页面'),
        ('dashboard', 'access', '访问工作台', '允许访问dashboard页面和基础功能')
        ON CONFLICT (target, action) DO NOTHING
    """)
    )

    # Create basic roles
    connection.execute(
        text("""
        INSERT INTO roles (name, display_name, description, permission_strategy)
        VALUES 
        ('super_admin', '超级管理员', '超级管理员，拥有所有权限', 'all'),
        ('admin', '管理员', '系统管理员，拥有管理权限但不能删除核心资源', 'admin'),
        ('user', '普通用户', '普通用户，只能访问基础功能', 'explicit')
        ON CONFLICT (name) DO NOTHING
    """)
    )

    # Assign permissions to user role (dashboard access)
    connection.execute(
        text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.target = 'dashboard' AND p.action = 'access'
        WHERE r.name = 'user'
        AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp 
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
        )
    """)
    )

    # Create admin user with hashed password for 'admin123'
    connection.execute(
        text("""
        INSERT INTO users (username, email, hashed_password)
        VALUES (
            'admin', 
            'admin@example.com',
            '$2b$12$m/5Jb7VLHPfS8/Psksw./OGmXDiDsAKF9wRJX6veE2OKzkPGq1d.O'
        )
        ON CONFLICT (username) DO NOTHING
    """)
    )

    # Assign super_admin role to admin user
    connection.execute(
        text("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        JOIN roles r ON r.name = 'super_admin'
        WHERE u.username = 'admin'
        AND NOT EXISTS (
            SELECT 1 FROM user_roles ur 
            WHERE ur.user_id = u.id AND ur.role_id = r.id
        )
    """)
    )


def downgrade() -> None:
    """Remove initial data."""
    connection = op.get_bind()

    # Remove admin user's role assignments
    connection.execute(
        text("""
        DELETE FROM user_roles
        WHERE user_id IN (SELECT id FROM users WHERE username = 'admin')
    """)
    )

    # Remove admin user
    connection.execute(
        text("""
        DELETE FROM users WHERE username = 'admin'
    """)
    )

    # Remove role permissions
    connection.execute(
        text("""
        DELETE FROM role_permissions
    """)
    )

    # Remove roles
    connection.execute(
        text("""
        DELETE FROM roles WHERE name IN ('super_admin', 'admin', 'user')
    """)
    )

    # Remove permissions
    connection.execute(
        text("""
        DELETE FROM permissions
    """)
    )
