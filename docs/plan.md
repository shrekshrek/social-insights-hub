# 模块方案: Strategy Define (策略定义)

> 数据驱动的策略草案生成器。基于切片数据，通过 3 阶段 AI 生成（洞察→策略→创意），每阶段人工卡点确认，最终导出 Word 文档。

**设计文档**: `docs/plans/2026-03-04-strategy-define-design.md`

**状态**: 方案已确认

---

## 1. 数据模型

### strategies 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | |
| name | VARCHAR(255) | NOT NULL | 策略名称 |
| created_by | INTEGER | NOT NULL, FK → users(id) | 创建者 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'draft', CHECK IN ('draft','phase1_done','phase2_done','completed') | 状态 |
| brand_brief | JSONB | NULLABLE | 可选 Brief |
| phase1_result | JSONB | NULLABLE | Tension + Opportunity |
| phase2_result | JSONB | NULLABLE | Role + Strategy |
| phase3_result | JSONB | NULLABLE | Big Idea + Content Strategy |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now(), onupdate | |

索引: `ix_strategies_created_by(created_by)`

### strategy_slices 关联表

| 字段 | 类型 | 约束 |
|------|------|------|
| strategy_id | INTEGER | PK, FK → strategies(id) ON DELETE CASCADE |
| slice_id | INTEGER | PK, FK → project_analysis_slices(id) ON DELETE CASCADE |

索引: `ix_strategy_slices_slice_id(slice_id)`

设计要点:
- `status` 用 VARCHAR + CHECK 而非 PG enum，便于扩展
- `phase*_result` 用普通 JSON（整体写入，不需要 MutableDict）
- 复合主键 (strategy_id, slice_id)，CASCADE 双向删除

---

## 2. API / Interface Design

前缀: `/api/v1/strategies`，标签: `Strategies`

### 端点列表

| # | 方法 | 路径 | 请求体 | 响应 | 状态码 |
|---|------|------|--------|------|--------|
| 1 | POST | `/strategies` | StrategyCreate | StrategyRead | 201 |
| 2 | GET | `/strategies` | query: page, page_size, search | PaginatedResponse[StrategyListItem] | 200 |
| 3 | GET | `/strategies/{id}` | — | StrategyRead | 200 |
| 4 | PUT | `/strategies/{id}` | StrategyUpdate | StrategyRead | 200 |
| 5 | DELETE | `/strategies/{id}` | — | MessageResponse | 200 |
| 6 | POST | `/strategies/{id}/generate/phase1` | — | StrategyRead | 200 |
| 7 | POST | `/strategies/{id}/generate/phase2` | — | StrategyRead | 200 |
| 8 | POST | `/strategies/{id}/generate/phase3` | — | StrategyRead | 200 |
| 9 | PUT | `/strategies/{id}/phase1` | PhaseResultEdit | StrategyRead | 200 |
| 10 | PUT | `/strategies/{id}/phase2` | PhaseResultEdit | StrategyRead | 200 |
| 11 | PUT | `/strategies/{id}/phase3` | PhaseResultEdit | StrategyRead | 200 |
| 12 | GET | `/strategies/{id}/export` | — | StreamingResponse (docx) | 200 |

### Schemas

```
StrategyCreate:
  name: str (1~255)
  slice_ids: list[int] (min_length=1)
  brand_brief: dict | None

StrategyUpdate:
  name: str | None (1~255)
  brand_brief: dict | None

StrategyListItem:
  id, name, status, slice_count: int, created_by, creator_name, created_at, updated_at

StrategyRead:
  id, name, status, brand_brief,
  phase1_result, phase2_result, phase3_result,
  slices: list[SliceSummary],
  created_by, creator_name, created_at, updated_at

SliceSummary:
  slice_id, slice_name, project_id, project_name

PhaseResultEdit:
  result: dict
```

### 权限控制

- 所有端点: `Depends(get_current_user)`
- 创建/列表: `strategy:access`
- 详情/编辑/删除/生成: 创建者 OR admin (通过 `validate_strategy_owner` 依赖)
- 创建时校验: 每个 slice 的所属项目用户有访问权限

### 错误响应

