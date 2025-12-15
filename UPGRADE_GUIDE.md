# 脚手架升级指南

本文档记录了脚手架的最新变更，供基于此脚手架开发的项目参考升级。

---

## 📋 变更概览

| 类型 | 数量 |
|------|------|
| 删除文件 | 4 个 |
| 修改文件 | 42 个 |
| 新增文件 | 1 个 |

---

## 🗑️ 删除的文件

以下文件已删除，如果你的项目中有这些文件，请同步删除：

### 后端

| 文件 | 原因 |
|------|------|
| `backend/src/auth/exceptions.py` | 与 `src/exceptions.py` 重复，已统一到全局异常处理 |
| `backend/src/auth/utils.py` | 验证逻辑已由 Pydantic `@field_validator` 替代 |
| `backend/src/cache.py` | 未被使用，RBAC 模块有自己的缓存机制 |

### 前端

| 文件 | 原因 |
|------|------|
| `frontend/app/pages/charts.vue` | 图表功能已整合到工作台页面 |

---

## ⚠️ 重大变更（需要手动处理）

### 1. 后端消息响应类型统一

**变更**：`Msg` 类型改为 `MessageResponse`

**影响文件**：
- `backend/src/auth/schemas.py` - 删除 `Msg` 类定义
- `backend/src/auth/router.py` - 改用 `MessageResponse`

**升级步骤**：

```python
# 之前
from .schemas import Msg
return {"msg": "Success"}

# 之后
from src.schemas import MessageResponse
return MessageResponse(message="Success")
```

### 2. 前端消息类型同步更新

**影响文件**：
- `frontend/types/auth.ts` - `Msg` 改为 `MessageResponse`
- `frontend/types/index.ts` - 导出类型更新
- `frontend/layers/auth/composables/useAuthApi.ts` - 使用新类型

**升级步骤**：

```typescript
// 之前
interface Msg { msg: string }

// 之后
interface MessageResponse { message: string }
```

### 3. ECharts 集成修复（Vue 3 响应式兼容）

**问题**：Vue 3 的 `ref` 会深度代理对象，干扰 ECharts 内部属性

**影响文件**：`frontend/app/composables/useCharts.ts`

**升级步骤**：

```typescript
// 之前
import { ref } from 'vue'
const chartInstance = ref<ECharts | null>(null)
chartInstance.value = echarts.init(element, theme, options)

// 之后
import { shallowRef, markRaw } from 'vue'
const chartInstance = shallowRef<ECharts | null>(null)
chartInstance.value = markRaw(echarts.init(element, theme, options))
```

### 4. 图表页面整合到工作台

**变更**：删除独立的 `/charts` 页面，图表直接在工作台展示

**影响文件**：
- 删除 `frontend/app/pages/charts.vue`
- 修改 `frontend/app/pages/dashboard.vue` - 添加图表
- 修改 `frontend/config/routes.ts` - 移除 `/charts` 路由
- 修改 `frontend/app/pages/index.vue` - 移除图表链接

---

## 🔧 后端变更详情

### Pydantic v2 兼容性修复

| 文件 | 变更 |
|------|------|
| `backend/src/middleware.py` | `error_response.dict()` → `error_response.model_dump()` |
| `backend/src/rbac/service.py` | `role.dict()` → `role.model_dump()` |

### SQLAlchemy 导入更新

| 文件 | 变更 |
|------|------|
| `backend/src/database.py` | `from sqlalchemy.ext.declarative import declarative_base` → `from sqlalchemy.orm import declarative_base` |

### 常量文件精简

| 文件 | 变更 |
|------|------|
| `backend/src/auth/constants.py` | 仅保留 `REDIS_BLACKLIST_PREFIX`，其他常量已删除 |

### 函数重命名

| 文件 | 变更 |
|------|------|
| `backend/src/rbac/init_data.py` | `init_permissions_legacy` → `init_permissions` |

### pyproject.toml 清理

移除重复的 `[dependency-groups].dev` 配置。

---

## 🎨 前端变更详情

### useCharts.ts 增强

新增功能：
- ✅ ResizeObserver 容器大小监听
- ✅ 暗色模式自动切换
- ✅ 事件绑定 (on/off)
- ✅ shallowRef + markRaw 修复响应式问题

删除功能：
- ❌ `chartPresets` 预设模板（未使用）

### Dashboard 页面增强

新增内容：
- 数据概览卡片（用户总数、今日活跃、角色数量、权限数量）
- 用户活动趋势图（柱状图）
- 用户角色分布图（饼图）
- 演示数据说明提示

### 注释清理

| 文件 | 变更 |
|------|------|
| `frontend/layers/auth/stores/user.ts` | "兼容方法" 注释改为更清晰的描述 |
| `frontend/app/layouts/default.vue` | "兼容原有代码" 注释改为 "用于导航逻辑" |

---

## 🐳 Docker 和部署变更

### docker-compose.prod.yml

- 移除过时的 `version: '3.8'` 字段（Docker Compose V2 已弃用）

### pnpm-workspace.yaml

- 移除 `backend`（Python 项目不应在 pnpm workspace 中）

---

## 📦 依赖变更

### 前端

无新增依赖，仅更新 `pnpm-lock.yaml`。

### 后端

无新增依赖，仅更新 `uv.lock`。

---

## ✅ 升级检查清单

完成升级后，请运行以下检查：

```bash
# 后端检查
pnpm be:lint
pnpm be:test

# 前端检查
pnpm fe:typecheck
pnpm fe:lint
```

---

## 📝 注意事项

1. **如果你的项目使用了 `Msg` 类型**，需要全局替换为 `MessageResponse`
2. **如果你的项目有自定义图表组件**，请参考 `useCharts.ts` 的 `shallowRef + markRaw` 修复方案
3. **如果你的项目有 `/charts` 页面的引用**，需要更新为 `/dashboard`

---

## 🔄 快速升级命令

```bash
# 1. 删除废弃文件
rm -f backend/src/auth/exceptions.py
rm -f backend/src/auth/utils.py
rm -f backend/src/cache.py
rm -f frontend/app/pages/charts.vue

# 2. 同步依赖
pnpm install
cd backend && uv sync

# 3. 运行检查
pnpm be:lint && pnpm be:test
pnpm fe:typecheck && pnpm fe:lint
```

---

*文档生成时间：2024年12月*
