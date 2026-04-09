# Strategy 模块重构计划

> ⚠️ **此文档为历史规划，已完全实施。当前设计请参考：**
> - **`backend/src/strategies/CLAUDE.md`** — 策略模块最新约定与实现细节
> - **`docs/strategy-multi-source-architecture.md`** — 多数据源架构

---

> 将策略从"末端消费者"重构为"流程发起者与编排者"
> 包含前置工作：Project → Monitor 全局改名

---

## 前置工作：Project → Monitor 改名

### 命名映射

| 旧名 | 新名 | 位置 |
|------|------|------|
| `SocialProject` | `Monitor` | Python 类名 |
| `social_projects` | `monitors` | 数据库表名 |
| `social_project_participants` | `monitor_participants` | 数据库关联表名 |
| `project_id` (FK) | `monitor_id` | 3 张表的外键列 |
| `ProjectAnalysisSlice` | `AnalysisSlice` | Python 类名 |
| `project_analysis_slices` | `analysis_slices` | 数据库表名 |
| `project_slice.py` | `monitor_slice.py` | 文件名 |
| `celery_tasks/project_slice/` | `celery_tasks/monitor_slice/` | 目录名 |
| `backend/src/social_media/projects/` | `backend/src/social_media/monitors/` | 目录名 |
| `frontend/layers/social-media/projects/` | `frontend/layers/social-media/monitors/` | 目录名 |
| `/social-media/projects` | `/social-media/monitors` | API 路径 |
| `SOCIAL_PROJECT_*` | `MONITOR_*` | 权限常量 |

### 数据库迁移策略

- **旧迁移文件不动**（历史记录保持原样）
- 新建一个 Alembic 迁移，执行:
  - `ALTER TABLE social_projects RENAME TO monitors`
  - `ALTER TABLE social_project_participants RENAME TO monitor_participants`
  - `ALTER TABLE project_analysis_slices RENAME TO analysis_slices`
  - 各表 `project_id` 列 `RENAME TO monitor_id`
  - 更新索引名、约束名

### 改名执行顺序

1. 新建 Alembic 迁移（表名 + 列名 + 索引名）
2. 后端目录重命名 `projects/` → `monitors/`
3. 后端模型/Schema/Service/Router/Dependencies 全局替换
4. 后端分析模块（analysis）中所有 `project_id` → `monitor_id` 引用
5. 后端 Celery 任务目录 + 文件名 + 内部引用
6. 后端 main.py 路由注册
7. 后端权限常量
8. 前端目录重命名
9. 前端类型/Composable/页面/组件全局替换
10. 前端路由配置 + 权限常量
11. 文档更新（CLAUDE.md 等）
12. `pnpm be:lint` + `pnpm be:test` 验证

---

## 总体流程

```
⚠️ 旧状态流（已废弃）:
  briefing → consulting → monitors_created → slices_ready → phase1_done → phase2_done → completed

✅ 当前状态流:
  draft → planned → probing → collecting → ready → phase1_done → phase2_done → completed
```

### 阶段 A: 需求对齐（新增）

1. 用户创建策略，填写结构化 Brief（品牌/目标/关注点/约束）
2. AI 咨询（可多轮）：理解需求 → 追问澄清 → 输出监测建议草案 + 切片规划草案
3. 用户确认建议 → 一键创建监测 + 数据任务

### 阶段 B: 数据采集 + 分析（人工操作，现有流程不变）

爬虫采集 → 初筛 → 深度分析 → 聚合 → 用户查看结果

### 阶段 C: 数据评估（新增）

1. 用户手动关联切片到策略（或按 AI 建议一键关联）
2. AI 审查切片数据，对照 Brief 和切片规划，评估充分性
3. 不足 → 建议补充采集（回到阶段 B）；足够 → 进入阶段 D

### 阶段 D: 策略生成（重构现有 Phase 1/2/3）

生成 6 部分内容（Social Tension / Brand Opportunity / Brand Social Role / Social Strategy / Big Idea / Content Strategy）→ 用户编辑 → 导出

