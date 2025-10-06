# 爬虫任务模块实现总结

## 📋 已完成功能

### ✅ 后端实现

#### 1. 权限定义 ([backend/src/rbac/init_data.py:182-200](backend/src/rbac/init_data.py))
```python
*create_module_permissions(
    "crawler_tasks",
    ["access", "read", "write", "delete", "execute"],
    display_names={...},
    descriptions={...}
)
```

#### 2. 数据模型 ([backend/src/tasks/models.py](backend/src/tasks/models.py))
- **CrawlerTask**: 爬虫任务主表
  - 支持7个平台: 小红书、微博、抖音、快手、B站、贴吧、知乎
  - 4种爬取模式: search、detail、creator、homefeed
  - 6种状态: pending、running、paused、completed、failed、cancelled
  - JSON配置: 关键词、URL、数量、评论、代理等（XHS 最小链路读取 `keywords`、`max_count`）
  - 断点续爬支持: checkpoint_id, checkpoint_data

- **TaskLog**: 任务日志表
  - 记录任务执行的详细日志
  - 支持级别: INFO/WARNING/ERROR

#### 3. API路由 ([backend/src/tasks/router.py](backend/src/tasks/router.py))
**任务管理**:
- `POST /api/v1/crawler-tasks/` - 创建任务
- `GET /api/v1/crawler-tasks/` - 任务列表(分页+筛选)
- `GET /api/v1/crawler-tasks/{id}` - 任务详情
- `PATCH /api/v1/crawler-tasks/{id}` - 更新任务
- `DELETE /api/v1/crawler-tasks/{id}` - 删除任务

**任务控制**:
- `POST /api/v1/crawler-tasks/{id}/start` - 启动任务
- `POST /api/v1/crawler-tasks/{id}/pause` - 暂停任务
- `POST /api/v1/crawler-tasks/{id}/stop` - 停止任务

**日志和统计**:
- `GET /api/v1/crawler-tasks/{id}/logs` - 获取任务日志
- `GET /api/v1/crawler-tasks/statistics/summary` - 获取统计数据

#### 4. 业务逻辑 ([backend/src/tasks/service.py](backend/src/tasks/service.py))
- 任务CRUD操作
- 任务状态管理(启动/暂停/停止)
- 进度更新机制
- 日志记录功能
- 统计数据查询

#### 5. 资源管理模块 ([backend/src/resources](backend/src/resources))
- 新增账号/代理资源模型 (`models.py`)，支持锁定/释放、失败计数
- 提供创建、查询、状态切换接口 (`router.py`)，与 RBAC 权限联动
- 服务层实现资源分配/释放 (`service.py`)，与任务执行上下文集成

#### 6. 签名策略基础结构 ([backend/src/signing](backend/src/signing))
- 定义统一的签名策略抽象与工厂 (`base.py`, `factory.py`)
- 提供 JavaScript / Playwright 策略占位实现，支持健康检查
- `client.generate_signature` 统一封装调用；默认 JavaScript 策略返回稳定签名，供 XHS 适配器接入
- 暴露 `/api/v1/signing/health` 健康检查接口

---

### ✅ 前端实现

#### 1. 类型定义 ([frontend/layers/crawler-tasks/types/index.ts](frontend/layers/crawler-tasks/types/index.ts))
- 枚举: TaskStatus, PlatformType, CrawlerType
- 接口: CrawlerTask, TaskConfig, TaskLog, TaskStatistics
- 显示映射: 中文标签、状态颜色

#### 2. API封装 ([frontend/layers/crawler-tasks/composables/useCrawlerTasksApi.ts](frontend/layers/crawler-tasks/composables/useCrawlerTasksApi.ts))
- `getTasks()` - 获取任务列表
- `getTaskDetail()` - 获取任务详情
- `createTask()` - 创建任务
- `updateTask()` - 更新任务
- `deleteTask()` - 删除任务
- `startTask()` / `pauseTask()` / `stopTask()` - 任务控制
- `getTaskLogs()` - 获取日志
- `getStatistics()` - 获取统计

#### 3. 页面组件 ([frontend/layers/crawler-tasks/pages/crawler-tasks/index.vue](frontend/layers/crawler-tasks/pages/crawler-tasks/index.vue))
- 任务列表展示
- 统计卡片展示
- 平台和状态筛选
- 分页支持
- 创建任务对话框

#### 4. UI组件
- **StatCard.vue**: 统计卡片
- **TaskCard.vue**: 任务卡片
  - 显示任务信息、进度、状态
  - 启动/暂停/停止按钮
  - 错误信息展示
