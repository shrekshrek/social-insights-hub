# 实施方案：Strategy 模块重构（Steps 1-6）

> 将策略从"末端消费者"重构为"流程发起者与编排者"
> 前置工作（Step 0: Project → Monitor 改名）已完成（commit 73278c4）

---

## 模块职责

在现有 3 阶段策略生成（Phase 1/2/3）基础上，增加：
- **阶段 A（需求对齐）**: 结构化 Brief → AI 多轮咨询 → 一键创建监测
- **阶段 C（数据评估）**: 切片关联 → AI 充分性评估 → 确认就绪
- **Phase 生成保持兼容**: 快速路径（直接带切片创建）和引导路径均可进入生成

---

## 1. Data Model

### strategies 表变更（ALTER 不重建）

```sql
-- 新增 4 列
ALTER TABLE strategies ADD COLUMN consultation_rounds   JSONB DEFAULT '[]';
ALTER TABLE strategies ADD COLUMN suggested_monitor_ids JSONB DEFAULT '[]';
ALTER TABLE strategies ADD COLUMN slice_plan            JSONB DEFAULT '[]';
ALTER TABLE strategies ADD COLUMN evaluation_result     JSONB DEFAULT NULL;

-- 修改 status 枚举约束
ALTER TABLE strategies DROP CONSTRAINT strategies_status_check;
ALTER TABLE strategies ALTER COLUMN status SET DEFAULT 'briefing';
ALTER TABLE strategies ADD CONSTRAINT strategies_status_check
  CHECK (status IN (
    'briefing', 'consulting', 'monitors_created',
    'slices_ready', 'phase1_done', 'phase2_done', 'completed'
  ));
```

### models.py 对应字段

```python
status = Column(String(20), default="briefing", nullable=False)
consultation_rounds   = Column(JSONB, default=list)
suggested_monitor_ids = Column(JSONB, default=list)
slice_plan            = Column(JSONB, default=list)
evaluation_result     = Column(JSONB, nullable=True)
```

### service.py STATUS_ORDER 扩展

```python
STATUS_ORDER = {
    "briefing": 0, "consulting": 1, "monitors_created": 2,
    "slices_ready": 3, "phase1_done": 4, "phase2_done": 5, "completed": 6,
}
```

### Phase1 前置条件变更

**从** `status >= draft`（任意可生成）
**改为** `len(strategy.slices) > 0`（切片非空即可）

不绑定具体 status，兼容快速路径和引导路径。

### strategy_slices 表

不变。strategy_references 不变。

---

## 2. API / Interface Design

### 新增端点（5 个）

| 方法 | 路径 | 说明 | 状态变化 |
|------|------|------|----------|
| POST | `/strategies/{id}/consult` | 多轮 AI 咨询 | briefing → consulting（首轮），后续保持 consulting |
| POST | `/strategies/{id}/confirm-plan` | 确认建议，一键创建监测 | * → monitors_created |
| POST | `/strategies/{id}/slices` | 批量关联切片 | 无 |
| POST | `/strategies/{id}/evaluate` | AI 评估切片充分性 | 无（写 evaluation_result） |
| POST | `/strategies/{id}/confirm-ready` | 确认数据就绪 | * → slices_ready |

### 变更端点

| 端点 | 变更 |
|------|------|
| `POST /strategies` | `slice_ids` 改为 `Optional[list[int]] = []`，`brand_brief` 类型改为 `BrandBrief \| None` |
| `POST /strategies/{id}/generate/phase1` | 前置从 status 检查改为 slices 非空检查 |

### Schemas

