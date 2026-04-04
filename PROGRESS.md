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
| 部署配置 | 已完成 | Docker Compose 开发/生产双配置；celery-beat 容器已删除，定时任务迁移至 APScheduler（在 FastAPI asyncio 事件循环中运行） |
| strategies/后端 | 已完成 | 策略定义模块：3 阶段 AI 生成（洞察→策略→创意），Phase 1/2/3 Chain + CRUD API + Word 导出 |
| strategies/前端 | 已完成 | 策略列表/创建/详情页，3 阶段结果展示与编辑，跨项目切片选择器 |
| analysis/slice_enrichment/后端 | 已完成 | 切片流水线数据补全：time_distribution(Stage1) + kol_voices(Stage1) + ipa_analysis(Stage2) |
| strategy-research-engine/全栈 | 已完成 | 策略模块重构为智能研究编排者：4 阶段自动化（研究设计→探测验证→数据就绪→产出生成）+ 增量采集协议 + 6 条 LLM Chain + 前端 4 阶段面板 |
| knowledge_base/全栈 | 已完成 | 市场知识库：文档上传/解析/向量化/RAG 检索；策略 Phase1/2 注入 market_context；渠道架构同步（合并 industry_data、删除 ecommerce）；postgres 迁移至 pgvector/pgvector:pg16 |
| knowledge_base/crawlers/全栈 | 已完成 | Crawl4AI + APScheduler 定时爬取 CNNIC/NBS/gov.cn；admin GET /crawlers/status + POST /crawlers/{source_type}/run；Embedding API 迁移至 SiliconFlow |
| knowledge_base/前端 | 已完成 | 文档列表/上传/删除、RAG 检索测试、爬虫状态管理 |
| news_media/后端 | 已完成 | 监测项目/任务 CRUD，SerpAPI+Crawl4AI 采集，news_tagging_chain+news_insight_chain 两条 LLM 链，策略流水线集成（probe/collect 两阶段） |
| news_media/前端 | 已完成 | 监测项目列表/创建/详情页，任务列表（全局+按项目）/详情页，文章列表（含相关性/来源等级筛选），分析报告展示（coverage/sentiment/narratives/entities/competitive_landscape/key_quotes） |

## 下次继续的入口
新闻监测(news_media)前端模块已完成。根据项目当前状态，下一步建议：
- 验收：运行完整的测试，确保所有功能正常工作
- 测试：补充 news_media 后端集成测试
- 文档：更新根 CLAUDE.md 模块列表（添加 news_media）
- 部署：准备生产环境部署配置检查

