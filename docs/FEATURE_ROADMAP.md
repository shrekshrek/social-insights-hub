# 重构后功能规划路线图

## 📊 当前架构状态（2025-10-17）

### ✅ 已完成的核心模块

```
backend/src/
├── auth/              # 认证授权 ✅
├── users/             # 用户管理 ✅
├── rbac/              # 权限管理（代码驱动） ✅
├── tasks/             # 爬虫任务管理 ✅
├── resources/         # 资源管理（账号+代理） ✅
├── data/              # 数据模块 ✅
│   └── notes/         # 笔记数据（独立存储） ✅
├── platforms/         # 平台适配器 ✅
│   └── xhs/           # 小红书适配器 ✅
└── signing/           # 签名服务 ✅

数据库表: 12个（干净、规范）
API 端点: ~50个（RESTful）
```

---

## 🎯 待补充功能清单

### 优先级 P0（核心功能）

#### 1. 📊 评论数据模块
**状态**: 📋 待开发
**估时**: 2-3小时
**价值**: 高（完整数据采集）

```
backend/src/data/comments/
├── models.py          # Comment, NoteComment（关联表）
│   └── Comment
│       ├── id, platform, comment_id
│       ├── note_id（关联笔记）
│       ├── content, author_id, author_name
│       ├── liked_count, sub_comment_count
│       ├── parent_comment_id（支持回复）
│       ├── ip_location, published_at
│       └── crawled_at, updated_at
├── schemas.py         # CommentCreate, CommentInDB
├── service.py         # CRUD + bulk_save_comments_from_crawler()
└── router.py          # API 接口

API 端点:
- GET    /api/v1/data/comments                  # 评论列表
- GET    /api/v1/data/comments/{id}             # 评论详情
- GET    /api/v1/data/comments/note/{note_id}   # 笔记的评论
- GET    /api/v1/data/comments/tasks/{task_id}  # 任务的评论
- POST   /api/v1/data/comments                  # 创建评论
```

**集成点**:
```python
# backend/src/platforms/xhs/adapter.py
# 在 _execute_search 中添加评论爬取
if config.get("enable_comments", False):
    comments = await self._fetch_note_comments(context, client, notes)
    await comments_service.bulk_save_comments_from_crawler(...)
```

---

#### 2. 🔍 数据导出功能
**状态**: 📋 待开发
**估时**: 2小时
**价值**: 高（数据分析需求）

```python
# backend/src/data/notes/export.py

async def export_notes_to_csv(
    db: AsyncSession,
    task_id: int | None = None,
    filters: dict = None
) -> bytes:
    """导出笔记为 CSV"""
    notes = await service.list_notes(db, ...)
    # 使用 pandas 或 csv 模块生成
    return csv_bytes

async def export_notes_to_json(
    db: AsyncSession,
    task_id: int | None = None
) -> dict:
    """导出笔记为 JSON"""
    notes = await service.list_notes(db, ...)
    return {"notes": [note.dict() for note in notes]}

async def export_notes_to_excel(
    db: AsyncSession,
    task_id: int | None = None
) -> bytes:
    """导出笔记为 Excel（包含多个 sheet）"""
    # Sheet 1: 笔记基本信息
    # Sheet 2: 统计数据
    # Sheet 3: 评论数据
    return excel_bytes
```

**API 端点**:
```python
# backend/src/data/notes/router.py
@router.get("/export/csv")
async def export_notes_csv(...):
    csv_data = await export.export_notes_to_csv(...)
    return Response(content=csv_data, media_type="text/csv")

@router.get("/export/json")
async def export_notes_json(...):
    return await export.export_notes_to_json(...)

@router.get("/export/excel")
async def export_notes_excel(...):
    excel_data = await export.export_notes_to_excel(...)
    return Response(content=excel_data, media_type="application/vnd.ms-excel")
```

---

### 优先级 P1（增强功能）

#### 3. 🔄 任务调度功能
**状态**: 📋 待开发
**估时**: 3-4小时
**价值**: 中（自动化运行）