---

## 数据模型变更

### strategies 表变更

| 字段 | 类型 | 变更 | 说明 |
|------|------|------|------|
| status | String(20) | 修改枚举值 | `briefing / consulting / monitors_created / slices_ready / phase1_done / phase2_done / completed` |
| brand_brief | JSON | 结构化重定义 | 从自由 JSON 改为结构化 Brief Schema |
| consultation_rounds | JSON | **新增** | `list[{round_number, user_input, ai_response, created_at}]` |
| suggested_monitor_ids | JSON | **新增** | AI 建议后创建的监测 ID 列表（弱关联，不建外键） |
| slice_plan | JSON | **新增** | 切片规划草案（阶段 A 产出，阶段 C 对照） |
| evaluation_result | JSON | **新增** | 充分性评估结果（阶段 C 产出） |
| phase1_result | JSON | 保留 | Phase 1: Social Tension + Brand Opportunity |
| phase2_result | JSON | 保留 | Phase 2: Brand Social Role + Social Strategy |
| phase3_result | JSON | 保留 | Phase 3: Big Idea + Content Strategy |

### strategy_slices 表

不变。切片关联仍为手动操作，但阶段 C 可一键批量关联 AI 建议的切片。
外键 `slice_id` 指向改名后的 `analysis_slices.id`。

### 创建时不再需要 slice_ids

`StrategyCreate` 的 `slice_ids` 从必填改为可选（默认空列表），因为切片在阶段 B 之后才产生。

---

## API 端点变更

### 新增端点

| 方法 | 路径 | 阶段 | 说明 |
|------|------|------|------|
| POST | `/strategies/{id}/consult` | A | AI 咨询（多轮），入参为用户本轮输入，返回 AI 回复（含追问+建议） |
| POST | `/strategies/{id}/confirm-plan` | A | 确认 AI 建议，一键创建监测+任务，状态 → `monitors_created` |
| POST | `/strategies/{id}/slices` | C | 批量关联切片（支持 AI 建议的一键关联） |
| POST | `/strategies/{id}/evaluate` | C | AI 评估切片充分性，返回评估结果+切片组合建议 |
| POST | `/strategies/{id}/confirm-ready` | C | 用户确认数据就绪，状态 → `slices_ready` |

### 变更端点

| 端点 | 变更 |
|------|------|
| `POST /strategies` | `slice_ids` 改为可选，新增结构化 `brand_brief` |
| `POST /strategies/{id}/generate/phase1` | 前置条件从 `draft` 改为 `slices_ready` |

### 保留端点（不变）

- GET/PUT/DELETE `/strategies/{id}`
- POST `/strategies/{id}/generate/phase{2,3}`
- PUT `/strategies/{id}/phase{1,2,3}`
- GET `/strategies/{id}/export`

---

## LangChain Chains 变更

### 新增 Chain

| Chain | 输入 | 输出 |
|-------|------|------|
| `strategy_consult_chain` | Brief + 历史轮次 + 用户本轮输入 | 需求理解摘要 / 追问列表 / 监测建议草案 / 切片规划草案 |
| `strategy_evaluate_chain` | Brief + 切片规划 + 实际切片数据摘要 | 充分性评分 / 缺口分析 / 切片组合建议 / 补充采集建议 |

### 保留 Chain（可能微调 prompt）

- `strategy_phase1_chain` — 洞察层
- `strategy_phase2_chain` — 策略层
- `strategy_phase3_chain` — 创意层

---

## Schemas 设计

### Brand Brief（结构化）

```python
# ⚠️ 已更新 — 见 src/strategies/schemas.py BrandBrief
class BrandBrief(CustomBaseModel):
    subject: str                 # 研究主体（品牌/产品/品类）
    analysis_goal: str           # 分析目标（自由文本）
    constraints: str | None      # 补充说明/约束
    source_plan: list | None     # AI 建议数据源（存于 brand_brief JSON，非独立列）
```

