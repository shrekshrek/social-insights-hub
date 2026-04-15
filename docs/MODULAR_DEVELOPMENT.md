# 模块化开发指南

本指南介绍如何在项目中开发新的业务模块，从权限定义到前后端实现的完整流程。

## 🔄 开发阶段

一个功能从构思到上线的标准流程：

| 阶段 | 工作 |
|------|------|
| **0. 设计** | 数据库表设计、API 端点规划、权限规划 |
| **1. 后端** | models → schemas → service → router → 注册路由 → 迁移 → Swagger 测试 |
| **2. 前端** | composables 封装 API → 页面/组件开发 → 注册 Layer 和路由权限 |
| **3. 联调** | 端到端测试完整流程 → `pnpm fe:typecheck && pnpm be:lint` |

后端先行：先交付稳定 API，再开发前端，减少等待和返工。

---

## 📋 概述

本项目采用**领域驱动设计（DDD）**，前后端模块化架构：

- **后端**：按业务领域划分模块（auth、rbac、users等）
- **前端**：使用 Nuxt Layers 实现模块化（对应后端模块）
- **权限**：代码驱动，自动同步
- **原则**：高内聚、低耦合、渐进式发展

### 架构特点

| 特性 | 说明 |
|------|------|
| **对称设计** | 前后端模块一一对应 |
| **独立开发** | 模块可独立开发、测试、部署 |
| **统一权限** | 代码定义，自动同步 |
| **渐进式** | 从简单开始，按需扩展 |

## 🚀 快速开始：30秒创建新模块

以创建 `reports` 报表模块为例，支持查看和导出功能：

```python
# 1. 后端权限定义 (backend/src/rbac/init_data.py)
*create_module_permissions("reports", ["access", "read", "write", "delete"])

# 2. 后端快捷依赖 (backend/src/rbac/dependencies.py)
require_reports_read   = create_permission_dependency("reports:read")
require_reports_write  = create_permission_dependency("reports:write")
require_reports_delete = create_permission_dependency("reports:delete")

# 3. 重启服务自动同步
# pnpm dev

# 4. 前端权限配置 (frontend/config/permissions.ts)
REPORTS_ACCESS: {target: 'reports', action: 'access'},
REPORTS_READ:   {target: 'reports', action: 'read'},
REPORTS_WRITE:  {target: 'reports', action: 'write'},
REPORTS_DELETE: {target: 'reports', action: 'delete'},

# 5. 路由权限 (frontend/config/routes.ts)
'/reports':        { permission: PERMISSIONS.REPORTS_ACCESS, label: '报表', showInNav: true, order: 60 },
'/reports/create': { permission: PERMISSIONS.REPORTS_WRITE },
'/reports/[id]':   { permission: PERMISSIONS.REPORTS_READ },
```

完成！模块基础权限已配置。

## ✅ 新模块开发清单

### 第一步：定义权限（1分钟）

**1a. 在 `backend/src/rbac/init_data.py` 注册权限：**

```python
# 基础访问权限
*create_module_permissions("module_name", ["access"])

# 数据操作权限
*create_module_permissions("module_name", ["access", "read", "write"])

# 完整CRUD权限
*create_module_permissions("module_name", ["access", "read", "write", "delete"])

# 自定义权限
*create_module_permissions("module_name", ["access", "read", "export", "approve"])
```

**常用权限组合**：
- `["access"]` - 仅页面访问
- `["access", "read"]` - 查看数据（access 控前端页面，read 控后端 API，两者并行）
- `["access", "read", "write"]` - 增改操作
- `["access", "read", "write", "delete"]` - 完整CRUD
- `["access", "read", "export"]` - 数据导出

**1b. 在 `backend/src/rbac/dependencies.py` 注册快捷依赖：**

```python
# 在文件末尾追加
require_module_name_read   = create_permission_dependency("module_name:read")
require_module_name_write  = create_permission_dependency("module_name:write")
require_module_name_delete = create_permission_dependency("module_name:delete")
```

> 快捷依赖让路由文件的 `Depends(...)` 写法更简洁，且统一在一处管理。

### 第二步：创建后端模块（10分钟）

#### 2.1 创建模块目录

```bash
backend/src/reports/
├── __init__.py
├── router.py       # API路由
├── service.py      # 业务逻辑
├── schemas.py      # Pydantic模型
├── models.py       # 数据库模型（可选）
└── dependencies.py # 依赖注入（可选）
```

#### 2.2 基础路由示例

```python
# backend/src/reports/router.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.database import get_async_db
from src.rbac.dependencies import (
    require_reports_read,
    require_reports_write,
    require_reports_delete,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get(
    "",
    response_model=ReportListResponse,
    status_code=200,
    summary="获取报表列表",
)
async def list_reports(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_reports_read),  # 用 current_user 当需要 .id；否则用 _
):
    return await service.get_reports(db, current_user.id)

@router.post(
    "",
    response_model=ReportResponse,
    status_code=201,
    summary="创建报表",
)
async def create_report(
    data: ReportCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_reports_write),
):
    return await service.create_report(db, data, current_user.id)

@router.delete(
    "/{report_id}",
    status_code=200,
    summary="删除报表",
)
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_reports_delete),  # 不需要 .id 时用 _
):
    return await service.delete_report(db, report_id)
```

