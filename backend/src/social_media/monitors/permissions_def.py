"""社交媒体模块权限定义

定义social_media模块的所有权限，用于RBAC系统初始化
"""

from src.rbac.init_data import create_module_permissions


# 监测管理权限
SOCIAL_MEDIA_PERMISSIONS = create_module_permissions(
    module_name="social_media",
    actions=[
        "monitor.create",
        "monitor.view",
        "monitor.update",
        "monitor.delete",
        "data.view",
        "data.export",
    ],
    display_names={
        "monitor.create": "创建监测",
        "monitor.view": "查看监测",
        "monitor.update": "编辑监测",
        "monitor.delete": "删除监测",
        "data.view": "查看社交媒体数据",
        "data.export": "导出社交媒体数据",
    },
    descriptions={
        "monitor.create": "允许创建新的社交媒体数据分析项目",
        "monitor.view": "允许查看项目列表和项目详情",
        "monitor.update": "允许编辑项目信息、关联平台、管理参与者",
        "monitor.delete": "允许删除项目及其关联数据",
        "data.view": "允许查看项目中的原文和评论数据",
        "data.export": "允许导出数据为Excel、CSV等格式",
    },
)

# 所有权限汇总
ALL_PERMISSIONS = SOCIAL_MEDIA_PERMISSIONS
