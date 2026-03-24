# 实施方案：Strategy Research Engine（Steps 1-8）

> 将策略模块从"末端消费者"重构为"智能研究编排者"。
> 用户全程留在策略页面，系统自动完成 Monitor 创建、任务管理、切片创建。
> 设计文档：`docs/strategy-research-engine.md`

---

## 文件变更总览

### 后端 — 新增

| 文件 | 说明 |
|------|------|
| `langchain/chains/strategy_research_design_chain.py` | 替代 consult_chain |
| `langchain/chains/strategy_probe_review_chain.py` | 探测结果审查 |
| `langchain/chains/strategy_coverage_check_chain.py` | 替代 architect + evaluate 组合 |
| `alembic/versions/xxx_strategy_research_engine.py` | 数据迁移 |

### 后端 — 改造

| 文件 | 变更范围 |
|------|----------|
| `strategies/models.py` | 重写：字段替换 + status 枚举 |
| `strategies/schemas.py` | 重写：新 request/response 结构 |
| `strategies/service.py` | 重写：新业务逻辑 |
| `strategies/router.py` | 重写：端点替换 |
| `strategies/CLAUDE.md` | 重写：模块文档 |
| `strategies/export_docx.py` | 小改：适配新字段名 |
| `strategies/dependencies.py` | 不变 |
| `agent/service.py` | 改造：upload_result 增加 probe_ready + approved 追加模式 |
| `agent/schemas.py` | 小改：新增 TaskStatusResponse |
| `agent/router.py` | 小改：新增 GET /agent/tasks/{id} |
| `social_media/tasks/models.py` | 小改：status 注释扩展 |
| `langchain/chains/strategy_phase1_chain.py` | 小改：注入 research_questions |
| `langchain/chains/strategy_phase2_chain.py` | 小改：注入 research_questions |
| `langchain/chains/strategy_phase3_chain.py` | 小改：注入 research_questions |

### 后端 — 删除

| 文件 | 原因 |
|------|------|
| `langchain/chains/strategy_consult_chain.py` | 被 research_design_chain 替代 |
| `langchain/chains/strategy_architect_chain.py` | 被 coverage_check_chain 吸收 |
| `langchain/chains/strategy_evaluate_chain.py` | 被 coverage_check_chain 吸收 |

### 前端 — 改造

| 文件 | 变更范围 |
|------|----------|
| `strategies/types/index.ts` | 重写 |
| `strategies/composables/useStrategies.ts` | 重写 |
| `strategies/pages/strategies/index.vue` | 改造：status 显�� |
| `strategies/pages/strategies/create.vue` | 改造：Brief 表单 |
| `strategies/pages/strategies/[id]/index.vue` | 重写：4 阶段面板 |
| `strategies/components/MonitorSuggestionsEditor.vue` | 改造 → ResearchPlanEditor |
| `strategies/components/SlicePlanEditor.vue` | 改造 → SliceBlueprintEditor |

### 前端 — 新增

| 文件 | 说明 |
|------|------|
| `strategies/components/ProbeReportPanel.vue` | 探测审查报告 |
| `strategies/components/DataOverviewPanel.vue` | 数据全景 + 切片 + 覆盖度 |
| `strategies/components/SliceAdjustModal.vue` | 切片微调弹窗 |

### 前端 — 保留

| 文件 | 说明 |
|------|------|
| `Phase1Content.vue` / `Phase1EditForm.vue` | 不变 |
| `Phase2Content.vue` / `Phase2EditForm.vue` | 不变 |
| `Phase3Content.vue` / `Phase3EditForm.vue` | 不变 |
| `StrategyEvidenceList.vue` / `EvidenceEditList.vue` | 不变 |

---

## Step 1 — 数据模型 + 迁移

**目标**: 新字段就位，旧数据平滑迁移，现有功能不破坏。

**文件:**
- `backend/src/strategies/models.py` (modify)
- `backend/src/strategies/schemas.py` (modify: StrategyRead 适配新字段)
- `backend/src/strategies/service.py` (modify: STATUS_ORDER + build_strategy_read)
- `backend/alembic/versions/xxx_strategy_research_engine.py` (new)

**模型变更:**