| 场景 | 状态码 | 说明 |
|------|--------|------|
| slice_ids 为空 | 422 | Pydantic 校验 |
| slice 不存在或无权访问 | 403 | "无权访问切片 {id} 所属项目" |
| slice 分析未完成 (生成时) | 400 | "切片 {id} 尚未完成分析" |
| generate phase2 但 status < phase1_done | 409 | "请先完成并确认 Phase 1" |
| generate phase3 但 status < phase2_done | 409 | "请先完成并确认 Phase 2" |
| LLM 返回非法 JSON | 500 | "AI 生成结果解析失败，请重试" |
| strategy 不存在 | 404 | |

---

## 3. Implementation Steps

### Step 1: 数据模型 + 迁移

**文件**:
- `backend/src/strategies/__init__.py` (新建)
- `backend/src/strategies/models.py` (新建)

**接口**:
```python
class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[int], name: Mapped[str], created_by: Mapped[int] (FK users.id),
    status: Mapped[str] (default "draft"), brand_brief: Mapped[dict | None],
    phase1_result: Mapped[dict | None], phase2_result: Mapped[dict | None],
    phase3_result: Mapped[dict | None], created_at, updated_at
    # 关系
    creator: Mapped["User"] (lazy="selectin")
    slices: Mapped[list["StrategySlice"]] (back_populates="strategy", cascade="all, delete-orphan")

class StrategySlice(Base):
    __tablename__ = "strategy_slices"
    strategy_id: Mapped[int] (PK, FK strategies.id, ondelete CASCADE)
    slice_id: Mapped[int] (PK, FK project_analysis_slices.id, ondelete CASCADE)
    # 关系
    strategy: Mapped["Strategy"] (back_populates="slices")
    slice: Mapped["ProjectAnalysisSlice"] (lazy="selectin")
```

**关键断言**:
- Strategy 与 User 有 created_by 外键 + selectin 关系
- StrategySlice 与 ProjectAnalysisSlice 有 slice_id 外键
- CASCADE: 删 Strategy 自动删 strategy_slices

**验证**: `pnpm be:migrate:make "add strategies tables" && pnpm be:migrate:up && pnpm be:lint`

**依赖**: 无

---

### Step 2: Pydantic Schemas

**文件**: `backend/src/strategies/schemas.py` (新建)

**接口**:
```python
class StrategyCreate(CustomBaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slice_ids: list[int] = Field(..., min_length=1)
    brand_brief: dict | None = None

class StrategyUpdate(CustomBaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    brand_brief: dict | None = None

class SliceSummary(CustomBaseModel):
    slice_id: int
    slice_name: str | None
    project_id: int
    project_name: str

class StrategyListItem(CustomBaseModel):
    id: int; name: str; status: str; slice_count: int
    created_by: int; creator_name: str
    created_at: datetime; updated_at: datetime

class StrategyRead(CustomBaseModel):
    id: int; name: str; status: str; brand_brief: dict | None
    phase1_result: dict | None; phase2_result: dict | None; phase3_result: dict | None
    slices: list[SliceSummary]
    created_by: int; creator_name: str
    created_at: datetime; updated_at: datetime

class PhaseResultEdit(CustomBaseModel):
    result: dict

StrategyListResponse = PaginatedResponse[StrategyListItem]
```

**关键断言**:
- StrategyCreate.name 长度 1~255
- StrategyCreate.slice_ids min_length=1

**验证**: `pnpm be:lint`

**依赖**: Step 1

---

### Step 3: Service 层 (CRUD)

**文件**: `backend/src/strategies/service.py` (新建)

**接口**:
```python
async def create_strategy(db: AsyncSession, data: StrategyCreate, user_id: int) -> Strategy
    # 1. 校验每个 slice_id: 查询 ProjectAnalysisSlice，check_project_access
    # 2. 创建 Strategy + StrategySlice 记录
    # 3. 返回 Strategy (status=draft)

async def get_strategies(db, user_id, is_admin, skip, limit, search?) -> tuple[list[Strategy], int]
    # admin 看全部，普通用户只看自己创建的

async def get_strategy_by_id(db, strategy_id) -> Strategy | None
    # selectinload slices + slice.slice (ProjectAnalysisSlice) + slice.slice.project

async def update_strategy(db, strategy: Strategy, data: StrategyUpdate) -> Strategy

async def delete_strategy(db, strategy: Strategy) -> None

async def load_slice_data(db, strategy: Strategy) -> list[dict]
    # 读取关联的 ProjectAnalysisSlice.result_data，返回 list[result_data]

async def build_strategy_read(strategy: Strategy) -> StrategyRead
    # 组装 StrategyRead，含 slices summary + creator_name
```

