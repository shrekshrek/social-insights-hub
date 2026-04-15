# ADR-001: 取消通用 `analysis/` 模块，分析代码下沉到各渠道

- **状态**：Accepted
- **日期**：2026-04-10
- **决策者**：@shrekwang
- **相关**：`backend/CLAUDE.md` 架构约定、`docs/strategy-multi-source-architecture.md`

---

## 背景

项目最早只有社媒一个数据渠道，分析流水线（screening → deep → aggregation → slice）被写在顶层的 `src/analysis/` 模块下，姿态是"通用分析编排层"。后续陆续接入 `news_media`、`knowledge_base`、`strategies` 三个渠道/编排层，才逐渐暴露出这个抽象立不住：

1. **`analysis/celery_tasks/` 里的内容全是社媒特有领域逻辑**——CII / NSR / SERP / spam 4D 分布 / 实体与观点聚合 / KOL 声音 / 竞品雷达。没有任何一项对 news 或 knowledge_base 有意义
2. **`news_media` 不走这条流水线**。news 的 tagging / insight celery 任务住在 `news_media/tasks/tasks.py`，只是"来 analysis 领一张 AnalysisJob 票据"做成本追踪
3. **`knowledge_base` 也不走这条流水线**。vectorization / RAG 检索住在 `knowledge_base/tasks.py` 和 `knowledge_base/retrieval/`
4. **`strategies` 作为编排层**，各渠道的分析调用走各自的 celery 入口，并不依赖一个"通用 analysis 模块"

于是 `src/analysis/` 的实际内容是一个**混合体**：
- 一部分真正跨渠道：`jobs/`（AnalysisJob CRUD + factory）
- 一部分是社媒流水线被放错位置：`celery_tasks/*`、`service.py` 大部分、`router.py` 所有端点、`monitor_slice.py`、`export_docx.py` 等
- 一部分是派发层：`sources/news.py`（已实现，薄）、`sources/social.py`（空壳 TODO）

这种混合带来的真实问题：

- **循环依赖规避遍地**：`analysis/service.py` 有 14 处函数内 `from src.social_media.xxx import ...` lazy import，只是为了躲开 `analysis ↔ social_media` 的顶层循环
- **Import 统计扭曲**：`analysis/` 下对 `social_media.*` 的直接 import 共 ~34 处；对 `news_media` 9 处（大半是 `TYPE_CHECKING`）；对 `knowledge_base` / `strategies` **0 处**
- **架构约束和现实割裂**：`backend/CLAUDE.md` 写了"analysis 模块不得直接 import 渠道模块，必须通过 `sources/` 适配器"，但 social 那 34 处存量一直没法迁——因为它们本来就是社媒代码，迁到 `sources/social.py` 只是多加一层 re-export 薄壳
- **新渠道接入心智成本**：接新渠道时要纠结"这段分析代码是放在 `analysis/celery_tasks/` 还是 `{channel}/`"，而答案其实永远是后者
- **`sources/` 适配器是 cargo cult**：它存在的唯一理由是遮盖"分析模块不该 import 渠道模块"这条约束，但若领域代码本来就住在领域模块内，适配器层就是多余的

---

## 决策

**取消 `src/analysis/` 模块。将其内容按真实归属重新分配：**

1. **`jobs/` 提升到 `src/jobs/`**——这是唯一真正跨渠道的共享组件，记录 AnalysisJob（token / cost / status / FK 到各渠道 task），依赖零渠道模块
2. **社媒分析流水线搬回 `src/social_media/analysis/`**——`celery_tasks/*`、`monitor_slice.py`、`export_docx.py`、`service.py` 的社媒分支、`router.py` 全部社媒端点、`constants.py`、`base_task.py`
3. **`langchain/` 改名 `src/llm/`**——避免与第三方库同名，职责更清晰
4. **删除 `src/analysis/sources/` 整个目录**——适配器模式不再需要
5. **新渠道的分析代码一律住在 `src/{channel}/analysis/`**——不再有"通用 analysis 模块"的落脚点

---

## 目标结构