```python
# --- 替换的字段 ---
# consultation_rounds (JSONB [])  → research_design (JSONB NULL)
# suggested_monitor_ids (JSONB []) → monitor_id (Integer NULL, FK monitors.id)
# slice_plan (JSONB [])           → 移除（包含在 research_design.slice_blueprint 中）
# evaluation_result (JSONB NULL)  → coverage_check_result (JSONB NULL)

# --- 新增字段 ---
# probe_review_result  JSONB NULL    探测审查结果
# probe_round          Integer 0     当前探测轮次
# output_type          String(30) NULL  产出类型
# task_ids             JSONB []      策略创建的所有任务 ID

# --- status 枚举变更 ---
# 旧: briefing / consulting / monitors_created / slices_ready / phase1_done / phase2_done / completed
# 新: draft / planned / probing / collecting / ready / phase1_done / phase2_done / completed
```

**迁移策略:**

```sql
-- 1. 新增列
ALTER TABLE strategies ADD COLUMN research_design     JSONB DEFAULT NULL;
ALTER TABLE strategies ADD COLUMN probe_review_result  JSONB DEFAULT NULL;
ALTER TABLE strategies ADD COLUMN probe_round          INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE strategies ADD COLUMN coverage_check_result JSONB DEFAULT NULL;
ALTER TABLE strategies ADD COLUMN output_type          VARCHAR(30) DEFAULT NULL;
ALTER TABLE strategies ADD COLUMN task_ids             JSONB DEFAULT '[]' NOT NULL;
ALTER TABLE strategies ADD COLUMN monitor_id           INTEGER DEFAULT NULL REFERENCES monitors(id);

-- 2. 数据迁移：旧字段 → 新字段
-- consultation_rounds → research_design（取最新一轮的 ai_response 作为临时数据）
-- suggested_monitor_ids → monitor_id（取第一个）
-- evaluation_result → coverage_check_result
UPDATE strategies SET
  research_design = CASE
    WHEN consultation_rounds != '[]'::jsonb
    THEN (consultation_rounds->-1->'ai_response')
    ELSE NULL
  END,
  monitor_id = CASE
    WHEN suggested_monitor_ids != '[]'::jsonb
    THEN (suggested_monitor_ids->0)::int
    ELSE NULL
  END,
  coverage_check_result = evaluation_result;

-- 3. 状态映射
UPDATE strategies SET status = 'draft' WHERE status = 'briefing';
UPDATE strategies SET status = 'planned' WHERE status = 'consulting';
UPDATE strategies SET status = 'collecting' WHERE status = 'monitors_created';
UPDATE strategies SET status = 'ready' WHERE status = 'slices_ready';
-- phase1_done / phase2_done / completed 保持不变

-- 4. 删除旧列
ALTER TABLE strategies DROP COLUMN consultation_rounds;
ALTER TABLE strategies DROP COLUMN suggested_monitor_ids;
ALTER TABLE strategies DROP COLUMN slice_plan;
ALTER TABLE strategies DROP COLUMN evaluation_result;

-- 5. 更新约束
ALTER TABLE strategies DROP CONSTRAINT valid_status;
ALTER TABLE strategies ADD CONSTRAINT valid_status
  CHECK (status IN (
    'draft', 'planned', 'probing', 'collecting', 'ready',
    'phase1_done', 'phase2_done', 'completed'
  ));
ALTER TABLE strategies ALTER COLUMN status SET DEFAULT 'draft';
```

**STATUS_ORDER 更新:**

```python
STATUS_ORDER = {
    "draft": 0, "planned": 1, "probing": 2, "collecting": 3,
    "ready": 4, "phase1_done": 5, "phase2_done": 6, "completed": 7,
}
```

**StrategyRead 适配:** 新字段替换旧字段，保持 API 响应结构与新模型一致。

**关键断言:**
- 迁移后旧策略 status 正确映射（briefing→draft, consulting→planned 等）
- 旧策略的 phase1/2/3_result 不受影响
- 新建策略 status 默认为 draft
- monitor_id 正确引用旧的 suggested_monitor_ids[0]

**验证:** `pnpm be:migrate:up && pnpm be:lint && pnpm be:test`
**依赖:** 无

---

## Step 2 — research_design_chain + 端点

**目标**: 实现 ① 阶段（研究设计），替代现有 consult 流程。

**文件:**
- `backend/src/langchain/chains/strategy_research_design_chain.py` (new)
- `backend/src/strategies/schemas.py` (modify: 新增 DesignResearchRequest/Response)
- `backend/src/strategies/service.py` (modify: 新增 design_research() + confirm_research())
- `backend/src/strategies/router.py` (modify: 替换 consult + confirm-plan 端点)

