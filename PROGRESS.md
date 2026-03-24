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
| social_media/projects/后端 | 已完成 | 项目管理、平台初始化、参与者管理、批量创建任务 API |
| social_media/projects/前端 | 已完成 | 项目列表、创建、详情、切片洞察、批量创建任务弹窗、QuickTaskForm 组件提取 |
| social_media/tasks/后端 | 已完成 | 任务管理、多平台适配器、原文/评论存储 |
| social_media/tasks/前端 | 已完成 | 任务列表、创建、详情、数据上传 |
| social_media/analysis/后端 | 已完成 | LLM 分析编排、批处理、成本追踪、报告聚合 |
| social_media/analysis/前端 | 已完成 | 分析报告展示、图表可视化、成本面板、切片重命名 |
| langchain/后端 | 已完成 | DeepSeek 集成、9 条分析链 |
| agent/后端 | 已完成 | 爬虫代理 API、API Key 认证、数据上传 |
| analysis/spam_distribution/后端 | 已完成 | 全模块 spam 分布: 实体/观点(4维) + 四象限/KOL(标记) + IPA/竞品/时间(2维) + NSR拆分 |
| analysis/spam_display/前端 | 已完成 | 4维可视化(比例条+popover) + 排序控件 + 时间分布堆叠图 + IPA/竞品tooltip增强 |
| analysis/spam_4d/后端 | 已完成 | IPA/竞品携带 post_source_ids+comment_source_ids，spam 计算 2D→4D，重命名 spam_distribution |
| analysis/spam_4d/前端 | 已完成 | IPA/竞品类型升级 SpamCountBreakdown→SpamDistribution，tooltip 展示 4D |
| analysis/spam_dimension_view/前端 | 已完成 | 实体/话题 4 维排序控件 + IPA/KOL/竞品维度筛选 |
| analysis/spam_dimension_chart/后端 | 已完成 | 关联网络和竞品雷达 3 层预计算（全部/有机/推广），KOL 池扩展至 top_n=10 |
| analysis/spam_dimension_chart/前端 | 已完成 | 竞品雷达 HTML 图例 + 品牌可见性控制 + 维度 TabSwitch；类型一致性修复 |
| analysis/project_slice_spam/后端 | 已完成 | 项目级切片实体/话题 4D spam 分布：PostAnalysis join 查询 spam_score，构建 spam_map_by_key，post/comment 来源追踪，Stage2 归一化传递 |
| analysis/project_slice_spam/前端 | 已完成 | ProjectTopicOrEntity 接口加 spam_distribution，证据面板话题行/实体行/实体侧边栏展示 SpamRatioBar |
| analysis/task_metrics_qa/后端 | 已完成 | 修复3个指标Bug：舆论反差度始终为零（改用 general_opinions 均值）、营销浓度阈值从硬编码4改为 SPAM_HIGH_THRESHOLD(6.0)、orchestrator 传递 spam_threshold 参数 |
| analysis/task_metrics_qa/前端 | 已完成 | NSR 情感标签 /2 归一化（-2~+2→-1~+1 范围）、KOL 声音情感标签和颜色同步 /2 归一化 |
| 代码命名/snapshot→slice/全栈 | 已完成 | 后端文件/目录重命名 + DB migration + 前端类型/API 路径全部更新为 slice |
| 文档补全/architecture | 已完成 | backend-architecture.md 补充 social_media/langchain/agent 模块；frontend-architecture.md 补充 social-media Layer 及 spam 可视化约定 |
| 部署配置 | 已完成 | Docker Compose 开发/生产双配置 |
| strategies/后端 | 已完成 | 策略定义模块：3 阶段 AI 生成（洞察→策略→创意），Phase 1/2/3 Chain + CRUD API + Word 导出 |
| strategies/前端 | 已完成 | 策略列表/创建/详情页，3 阶段结果展示与编辑，跨项目切片选择器 |
| analysis/slice_enrichment/后端 | 已完成 | 切片流水线数据补全：time_distribution(Stage1) + kol_voices(Stage1) + ipa_analysis(Stage2) |
| strategy-research-engine/全栈 | 已完成 | 策略模块重构为智能研究编排者：4 阶段自动化（研究设计→探测验证→数据就绪→产出生成）+ 增量采集协议 + 6 条 LLM Chain + 前端 4 阶段面板 |

## 已完成的里程碑

- v1.0: 全栈基础框架 (auth + rbac + users)
- v1.x: 社交媒体数据采集与分析功能 (projects + tasks + analysis + langchain + agent)
- v1.x: 数据任务分析 spam 维度功能完成 (4D 分布 + 维度排序 + 图表预计算 + 全栈类型一致性)
- v1.x: 项目级切片 spam 维度增强 (实体/话题 4D 分布 + SpamRatioBar 展示)
- v1.x: 任务级分析指标 QA 与修复 (舆论反差度/营销浓度阈值/NSR+KOL 情感标签归一化)
- v1.x: 全栈代码命名统一 (snapshot → slice) + 架构文档补全
- v1.x: 项目详情页批量创建任务 + 切片重命名功能
- v2.0: Strategy Define 全栈实现（3 阶段 AI 策略生成 + 数据依赖精选 + Word 导出）
- v2.1: 切片流水线数据补全（time_distribution + kol_voices + ipa_analysis，策略 Phase 2/3 数据质量提升）
- v3.0: Strategy Research Engine 全栈实现（4 阶段自动编排 + 探测验证 + 增量采集协议 + 前端 4 阶段面板）

## 待改进项

- 测试覆盖率待提升（后端 aggregation 模块无单元测试）
- 切片页前端可选展示：time_distribution / kol_voices 数据已由后端生成但前端展示优先级低（time_distribution 是采集样本分布非真实趋势、kol_voices 任务级更直观），如需展示仅考虑 kol_voices
- 策略 Chain 数据精简：Phase 2 已移除 time_distribution（样本分布误导节奏建议）、Phase 3 已移除 ipa_analysis 读取；切片级 ipa_analysis 计算已删除（维度不一致 + 与现有数据冗余），仅保留 kol_voices 作为唯一新增数据源
- 研究设计链拆分预案：当前 research_design_chain 在单次调用中完成适配度评估 + 研究计划生成，输出质量可控。当系统接入更多数据能力（公众号搜索、网络搜索、行业报告检索）后，需拆为「预检链 → 编排链」两步——预检链评估各能力的适用性并推荐组合，编排链基于推荐结果为每种能力生成具体采集方案。拆分时机：能力清单 > 3 种 或 单次输出 JSON 超过 1500 tokens

## 下次继续的入口

Strategy Research Engine v3.0 全栈交付完成。可选后续方向：
- 端到端验收测试：以真实 Brief 走完 4 阶段流程，验证爬虫增量采集 + 自动建切片 + Phase 生成全链路
- 测试覆盖补全：为 `strategies/service.py` 新增方法（design_research / check_probe_status / check_collection_status）添加 mock LLM 单元测试
- 前端交互优化：探测/采集轮询增加超时提示、研究计划编辑增加拖拽排序