```python
# backend/src/tasks/models.py
class CrawlerTask:
    # 新增字段
    schedule_enabled: bool = False
    schedule_cron: str | None = None  # "0 */6 * * *" (每6小时)
    next_run_at: datetime | None = None

# backend/src/tasks/scheduler.py
from celery.schedules import crontab

@celery_app.on_after_configure.connect
def setup_scheduled_tasks(sender, **kwargs):
    """动态注册定时任务"""
    tasks = await get_scheduled_tasks()
    for task in tasks:
        sender.add_periodic_task(
            crontab.from_string(task.schedule_cron),
            execute_task.s(task.id),
            name=f"scheduled-task-{task.id}"
        )
```

**API 端点**:
```
PATCH /api/v1/crawler-tasks/{id}/schedule  # 设置定时任务
GET   /api/v1/crawler-tasks/scheduled      # 查看定时任务列表
```

---

#### 4. 📈 数据统计面板（可选 metrics 模块）
**状态**: 📋 待评估
**估时**: 4-6小时
**价值**: 中（运营分析）

**仅在需要时添加**，当前 `TaskStatistics` 已满足基本需求。

```
backend/src/metrics/
├── models.py          # MetricSnapshot（时间序列数据）
├── collector.py       # 收集任务执行指标
├── service.py         # 聚合统计
└── router.py          # API 接口

API 端点:
- GET /api/v1/metrics/tasks/trend              # 任务趋势
- GET /api/v1/metrics/tasks/success-rate       # 成功率
- GET /api/v1/metrics/accounts/health          # 账号健康度
- GET /api/v1/metrics/keywords/top             # 热门关键词
- GET /api/v1/metrics/notes/engagement         # 笔记互动数据
```

---

#### 5. 🔔 任务失败告警
**状态**: 📋 待开发
**估时**: 2-3小时
**价值**: 中（运维保障）

```python
# backend/src/tasks/alerts.py

async def check_task_alerts():
    """检查任务失败率"""
    recent_tasks = await get_recent_tasks(hours=24)
    failure_rate = calculate_failure_rate(recent_tasks)

    if failure_rate > 0.3:  # 失败率超过30%
        await send_alert(
            level="warning",
            message=f"任务失败率过高: {failure_rate:.1%}"
        )

async def send_alert(level: str, message: str):
    """发送告警（邮件/钉钉/企业微信）"""
    # 集成告警渠道
    ...
```

**告警规则**:
- 任务失败率 > 30%
- 代理池可用 < 20%
- 账号风控数 > 50%
- 任务执行时间 > 预期 2 倍

---

### 优先级 P2（体验优化）

#### 6. 🎨 前端数据可视化
**状态**: 📋 待开发
**估时**: 8-10小时
**价值**: 中（用户体验）

```
frontend/layers/crawler-data/
├── pages/
│   ├── notes/index.vue           # 笔记列表（表格+卡片视图）
│   ├── notes/[id].vue            # 笔记详情页
│   ├── comments/index.vue        # 评论列表
│   └── analytics/index.vue       # 数据分析面板
├── components/
│   ├── NoteCard.vue              # 笔记卡片
│   ├── NoteList.vue              # 笔记列表
│   ├── CommentTree.vue           # 评论树
│   ├── DataExportButton.vue      # 导出按钮
│   ├── EngagementChart.vue       # 互动数据图表
│   └── KeywordCloud.vue          # 关键词云
└── composables/
    ├── useNotes.ts               # 笔记数据
    └── useExport.ts              # 导出功能
```

**图表库**: ECharts / Chart.js
**表格库**: TanStack Table / Nuxt UI Table

---

#### 7. 🔍 高级搜索和筛选
**状态**: 📋 待开发
**估时**: 3-4小时
**价值**: 低（进阶功能）