**Chain 设计:**

```python
# 输入
brief_section: str      # Brief 格式化文本
extra_input: str        # 用户补充说明

# 输出 (JSON)
{
  "understanding_summary": str,
  "research_questions": [{"id", "question", "dimension", "priority"}],
  "data_plan": [{"dimension_name", "keywords", "platforms", "probe_size", "full_size", "rationale"}],
  "slice_blueprint": [{"name", "mode", "subject", "competitors", "source_dimensions", "serves_questions"}],
  "output_type": str,
  "output_type_rationale": str
}
```

**新增端点:**

| 方法 | 路径 | 说明 | 状态变化 |
|------|------|------|----------|
| POST | `/strategies/{id}/design-research` | AI 生成研究计划 | draft → planned |
| POST | `/strategies/{id}/confirm-research` | 确认计划，创建 Monitor + 探测任务 | planned → probing |

**confirm_research 逻辑:**
1. 创建一个 Monitor（name = strategy.name）
2. 遍历 data_plan 中每个 dimension × platform → 创建 DataTask
   - `task_params = {max_notes_count: full_size, probe_size: probe_size, enable_comments: 1, per_note_max_comments_count: 20}`
   - `auto_analyze = True, data_source = "remote_crawler"`
3. 存储 monitor_id, task_ids 到策略
4. 记录每个 task_id 对应的 dimension_name（存在 research_design 中，供后续自动建切片映射）
5. 状态 → probing

**ConfirmResearchRequest:**

```python
class ConfirmResearchRequest(CustomBaseModel):
    research_design: dict         # 用户编辑后的研究计划 (完整 JSON)
    notes_per_task: int = 50      # full_size 覆盖
    probe_notes: int = 15         # probe_size 覆盖
```

**移除端点:**
- `POST /strategies/{id}/consult` → 被 `design-research` 替代
- `POST /strategies/{id}/confirm-plan` → 被 `confirm-research` 替代

**关键断言:**
- design-research 输出包含 research_questions (≥1) 和 data_plan (≥1)
- confirm-research 创建的任务数 = Σ(len(platforms) for each data_plan item)
- 所有任务 task_params 包含 probe_size 字段
- LLM 解析失败 → 500，strategy 不更新

**验证:** `pnpm be:lint && pnpm be:test` (mock LLM)
**依赖:** Step 1

---

## Step 3 — Agent 增量上传协议

**目标**: 支持同一 DataTask 的探测上传 + 追加上传。

**文件:**
- `backend/src/agent/service.py` (modify: upload_result 行为分支)
- `backend/src/agent/schemas.py` (modify: 新增 TaskStatusResponse)
- `backend/src/agent/router.py` (modify: 新增 GET /agent/tasks/{id})
- `backend/src/social_media/tasks/models.py` (modify: status 注释扩展)

**upload_result 改造:**

```python
# 在现有 upload_result 中增加分支：

if task.status in ("accepted", "running"):
    # 首次上传
    probe_size = (task.task_params or {}).get("probe_size")
    if probe_size and len(contents) <= probe_size * 1.5:
        # 探测上传：存入数据，触发分析，但不标记 completed
        # ... 现有导入逻辑 ...
        await task_crud.update_task_status(db, task, "probe_ready")
        # 触发自动分析（现有逻辑复用）
    else:
        # 正常上传：现有逻辑不变
        await task_crud.update_task_status(db, task, "completed")

elif task.status == "approved":
    # 追加上传：不清空现有数据，追加新数据
    # 但需要清空旧分析结果（全量重新分析）
    await _clear_analysis_results(db, task)
    # ... 导入逻辑（追加模式，去重 post_id_on_platform）...
    await task_crud.update_task_status(db, task, "completed")
    # 触发自动分析

elif task.status == "completed":
    # 重传：现有逻辑不变（覆盖模式）
```

**新增端点:**

```python
@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get task status",
    description="查询任务当前状态（供爬虫轮询）",
    dependencies=[Depends(verify_agent_api_key)],
)
async def get_task_status(task_id: int, db = Depends(get_async_db)):
    task = await db.get(DataTask, task_id)
    return TaskStatusResponse(task_id=task.id, status=task.status)
```

**DataTask.status 扩展说明:**