```
backend/src/
├── jobs/                          # AnalysisJob 模型 + CRUD + factory + 跨渠道 GET /jobs 查询
│   ├── models.py
│   ├── crud.py
│   ├── factory.py
│   └── router.py
│
├── llm/                           # 原 langchain/
│   ├── chains/                    # 所有 chain 注册
│   ├── instances.py               # DeepSeek 实例管理
│   └── token_usage.py
│
├── social_media/
│   ├── monitors/
│   ├── tasks/
│   │   └── adapters/              # 各平台爬虫适配
│   └── analysis/                  ★ 新
│       ├── celery_tasks/
│       │   ├── screening.py
│       │   ├── deep_post.py
│       │   ├── deep_comment.py
│       │   └── aggregation/
│       │       ├── orchestrator.py
│       │       ├── entities.py
│       │       ├── opinions.py
│       │       ├── metrics.py
│       │       └── insights.py
│       ├── slices/                # monitor_slice / project_slice
│       ├── service.py
│       ├── router.py              # POST /social-media/analysis/*
│       ├── export_docx.py
│       └── constants.py
│
├── news_media/
│   ├── monitors/
│   ├── tasks/                     # 爬取 celery
│   └── analysis/                  ★ 新
│       ├── celery_tasks.py        # news_tagging / news_insight
│       └── jobs.py                # 原 sources/news.py
│
├── knowledge_base/
│   ├── documents/
│   ├── ingestion/                 # 解析、分块、向量化 celery
│   └── retrieval/                 # RAG 检索
│
├── strategies/                    # 纯编排层，依赖各渠道 analysis 的公共接口
│
├── agent/                         # social_media pull 模型爬虫认领 API
├── auth/ rbac/ users/
└── main.py
```

### 依赖方向

```
strategies
    ↓
{social_media, news_media, knowledge_base}
    ↓
{jobs, llm}
    ↓
(nothing)
```

严格单向、无环。`jobs/` 和 `llm/` 是底层设施；渠道模块各自独立、互不依赖；`strategies/` 作为最上层编排者可以自由 import 下层渠道的公共接口。

---

## 影响与迁移范围

### 物理改动

- **文件移动**：约 20 个 Python 文件换位置（`analysis/` 内容分散到 `social_media/analysis/` + `jobs/`）
- **Import 路径重写**：估计 100+ 处 `from src.analysis.xxx` / `from src.langchain.xxx`
- **目录改名**：`src/langchain/` → `src/llm/`
- **Celery include 列表**：`src/celery_app.py` 的 `include` 数组更新
- **Router 注册**：`src/main.py` 更新
- **路由路径变化**：
  - `POST /analysis/screening` → `POST /social-media/analysis/screening`
  - `POST /analysis/deep-posts` → `POST /social-media/analysis/deep-posts`
  - `POST /analysis/deep-comments` → `POST /social-media/analysis/deep-comments`
  - `POST /analysis/aggregation` → `POST /social-media/analysis/aggregation`
  - `POST /analysis/slices` → `POST /social-media/analysis/project-slices`
  - `GET /analysis/task/{task_id}/result` → `GET /social-media/analysis/tasks/{task_id}/result`
  - `GET /analysis/jobs` → `GET /jobs`（保留跨渠道查询能力）
- **前端 API 调用点**：约 20–30 处 `useApi` 调用需同步更新
- **Alembic 无改动**：表不搬家，只是 Python 包移动，FK 不变

### 风险点

- **Celery 任务名变化**：任务名包含模块路径（如 `src.analysis.celery_tasks.screening_tasks.process_screening` → `src.social_media.analysis.celery_tasks.screening.process_screening`），现有 Redis 队列里的任务切换后会找不到 worker
  - **缓解**：在 celery 队列空、无 in-flight 任务时切换；开发环境可直接 `redis-cli FLUSHDB`
- **缺乏 e2e 回归网**：screening → deep → aggregation → slice 四级流水线没有端到端自动化测试，主要靠人工冒烟
  - **缓解**：分阶段提交，每阶段单独跑 `pnpm be:test` + 手动触发一次完整链路
- **前后端路由路径对齐**：后端路径一旦改了，前端同步 PR 必须立刻跟上，否则 dev 环境会断
  - **缓解**：后端和前端改动放在同一个 PR 内

### 不向后兼容

本决策明确**不提供向后兼容**：

- 旧路由 `POST /analysis/*` 不保留别名
- 旧 celery 任务名不保留
- 旧 import 路径不保留
- 前端 API 调用同步一次性更新

理由：项目处于活跃开发阶段，尚无外部消费者依赖具体路径；保留兼容层会让重构本身失去意义，只是把债从一个地方搬到另一个地方。

---

## 分阶段实施计划

每个 Phase 独立 PR，每阶段后跑完整 `pnpm be:test` + 手动触发主流水线冒烟。

