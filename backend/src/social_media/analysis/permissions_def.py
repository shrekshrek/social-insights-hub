"""分析模块权限定义

定义analysis模块的所有权限，用于RBAC系统初始化
"""

from src.rbac.utils import create_module_permissions


# 数据分析权限
ANALYSIS_PERMISSIONS = create_module_permissions(
    module_name="analysis",
    actions=[
        "access",              # 访问AI分析统计页面
        "read",                # 查看分析任务列表和结果
        "task.run_screening",  # 运行任务级AI初筛分析
        "task.run_deep",  # 运行任务级深度分析
        "task.view_results",  # 查看任务级分析结果
        "task.delete_results",  # 删除任务级分析结果
        "monitor.run_clustering",  # 运行项目级主题聚类分析
        "monitor.run_competitive",  # 运行项目级竞品分析
        "monitor.view_results",  # 查看项目级分析结果
        "monitor.delete_results",  # 删除项目级分析结果
        "stats.view",  # 查看Token使用统计和成本
        "results.export",  # 导出分析结果
    ],
    display_names={
        "access": "访问AI分析",
        "read": "查看分析任务",
        "task.run_screening": "运行任务AI初筛",
        "task.run_deep": "运行任务深度分析",
        "task.view_results": "查看任务分析结果",
        "task.delete_results": "删除任务分析结果",
        "monitor.run_clustering": "运行主题聚类分析",
        "monitor.run_competitive": "运行竞品分析",
        "monitor.view_results": "查看项目分析结果",
        "monitor.delete_results": "删除项目分析结果",
        "stats.view": "查看统计信息",
        "results.export": "导出分析结果",
    },
    descriptions={
        "access": "允许访问AI分析统计页面",
        "read": "允许查看分析任务列表、详情和进度",
        "task.run_screening": "允许对单个任务执行AI初筛分析（垃圾分、价值分、相关度）",
        "task.run_deep": "允许对单个任务执行深度分析（原文和评论深度挖掘）",
        "task.view_results": "允许查看任务级分析结果和详情",
        "task.delete_results": "允许删除任务级分析结果和记录",
        "monitor.run_clustering": "允许对项目数据执行主题聚类分析",
        "monitor.run_competitive": "允许对项目数据执行竞品态势分析",
        "monitor.view_results": "允许查看项目级全局分析结果",
        "monitor.delete_results": "允许删除项目级分析结果和记录",
        "stats.view": "允许查看Token使用量、成本统计和性能指标",
        "results.export": "允许导出分析结果为Excel、PDF等格式",
    },
)

# 所有权限汇总
ALL_PERMISSIONS = ANALYSIS_PERMISSIONS