```
现有:  pending → accepted → running → completed / failed
新增:  ... → running → probe_ready → approved → completed / failed
                        ↑ 探测上传     ↑ 用户确认（或策略自动确认）
```

注意：不修改 DataTask 模型本身的 status 字段定义（它是 String(50)，无枚举约束），只在 agent/service.py 中增加新状态的处理逻辑。

**关键断言:**
- 有 probe_size 的任务首次上传 → status = probe_ready（不是 completed）
- 无 probe_size 的任务首次上传 → status = completed（现有行为不变）
- status = approved 时上传 → 追加数据，不清空帖子，清空分析结果
- GET /agent/tasks/{id} 返回正确 status
- 探测上传后自动触发分析（复用现有 auto_analyze 逻辑）

**验证:** `pnpm be:lint && pnpm be:test`
**依赖:** Step 1（DataTask 状态流转）

---

## Step 4 — probe_review_chain + 自动审查

**目标**: 实现 ② 阶段（探测验证），包含自动通过逻辑。

**文件:**
- `backend/src/langchain/chains/strategy_probe_review_chain.py` (new)
- `backend/src/strategies/service.py` (modify: 新增 check_probe_status(), review_probe(), approve_probe(), refine_probe())
- `backend/src/strategies/router.py` (modify: 新增 probe 相关端点)
- `backend/src/strategies/schemas.py` (modify: 新增 ProbeStatus/ProbeReview/RefineProbe schemas)

**Chain 设计:**

```python
# 输入
probe_tasks_section: str   # 每个任务的分析结果摘要
research_design_section: str  # 原始研究计划

# 输出 (JSON)
{
  "assessments": [
    {"task_id", "keyword", "platform", "quality", "relevance_rate",
     "entity_match", "topic_relevance", "verdict", "note"}
  ],
  "overall_verdict": "all_pass | partial_pass | fail",
  "refinement_suggestions": [
    {"task_id", "original_keyword", "suggested_keyword", "platform", "reason"}
  ]
}
```

**自动审查触发逻辑:**

策略状态 = probing 时，新增一个轮询端点 `GET /strategies/{id}/probe-status`，返回：
- 所有探测任务的完成状态
- 当所有任务分析完成 → 自动运行 probe_review_chain
- 如果 overall_verdict = all_pass → 自动标记所有任务 approved，状态 → collecting
- 否则 → 存储 probe_review_result，等待用户操作

**新增端点:**

| 方法 | 路径 | 说明 | 状态变化 |
|------|------|------|----------|
| GET | `/strategies/{id}/probe-status` | 探测进度 + 自动审查触发 | probing → collecting (如果全部通过) |
| POST | `/strategies/{id}/approve-probe` | 手动确认探测通过 | probing → collecting |
| POST | `/strategies/{id}/refine-probe` | 调整关键词，创建新探测任务 | probing → probing (probe_round++) |

**refine_probe 逻辑:**
1. 检查 probe_round < 3
2. 取消不合格的旧任务（标记 is_deleted）
3. 用新关键词创建新探测任务（同一 Monitor）
4. 更新 strategy.task_ids
5. probe_round += 1

**关键断言:**
- probe-status 在所有任务分析完成前返回 `{all_analyzed: false}`
- probe-status 在所有任务分析完成后自动运行 review → 返回审查结果
- overall_verdict = all_pass → 自动 approve 所有任务
- refine_probe 在 probe_round >= 3 时 → 400 "已达最大探测轮次"
- approve_probe 将所有 probe_ready 任务标记为 approved

**验证:** `pnpm be:lint && pnpm be:test` (mock LLM)
**依赖:** Steps 2, 3

---

## Step 5 — 自动建切片 + coverage_check_chain

**目标**: 实现 ③ 阶段（数据就绪），包含自动切片创建和覆盖度验证。

**文件:**
- `backend/src/langchain/chains/strategy_coverage_check_chain.py` (new)
- `backend/src/strategies/service.py` (modify: 新增 check_collection_status(), create_auto_slices(), get_data_overview(), adjust_slices())
- `backend/src/strategies/router.py` (modify: 新增 collection/overview/adjust 端点)
- `backend/src/strategies/schemas.py` (modify: 新增相关 schemas)

**自动建切片逻辑:**