- **CreateTaskDialog.vue**: 创建任务对话框
  - 表单验证
  - 根据爬取模式动态显示字段

#### 5. 权限配置
- [frontend/config/permissions.ts](frontend/config/permissions.ts): 定义权限常量
- [frontend/config/routes.ts](frontend/config/routes.ts): 配置路由权限
- [frontend/nuxt.config.ts](frontend/nuxt.config.ts): 注册 Layer

---

## 🗄️ 数据库结构

### crawler_tasks 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| name | VARCHAR(255) | 任务名称 |
| platform | ENUM | 平台类型 |
| crawler_type | ENUM | 爬取模式 |
| status | ENUM | 任务状态 |
| config | JSON | 爬取配置 |
| progress | INT | 进度(0-100) |
| crawled_count | INT | 已爬取数量 |
| error_message | TEXT | 错误信息 |
| checkpoint_id | VARCHAR(255) | 检查点ID |
| checkpoint_data | JSON | 检查点数据 |
| created_by | INT | 创建人 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### crawler_task_logs 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| task_id | INT | 任务ID(外键) |
| level | VARCHAR(20) | 日志级别 |
| message | TEXT | 日志内容 |
| detail | JSON | 详细信息 |
| created_at | DATETIME | 记录时间 |

---

## 🚀 下一步工作

## 🔄 重构整合规划

### 模块分层目标
1. **任务编排层**：后端模块统一更名为 `tasks`，在该包内新增 `orchestrator` 子组件负责任务入队、配置校验与执行策略选择，保持 API 与编排逻辑同域。
2. **执行管线层**：在 `backend/src/execution` 构建 Celery/Async worker，处理调度、重试、暂停/恢复与超时控制，确保与 orchestrator 解耦。
3. **平台适配层**：将 MediaCrawlerPro-Python 的各平台实现迁移至 `backend/src/platforms`（如 `platforms/xhs`, `platforms/douyin`），通过“平台注册表”暴露统一 `CrawlerAdapter` 接口，后续新增平台仅需注册。
4. **签名策略层**：重构为 `backend/src/signing`，提供策略工厂支持 Playwright、本地 JS、远程 HTTP 等实现，可按平台/任务选择并内置熔断重试。
5. **资源管理层**：在 `backend/src/resources` 中统一管理账号、代理等资源，全部改为数据库驱动的 CRUD/状态管理，移除 Excel 依赖。
6. **数据存储层**：`backend/src/repositories` 负责结果写入、去重与导出接口，复用现有 SQLAlchemy 会话，预留扩展钩子以支持后续数据处理流水线。
7. **可观测性层**：提供基础日志、指标与告警集成（如 Prometheus exporter、Webhook），覆盖任务执行率、签名成功率、资源可用率等核心指标。
8. **前端支持**：在 `frontend/layers` 拆分 `crawler-executions`（执行监控）、`crawler-resources`（账号/代理管理）、`crawler-metrics`（可视化指标），与现有任务创建界面协同。

### 交互流程 (Target Flow)
1. 用户在前端创建任务 → `tasks` API 写入主表，由 orchestrator 校验配置并入队。
2. 执行层消费任务 → 通过平台注册表获取对应 `CrawlerAdapter`，同时向签名策略层和资源管理层申请所需能力（账号、代理、签名）。
3. 执行层实时上报进度/日志 → 调用 `update_task_progress`、`add_task_log`，并通过 `repositories` 写入采集结果。
4. 任务完成或失败 → 执行层调用 `mark_task_completed`，记录最终状态并触发必要的告警或重试策略。
5. 前端在 `crawler-executions` Layer 轮询或订阅 WebSocket，获取进度、日志、统计，`crawler-resources` 负责资源维护。

### 后端重构任务
- [ ] 在 `backend/src/execution` 落地 Celery/Redis 基础设施，并接入 `start_task`/`pause`/`stop` 钩子。
- [ ] 迁移 MediaCrawlerPro 平台代码至 `platforms/{platform}`，实现 `CrawlerAdapter` 接口并注册到平台表。
- [ ] 构建数据库驱动的账号/代理管理（`resources`），提供 API、健康检查与使用统计，完全移除 Excel 配置。
- [ ] 实现签名策略工厂，封装 Playwright、本地 JS、远程 HTTP，加入熔断和缓存机制。
- [ ] 在 `repositories` 中实现结果写入与基础去重，补充必要的数据表和 Alembic 迁移。
- [ ] 整理配置项至 `.env` 与 `docs/CONFIGURATION.md`，涵盖签名、代理、执行并发、告警阈值等。