```python
# --- 结构化 Brief ---
class BrandBrief(CustomBaseModel):
    brand_name: str
    industry: str | None = None
    analysis_goal: str
    competitors: list[str] = []
    focus_areas: list[str] = []        # ["口碑", "竞品", "趋势"]
    time_range: str | None = None
    constraints: str | None = None

# --- 咨询 ---
class ConsultRequest(CustomBaseModel):
    user_input: str
    answers: dict[str, str] | None = None   # {question_id: answer}

class ConsultResponse(CustomBaseModel):
    round_number: int
    understanding_summary: str
    clarification_questions: list[dict]     # [{id, question}]
    monitor_suggestions: list[dict]         # MonitorSuggestion
    slice_plan: list[dict]                  # SlicePlanItem
    confidence: float

# --- 确认计划 ---
class ConfirmPlanRequest(CustomBaseModel):
    monitor_suggestions: list[dict]         # 用户可修改后的建议

class ConfirmPlanResponse(CustomBaseModel):
    created_monitor_ids: list[int]
    strategy: StrategyDetail

# --- 批量切片关联 ---
class AddSlicesRequest(CustomBaseModel):
    slice_ids: list[int]                    # min_length=1

# --- 评估（无请求体）---
class EvaluationResultResponse(CustomBaseModel):
    overall_score: float
    is_sufficient: bool
    coverage_analysis: list[dict]
    slice_suggestions: list[dict]
    gap_analysis: list[dict]
    supplementary_tasks: list[dict] | None

# --- StrategyCreate 变更 ---
class StrategyCreate(CustomBaseModel):
    name: str
    slice_ids: list[int] = []              # 改为可选，默认空
    brand_brief: BrandBrief | None = None
```

---

## 3. Implementation Steps

### Step 1 — 数据模型 + 迁移 + Schema 骨架

**文件:**
- `backend/src/strategies/models.py` (modify)
- `backend/src/strategies/schemas.py` (modify)
- `backend/src/strategies/service.py` (modify: STATUS_ORDER + phase1 前置条件)
- `backend/src/strategies/router.py` (modify: 新增5端点，返回占位数据)
- `backend/alembic/versions/xxx_strategy_new_fields.py` (new)

**接口:**
- `Strategy` 响应新增: `consultation_rounds`, `suggested_monitor_ids`, `slice_plan`, `evaluation_result`
- `StrategyCreate.slice_ids` 改为 `Optional[list[int]] = []`
- `create()` 创建时 status 默认为 `briefing`（而非 `draft`）
- 5 个新端点返回占位 JSON（不调 LLM）

**关键断言:**
- POST /strategies 不传 slice_ids → 创建成功，status=briefing
- POST /strategies/{id}/generate/phase1 当无切片 → 400 "请先关联分析切片"
- POST /strategies/{id}/generate/phase1 当有切片（任意 status）→ 正常生成
- 旧 draft 策略迁移后 status 变为 briefing，仍可生成（只要有切片）

**验证:** `pnpm be:lint && pnpm be:test`
**依赖:** Step 0 已完成

---

### Step 2 — AI 咨询 Chain

**文件:**
- `backend/src/langchain/chains/strategy_consult_chain.py` (new)
- `backend/src/strategies/service.py` (modify: add `consult_strategy()`)
- `backend/src/strategies/router.py` (modify: consult 端点接真实 chain)

**接口:**
```python
# chain 输入变量
brief_section: str      # 格式化的 BrandBrief 文本
history_section: str    # 历史轮次摘要
user_input: str         # 本轮用户输入

# chain 输出（JSON）
{
  "understanding_summary": str,
  "clarification_questions": [{"id": str, "question": str}],
  "monitor_suggestions": [{"name", "platforms", "keywords", "task_type", "rationale"}],
  "slice_plan": [{"name", "purpose", "expected_sources"}],
  "confidence": float
}

# service 方法签名
async def consult_strategy(
    strategy_id: int, user_input: str,
    answers: dict[str, str] | None, db: AsyncSession
) -> ConsultResponse
```

**关键断言:**
- 有效 brief + 用户输入 → AI 回复包含 monitor_suggestions（≥1）
- 连续两次 consult → consultation_rounds 长度累加（不覆盖）
- LLM 解析失败 → 500，strategy 不更新
- 首轮后 status = consulting

**验证:** `pnpm be:test` (mock LLM)
**依赖:** Step 1

---

### Step 3 — confirm-plan（一键创建监测）

**文件:**
- `backend/src/strategies/service.py` (modify: add `confirm_plan()`)
- `backend/src/strategies/router.py` (modify: confirm-plan 端点)

