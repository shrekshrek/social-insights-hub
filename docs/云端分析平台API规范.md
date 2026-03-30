# 云端分析平台 API 规范

本文档定义了云端分析平台与本地爬虫客户端之间的通信接口。

## 目录

- [架构概述](#架构概述)
- [认证方式](#认证方式)
- [通信流程](#通信流程)
- [API 接口](#api-接口)
  - [拉取待执行任务](#1-拉取待执行任务)
  - [确认接收任务](#2-确认接收任务)
  - [上报任务进度](#3-上报任务进度)
  - [上传任务结果](#4-上传任务结果)
  - [查询任务详情](#5-查询任务详情)
  - [健康检查](#6-健康检查)
- [数据结构](#数据结构)
- [错误码](#错误码)
- [实现建议](#实现建议)
- [与现有系统的对接](#与现有系统的对接)

---

## 架构概述

采用"云端大脑 + 本地手脚"的混合模式：

```
┌─────────────────────────────────────────────────────────────┐
│                   云端分析平台 (social-insights-hub)          │
│                                                             │
│   用户A 创建任务 ──┐                                         │
│   用户B 创建任务 ──┼──▶ 待执行任务池                           │
│   用户C 创建任务 ──┘   (data_source=remote_crawler, pending)  │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Web UI    │  │  Backend    │  │     Database        │  │
│  │ (用户创建任务)│  │  (API 服务) │  │    (PostgreSQL)     │  │
│  └─────────────┘  └──────┬──────┘  └─────────────────────┘  │
└───────────────────────────┼─────────────────────────────────┘
                            │ HTTPS (平台级 API Key)
                            │
                            ▼
                     ┌──────────────┐
                     │  爬虫客户端   │  ← 本地运行
                     │  (全局服务)   │  ← 拉取所有待执行任务
                     └──────────────┘
```

**核心设计**：
- **任务创建**：用户在 Web UI 创建任务，选择 `data_source = remote_crawler`
- **任务执行**：爬虫客户端轮询拉取所有待执行任务，执行后上传数据
- **数据归属**：上传的数据存入原任务，归属创建任务的用户和项目

**通信方式**：HTTP 轮询（非 WebSocket）

**优势**：
- 实现简单，无需维护长连接
- 防火墙友好（仅需 HTTPS 443 端口）
- 重启后自动恢复

---

## 认证方式

所有 Agent API 请求需在 Header 中携带：

```http
Authorization: Bearer {api_key}
```

| Header | 说明 | 示例 |
|--------|------|------|
| `Authorization` | 平台级 API Key，Bearer Token 格式 | `Bearer sk-platform-secret` |

**配置方式**（平台侧）：

```bash
# .env
AGENT_API_KEY=sk-your-secret-key-here
```

> 💡 **说明**：这是平台级 API Key，不绑定具体用户。爬虫客户端作为全局服务，处理所有用户创建的远程爬取任务。

---

## 通信流程

### 普通任务（单阶段）

```
爬虫客户端                                      云端平台
  │                                               │
  │  GET /api/v1/agent/tasks/pending              │
  │ ─────────────────────────────────────────────>│
  │  { tasks: [{ status:"pending", ... }] }       │
  │ <─────────────────────────────────────────────│
  │                                               │
  │  POST /api/v1/agent/tasks/{task_id}/accept    │
  │ ─────────────────────────────────────────────>│
  │  { ok: true }                                 │
  │ <─────────────────────────────────────────────│
  │                                               │
  │  [执行爬虫任务...]                              │
  │                                               │
  │  POST /api/v1/agent/tasks/{task_id}/progress  │
  │ ─────────────────────────────────────────────>│
  │                                               │
  │  POST /api/v1/agent/tasks/{task_id}/result    │
  │ ─────────────────────────────────────────────>│
  │  { ok: true, stored: {...} }                  │
  │ <─────────────────────────────────────────────│
```

### 探测/全量任务分离设计

策略研究引擎创建两类独立的任务：

**探测任务**（phase="probe"）：
- 验证关键词质量，约 20 条数据
- `max_pages` 限制翻页（微博/贴吧 2 页，其他平台 1 页）
- `enable_comments=0` 跳过评论，加快速度
- 分析完成后触发 probe_review_chain

**全量任务**（phase="collect"）：
- 探测通过后创建的独立任务
- `max_notes_count=50` 采集完整数据
- `max_pages=0` 或不设置（按 max_notes_count 采集）
- `enable_comments=1` 包含评论
- 分析完成后触发自动建切片

```
爬虫客户端                                      云端平台
  │                                               │
  │  ─── 探测任务（phase="probe")────────────── │
  │                                               │
  │  GET /api/v1/agent/tasks/pending              │
  │ ─────────────────────────────────────────────>│
  │  { tasks: [{ status:"pending",                │
  │              task_params: { max_pages:1,       │
  │                             max_notes_count:20,│
  │                             enable_comments:0 } }] }
  │ <─────────────────────────────────────────────│
  │                                               │
  │  POST /api/v1/agent/tasks/{task_id}/accept    │
  │ ─────────────────────────────────────────────>│
  │                                               │
  │  [执行探测：采集约 20 条，跳过评论]           │
  │                                               │
  │  POST /api/v1/agent/tasks/{task_id}/result    │
  │ ─────────────────────────────────────────────>│
  │  { ok: true }                                 │
  │ <─────────────────────────────────────────────│
  │       [云端分析数据，触发 probe_review_chain]     │
  │       [approve_probe 创建全量任务]                │
  │                                               │
  │  ─── 全量任务（phase="collect")────────────── │
  │                                               │
  │  GET /api/v1/agent/tasks/pending              │
  │ ─────────────────────────────────────────────>│
  │  { tasks: [{ status:"pending",                │
  │              task_params: { max_notes_count:50,  │
  │                             enable_comments:1 } }] }
  │ <─────────────────────────────────────────────│
  │                                               │
  │  [执行全量采集：50 条 + 评论]                   │
  │                                               │
  │  POST /api/v1/agent/tasks/{task_id}/result    │
  │ ─────────────────────────────────────────────>│
  │  { ok: true }                                 │
  │ <─────────────────────────────────────────────│
```

**关键规则**：
- `status = "pending"` 是唯一待执行状态
- 探测/全量通过 `phase` 字段区分，不影响执行流程
- 所有任务都需要 accept 步骤
- `/tasks/pending` 只返回 pending 状态任务

---

## API 接口

### 1. 拉取待执行任务

爬虫客户端定时轮询获取待执行任务。

**请求**

```http
GET /api/v1/agent/tasks/pending?limit=5
Authorization: Bearer {api_key}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 5 | 最多返回任务数量（1-20） |

**响应 200**

```json
{
  "tasks": [
    {
      "task_id": 123,
      "task_name": "小红书-AI关键词搜索",
      "platform": "xhs",
      "task_type": "search",
      "status": "pending",
      "priority": 1,
      "keywords": "人工智能",
      "task_params": {
        "max_notes_count": 50,
        "enable_comments": true,
        "enable_sub_comments": false,
        "per_note_max_comments_count": 20,
        "crawler_time_sleep": 2.0,
        "start_page": 1,
        "sort_type": "popularity_descending"
      },
      "created_at": "2025-01-01T10:00:00Z"
    }
  ]
}
```

**字段说明**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | int | ✅ | 任务唯一标识（平台 DataTask.id） |
| `task_name` | string | ✅ | 任务名称（用于展示） |
| `platform` | string | ✅ | 平台代码：`xhs/dy/bili/ks/wb/tieba/zhihu` |
| `task_type` | string | ✅ | 类型：`search/detail/creator/homefeed` |
| `status` | string | ✅ | `pending`（待执行，需 accept） |
| `priority` | int | ❌ | 优先级，数值越大越优先（默认 0） |
| `keywords` | string | ❌ | 搜索关键词（search 类型） |
| `task_params` | object | ❌ | 任务参数，详见下表 |
| `created_at` | string | ❌ | 创建时间 (ISO 8601) |

**task_params 参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `specified_ids` | string | - | 指定 ID 列表，逗号分隔（detail 类型） |
| `max_notes_count` | int | 50 | 最大采集数量 |
| `max_pages` | int | 0 | 最大翻页数（0=不限制）。探测任务通常设置 1 或 2 |
| `enable_comments` | bool | true | 是否采集评论 |
| `enable_sub_comments` | bool | false | 是否采集子评论 |
| `per_note_max_comments_count` | int | 20 | 每条内容最大评论数 |
| `crawler_time_sleep` | float | 2.0 | 爬取间隔（秒） |
| `start_page` | int | 1 | 起始页码 |
| `publish_time_type` | int | 0 | 发布时间筛选（0=全部,1=一天内,2=一周内,3=半年内） |
| `sort_type` | string | popularity_descending | 排序（popularity_descending/time_descending） |
| `enable_proxy` | bool | false | 是否启用代理 |

---

### 2. 确认接收任务

拉取到任务后，调用此接口确认接收，防止重复执行。

**请求**

```http
POST /api/v1/agent/tasks/{task_id}/accept
Authorization: Bearer {api_key}
Content-Type: application/json
```

```json
{
  "client_id": "my-laptop"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `client_id` | string | ❌ | 客户端标识（可选，用于追溯） |

**响应 200**

```json
{
  "ok": true,
  "message": "任务已接收"
}
```

**响应 409（任务已被接收）**

```json
{
  "ok": false,
  "error_code": "TASK_ALREADY_ACCEPTED",
  "message": "任务已被接收"
}
```

> 💡 **幂等性**：重复调用同一任务的 accept 接口应返回成功（幂等）。

---

### 3. 上报任务进度

任务执行过程中定期上报进度（建议每 30 秒或每处理 10 条数据）。

**请求**

```http
POST /api/v1/agent/tasks/{task_id}/progress
Authorization: Bearer {api_key}
Content-Type: application/json
```

```json
{
  "status": "running",
  "crawled_count": 25,
  "message": "正在爬取第 3 页"
}
```

**status 状态值**

| 状态 | 说明 |
|------|------|
| `accepted` | 已接收，准备执行 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `failed` | 失败 |

**响应 200**

```json
{
  "ok": true
}
```

> ⚠️ **注意**：进度上报失败不应中断任务执行，客户端应忽略错误继续执行。

---

### 4. 上传任务结果

任务完成后上传采集数据。

**请求**

```http
POST /api/v1/agent/tasks/{task_id}/result
Authorization: Bearer {api_key}
Content-Type: application/json
Content-Encoding: gzip
```

> ⚠️ **重要**：请求体必须使用 **gzip 压缩**，可节省 70-90% 带宽。

**请求体（压缩前）**

```json
{
  "platform": "xhs",
  "stats": {
    "contents_count": 50,
    "comments_count": 200
  },
  "data": {
    "contents": [...],
    "comments": [...]
  },
  "checkpoint_id": "cursor:page3:abc123",
  "error_message": null
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `error_message` | string | 任务失败原因。携带时云端保留已采集数据并将任务置为 `failed`（而非 `completed`）。正常完成时不携带或传 `null` |

**响应 200**

```json
{
  "ok": true,
  "stored": {
    "posts": 50,
    "comments": 200
  }
}
```

**响应 429（限流）**

```json
{
  "ok": false,
  "error_code": "RATE_LIMITED",
  "message": "请求过于频繁",
  "retry_after": 60
}
```

**服务端验证逻辑**：

| 验证项 | 失败响应 |
|-------|---------|
| 任务存在 | 404 TASK_NOT_FOUND |
| 状态为 accepted/running/completed | 409 INVALID_TASK_STATUS |
| platform 与任务配置一致 | 400 PLATFORM_MISMATCH |

> 💡 `completed` 状态允许重新上传（覆盖模式）。

---

### 5. 查询任务详情

查询指定任务的完整信息，包含 `task_params`（含 `checkpoint_id`）。

**请求**

```http
GET /api/v1/agent/tasks/{task_id}
Authorization: Bearer {api_key}
```

**响应 200**：返回与 `/tasks/pending` 列表中相同结构的单条 `AgentTaskInfo`。

**响应 404**：任务不存在或已删除。

> 💡 此接口供按需查询使用，正常流程中爬虫通过 `/tasks/pending` 轮询即可获取完整任务信息，无需额外调用此接口。

---

### 6. 健康检查

检测平台服务是否可用（无需认证）。

**请求**

```http
GET /api/v1/agent/health
```

**响应 200**

```json
{
  "status": "ok",
  "timestamp": "2025-01-01T10:00:00Z"
}
```

---

## 数据结构

### 内容数据 (contents)

不同平台字段有所差异，以下为通用字段：

```json
{
  "note_id": "abc123",
  "title": "AI 改变世界",
  "desc": "详细介绍人工智能...",
  "user_id": "user123",
  "nickname": "科技达人",
  "liked_count": 1000,
  "collected_count": 500,
  "comment_count": 100,
  "share_count": 50,
  "create_time": 1735689600,
  "note_url": "https://www.xiaohongshu.com/explore/xxx",
  "video_url": "https://...",
  "image_list": "url1,url2,url3",
  "tag_list": "科技,AI,人工智能",
  "transcript": "视频转写文本..."
}
```

### 评论数据 (comments)

```json
{
  "comment_id": "cmt123",
  "note_id": "abc123",
  "content": "说得太好了！",
  "user_id": "user456",
  "nickname": "路人甲",
  "create_time": 1735689700,
  "sub_comment_count": 5,
  "parent_comment_id": null,
  "liked_count": 10
}
```

> 💡 **说明**：平台会使用 Adapters 将上述格式转换为内部的 `SocialPost`/`SocialComment` 模型。

---

## 错误码

| HTTP 状态码 | error_code | 说明 | 客户端处理 |
|-------------|------------|------|-----------|
| 200 | - | 成功 | 继续 |
| 202 | - | 已接收（异步处理） | 继续 |
| 400 | INVALID_DATA | 数据格式错误 | 记录错误，不重试 |
| 401 | UNAUTHORIZED | API Key 无效 | 检查配置 |
| 404 | TASK_NOT_FOUND | 任务不存在 | 跳过任务 |
| 409 | TASK_ALREADY_ACCEPTED | 任务已被接收 | 跳过任务 |
| 409 | DUPLICATE_UPLOAD | 重复上传 | 跳过 |
| 429 | RATE_LIMITED | 请求限流 | 等待 retry_after 后重试 |
| 500 | INTERNAL_ERROR | 服务器错误 | 指数退避重试 |
| 502/503/504 | - | 网关/服务不可用 | 稍后重试 |

---

## 实现建议

### 平台侧

1. **任务筛选**
   - `/tasks/pending` 返回 `data_source=remote_crawler` 且 `status = "pending"` 的任务
   - 按 `priority` 降序、`created_at` 升序排列

2. **幂等性**
   - `accept` 接口幂等，重复调用返回成功
   - `result` 接口幂等，根据 task_id 判断重复上传

3. **超时处理**
   - APScheduler 定时任务（每 5 分钟，运行在 FastAPI asyncio 事件循环）：`accepted` 超过 2 小时未完成 → 重置为 `pending`，清空 `accepted_at`/`accepted_by`
   - 对应函数：`src/agent/tasks.py::reset_timed_out_tasks`（APScheduler 直接 await）
   - 处理爬虫 accept 后崩溃/重启导致任务丢失的场景

4. **数据入库**
   - 复用现有 `adapters/` 进行数据格式转换
   - 复用现有 `service.upload_task_data()` 进行数据存储

### 客户端侧

1. **轮询策略**
   - 默认 30 秒轮询间隔
   - 无任务时可延长间隔（如 60 秒）

2. **重试机制**
   - 网络错误：指数退避重试（最大 5 分钟）
   - 429 限流：按 `retry_after` 等待
   - 5xx 错误：最多重试 3 次

3. **压缩传输**
   - 结果上传自动 gzip 压缩
   - 典型压缩率 70-90%

---

## 与现有系统的对接

### 模型映射

| Agent API 字段 | DataTask 模型字段 | 说明 |
|---------------|------------------|------|
| `task_id` | `id` | 任务主键 |
| `platform` | `platform.code` | 通过 platform_id 关联 |
| `task_type` | `task_type` | 直接映射 |
| `keywords` | `keywords` | 直接映射 |
| `task_params` | `task_params` | JSON 字段 |
| `priority` | `priority` | **需新增字段** |

### 需要扩展的 DataTask 字段

```python
# 新增字段
priority: Mapped[int] = mapped_column(Integer, default=0, comment="优先级")
crawled_count: Mapped[int] = mapped_column(Integer, default=0, comment="已爬取数量")
accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
accepted_by: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="执行客户端标识")
```

### 状态扩展

```python
# 现有：pending/running/completed/failed
# 扩展：增加 accepted 状态
# pending → accepted → running → completed/failed
```

### 新增路由模块

```
src/
├── agent/                    # 新增 Agent 模块
│   ├── __init__.py
│   ├── router.py             # Agent API 路由
│   ├── schemas.py            # Agent 相关 Schema
│   ├── service.py            # Agent 业务逻辑
│   └── dependencies.py       # API Key 认证
```

### 环境配置

```bash
# .env
AGENT_API_KEY=sk-your-secret-key-here
```