```python
async def create_auto_slices(db, strategy):
    """当所有任务分析完成后，按 slice_blueprint 自动创建切片"""
    blueprint = strategy.research_design.get("slice_blueprint", [])
    data_plan = strategy.research_design.get("data_plan", [])

    # 建立 dimension_name → task_ids 映射
    dim_to_tasks = {}
    for item in data_plan:
        dim_name = item["dimension_name"]
        # 从 task_ids 中找到属于该维度的任务
        # （confirm_research 时已在 research_design 中记录了 task_id → dimension 映射）
        dim_to_tasks[dim_name] = [...]

    # 按 blueprint 创建切片
    for slice_spec in blueprint:
        task_ids_for_slice = []
        for dim in slice_spec["source_dimensions"]:
            task_ids_for_slice.extend(dim_to_tasks.get(dim, []))

        # 调用现有切片创建 API
        # monitor_slice.create_slice(
        #     monitor_id=strategy.monitor_id,
        #     task_ids=task_ids_for_slice,
        #     name=slice_spec["name"],
        #     subject=slice_spec.get("subject", ""),
        #     competitors=slice_spec.get("competitors", []),
        # )

    # 切片分析完成后关联到策略
    # 触发 coverage_check_chain
```

**coverage_check_chain:**

```python
# 输入
brief_section: str
research_questions_section: str   # 研究问题列表
slices_summary_section: str       # 切片 result_data 摘要

# 输出 (JSON)
{
  "question_coverage": [
    {"question_id", "question", "covered": bool, "covered_by", "note"}
  ],
  "overall_ready": bool,
  "data_highlights": [str],
  "slice_adjustments": [{"slice_name", "issue", "suggestion"}]
}
```

**���增端点:**

| 方法 | 路径 | 说明 | 状态变化 |
|------|------|------|----------|
| GET | `/strategies/{id}/collection-status` | 全量采集+分析进度 + 自动建切片触发 | collecting → ready (自动) |
| GET | `/strategies/{id}/data-overview` | 数据全景 + 切片列表 + 覆盖度 | — |
| POST | `/strategies/{id}/adjust-slices` | 微调切片配置 | ready → ready (重新验证) |

**collection-status 自动化链:**
1. 检查所有 task_ids 中 status=completed 的比例
2. 全部完成 → 自动调用 create_auto_slices()
3. 切片分析完成 → 自动运行 coverage_check_chain
4. overall_ready=true → 状态 → ready

**关键断言:**
- collection-status 在任务未全部完成时返回进度百分比
- 所有任务完成后自动创建切片（按 blueprint 中的条目数）
- coverage_check 返回每个 research_question 的覆盖状态
- adjust_slices 修改后重新触发切片分析和覆盖度验证

**验证:** `pnpm be:lint && pnpm be:test` (mock LLM + mock 切片创建)
**依赖:** Steps 1, 2, 4

---

## Step 6 — Phase Chain 增强 + 清理旧 Chain

**目标**: Phase 1/2/3 注入 research_questions 上下文，删除不再使用的旧 Chain。

**文件:**
- `backend/src/langchain/chains/strategy_phase1_chain.py` (modify)
- `backend/src/langchain/chains/strategy_phase2_chain.py` (modify)
- `backend/src/langchain/chains/strategy_phase3_chain.py` (modify)
- `backend/src/strategies/service.py` (modify: format 函数传入新上下文)
- `backend/src/langchain/chains/strategy_consult_chain.py` (delete)
- `backend/src/langchain/chains/strategy_architect_chain.py` (delete)
- `backend/src/langchain/chains/strategy_evaluate_chain.py` (delete)

**Phase Chain 变更:**

每条 chain 的 USER_TEMPLATE 新增 `{research_context_section}` 变量：

```
## 研究问题（本次分析要回答的核心问题）
1. [rq1] 大魔王在零食品类中的消费者认知如何？（维度: brand_voice, 优先级: high）
2. [rq2] 主要竞品的社媒表现如何？（维度: competitive, 优先级: high）

## 需求理解摘要
{understanding_summary}
```

**service.py 变更:**
- `generate_phase1/2/3` 中调用 format 函数时传入 `strategy.research_design`
- 从 research_design 提取 research_questions 和 understanding_summary

**清理旧 Chain:**
- 删除 `strategy_consult_chain.py`（已被 research_design_chain 替代）
- 删除 `strategy_architect_chain.py`（已被 coverage_check_chain 吸收）
- 删除 `strategy_evaluate_chain.py`（已被 coverage_check_chain 吸收）
- 从 service.py 移除所有对旧 Chain 的 import

