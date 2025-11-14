# 社交媒体数据洞察模块 (Social Insights)

## 功能概述

社交媒体数据洞察模块是一个完整的社交媒体数据采集、管理和分析系统，支持多平台数据采集和JSON数据上传功能。

## 已完成功能

### 后端 API (阶段1 & 2)

#### 1. 社交媒体项目管理 (`/api/v1/social-media/projects`)
- ✅ 创建项目 (POST)
- ✅ 获取项目列表 (GET) - 支持分页和搜索
- ✅ 获取项目详情 (GET `/:id`)
- ✅ 更新项目 (PUT `/:id`)
- ✅ 删除项目 (DELETE `/:id`)
- ✅ 管理项目参与者 (POST/DELETE `/participants`)
- ✅ 平台数据初始化（Bilibili、Douyin、Weibo等10个平台）

#### 2. 数据采集任务管理 (`/api/v1/tasks`)
- ✅ 创建任务 (POST)
- ✅ 获取任务列表 (GET) - 支持多维度过滤
  - 按项目、平台、状态、数据源、创建者过滤
  - 关键词搜索
- ✅ 获取任务详情 (GET `/:id`)
- ✅ 更新任务 (PUT `/:id`)
- ✅ 删除任务 (DELETE `/:id`)

#### 3. JSON数据上传 (`/api/v1/tasks/:id/upload`)
- ✅ 上传JSON格式的帖子和评论数据
- ✅ 自动数据验证和关联
- ✅ 事务性数据导入（失败自动回滚）
- ✅ 任务状态自动更新

#### 4. 数据查询 API
- ✅ 获取任务的原文列表 (GET `/tasks/:id/posts`)
- ✅ 获取原文及其评论 (GET `/tasks/posts/:id`)
- ✅ 跨任务查询同一帖子 (GET `/tasks/posts/cross-task/:platform_id/:post_id_on_platform`)
  - 用于追踪同一帖子在不同时间点的数据变化

### 前端界面 (阶段3)

#### 1. 项目管理界面
- ✅ 项目列表页 (`/social-insights/projects`)
  - 搜索和分页
  - 显示平台标签
  - 快速操作（查看、删除）
- ✅ 创建项目页 (`/social-insights/projects/create`)
  - 表单验证
  - 多平台选择
  - 时间范围设置
- ✅ 项目详情页 (`/social-insights/projects/:id`)
  - 项目信息展示
  - 任务列表（卡片式）
  - 快速创建任务

#### 2. 任务管理界面
- ✅ 任务列表页 (`/social-insights/tasks`)
  - 多维度过滤（项目、平台、状态、数据源）
  - 搜索功能
  - 表格展示（状态标签、数据统计）
  - 快速上传入口
- ✅ 创建任务页 (`/social-insights/tasks/create`)
  - 任务类型选择（search/detail/creator/homefeed）
  - 数据源选择（本地上传/远程爬虫）
  - 自动跳转到上传页面
- ✅ 任务详情页 (`/social-insights/tasks/:id`)
  - 任务信息展示
  - 原文列表（卡片式）
  - 数据统计

#### 3. JSON数据上传界面
- ✅ JSON上传页 (`/social-insights/tasks/:id/upload`)
  - 文件上传
  - 在线编辑
  - 实时验证
  - 示例数据加载
  - 数据格式说明

#### 4. 导航集成
- ✅ 主导航菜单集成
  - "社交媒体项目" 菜单项
  - "数据采集任务" 菜单项
- ✅ 响应式设计（桌面端+移动端）

## 数据库设计

### 核心表结构

1. **platforms** - 社交媒体平台
   - 10个预置平台（Bilibili、Douyin、Weibo等）

2. **social_projects** - 社交媒体项目
   - 项目基本信息
   - 多对多关联平台
   - 参与者管理

3. **social_data_tasks** - 数据采集任务
   - 任务配置（类型、关键词、参数）
   - 数据源（本地上传/远程爬虫）
   - 状态管理（pending/running/completed/failed）
   - 数据统计（原文数、评论数）

4. **social_posts** - 社交媒体原文
   - 帖子内容和元数据
   - 互动数据（赞、评论、分享、浏览量）
   - 媒体资源（图片、视频）
   - 原始JSON数据

5. **social_comments** - 评论数据
   - 评论内容和元数据
   - 楼中楼支持（parent_comment_id）
   - 互动数据
   - 原始JSON数据

### 关键特性

- ✅ 软删除支持（is_deleted字段）
- ✅ 时间戳自动管理
- ✅ 复合索引优化（跨任务查询）
- ✅ 级联删除配置
- ✅ JSON字段支持（task_params、raw_data等）

## 技术栈

### 后端
- FastAPI - 异步Web框架
- SQLAlchemy 2.0 - ORM（异步模式）
- Pydantic v2 - 数据验证
- Alembic - 数据库迁移
- PostgreSQL - 数据库