> **命名约定**：端点参数需要 `current_user.id` 时用 `current_user: User = Depends(...)`；仅做权限门控不需要用户信息时用 `_: User = Depends(...)`。

#### 2.3 注册路由

```python
# backend/src/main.py
from src.reports import router as reports_router

app.include_router(reports_router.router, prefix=settings.API_PREFIX)
```

### 第三步：创建前端 Layer（10分钟）

#### 3.1 创建 Layer 结构

```bash
frontend/layers/reports/
├── components/        # 组件
│   └── ReportList.vue
├── pages/            # 页面
│   └── reports/
│       ├── index.vue
│       └── export.vue
├── composables/      # API封装
│   └── useReportsApi.ts
├── types/           # 类型定义
│   └── index.ts
└── nuxt.config.ts   # Layer配置
```

#### 3.2 API 封装示例

```typescript
// frontend/layers/reports/composables/useReportsApi.ts
export const useReportsApi = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  const getReports = (params?: Record<string, unknown>) => {
    return useApiData('/reports/', {
      query: params,
      key: computed(() => `reports-${params?.page || 1}`)
    })
  }

  const exportReports = async () => {
    const data = await apiRequest('/reports/export')
    showSuccess('报表导出成功')
    return data
  }

  return { getReports, exportReports }
}
```

#### 3.3 注册 Layer

**重要**：必须在 `frontend/nuxt.config.ts` 的 `extends` 数组中注册新的 layer，否则模块不会被加载：

```typescript
// frontend/nuxt.config.ts
export default defineNuxtConfig({
  extends: [
    './layers/ui-kit',
    './layers/auth',
    './layers/reports',  // 添加新 Layer
  ]
})
```

### 第四步：配置路由权限（2分钟）

```typescript
// frontend/config/permissions.ts
export const PERMISSIONS = {
  // ... 现有权限
  
  // 报表模块权限
  REPORTS_ACCESS: {target: 'reports', action: 'access'},
  REPORTS_READ: {target: 'reports', action: 'read'},
  REPORTS_EXPORT: {target: 'reports', action: 'export'},
}

// frontend/config/routes.ts
export const ROUTE_CONFIG = {
  // ... 现有路由

  // 报表模块路由
  '/reports': {
    permission: PERMISSIONS.REPORTS_ACCESS,
    label: '报表中心',
    showInNav: true,
    order: 60,
  },
  '/reports/export': { permission: PERMISSIONS.REPORTS_EXPORT },
}
```

### 第五步：组件级权限控制（按需）

路由守卫只控制页面能否进入。页面内的编辑/删除按钮需要额外的组件级权限控制。

#### 编辑/删除按钮模式

```vue
<script setup lang="ts">
import { PERMISSIONS } from '~/config/permissions'
const { currentUserId, hasPermission } = usePermissions()

// 有 participants 概念的模块：owner 或有写权限者可编辑
const canEdit = computed(() =>
  hasPermission(PERMISSIONS.REPORTS_WRITE) || item.value?.user_id === currentUserId.value
)

// 删除同理
const canDelete = computed(() =>
  hasPermission(PERMISSIONS.REPORTS_DELETE) || item.value?.user_id === currentUserId.value
)
</script>

<template>
  <UButton v-if="canEdit" @click="openEditModal">编辑</UButton>
  <UButton v-if="canDelete" color="error" @click="handleDelete">删除</UButton>
</template>
```