| Phase | 内容 | 风险 |
|---|---|---|
| **P1** | `src/analysis/jobs/` → `src/jobs/`；更新所有 import；`analysis/router.py` 中 `GET /analysis/jobs` → `GET /jobs` | 低 |
| **P2** | `src/langchain/` → `src/llm/`；批量 import 重写 | 低（纯改名） |
| **P3** | 社媒流水线搬家：`analysis/celery_tasks/*` + `monitor_slice.py` + `export_docx.py` + `base_task.py` + `constants.py` → `src/social_media/analysis/`；更新 `celery_app.py` include 列表 | 中 |
| **P4** | `analysis/service.py` 按内容拆分：社媒部分 → `social_media/analysis/service.py`；剩余跨渠道 helper 视情况归属 | 中 |
| **P5** | `analysis/router.py` → `social_media/analysis/router.py`；路由路径前缀更新；前端 `useApi` 调用点同步更新 | 中（前后端必须同步） |
| **P6** | `news_media/tasks/tasks.py` 中的 tagging/insight → `news_media/analysis/celery_tasks.py`；`sources/news.py` → `news_media/analysis/jobs.py` | 低 |
| **P7** | 删除空壳 `src/analysis/` 整个目录（含 `sources/`）；更新 `backend/CLAUDE.md` 架构章节 | 低 |

每个 Phase 完成后必须达到的检查点：
- `pnpm be:lint` 通过
- `pnpm be:test` 通过（168+ passed）
- `pnpm fe:typecheck` 通过
- `pnpm fe:lint` 通过
- 手动冒烟：任意一条社媒任务跑通 screening + deep + aggregation；任意一条新闻 collect 任务跑通 tagging + insight

---

## 新的架构约束（替换 `backend/CLAUDE.md` 旧版）

落地后 `backend/CLAUDE.md` 相关章节改写为：

> **领域代码住领域模块**。每个渠道的分析/聚合/导出等 domain-specific 代码必须放在 `src/{channel}/analysis/` 下，不得放到任何共享位置。
>
> **跨渠道共享组件仅限两类**：
> - `src/jobs/`：AnalysisJob 成本与状态追踪
> - `src/llm/`：LLM 实例与 chain 注册
>
> **依赖方向严格单向**：`strategies → {channels} → {jobs, llm}`。渠道之间不得互相 import；`jobs` 和 `llm` 不得 import 任何渠道模块（`TYPE_CHECKING` 下的 relationship hint 除外）。
>
> **新渠道接入**：在 `src/{channel}/` 下新建完整模块（`monitors/` / `tasks/` / `analysis/`），通过 `src/jobs/` 和 `src/llm/` 复用成本追踪和 LLM 基础设施，无需也不应向 `src/` 顶层添加任何"通用分析"抽象。

---

## 被拒绝的替代方案

### 方案 A：保持现状，把 34 处 `from src.social_media.*` 迁移到 `sources/social.py`

拒绝理由：这是在错误位置的代码上盖一层适配器壳子。社媒分析代码本身就**不应该住在 `analysis/` 下**，迁 import 只是治标；而且 `sources/social.py` 会变成一个 re-export 转发模块，没有真正的解耦收益，只是让 CLAUDE.md 的规则表面上被遵守。

### 方案 B：保持现状，修改 `backend/CLAUDE.md` 让约束匹配现实

拒绝理由：约束匹配现实的正确做法是**让现实变正确**，而不是**让约束变软**。用改标准来掩盖未修的债，会让项目的架构规约失去权威——以后每条约束都可以被"现实情况"稀释。

### 方案 C：`analysis/` 改名为 `social_media_analysis/`，保留为顶层模块

拒绝理由：只解决了命名问题，没解决依赖方向问题。社媒的 monitors/tasks/analysis 三者本来就紧密耦合（分析代码查 SocialPost、SocialTask），强行分在两个顶层模块会继续引入循环依赖规避的 lazy import。

---

## 后续

本 ADR 立项后，**P1 启动的前置条件**：

- [ ] 确认无 in-flight celery 任务（或确认可接受 dev 环境 flush）
- [ ] 确认当前分支干净（无未提交改动）
- [ ] 新建 feature 分支 `refactor/channel-local-analysis`
- [ ] 在分支上按 Phase 顺序推进，每个 Phase 一个 commit（可独立 revert）
- [ ] 每个 Phase 结束后在本 ADR 末尾追加"已完成"勾选