**关键断言**:
- create: slice 不存在 → HTTPException 404
- create: slice 所属项目无权访问 → HTTPException 403
- get_strategies: 非 admin 只返回 created_by = user_id
- delete: CASCADE 自动清理 strategy_slices

**验证**: `pnpm be:lint`

**依赖**: Step 1, 2

---

### Step 4: Dependencies + Router (CRUD) + 注册

**文件**:
- `backend/src/strategies/dependencies.py` (新建)
- `backend/src/strategies/router.py` (新建)
- `backend/src/main.py` (修改)

**接口**:
```python
# dependencies.py
async def validate_strategy_exists(strategy_id: int, db) -> Strategy
    # 不存在 → 404

async def validate_strategy_owner(strategy, current_user) -> Strategy
    # 创建者 or admin，否则 → 403

# router.py
router = APIRouter(prefix="/strategies", tags=["Strategies"])

POST /strategies (response_model=StrategyRead, status_code=201, summary="创建策略")
GET /strategies (response_model=StrategyListResponse, status_code=200, summary="策略列表")
GET /strategies/{id} (response_model=StrategyRead, status_code=200, summary="策略详情")
PUT /strategies/{id} (response_model=StrategyRead, status_code=200, summary="更新策略")
DELETE /strategies/{id} (response_model=MessageResponse, status_code=200, summary="删除策略")

# main.py 添加:
from src.strategies.router import router as strategies_router
app.include_router(strategies_router, prefix=settings.API_PREFIX)
```

**关键断言**:
- 所有端点需要 get_current_user
- 详情/编辑/删除通过 validate_strategy_owner 依赖
- 不存在 → 404

**验证**: `pnpm be:lint`

**依赖**: Step 3

---

### Step 5: RBAC 权限注册

**文件**:
- `backend/src/rbac/init_data.py` (修改)
- `frontend/config/permissions.ts` (修改)
- `frontend/config/routes.ts` (修改)

**接口**:
```python
# init_data.py BUSINESS_PERMISSIONS 添加:
*create_module_permissions("strategy", ["access", "read", "write", "delete"],
    display_names={"access": "访问策略", "read": "查看策略", "write": "编辑策略", "delete": "删除策略"},
    descriptions={"access": "允许访问策略管理模块", ...}),
```

```typescript
// permissions.ts 添加:
STRATEGY_ACCESS: { target: 'strategy', action: 'access' },
STRATEGY_READ: { target: 'strategy', action: 'read' },
STRATEGY_WRITE: { target: 'strategy', action: 'write' },
STRATEGY_DELETE: { target: 'strategy', action: 'delete' },

// routes.ts ROUTE_CONFIG 添加:
'/strategies': { permission: PERMISSIONS.STRATEGY_ACCESS, label: '策略管理', showInNav: true, order: 90 },
'/strategies/create': { permission: PERMISSIONS.STRATEGY_WRITE },
'/strategies/[id]': { permission: PERMISSIONS.STRATEGY_READ },
```

**关键断言**:
- 重启后端后 permissions 表自动新增 strategy 权限
- /strategies 出现在导航栏

**验证**: `pnpm be:lint && pnpm fe:typecheck && pnpm fe:lint`

**依赖**: Step 4

---

### Step 6: LLM 链 — Phase 1 (洞察层)

**文件**: `backend/src/langchain/chains/strategy_phase1_chain.py` (新建)