### Consultation Round

```python
class ConsultationUserInput(CustomBaseModel):
    answers: dict[str, str] | None   # 对上轮追问的回答 {question_id: answer}
    additional_notes: str | None     # 用户补充说明
    plan_adjustments: dict | None    # 对建议草案的修改

class ConsultationAIResponse(CustomBaseModel):
    understanding_summary: str       # "我理解你需要..."
    clarification_questions: list[ClarificationQuestion]  # 追问列表（可为空）
    monitor_suggestions: list[MonitorSuggestion]          # 监测建议草案
    slice_plan: list[SlicePlanItem]                       # 切片规划草案
    confidence: float                # AI 对需求理解的自信度 0~1

class MonitorSuggestion(CustomBaseModel):
    name: str                    # 建议的监测名
    platforms: list[str]         # 建议的平台
    keywords: list[str]          # 建议的关键词
    task_type: str               # search/detail/...
    rationale: str               # 建议理由

class SlicePlanItem(CustomBaseModel):
    name: str                    # 切片名称
    purpose: str                 # 这个切片要回答什么问题
    expected_sources: list[str]  # 预期数据来源（哪些监测/平台）
```

### Evaluation Result

```python
class EvaluationResult(CustomBaseModel):
    overall_score: float              # 总体充分性评分 0~1
    is_sufficient: bool               # 是否满足 Brief 需求
    coverage_analysis: list[CoverageItem]  # 逐条对照 Brief 目标的覆盖情况
    slice_suggestions: list[SliceSuggestion]  # 具体切片组合建议
    gap_analysis: list[GapItem]       # 数据缺口
    supplementary_tasks: list[MonitorSuggestion] | None  # 补充采集建议
```

---

## 实施阶段

### Step 0: Project → Monitor 全局改名（前置工作）

详见上方"前置工作"章节。此步骤完成后，代码库中不再有 `SocialProject` / `social_projects` / `ProjectAnalysisSlice` / `project_analysis_slices` 引用。

### Step 1: Strategy 数据模型 + 基础 API

1. 修改 `strategies` 表 — 新增字段、修改 status 枚举
2. 创建 Alembic 迁移
3. 更新 Schemas（BrandBrief 结构化、StrategyCreate 改 slice_ids 可选）
4. 更新 service.py（状态流转逻辑）
5. 新增 consult / confirm-plan / evaluate / confirm-ready 端点（先返回 mock 数据）

### Step 2: AI 咨询 Chain

1. 实现 `strategy_consult_chain`（prompt + parser）
2. 接入 consult 端点
3. 实现 confirm-plan 的一键创建逻辑（调用 Monitor/Task 创建 API）

### Step 3: AI 评估 Chain

1. 实现 `strategy_evaluate_chain`（prompt + parser）
2. 接入 evaluate 端点
3. 实现批量切片关联 + 一键关联

### Step 4: 前端重构

1. 策略创建页 → Brief 表单 + 咨询轮次展示
2. 策略详情页 → 阶段指示器 + 各阶段面板
3. 切片关联 + 评估结果展示
4. Phase 1/2/3 生成（基本保留）

### Step 5: 现有 Phase Chain 微调

1. Phase 1/2/3 prompt 加入 Brief 上下文和咨询结论
2. 确保 evaluation_result 可传递给 Phase 1 作为补充上下文

---

## 关键设计决策

1. **咨询轮次存储在 strategy 表的 JSONB 字段**，不建独立表 — 轮次少（通常 1~3 轮），无需独立查询
2. **suggested_monitor_ids 弱关联**，不建外键 — 监测独立存在，删除策略不影响监测
3. **切片关联保持手动**，但 AI 评估时输出建议，用户可一键确认 — 平衡自动化和用户控制
4. **阶段可跳过** — 用户可以跳过咨询直接手动关联切片，兼容老流程
5. **consultation_rounds 累加不覆盖** — 每轮追加到数组，AI 每次看到完整历史