**关键断言:**
- Phase 1 生成结果中的 tensions/opportunities 与 research_questions 相关
- 删除旧 chain 后无 import 报错
- 现有 Phase 生成逻辑不被破坏（切片数据读取不变）

**验证:** `pnpm be:lint && pnpm be:test`
**依赖:** Steps 1-5

---

## Step 7 — 后端清理 + router 端点移除

**目标**: 移除所有不再使用的旧端点和旧 service 方法。

**文件:**
- `backend/src/strategies/router.py` (modify: 移除旧端点)
- `backend/src/strategies/service.py` (modify: 移除旧方法)
- `backend/src/strategies/schemas.py` (modify: 移除旧 schemas)
- `backend/src/strategies/CLAUDE.md` (rewrite)

**移除端点:**

| 端点 | 原因 |
|------|------|
| `POST /strategies/{id}/consult` | 被 design-research 替代 |
| `POST /strategies/{id}/confirm-plan` | 被 confirm-research 替代 |
| `POST /strategies/{id}/slices` | 切片自动创建 |
| `DELETE /strategies/{id}/slices/{id}` | 改为 adjust-slices 统一处理 |
| `POST /strategies/{id}/evaluate` | 被 coverage_check 自动触发替代 |
| `POST /strategies/{id}/confirm-supplementary` | 移除补采循环 |
| `GET /strategies/{id}/supplementary-status` | 移除补采循环 |
| `POST /strategies/{id}/confirm-ready` | 自动验证后直接进入 ready |

**移除 service 方法:**
- `consult_strategy()`
- `confirm_plan()`
- `batch_add_slices()` / `remove_slice()`
- `evaluate_strategy()` / `_load_monitors_for_architect()` / `_validate_architect_references()`
- `confirm_supplementary()` / `get_supplementary_status()`
- `confirm_ready()`
- `filter_existing_monitor_ids()`

**移除 schemas:**
- `ConsultRequest` / `ConsultResponse`
- `ConfirmPlanRequest` / `ConfirmPlanResponse`
- `AddSlicesRequest`
- `StructureAnalysisResult` / `EvaluationResultResponse`
- `ConfirmSupplementaryRequest` / `ConfirmSupplementaryResponse`
- `SupplementaryStatusResponse`

**关键断言:**
- 移除后无 import 报错
- CRUD 端点不受影响
- Phase 生成端点不受影响
- export 端点不受影响

**验证:** `pnpm be:lint && pnpm be:test`
**依赖:** Steps 1-6

---

## Step 8 — 前端重构

**目标**: 策略详情页 4 阶段面板，用户全程不离开策略页。

**文件:**
- `frontend/layers/strategies/types/index.ts` (rewrite)
- `frontend/layers/strategies/composables/useStrategies.ts` (rewrite)
- `frontend/layers/strategies/pages/strategies/index.vue` (modify)
- `frontend/layers/strategies/pages/strategies/create.vue` (modify)
- `frontend/layers/strategies/pages/strategies/[id]/index.vue` (rewrite)
- `frontend/layers/strategies/components/ResearchPlanEditor.vue` (new, 替代 MonitorSuggestionsEditor)
- `frontend/layers/strategies/components/ProbeReportPanel.vue` (new)
- `frontend/layers/strategies/components/DataOverviewPanel.vue` (new)
- `frontend/layers/strategies/components/SliceAdjustModal.vue` (new)

**类型变更:**

```typescript
export type StrategyStatus =
  | 'draft' | 'planned' | 'probing' | 'collecting'
  | 'ready' | 'phase1_done' | 'phase2_done' | 'completed'

export interface Strategy {
  id: number
  name: string
  status: StrategyStatus
  brand_brief: BrandBrief | null
  research_design: ResearchDesign | null
  probe_review_result: ProbeReviewResult | null
  probe_round: number
  coverage_check_result: CoverageCheckResult | null
  output_type: string | null
  monitor_id: number | null
  task_ids: number[]
  phase1_result: Record<string, any> | null
  phase2_result: Record<string, any> | null
  phase3_result: Record<string, any> | null
  slices: SliceSummary[]
  // ...
}

export interface ResearchDesign {
  understanding_summary: string
  research_questions: ResearchQuestion[]
  data_plan: DataPlanItem[]
  slice_blueprint: SliceBlueprintItem[]
  output_type: string
  output_type_rationale: string
}
```

**useStrategies.ts 新增方法:**