**接口**:
```python
def create_strategy_phase1_chain() -> Runnable
    # system prompt: 社交媒体策略分析师角色
    # 任务: 从切片数据中提取 Social Tension + Brand Opportunity
    # 输出: JSON { social_tensions: [...], brand_opportunities: [...] }

def format_slice_data_for_phase1(slices: list[dict], brief: dict | None) -> dict
    # 从每个 slice 的 result_data 中提取:
    # - meta (subject, competitors, keywords)
    # - foundation.aligned_entities[:40] (name, role, heat, sentiment, top_features, top_issues)
    # - foundation.aligned_topics[:40] (name, category, heat, sentiment, original_terms)
    # - layers.landscape.overview (NSR, volume)
    # - layers.landscape.sov_ranking[:20]
    # - layers.landscape.industry_quadrant
    # - layers.intent.topic_radar (pains, gains, controversies)
    # - layers.intent.unmet_needs
    # - layers.focus.swot (if exists)
    # - reports (landscape_report, topic_report, focus_report)
    # 每个维度截断字符数，总输入控制在 ~30K tokens

def parse_phase1_response(response_text: str) -> dict
    # JSON 解析 + 缺失字段填默认值
```

**关键断言**:
- 输出 JSON 包含 social_tensions[] 和 brand_opportunities[]
- 每个 tension: statement + evidence[] + confidence
- 每个 opportunity: statement + evidence[] + related_tensions[]

**验证**: `pnpm be:lint`

**依赖**: 无 (独立)

---

### Step 7: LLM 链 — Phase 2 (策略层)

**文件**: `backend/src/langchain/chains/strategy_phase2_chain.py` (新建)

**接口**:
```python
def create_strategy_phase2_chain() -> Runnable
def format_data_for_phase2(phase1_result: dict, slices: list[dict], brief: dict | None) -> dict
    # Phase 1 结果 + KOL 声音 + 平台特征 + 时间趋势
def parse_phase2_response(response_text: str) -> dict
```

**关键断言**:
- 输出: brand_social_role{statement, elaboration, evidence[]} + social_strategy{statement, core_message, rhythm, evidence[]}
- 每个产物引用上游 Phase 1 的 opportunity index

**验证**: `pnpm be:lint`

**依赖**: 无 (独立)

---

### Step 8: LLM 链 — Phase 3 (创意层)

**文件**: `backend/src/langchain/chains/strategy_phase3_chain.py` (新建)

**接口**:
```python
def create_strategy_phase3_chain() -> Runnable
def format_data_for_phase3(phase1_result, phase2_result, slices, brief) -> dict
    # Phase 1+2 结果 + 高互动内容分析 + KOL 生态
def parse_phase3_response(response_text: str) -> dict
```

**关键断言**:
- 输出: big_idea{statement, elaboration, tension_echo, evidence[]} + content_strategy{pillars[], evidence[]}
- big_idea.tension_echo 说明创意如何回应核心矛盾
- content_strategy.pillars 2-4 个，每个含 name + description + reference_examples[]

**验证**: `pnpm be:lint`

**依赖**: 无 (独立)

---

### Step 9: Service 层 (生成 + 编辑 + 成本追踪)

**文件**: `backend/src/strategies/service.py` (修改)

**接口**:
```python
async def generate_phase1(db, strategy: Strategy) -> Strategy
    # 1. 校验 slices 有 result_data
    # 2. load_slice_data → format_slice_data_for_phase1
    # 3. chain.ainvoke() → parse_phase1_response
    # 4. 记录 AnalysisJob (job_type="strategy_phase1", 关联 token stats)
    # 5. strategy.phase1_result = result, status = "phase1_done"
    # 6. 清除 phase2_result + phase3_result (如果重新生成)

async def generate_phase2(db, strategy: Strategy) -> Strategy
    # 前置: status 必须 >= phase1_done → 否则 HTTPException 409
    # 类似 phase1，job_type="strategy_phase2"
    # 设置 status = "phase2_done"，清除 phase3_result

async def generate_phase3(db, strategy: Strategy) -> Strategy
    # 前置: status 必须 >= phase2_done → 否则 HTTPException 409
    # 类似，job_type="strategy_phase3"
    # 设置 status = "completed"

async def edit_phase_result(db, strategy: Strategy, phase: int, result: dict) -> Strategy
    # phase=1: 设 phase1_result, 清除 phase2/3_result, status="phase1_done"
    # phase=2: 设 phase2_result, 清除 phase3_result, status="phase2_done"
    # phase=3: 设 phase3_result, 保持 status="completed"
```