```python
# backend/src/data/notes/service.py

async def search_notes(
    db: AsyncSession,
    q: str | None = None,              # 全文搜索
    platform: str | None = None,
    author_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_likes: int | None = None,      # 最小点赞数
    note_type: str | None = None,      # video/image
    sort_by: str = "crawled_at",       # 排序字段
    sort_order: str = "desc",
    skip: int = 0,
    limit: int = 100,
) -> List[models.Note]:
    """高级搜索"""
    stmt = select(models.Note)

    if q:
        stmt = stmt.where(
            or_(
                models.Note.title.contains(q),
                models.Note.content.contains(q)
            )
        )

    if platform:
        stmt = stmt.where(models.Note.platform == platform)

    if min_likes:
        stmt = stmt.where(models.Note.liked_count >= min_likes)

    # ... 更多筛选条件

    return await db.execute(stmt)
```

---

#### 8. 🤖 更多平台适配器
**状态**: 📋 待开发
**估时**: 每个平台 8-16小时
**价值**: 高（业务扩展）

```
backend/src/platforms/
├── xhs/           # 小红书 ✅
├── douyin/        # 📋 抖音（待开发）
├── bilibili/      # 📋 B站（待开发）
├── weibo/         # 📋 微博（待开发）
└── zhihu/         # 📋 知乎（待开发）

每个平台需要:
1. adapter.py      # 平台适配器
2. client.py       # API 客户端
3. 签名算法        # X-Bogus / X-S-Common 等
4. 字段映射        # 统一数据格式
```

---

### 优先级 P3（长期规划）

#### 9. 🧠 AI 数据分析（可选）
**状态**: 💡 规划中
**估时**: 16+ 小时
**价值**: 低（创新功能）

- 热门话题识别
- 情感分析
- 趋势预测
- 内容推荐

---

#### 10. 🔐 数据脱敏和隐私保护
**状态**: 💡 规划中
**估时**: 4-6小时
**价值**: 中（合规要求）

- 用户数据脱敏
- 敏感信息过滤
- 数据访问审计日志

---

## 📅 推荐开发顺序

### Phase 1: 数据完整性（1-2周）
1. ✅ Notes 数据模块（已完成）
2. 📋 Comments 数据模块
3. 📋 数据导出功能

### Phase 2: 自动化增强（1周）
4. 📋 任务调度功能
5. 📋 失败告警

### Phase 3: 用户体验（1-2周）
6. 📋 前端数据可视化
7. 📋 高级搜索筛选

### Phase 4: 业务扩展（按需）
8. 📋 更多平台适配器
9. 💡 Metrics 模块（可选）
10. 💡 AI 数据分析（可选）

---

## 🎯 近期优先建议

基于当前架构，**建议优先完成**：

### 本周（P0 核心功能）
1. **评论数据模块** - 补全数据采集
2. **数据导出功能** - 满足数据分析需求

### 下周（P1 增强功能）
3. **任务调度** - 实现自动化运行
4. **失败告警** - 保障系统稳定

### 之后按需（P2-P3）
5. 前端可视化
6. 更多平台

---

## ✅ 已完成的重要功能

- ✅ 用户认证和权限管理（RBAC）
- ✅ 爬虫任务 CRUD
- ✅ 小红书搜索和详情爬取
- ✅ 资源管理（账号+代理）
- ✅ 独立数据存储（Notes）
- ✅ 自动去重和更新
- ✅ Cookie 验证
- ✅ 签名生成服务
- ✅ 任务日志记录
- ✅ 基础统计功能

---

## 📝 开发建议

### 保持架构简洁
- ✅ 扁平化目录结构
- ✅ 模块职责清晰
- ✅ YAGNI 原则（只在需要时添加）

### 代码质量
- ✅ 类型提示（Python Type Hints）
- ✅ 文档字符串（Docstrings）
- ✅ 单元测试（Pytest）
- ✅ Lint 检查（Ruff）

### 数据库设计
- ✅ 合理的索引
- ✅ 外键约束
- ✅ 数据迁移管理（Alembic）

---

**核心理念**: Keep It Simple, Stupid (KISS)

只做当前需要的功能，避免过度设计。等业务增长后再按需扩展。
