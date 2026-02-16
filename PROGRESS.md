# 项目进度

## 模块状态

| 模块 | 状态 | 说明 |
|------|------|------|
| auth/后端 | 已完成 | JWT 认证、用户注册登录、令牌管理、黑名单 |
| auth/前端 | 已完成 | 登录注册页面、认证状态管理 (Pinia store) |
| rbac/后端 | 已完成 | 角色权限 CRUD、代码驱动启动时自动同步 |
| rbac/前端 | 已完成 | 角色权限管理界面 |
| users/后端 | 已完成 | 用户 CRUD、角色分配 |
| users/前端 | 已完成 | 用户管理界面 |
| social_media/projects/后端 | 已完成 | 项目管理、平台初始化、参与者管理 |
| social_media/projects/前端 | 已完成 | 项目列表、创建、详情、快照分析 |
| social_media/tasks/后端 | 已完成 | 任务管理、多平台适配器、帖子/评论存储 |
| social_media/tasks/前端 | 已完成 | 任务列表、创建、详情、数据上传 |
| social_media/analysis/后端 | 已完成 | LLM 分析编排、批处理、成本追踪、报告聚合 |
| social_media/analysis/前端 | 已完成 | 分析报告展示、图表可视化、成本面板 |
| langchain/后端 | 已完成 | DeepSeek 集成、9 条分析链 |
| agent/后端 | 已完成 | 爬虫代理 API、API Key 认证、数据上传 |
| analysis/spam_distribution/后端 | 已完成 | 全模块 spam 分布: 实体/观点(4维) + 四象限/KOL(标记) + IPA/竞品/时间(2维) + NSR拆分 |
| analysis/spam_display/前端 | 已完成 | 4维可视化(比例条+popover) + 排序控件 + 时间分布堆叠图 + IPA/竞品tooltip增强 |
| analysis/spam_4d/后端 | 已完成 | IPA/竞品携带 post_source_ids+comment_source_ids，spam 计算 2D→4D，重命名 spam_distribution |
| analysis/spam_4d/前端 | 已完成 | IPA/竞品类型升级 SpamCountBreakdown→SpamDistribution，tooltip 展示 4D |
| analysis/spam_dimension_view/前端 | 实施中 | 实体和话题列表 4 维排序控件，按推广/有机×原文/评论排序对比（已完成：实体/话题/IPA/KOL 筛选） |
| analysis/spam_dimension_chart/后端 | 方案已确认 | 关联网络和竞品雷达按维度预计算 3 版本（全部/有机/推广） |
| analysis/spam_dimension_chart/前端 | 方案已确认 | 关联网络和竞品雷达维度筛选 UI，TabSwitch 切换展示 |
| 部署配置 | 已完成 | Docker Compose 开发/生产双配置 |

## 已完成的里程碑

- v1.0: 全栈基础框架 (auth + rbac + users)
- v1.x: 社交媒体数据采集与分析功能 (projects + tasks + analysis + langchain + agent)

## 待改进项

- `docs/backend-architecture.md` 缺少 social_media、langchain、agent 模块描述（仅包含 auth/rbac/users）
- `docs/frontend-architecture.md` 缺少 social-media Layer 描述
- 测试覆盖率待提升

## 下次继续的入口

`analysis/spam_dimension_chart` 模块方案已确认，参考 `docs/plan.md`。后端 7 步，前端 3 步，需改动 `orchestrator.py` + `insights.py` + 前端 3 个文件。从后端 Step 1（提前构建 spam_map）开始实施。运行 `/module-dev` 启动实现。