### 前端
- Nuxt 3 - SSR框架
- Vue 3 - Composition API
- TypeScript - 类型安全
- Nuxt UI - UI组件库
- Zod - 表单验证

## 使用指南

### 1. 创建项目

```bash
# 访问项目创建页面
http://localhost:3001/social-insights/projects/create

# 填写信息
- 项目名称（必填）
- 项目描述
- 关键词
- 目标平台（至少选择一个）
- 项目时间范围（可选）
```

### 2. 创建任务

```bash
# 访问任务创建页面
http://localhost:3001/social-insights/tasks/create

# 填写信息
- 任务名称（必填）
- 所属项目（必填）
- 目标平台（必填）
- 任务类型（search/detail/creator/homefeed）
- 数据源（local_upload/remote_crawler）
```

### 3. 上传JSON数据

```json
{
  "contents": [
    {
      "post_id_on_platform": "BV1234567890",
      "title": "测试视频标题",
      "content": "视频描述内容",
      "author_name": "UP主名称",
      "likes_count": 1000,
      "comments_count": 50,
      "shares_count": 20,
      "views_count": 5000,
      "published_at": "2025-11-10T10:00:00Z"
    }
  ],
  "comments": [
    {
      "comment_id_on_platform": "comment_001",
      "content": "评论内容",
      "author_name": "评论者",
      "likes_count": 10,
      "raw_data": {
        "post_id_on_platform": "BV1234567890"
      }
    }
  ]
}
```

### 4. API测试示例

```bash
# 获取Token
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=testuser&password=testpass123"

# 创建项目
curl -X POST http://localhost:8000/api/v1/social-media/projects \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试项目",
    "platform_ids": [1, 2],
    "keywords": "测试关键词"
  }'

# 创建任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试任务",
    "project_id": 1,
    "platform_id": 1,
    "task_type": "search",
    "data_source": "local_upload"
  }'

# 上传数据
curl -X POST http://localhost:8000/api/v1/tasks/1/upload \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @test_data.json
```

## 后续计划

### 阶段4: AI分析功能（待开发）
- 舆情分析
- 情感分析
- 热点话题挖掘
- Langchain集成
- Celery异步任务队列

### 阶段5: 优化与完善（待开发）
- RBAC权限集成
- 性能优化
- 数据可视化
- 导出功能
- WebSocket爬虫通信

## 目录结构

```
social-insights-hub/
├── backend/
│   ├── src/
│   │   ├── social_media/      # 项目管理模块
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── crud.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   └── task_manager/      # 任务管理模块
│   │       ├── models.py
│   │       ├── schemas.py
│   │       ├── crud.py
│   │       ├── service.py
│   │       ├── dependencies.py
│   │       └── router.py
│   └── alembic/versions/
│       ├── *_add_social_media_tables.py
│       └── *_add_task_manager_tables.py
│
└── frontend/
    ├── layers/
    │   └── social-insights/   # 社交洞察Layer
    │       ├── types/         # TypeScript类型
    │       ├── composables/   # API封装
    │       │   ├── useSocialProjects.ts
    │       │   ├── useTasks.ts
    │       │   ├── usePosts.ts
    │       │   ├── useJSONUpload.ts
    │       │   └── usePlatforms.ts
    │       └── pages/
    │           └── social-insights/
    │               ├── projects/
    │               │   ├── index.vue      # 项目列表
    │               │   ├── create.vue     # 创建项目
    │               │   └── [id].vue       # 项目详情
    │               └── tasks/
    │                   ├── index.vue      # 任务列表
    │                   ├── create.vue     # 创建任务
    │                   └── [id]/
    │                       ├── index.vue  # 任务详情
    │                       └── upload.vue # 上传数据
    └── config/
        └── routes.ts          # 导航配置
```

## 测试结果

### 后端测试（阶段2.3完成）
- ✅ JSON上传功能正常
- ✅ 导入2个帖子 + 3条评论
- ✅ 任务状态自动更新（pending → running → completed）
- ✅ 跨任务查询功能正常
- ✅ 数据统计准确

### 前端测试
- ✅ 页面路由正常
- ✅ 导航菜单显示正常
- ✅ 组件渲染正常
- ✅ API调用成功

## 注意事项

1. **数据源选择**：目前仅支持"本地上传"，WebSocket爬虫功能标记为待开发
2. **权限控制**：当前所有路由设置为`permission: null`，后续可集成RBAC权限
3. **性能优化**：大量数据时建议分批上传
4. **数据验证**：上传前务必验证JSON格式，必填字段：
   - contents: `post_id_on_platform`
   - comments: `comment_id_on_platform` 和 `raw_data.post_id_on_platform`

## 开发者

- 后端开发：阶段1-2完成
- 前端开发：阶段3完成
- 生成工具：Claude Code (Sonnet 4.5)