**AnalysisJob 成本追踪**:
- 复用现有 `analysis_jobs` 表，`job_type` 使用 `strategy_phase1/2/3`
- 记录 input_tokens, output_tokens, cost, llm_model, duration
- 通过 `await chain.ainvoke()` 获取 response，从 response.usage_metadata 提取 token stats

**关键断言**:
- generate_phase2 在 status=draft 时 → 409
- generate_phase3 在 status!=phase2_done 时 → 409
- edit_phase1 自动清除 phase2_result + phase3_result
- edit_phase2 自动清除 phase3_result
- 每次 generate 创建 AnalysisJob 记录

**验证**: `pnpm be:lint`

**依赖**: Step 3, 6, 7, 8

---

### Step 10: Router (生成 + 编辑端点)

**文件**: `backend/src/strategies/router.py` (修改)

**接口**:
```python
POST /strategies/{id}/generate/phase1 (summary="生成 Phase 1 洞察层")
POST /strategies/{id}/generate/phase2 (summary="生成 Phase 2 策略层")
POST /strategies/{id}/generate/phase3 (summary="生成 Phase 3 创意层")
PUT /strategies/{id}/phase1 (summary="编辑 Phase 1 结果")
PUT /strategies/{id}/phase2 (summary="编辑 Phase 2 结果")
PUT /strategies/{id}/phase3 (summary="编辑 Phase 3 结果")
```

**关键断言**:
- generate 端点同步调用 LLM (MVP 不做 Celery 异步)
- 所有端点通过 validate_strategy_owner 依赖
- 状态不满足 → 409

**验证**: `pnpm be:lint`

**依赖**: Step 9

---

### Step 11: Word 导出

**文件**:
- `backend/src/strategies/export_docx.py` (新建)
- `backend/src/strategies/router.py` (修改)

**接口**:
```python
def generate_strategy_docx(strategy: Strategy) -> BytesIO
    # 封面: 策略名称 + 创建日期
    # Phase 1 章节: Social Tension (结论+论据) + Brand Opportunity (结论+论据)
    # Phase 2 章节: Brand Social Role + Social Strategy
    # Phase 3 章节: Big Idea (含 tension_echo) + Content Strategy (含 pillars)
    # 未完成的 phase 标注 "未完成"

GET /strategies/{id}/export → StreamingResponse
    # Content-Disposition: attachment; filename*=UTF-8''{encoded_name}.docx
```

**关键断言**:
- 复用 analysis/export_docx.py 的样式设置 (_setup_styles) 和 Markdown 渲染 (_render_markdown)
- 未完成 phase 不报错，只导出已有内容

**验证**: `pnpm be:lint`

**依赖**: Step 10

---

### Step 12: 前端 Layer 基础设施

**文件**:
- `frontend/layers/strategies/nuxt.config.ts` (新建)
- `frontend/layers/strategies/types/index.ts` (新建)
- `frontend/layers/strategies/composables/useStrategies.ts` (新建)
- `frontend/nuxt.config.ts` (修改 - extends 添加 `'./layers/strategies'`)

**接口**:
```typescript
// types/index.ts
interface Strategy { id, name, status, brand_brief, phase1_result, phase2_result, phase3_result, slices, ... }
interface StrategyListItem { id, name, status, slice_count, creator_name, created_at, updated_at }
interface StrategyCreate { name, slice_ids, brand_brief? }
interface SliceSummary { slice_id, slice_name, project_id, project_name }
interface PhaseResult { social_tensions?, brand_opportunities?, brand_social_role?, ... }

// composables/useStrategies.ts
const getStrategies = (params?) => useApiData<PaginatedResponse<StrategyListItem>>('/strategies', ...)
const getStrategy = (id) => useApiData<Strategy>(`/strategies/${id}`, ...)
const createStrategy = async (data) => apiRequest<Strategy>('/strategies', { method: 'POST', body: data })
const updateStrategy = async (id, data) => apiRequest<Strategy>(`/strategies/${id}`, { method: 'PUT', body: data })
const deleteStrategy = async (id) => apiRequest(`/strategies/${id}`, { method: 'DELETE' })
const generatePhase = async (id, phase) => apiRequest<Strategy>(`/strategies/${id}/generate/phase${phase}`, { method: 'POST' })
const editPhase = async (id, phase, result) => apiRequest<Strategy>(`/strategies/${id}/phase${phase}`, { method: 'PUT', body: { result } })
const exportStrategy = (id) => apiDownload(`/strategies/${id}/export`, '策略报告.docx')
```