**接口:**
```python
async def confirm_plan(
    strategy_id: int,
    monitor_suggestions: list[dict],
    current_user_id: int,
    db: AsyncSession
) -> ConfirmPlanResponse
# 内部调用 monitors.service.create_monitor() 逐个创建
# 写入 suggested_monitor_ids，status → monitors_created
```

**关键断言:**
- 2 条 suggestion → DB 新增 2 个 Monitor，suggested_monitor_ids=[id1, id2]
- Monitor 创建部分失败 → 已创建的保留，返回 partial_errors 字段
- 重复调用 confirm-plan → suggested_monitor_ids 追加（不覆盖）

**验证:** `pnpm be:test`
**依赖:** Step 2

---

### Step 4 — AI 评估 Chain + 批量切片关联 + confirm-ready

**文件:**
- `backend/src/langchain/chains/strategy_evaluate_chain.py` (new)
- `backend/src/strategies/service.py` (modify: add `evaluate()`, `batch_add_slices()`, `confirm_ready()`)
- `backend/src/strategies/router.py` (modify: slices/evaluate/confirm-ready 端点接真实逻辑)

**接口:**
```python
# evaluate chain 输入
brief_section: str          # BrandBrief 文本
slice_plan_section: str     # slice_plan 文本
slice_summary_section: str  # 已关联切片的数据摘要

# evaluate chain 输出（JSON）
{
  "overall_score": float,
  "is_sufficient": bool,
  "coverage_analysis": [...],
  "slice_suggestions": [...],
  "gap_analysis": [...],
  "supplementary_tasks": [...] | null
}

# service 方法签名
async def batch_add_slices(strategy_id: int, slice_ids: list[int], db) -> Strategy
async def evaluate(strategy_id: int, db) -> EvaluationResultResponse
async def confirm_ready(strategy_id: int, db) -> Strategy
```

**关键断言:**
- evaluate 时无关联切片 → is_sufficient=false, overall_score < 0.3
- batch_add_slices 重复 slice_id → upsert，不报错
- confirm_ready 在任意 status 下均可触发（向前跳转至 slices_ready）
- confirm_ready 在 completed 状态 → 400

**验证:** `pnpm be:test`
**依赖:** Step 1（evaluate/confirm-ready 独立于 Step 2/3）

---

### Step 5 — 前端重构

**文件:**
- `frontend/layers/strategies/types/index.ts` (modify)
- `frontend/layers/strategies/composables/useStrategies.ts` (modify: 5 个新方法)
- `frontend/layers/strategies/pages/strategies/create.vue` (modify: Brief 表单重构)
- `frontend/layers/strategies/pages/strategies/[id]/index.vue` (rewrite: 阶段指示器 + 4 面板)

**类型变更:**
```typescript
// 新状态
export type StrategyStatus =
  | 'briefing' | 'consulting' | 'monitors_created'
  | 'slices_ready' | 'phase1_done' | 'phase2_done' | 'completed'

// Strategy 接口新增字段
consultation_rounds: ConsultRound[]
suggested_monitor_ids: number[]
slice_plan: SlicePlanItem[]
evaluation_result: EvaluationResult | null

// StrategyCreate 变更
export interface StrategyCreate {
  name: string
  slice_ids?: number[]          // 改为可选
  brand_brief?: BrandBrief | null
}

// BrandBrief 结构化
export interface BrandBrief {
  brand_name: string
  industry?: string
  analysis_goal: string
  competitors?: string[]
  focus_areas?: string[]
  time_range?: string
  constraints?: string
}
```

**useStrategies.ts 新增方法:**
```typescript
consult(id: number, input: string, answers?: Record<string, string>) → ConsultResponse
confirmPlan(id: number, suggestions: MonitorSuggestion[]) → ConfirmPlanResponse
addSlices(id: number, sliceIds: number[]) → Strategy
evaluate(id: number) → EvaluationResult
confirmReady(id: number) → Strategy
```

**create.vue 变更:**
- Brief 表单改为结构化字段（brand_name + analysis_goal 必填，其余可选）
- 切片选择区域保留（快速路径），作为可选折叠面板
- 创建后跳转详情页