> `hasPermission()` 对 super_admin 和 admin 自动返回 `true`，无需额外处理。
>
> 所有者字段全栈统一为 `user_id`，详见 [权限系统深度指南](./PERMISSION_MANAGEMENT.md#所有者字段命名规范)。

### 第六步：测试集成（5分钟）

1. **重启服务**：`pnpm dev`（自动同步新权限到数据库）
2. **检查权限同步**：查看后端日志确认权限已创建
3. **访问页面**：登录后访问 `/reports`
4. **测试权限**：分配角色权限，验证访问控制
5. **类型检查**：`pnpm fe:typecheck && pnpm be:lint`

## 📁 模块结构模板

### 后端模块标准结构

```python
backend/src/[module_name]/
├── __init__.py           # 模块初始化
├── router.py            # API路由定义
├── service.py           # 业务逻辑层
├── schemas.py           # Pydantic模型
├── models.py            # SQLAlchemy模型（可选）
├── dependencies.py      # 依赖注入（可选）
├── tasks.py             # 后台任务（可选，见下方说明）
├── exceptions.py        # 模块异常（可选）
├── utils.py            # 工具函数（可选）
└── constants.py        # 常量定义（可选）
```

**文件职责**：
- `router.py` - 只处理HTTP请求/响应
- `service.py` - 包含所有业务逻辑
- `schemas.py` - 数据验证和序列化
- `models.py` - 数据库表定义
- `tasks.py` - 后台任务（需要时创建，遵循三层架构规范）

### 后台任务选型（tasks.py 开发规范）

模块需要后台任务时，根据场景选择正确的机制（**三选一，不可混用**）：

| 场景 | 机制 | 代码位置 |
|------|------|---------|
| AI 分析、文档处理等长时/重试任务 | Celery task（`@celery_app.task`） | 模块 `tasks.py` → 在 `celery_app.py` `include` 列表注册 |
| 定时/周期性轻量检测任务 | APScheduler（`async def`，无装饰器） | 模块 `tasks.py` → 在 `src/scheduler.py` 统一注册 |
| API 端点触发的一次性 fire-and-forget | FastAPI `BackgroundTasks` | 模块 `tasks.py` 定义 `async def` → `router.py` 中 `background_tasks.add_task(fn, ...)` |

**决策口诀**：需要计划表→APScheduler；端点触发无需跟踪→BackgroundTasks；其余→Celery。

详细规范与代码示例见 [`backend/CODING_GUIDE.md`](../backend/CODING_GUIDE.md) §4 "异步任务系统（三层架构）"。

### 前端 Layer 标准结构

```typescript
frontend/layers/[module_name]/
├── components/          # 模块组件
│   ├── [Module]List.vue
│   ├── [Module]Form.vue
│   └── [Module]Detail.vue
├── pages/              # 页面文件
│   └── [module]/
│       ├── index.vue
│       ├── create.vue
│       └── [id]/
│           ├── index.vue
│           └── edit.vue
├── composables/        # 组合式函数
│   └── use[Module]Api.ts
├── stores/            # 状态管理（可选）
│   └── [module].ts
├── types/             # 类型定义
│   └── index.ts
├── utils/             # 工具函数（可选）
└── nuxt.config.ts     # Layer配置
```

## 🔗 模块间通信规范

### 跨模块调用原则

1. **后端**：通过 service 层调用，避免直接访问其他模块的数据库
2. **前端**：优先使用全局 composables，避免直接引用其他 Layer 的组件

### 实际示例

```python
# 后端：在 reports 模块中获取用户信息
from src.users import service as users_service

async def get_report_with_user(report_id: int, db: AsyncSession):
    report = await get_report(db, report_id)
    user = await users_service.get_user_by_id(db, report.user_id)
    return {"report": report, "user": user}
```

```typescript
// 前端：使用全局 API
const { getUser } = useUsersApi()
const user = await getUser(userId)
```


## 💡 最佳实践

### 何时创建新模块？

创建新模块的标准：
- ✅ 有明确的业务边界
- ✅ 包含3个以上相关页面
- ✅ 需要独立的权限控制
- ✅ 可能被其他项目复用

### 模块拆分原则

| 原则 | 说明 | 示例 |
|------|------|------|
| **单一职责** | 一个模块只负责一个业务领域 | users只管用户，不管订单 |
| **高内聚** | 相关功能放在一起 | 报表的查看、导出、生成都在reports模块 |
| **低耦合** | 模块间依赖最小化 | 通过API而非直接调用 |
| **渐进式** | 从简单开始，按需扩展 | 先实现基础CRUD，再加高级功能 |

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **模块名** | 小写复数 | users, reports, orders |
| **API路径** | RESTful风格 | GET /reports, POST /reports |
| **权限名** | 模块_动作 | reports_read, reports_export |
| **组件名** | Pascal命名 | ReportList, ReportDetail |
| **文件名** | kebab-case | report-list.vue, use-reports-api.ts |


## ❓ 常见问题

### Q: 模块间如何共享代码？

**A:** 三种方式：
1. **全局工具** - 放在 `src/utils` 或 `composables/`
2. **基类继承** - 创建基础类供继承
3. **服务调用** - 通过 service 层相互调用

### Q: 权限没有生效？

**A:** 检查步骤：
1. 重启服务确保权限同步
2. 检查用户角色是否分配了权限
3. 清除浏览器缓存重新登录
4. 查看后端日志确认权限创建

### Q: 前端页面404？

**A:** 确认：
1. Layer 已在 `nuxt.config.ts` 中注册
2. 页面文件在正确的 `pages/` 目录下
3. 路由权限已配置
4. 重启前端服务

### Q: 如何处理复杂的模块依赖？

**A:** 最佳实践：
1. 使用依赖注入而非直接导入
2. 通过事件总线解耦
3. 考虑将共享逻辑提取到独立模块

## 📚 相关文档

- [权限系统深度指南](./PERMISSION_MANAGEMENT.md) - 了解权限同步原理
- [后端架构文档](./backend-architecture.md) - 模块边界、数据模型、分析管线
- [后端开发规范](../backend/CODING_GUIDE.md) - 后端详细规范
- [前端开发规范](../frontend/CODING_GUIDE.md) - 前端详细规范

## 🎯 下一步

1. **实践**：按照清单创建你的第一个模块
2. **优化**：根据业务需求调整模块结构
3. **贡献**：分享你的模块开发经验

---

*提示：遇到问题？先检查常见问题，再查看相关文档，最后询问团队。*
