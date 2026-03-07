# 补充采集闭环：评估 → 补充 → 重新评估

## Context

策略流程 Stage C（数据评估）评估数据充分性后，当 score < 0.75 时 LLM 会输出 `supplementary_tasks`（推荐补充采集的平台+关键词），但：
- 前端**完全不展示** supplementary_tasks
- **没有**从评估结果创建补充任务的能力
- 用户只能手动回到���测管理页面创建任务

本次实现完整闭环：评估不足 → 展示可编辑补充建议 → 确认创建任务 → 采集分析 → 一键切片+重新评估。

## 方案概览

```
评估 → score < 0.75 → 展示 supplementary_suggestions（可编辑）
  ↓
用户编辑确认 → POST /strategies/{id}/confirm-supplementary
  → 创建任务到现有 Monitor（复用 confirm_plan 的任务创建逻辑）
  → 任务 ID 存入 evaluation_result.pending_supplementary_task_ids
  ↓
任务自动采集+分析（已有 auto_analyze 流水线）
  ↓
前端轮询任务状态 → 全部完成后提示
  ↓
提示"补充采集完成，前往监测页面创建/调整切片"（附链接）
  ↓
用户手动：创建/调整切片 → 回来关联切片 → 重新评估
（若仍不足可再次补充，循环）
```

**为什么切片不自动创建？**
- 补充数据可能需要和已有任务重新组合（如把新的微博数据合并到已有切片）
- 切片分组是语义决策，需要人工判断
- 沿用现有的手动切片流程，不增加系统复杂度

**关键设计决策**：
- 补充任务挂到**同一个 Monitor**（策略只关联一个监测）
- 无需 DB 迁移（补充任务 ID 存在现有 `evaluation_result` JSON 字段中）
- 前端驱动（轮询+按钮），不在 Celery 任务中耦合策略逻辑

---

## Step 1: 评估链 Prompt 约束

**文件**: `backend/src/langchain/chains/strategy_evaluate_chain.py`

- `supplementary_tasks` 重命名为 `supplementary_suggestions`
- 输出格式对齐咨询链的 `monitor_suggestions`：
  ```json
  { "name": "补充名称", "platforms": ["xiaohongshu"], "keywords": ["kw1", "kw2"], "rationale": "原因" }
  ```
- 添加约束：最多 2-3 条建议，每条 2-3 个关键词、1-2 个平台
- 添加约束：只补缺失维度，不重复已有数据
- `parse_evaluate_response` 直接使用新字段名 `supplementary_suggestions`，不兼容旧名

## Step 2: 后端 Schema

**文件**: `backend/src/strategies/schemas.py`

- `EvaluationResultResponse.supplementary_tasks` → 直接改为 `supplementary_suggestions`，删除旧字段
- 新增 `ConfirmSupplementaryRequest`（monitor_suggestions + notes_per_task）
- 新增 `ConfirmSupplementaryResponse`（created_task_ids, task_count, partial_errors, strategy）
- 新增 `SupplementaryStatusResponse`（total, completed, pending, all_done, completed_task_ids）

## Step 3: 后端 Service — 3 个新函数

**文件**: `backend/src/strategies/service.py`

### 3a. `confirm_supplementary()`
- 从 `strategy.suggested_monitor_ids[0]` 获取现有 Monitor
- 复用 `confirm_plan` 的 keyword×platform 任务创建逻辑（不创建新 Monitor）
- 创建的任务 ID 存入 `evaluation_result["pending_supplementary_task_ids"]`
- 使用 `flag_modified` 持久化

### 3b. `get_supplementary_status()`
- 读取 `pending_supplementary_task_ids`
- 查询任务状态，返回完成进度

## Step 4: 后端 Router — 2 个新端点

**文件**: `backend/src/strategies/router.py`

| 方法 | 路径 | 函数 |
|------|------|------|
| POST | `/{id}/confirm-supplementary` | confirm_supplementary |
| GET | `/{id}/supplementary-status` | get_supplementary_status |

## Step 5: 前端抽取共享编辑组件

**新文件**: `frontend/layers/strategies/components/MonitorSuggestionsEditor.vue`

从 `[id]/index.vue` 的 Stage A 编辑 UI（lines 174-310）抽取为独立组件：
- Props: `suggestions`（v-model）, `notesPerTask`（v-model）, `editing`（是否编辑模式）
- 内含：tag 关键词、checkbox 平台、采集量选择器、预估任务数
- Stage A 和 Stage C 补充建议共用此组件

当前 `[id]/index.vue` 已 926 行，超过 800 行上限，抽组件势在必行。

## Step 6: 前端类型 + Composable

**文件**: `frontend/layers/strategies/types/index.ts`
- 更新 `EvaluationResult`：添加 `supplementary_suggestions`, `pending_supplementary_task_ids`

**文件**: `frontend/layers/strategies/composables/useStrategies.ts`
- 添加 `confirmSupplementary(id, suggestions, notesPerTask)`
- 添加 `getSupplementaryStatus(id)`

## Step 7: 前端 Stage C UI

**文件**: `frontend/layers/strategies/pages/strategies/[id]/index.vue`

在评估结果（gap_analysis）下方，根据状态显示不同内容：

**状态 1: 评估不足 + 有 supplementary_suggestions + 未确认补充**
- 使用 `MonitorSuggestionsEditor` 展示可编辑补充建议
- "确认补充采集" 按钮

**状态 2: 补充采集进行中（有 pending_supplementary_task_ids 且未全部完成）**
- "补充采集进行中 X/Y 已完成" 进度提示
- 每 10 秒轮询 `getSupplementaryStatus`

**状态 3: 补充任务全部完成**
- 显示"补充采集完成"提示 + 前往监测页面的链接
- 引导用户：创建/调整切片 → 回来关联 → 重新评估（沿用现有 Stage C 流程）

---

## 验证方案

1. 后端: `pnpm be:lint` + `pnpm be:test`
2. 前端: `pnpm fe:typecheck` + `pnpm fe:lint`
3. 手动测试流程：
   - 打开现有策略（ID=5），Stage C 评估已显示 40% 不足
   - 确认可以看到补充建议并编辑
   - 确认补充采集后检查任务是否创建在同一 Monitor
   - 等待任务完成后点击"生成切片并重新评估"
   - 确认新评估分数更新