**[id]/index.vue 变更:**
- 顶部阶段进度指示器（A: 需求对齐 / B: 数据采集 / C: 数据评估 / D: 策略生成）
- 阶段 A 面板: Brief 展示 + 咨询轮次 + confirm-plan 按钮
- 阶段 B 面板: 提示语（人工操作，跳转监测页）
- 阶段 C 面板: 切片关联表 + AI 评估结果 + confirm-ready 按钮
- 阶段 D 面板: 现有 Phase 1/2/3 卡片（基本保留）
- STATUS_MAP 更新为 7 个状态颜色/标签

**验证:** `pnpm fe:typecheck && pnpm fe:lint`
**依赖:** Steps 1-4

---

### Step 6 — Phase Chain 微调（可最后执行）

**文件:**
- `backend/src/langchain/chains/strategy_phase1_chain.py` (modify)
- `backend/src/langchain/chains/strategy_phase2_chain.py` (modify)
- `backend/src/langchain/chains/strategy_phase3_chain.py` (modify)
- `backend/src/strategies/service.py` (modify: load_phase_inputs 加 brief/evaluation 上下文)

**变更要点:**
- 每条 chain 的 HUMAN_TEMPLATE 新增 `{brief_section}` 和 `{consult_summary}` 变量
- `_format_for_phase1/2/3` 补充这两个变量的格式化函数
- 若 evaluation_result 存在，Phase1 输入额外附加 `{evaluation_summary}`

**验证:** 手动测试 Phase1 生成输出
**依赖:** Steps 1-5

---

## 4. Edge Cases & Error Handling

| 场景 | 处理 |
|------|------|
| 创建策略时 Brief 为空 | 允许（briefing 状态，Brief 可后填）|
| 咨询时 Brief 为空 | brief_section 渲染为 "用户未提供 Brief"，仍调 LLM |
| LLM 输出不符合 JSON schema | 捕获 OutputParserException → 500 + 日志，不更新 strategy |
| confirm-plan 部分监测创建失败 | 已创建写入 suggested_monitor_ids，失败条目放 partial_errors |
| 跳过咨询直接关联切片 | 合法，status 可从 briefing 直接手动推进 |
| evaluate 时切片数据不完整 | slice_summary 渲染提示，AI 输出 is_sufficient=false |
| generate phase1 无切片 | 400 "请先关联分析切片" |
| confirm-ready 在 completed 状态 | 400 "策略已完成" |
| 重复 consult | 每次追加到 consultation_rounds，无次数限制 |

---

## 5. Test Strategy

**后端（pytest）:**
- `test_strategies_model.py` — 新字段 default 值正确，STATUS_ORDER 覆盖 7 个值
- `test_strategies_service.py` — mock LLM 测试 consult/evaluate 状态流转
- `test_strategies_router.py` — 现有 CRUD 测试保持通过；新端点 happy path + 错误场景

**前端:**
- `pnpm fe:typecheck` — 所有新 interface 类型正确
- `pnpm fe:lint` — ESLint 通过

**不测试:**
- LLM prompt 质量（人工评审）
- Chain 实际 LLM 调用（mock 替代）

---

## 6. Key Decisions

| 决策 | 理由 |
|------|------|
| Phase1 前置改为「切片非空」而非「status >= slices_ready」 | 兼容快速路径（直接带切片创建），引导流程可选 |
| consultation_rounds 存 JSONB，不建独立表 | 通常 1~3 轮，无独立查询需求，简化 schema |
| suggested_monitor_ids 弱关联，不建外键 | 删策略不影响监测，监测独立存在 |
| confirm-plan 接受用户修改后的 suggestions | AI 建议仅参考，控制权在用户 |
| evaluate 无请求体，切片数据从 DB 自动读 | 避免前端重复传输大 payload |
| create.vue 保留切片选择为可选折叠面板 | 快速路径：创建时直接带切片，无需走咨询流程 |
| Step 6（Phase Chain 微调）独立为最后步骤 | 不阻塞主体功能交付，可单独迭代 |