**关键断言**:
- 所有 API 调用通过 useApi() 的 apiRequest/useApiData/apiDownload
- nuxt.config.ts 中 extends 注册 strategies layer

**验证**: `pnpm fe:typecheck && pnpm fe:lint`

**依赖**: Step 5

---

### Step 13: 策略列表页

**文件**: `frontend/layers/strategies/pages/strategies/index.vue` (新建)

**接口**:
- UTable: name (链接到详情), status (UBadge), slice_count, creator_name, created_at
- 分页 (UPagination) + 搜索 (UInput)
- 创建按钮 → `/strategies/create`
- 行操作: 查看详情、删除 (需确认)

**关键断言**:
- ClientOnly 包装表格和分页
- 创建按钮需要 STRATEGY_WRITE 权限
- 从 `#components` 导入 UBadge/UButton

**验证**: `pnpm fe:typecheck && pnpm fe:lint`

**依赖**: Step 12

---

### Step 14: 策略创建页

**文件**: `frontend/layers/strategies/pages/strategies/create.vue` (新建)

**接口**:
- Zod 表单: name (必填 1~255) + 切片选择器
- 切片选择器: 先选项目 (下拉) → 显示该项目的切片列表 (checkbox)，支持跨项目多选
- 可选: Brand Brief (JSON 文本域，MVP 简单实现)
- 提交 → POST /strategies → navigateTo(`/strategies/${id}`)

**关键断言**:
- slice_ids 至少 1 个
- 项目列表和切片列表通过现有 composable 获取 (useSocialProjects, useAnalysis)

**验证**: `pnpm fe:typecheck && pnpm fe:lint`

**依赖**: Step 12

---

### Step 15: 策略详情页

**文件**:
- `frontend/layers/strategies/pages/strategies/[id]/index.vue` (新建)
- `frontend/layers/strategies/components/StrategyPhaseCard.vue` (新建)
- `frontend/layers/strategies/components/StrategyItemEditor.vue` (新建)
- `frontend/layers/strategies/components/StrategyEvidenceList.vue` (新建)

**接口**:
- 页面顶部: 策略名称 + 状态 badge + 关联切片 tags + 编辑/导出/删除按钮
- 3 个 StrategyPhaseCard 垂直排列:
  - Phase 1 (洞察层): Social Tension + Brand Opportunity
  - Phase 2 (策略层): Brand Social Role + Social Strategy
  - Phase 3 (创意层): Big Idea + Content Strategy
- 每个 PhaseCard:
  - 无结果: 「生成」按钮 (前置条件满足时 enabled)
  - 有结果: 产物列表，每个产物 statement + evidence
  - Phase 1/2: 「确认并继续」按钮
- StrategyItemEditor: 可编辑 statement 文本 (contenteditable 或 textarea)
- StrategyEvidenceList: evidence 卡片列表 (type + description + source)

**关键断言**:
- Phase 1 生成按钮总是可用
- Phase 2 生成需 status >= phase1_done
- Phase 3 生成需 status >= phase2_done
- 编辑保存后 refresh 页面数据 (后端已处理下游清除)
- 生成中: 按钮 disabled + loading spinner
- ClientOnly 包装所有动态内容

**验证**: `pnpm fe:typecheck && pnpm fe:lint`

**依赖**: Step 12, 13

---

## 4. Edge Cases & Error Handling

| 场景 | 处理 |
|------|------|
| slice_ids 含不存在的 slice | 404 "切片 {id} 不存在" |
| slice 所属项目用户无权访问 | 403 |
| generate 时 slice result_data 为空 | 400 "切片 {id} 尚未完成分析" |
| generate phase2 但 status < phase1_done | 409 |
| generate phase3 但 status < phase2_done | 409 |
| 重复 generate 同一 phase | 允许覆盖，自动清除下游 |
| 编辑 phase1 | 清除 phase2/3 result, status→phase1_done |
| 编辑 phase2 | 清除 phase3 result, status→phase2_done |
| LLM 返回非法 JSON | 500 "AI 生成结果解析失败，请重试" |
| LLM 缺少字段 | 宽松解析，缺失填默认值 |
| 关联 slice 被外部删除 | generate 时重新检查，缺失 → 提示 |
| 导出时部分 phase 未完成 | 只导出已有部分 |
| 并发 generate | 前端 disable + loading 防重复 |