### 前端重构任务
- [ ] 新增执行监控页面：展示进度、实时日志、执行耗时，支持 WebSocket 或轮询刷新。
- [ ] 新增资源管理页面：账号、代理的列表、状态标记与操作入口。
- [ ] 平台配置管理：按平台展示必填参数模板，支持克隆/验证，与 orchestrator 校验接口联动。
- [ ] 统计与告警视图：任务成功率、失败原因、签名命中率等指标展示。
- [ ] 在 `frontend/config/routes.ts`、`permissions.ts` 中注册新页面与权限常量。

### 迁移步骤与里程碑
1. **阶段一：基础设施准备**
   - 引入 Celery/Redis 与 Playwright 依赖，更新 `.env.example`、Docker 配置。
   - 完成签名策略工厂骨架，确保本地 JS/Playwright 可运行并提供健康检查。
2. **阶段二：执行链路打通**
   - 在 `tasks` 模块内完成与执行层的衔接，跑通“创建任务 → Worker 执行 → 进度回写”。
   - 优先迁移小红书平台，验证账号、代理、签名协作链路。
3. **阶段三：资源与监控完善**
   - 提供账号/代理管理 API + 前端页面，接入资源状态统计。
   - 补齐基础指标与告警（任务成功率、签名成功率、资源可用率）。
4. **阶段四：扩平台与清理**
   - 按注册表模式迁移剩余平台，实现配置模板。
   - 移除 `MediaCrawlerPro-Python` 与 `MediaCrawlerPro-SignSrv` 目录，完成文档与脚本更新。

### 开发计划
1. **基础设施落地**
   - 安装并配置 Celery/Redis，与现有 `pnpm` 脚本、Docker Compose 对齐，更新 `.env.example`、`docs/CONFIGURATION.md`。
   - 调整 `backend/src/main.py`、`backend/celery_app.py` 等入口，确保 Worker 启动方式与其他模块一致。
   - 构建签名策略工厂骨架（Playwright + 本地 JS），提供健康检查端点，并在 `scripts/` 中补充通用启动、重启脚本。
   - 前端配置层面同步扩展 `nuxt.config.ts`、`frontend/config/routes.ts`、`permissions.ts`，预留执行监控与资源管理路由。

2. **任务执行闭环**
   - 将后端目录 `backend/src/crawler_tasks` 重命名为 `backend/src/tasks`，同步更新引入路径、FastAPI 路由与测试引用。
   - 在 `backend/src/tasks/orchestrator/` 内实现任务调度、配置校验、入队逻辑，遵循现有 services/repositories 分层惯例。
   - 调整 `tasks/service.py` 以调用 orchestrator 的调度接口，保证 API 层与执行层解耦。
   - 迁移小红书平台到 `backend/src/platforms/xhs/`，实现统一的 `CrawlerAdapter` 接口，遵循应用内依赖注入规范。
   - 补充端到端测试：创建任务→触发 Worker→更新进度→写入结果，纳入 CI。

3. **资源与监控上线**
   - 在 `backend/src/resources` 实现账号池、代理池的数据库模型、CRUD API、健康检查，与 RBAC 权限保持一致；同步生成 Alembic 迁移。
   - 前端新增 `crawler-resources` Layer，复用现有组件体系，实现账号/代理管理视图，遵循 UI 设计规范。
   - 构建核心指标（任务成功率、签名成功率、资源可用率、Worker 延迟等）并输出 Prometheus 指标端点；提供告警配置（Webhook/Email 模板）。

4. **平台扩展与收尾**
   - 按平台注册表模式迁移剩余平台模块，输出平台模板配置界面，并编写平台接入指引。
   - 清理 `MediaCrawlerPro-Python`、`MediaCrawlerPro-SignSrv` 目录，迁移必要脚本/文档至主项目，更新 README/部署指南。
   - 完成全量回归（后端单测、前端单测、端到端、性能压测），并记录变更日志、升级指南，确保与其它模块的开发规范一致。

### 验收标准
- 所有代码需通过 `pnpm be:lint`, `pnpm be:test`, `pnpm fe:typecheck`, `pnpm fe:lint`。
- 至少一条端到端用例（创建任务→执行→结果落库→状态完成）稳定通过。
- 签名、资源、执行模块提供健康检查并接入指标上报。
- 文档和配置同步更新，确认旧任务数据在迁移后仍可访问或已提供迁移脚本。

