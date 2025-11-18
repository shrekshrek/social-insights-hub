"""RBAC工具函数"""


def create_module_permissions(
    module_name: str,
    actions: list[str],
    display_names: dict[str, str] = None,
    descriptions: dict[str, str] = None,
) -> list[dict]:
    """
    快速创建模块权限集

    Args:
        module_name: 模块名，如 "reports"
        actions: 权限动作列表，如 ["access", "read", "export"]
        display_names: 自定义显示名称 (可选)
        descriptions: 自定义描述 (可选)

    Returns:
        权限定义列表

    常用权限组合:
    - ["access"] - 仅页面访问（最简单）
    - ["access", "read"] - 页面 + 查看数据
    - ["access", "read", "write"] - 页面 + 增改操作
    - ["access", "read", "write", "delete"] - 完整CRUD
    - ["access", "read", "export"] - 页面 + 查看 + 导出
    - ["access", "read", "write", "export"] - 管理 + 导出
    """
    default_display_names = {
        "access": f"访问{module_name}",
        "read": f"查看{module_name}",
        "write": f"编辑{module_name}",
        "delete": f"删除{module_name}",
        "export": f"导出{module_name}",
        "approve": f"审批{module_name}",
        "publish": f"发布{module_name}",
        "import": f"导入{module_name}",
        "manage": f"管理{module_name}",
    }

    default_descriptions = {
        "access": f"允许访问{module_name}页面和基础功能",
        "read": f"允许查看{module_name}的详细数据和列表",
        "write": f"允许创建、编辑{module_name}的数据",
        "delete": f"允许删除{module_name}的数据",
        "export": f"允许导出{module_name}的数据",
        "approve": f"允许审批{module_name}相关流程",
        "publish": f"允许发布{module_name}到外部系统",
        "import": f"允许导入{module_name}数据",
        "manage": f"允许管理{module_name}的高级设置",
    }

    permissions = []
    for action in actions:
        target, sep, action_name = action.partition(".")
        if not sep:  # 没有点，说明是简单action
            target = module_name
            action_name = action

        permission_code = f"{target}:{action_name}"

        # 使用自定义或默认显示名
        if display_names and action in display_names:
            display_name = display_names[action]
        elif display_names and permission_code in display_names:
            display_name = display_names[permission_code]
        elif action_name in default_display_names:
            display_name = default_display_names[action_name]
        else:
            display_name = f"{module_name}:{action_name}"

        # 使用自定义或默认描述
        if descriptions and action in descriptions:
            description = descriptions[action]
        elif descriptions and permission_code in descriptions:
            description = descriptions[permission_code]
        elif action_name in default_descriptions:
            description = default_descriptions[action_name]
        else:
            description = f"允许执行{module_name}的{action_name}操作"

        permissions.append({
            "target": target,
            "action": action_name,
            "display_name": display_name,
            "description": description,
        })

    return permissions