---

## 5. Test Strategy

| 层 | 测试内容 | 方式 | 优先级 |
|---|---------|------|--------|
| Schemas | name 长度、slice_ids 非空 | 单元测试 | P0 |
| Service 状态流转 | generate 前置条件、edit 清除下游 | 单元测试 (mock LLM) | P0 |
| LLM 输出解析 | JSON 解析、缺失字段兜底 | 单元测试 (mock response) | P0 |
| Router | 端点可达性、状态码、权限 | 集成测试 (httpx) | P1 |
| Export | docx 生成不报错 | 单元测试 | P1 |
| 前端 | 类型正确性 | typecheck + lint | P0 |

---

## 6. Key Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 模块位置 | `backend/src/strategies/` (顶级) | 与 Project 平级的独立决策层模块 |
| API 前缀 | `/api/v1/strategies` | 不嵌套在 /social-media 下 |
| LLM 调用 | MVP 同步 (await chain.ainvoke) | 用户主动触发等待结果，先不引入 Celery |
| status 类型 | VARCHAR(20) + CHECK | 比 PG enum 更易扩展 |
| phase result | 3 个独立 JSONB 列 | 各 phase 独立读写不冲突 |
| 权限模型 | 创建者 + admin | MVP 简化，后续可加协作者 |
| 切片数据读取 | 直接查 ProjectAnalysisSlice.result_data | 全量读取，format 函数中截断 |
| 下游清除 | 编辑 phase N 清除 N+1 及以后 | 避免不一致 |
| 前端 Layer | `frontend/layers/strategies/` | 独立 Layer |
| 成本追踪 | 复用 analysis_jobs 表 | 统一 LLM 成本管理 |
| 生成 loading | 前端 disabled + spinner | MVP 不做 SSE 进度推送 |

---

## 7. 关键文件清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/src/strategies/__init__.py` | 模块初始化 |
| `backend/src/strategies/models.py` | ORM 模型 |
| `backend/src/strategies/schemas.py` | Pydantic schemas |
| `backend/src/strategies/service.py` | 业务逻辑 |
| `backend/src/strategies/dependencies.py` | 依赖注入 (exists/owner) |
| `backend/src/strategies/router.py` | API 端点 |
| `backend/src/strategies/export_docx.py` | Word 导出 |
| `backend/src/langchain/chains/strategy_phase1_chain.py` | Phase 1 LLM 链 |
| `backend/src/langchain/chains/strategy_phase2_chain.py` | Phase 2 LLM 链 |
| `backend/src/langchain/chains/strategy_phase3_chain.py` | Phase 3 LLM 链 |
| `frontend/layers/strategies/nuxt.config.ts` | Layer 配置 |
| `frontend/layers/strategies/types/index.ts` | TypeScript 类型 |
| `frontend/layers/strategies/composables/useStrategies.ts` | API composable |
| `frontend/layers/strategies/pages/strategies/index.vue` | 列表页 |
| `frontend/layers/strategies/pages/strategies/create.vue` | 创建页 |
| `frontend/layers/strategies/pages/strategies/[id]/index.vue` | 详情页 |
| `frontend/layers/strategies/components/StrategyPhaseCard.vue` | 阶段卡片 |
| `frontend/layers/strategies/components/StrategyItemEditor.vue` | 产物编辑器 |
| `frontend/layers/strategies/components/StrategyEvidenceList.vue` | 论据列表 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/src/main.py` | 添加 strategies router 注册 |
| `backend/src/rbac/init_data.py` | 添加 strategy 权限 |
| `frontend/config/permissions.ts` | 添加 STRATEGY_* 常量 |
| `frontend/config/routes.ts` | 添加 /strategies 路由配置 |
| `frontend/nuxt.config.ts` | extends 添加 strategies layer |