- **签名服务依赖 Playwright 环境** → 优先完成容器化与无头配置，同时保证本地 JS/远程 HTTP 策略可回退。
- **账号与代理敏感信息** → 统一加密存储与脱敏展示，引入资源使用审计。
- **执行压力波动** → 通过执行层并发配置、速率限制与幂等校验控制峰值；必要时引入优先级队列。
- **历史任务兼容** → 在迁移阶段提供数据导入脚本，确保旧任务能映射到新平台注册表。

### 1. 数据库迁移
```bash
# 启动数据库后执行
cd backend
uv run alembic upgrade head
```

### 2. 启动服务验证
```bash
# 启动后端
pnpm be:dev

# 启动前端
pnpm fe:dev
```

### 3. 功能测试
1. 登录系统 (admin/admin123)
2. 访问 `/crawler-tasks` 页面
3. 创建一个测试任务
4. 测试任务启动/暂停/停止功能

### 4. 后续开发任务
- [ ] 集成 MediaCrawlerPro 爬虫核心
- [ ] 实现后台任务队列 (Celery/AsyncIO)
- [ ] WebSocket 实时推送任务进度
- [ ] 任务详情页面 (查看日志、配置等)
- [ ] 平台配置管理模块
- [ ] 账号池管理模块
- [ ] 代理IP管理模块

---

## 📂 项目文件清单

### 后端文件
```
backend/src/tasks/
├── __init__.py
├── models.py          # 数据模型
├── schemas.py         # Pydantic模型
├── service.py         # 业务逻辑
├── router.py          # API路由
└── orchestrator/      # 任务编排子模块 (dispatch、validator、runner等)

backend/src/platforms/
├── __init__.py
├── base.py            # 适配器抽象与执行上下文
├── registry.py        # 平台注册表
└── xhs/adapter.py     # 小红书平台适配器（占位实现）

backend/src/signing/
├── __init__.py
├── base.py            # 策略抽象
├── factory.py         # 策略工厂
├── router.py          # 健康检查路由
├── schemas.py         # 请求/响应模型
└── strategies/        # 具体策略实现 (javascript, playwright)

backend/src/results/
├── __init__.py
├── models.py          # 结果模型 (crawler_note_results)
├── schemas.py         # 响应模型
└── service.py         # 批量写入与查询接口
```

### 前端文件
```
frontend/layers/crawler-tasks/
├── nuxt.config.ts
├── types/index.ts                        # 类型定义
├── composables/useCrawlerTasksApi.ts     # API封装
├── pages/crawler-tasks/index.vue         # 任务列表页面
└── components/
    ├── StatCard.vue                      # 统计卡片
    ├── TaskCard.vue                      # 任务卡片
    └── CreateTaskDialog.vue              # 创建对话框

frontend/layers/crawler-executions/
└── pages/crawler-executions/index.vue    # 执行监控占位

frontend/layers/crawler-resources/
└── pages/crawler-resources/index.vue     # 资源管理占位

frontend/layers/crawler-metrics/
└── pages/crawler-metrics/index.vue       # 指标监控占位
```

### 配置文件
```
backend/src/rbac/init_data.py              # 权限定义
backend/src/main.py                        # 路由注册
frontend/config/permissions.ts             # 前端权限
frontend/config/routes.ts                  # 路由配置
frontend/nuxt.config.ts                    # Layer注册
backend/alembic/versions/2025_09_30_*.py   # 数据库迁移
```

---

## 🎯 架构亮点

1. **完整的RBAC权限控制**: 5个独立权限(access/read/write/delete/execute)
2. **前后端类型安全**: TypeScript类型与Python模型对应
3. **模块化设计**: Layer架构,独立开发部署
4. **灵活的配置系统**: JSON配置支持多种爬取场景
5. **断点续爬支持**: checkpoint机制
6. **详细的日志记录**: 独立日志表
7. **实时状态更新**: 准备好WebSocket集成

---

## 📝 开发经验总结

1. **权限优先**: 先定义权限,后端自动同步
2. **数据模型完整性**: 考虑状态流转、错误处理、日志记录
3. **前端组件复用**: StatCard、TaskCard可在其他模块复用
4. **API设计规范**: RESTful + 语义化路径
5. **配置集中管理**: permissions.ts + routes.ts 统一配置

---

**模块创建时间**: 2025-09-30
**预计开发耗时**: 约1小时
**代码行数**: ~2000行 (后端800行 + 前端1200行)