```typescript
designResearch(id: number, userInput: string) → ResearchDesign
confirmResearch(id: number, request: ConfirmResearchRequest) → Strategy
getProbeStatus(id: number) → ProbeStatus
approveProbe(id: number) → Strategy
refineProbe(id: number, request: RefineProbeRequest) → Strategy
getCollectionStatus(id: number) → CollectionStatus
getDataOverview(id: number) → DataOverview
adjustSlices(id: number, request: AdjustSlicesRequest) → Strategy
```

**[id]/index.vue 4 阶段面板:**

```
① 研究设计 (draft / planned)
   - Brief 展示（只读）
   - 研究计划展示/编辑（ResearchPlanEditor）
   - [生成研究计划] / [确认并开始采集]

② 探测验证 (probing)
   - 探测进度条（轮询 probe-status）
   - 探测报告（ProbeReportPanel）
   - [全部继续] / [调整关键词] / [忽略继续]

③ 数据就绪 (collecting / ready)
   - 采集进度条（轮询 collection-status）
   - 数据全景 + 切片列表 + 覆盖度（DataOverviewPanel）
   - [微调切片] / [确认，开始生成]

④ 产出生成 (phase1_done / phase2_done / completed)
   - 现有 Phase 1/2/3 卡片（基本保留）
   - [一键生成全部] / [分步生成]
```

**验证:** `pnpm fe:typecheck && pnpm fe:lint`
**依赖:** Steps 1-7

---

## Edge Cases & Error Handling

| 场景 | 处理 |
|------|------|
| Brief 为空时生成研究计划 | brief_section 渲染 "用户未提供 Brief"，仍调 LLM |
| LLM 输出不符合 JSON | 捕获 → 500，strategy 不更新 |
| 探测任务部分失败 | 成功的正常审查，失败的标记在 probe_review_result 中 |
| 所有探测任务都不合格 | overall_verdict=fail，建议回 ① 重新设计 |
| 探测轮次达上限 (3轮) | refine_probe → 400，前端提示用户手动确认或回 ① |
| 全量采集部分任务失败 | 用已完成的任务建切片，覆盖度验证中标���数据缺口 |
| 自动建切片时 blueprint 引用的维度没有完成的任务 | 跳过该切片，在 coverage_check 中报告未覆盖的问题 |
| 快速路径（创建时带 slice_ids） | 跳过 ①②③，直接进入 ready 状态 |
| 用户在任意阶段编辑 Brief | 允许，但不影响已创建的任务（需重新确认计划才会重建） |
| 编辑 Phase 1 → 清空 Phase 2/3 | 现有行为保留 |

---

## Test Strategy

**后端 (pytest):**
- `test_strategies_model.py` — 新字段 default 值，STATUS_ORDER 覆盖 8 个值
- `test_strategies_migration.py` — 旧数据迁移后字段正确映射
- `test_strategies_service.py` — mock LLM 测试 design_research / review_probe / coverage_check 状态流转
- `test_strategies_router.py` — 新端点 happy path + 错误场景；旧端点 404 确认
- `test_agent_probe.py` — upload_result 探测模式 + 追加模式

**前端:**
- `pnpm fe:typecheck` — 所有新 interface 类型正确
- `pnpm fe:lint` — ESLint 通过

**不测试:**
- LLM prompt 质量（人工评审）
- Chain 实际 LLM 调用（mock 替代）
- 爬虫端增量采集行为（爬虫侧自行测试）

---

## Key Decisions

| 决策 | 理由 |
|------|------|
| 切片自动创建而非手动关联 | 用户不需要理解 Monitor/切片概念，减少操作步骤 |
| 探测默认自动通过 | 大多数情况 AI 设计的关键词质量 OK，不必每次打断用户 |
| coverage_check 替代 architect+evaluate | 不再需要发现未关联切片（系统自动创建），不再需要补采建议（探测已验证） |
| monitor_id 单值而非数组 | 一个策略始终只创建一个 Monitor |
| 旧字段直接删除而非保留 | 全新状态机，旧字段无法兼容，迁移脚本处理历史数据 |
| Phase 1 前置改为 status >= ready | 替代旧的 slices 非空检查，与新状态机对齐 |
| output_type 预留但 V1 不分支 | 降低首次交付复杂度，Phase chain 中只传不用 |
| probe_round 存在策略表而非任务表 | 探测轮次是策略级概念，不是单任务概念 |
