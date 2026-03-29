# Strategies 模块

策略研究引擎：4 阶段自动化流程（研究设计→探测验证→数据就绪→产出生成），用户全程留在策略页面，系统自动编排 Monitor 创建、任务管理、切片创建。

## Public Interface

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/strategies` | 创建策略（关联切片 + 可选 Brief） |
| GET | `/strategies` | 策略列表 |
| GET | `/strategies/{id}` | 策略详情 |
| PUT | `/strategies/{id}` | 更新名称/Brief |
| DELETE | `/strategies/{id}` | 删除策略 |
| POST | `/strategies/{id}/design-research` | AI 生成研究计划 |
| POST | `/strategies/{id}/confirm-research` | 确认计划→创建 Monitor + 探测任务 |
| GET | `/strategies/{id}/probe-status` | 探测进度 + 自动审查触发 |
| POST | `/strategies/{id}/approve-probe` | 手动确认探测通过 |
| POST | `/strategies/{id}/refine-probe` | 调整关键词，创建新探测任务 |
| GET | `/strategies/{id}/collection-status` | 全量采集进度 + 自动建切片 |
| GET | `/strategies/{id}/data-overview` | 数据全景（切片 + 覆盖度） |
| POST | `/strategies/{id}/adjust-slices` | 微调切片配置 |
| POST | `/strategies/{id}/generate/phase{1,2,3}` | 生成对应阶段 |
| PUT | `/strategies/{id}/phase{1,2,3}` | 编辑对应阶段结果 |
| GET | `/strategies/{id}/export` | 导出 Word 文档 |
| POST | `/strategies/parse-brief` | 上传 Brief 文档 AI 解析 |

### 权限

`strategy` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### 核心表

- `strategies`: 顶级实体，含 `brand_brief` / `research_design` / `probe_review_result` / `coverage_check_result` / `phase{1,2,3}_result` (均 JSONB) + `status` + `monitor_id` (FK) + `task_ids` (JSONB 数组)
- `strategy_slices`: 关联表（strategy_id → slice_id），切片由系统自动创建

### 状态流转

```
draft → planned → probing → collecting → ready → phase1_done → phase2_done → completed
```

- `draft`: 初始状态，有 Brief 但未生成研究计划
- `planned`: AI 已生成研究计划（research_design）
- `probing`: 用户确认计划，探测任务已创建，等待数据
- `collecting`: 探测通过，全量采集进行中
- `ready`: 切片已创建且覆盖度验证通过
- `phase1_done` / `phase2_done` / `completed`: 策略生成各阶段

## 4 阶段流程

### ① 研究设计 (draft → planned → probing)

1. `design-research`: research_design_chain 基于 Brief 生成研究问题 + 数据采集方案 + 切片蓝图 + 产出类型
2. 用户可编辑 data_plan（关键词/平台）和 slice_blueprint（切片名/主体）
3. `confirm-research`: 创建一个 Monitor + 所有 keyword×platform 的 phase="probe" 任务（设置 max_pages 限制翻页），状态 → probing

### ② 探测验证 (probing → collecting)

1. 前端轮询 `probe-status`，爬虫采集约 20 条（受 max_pages 限制），跳过评论
2. 所有任务分析完成后自动运行 probe_review_chain
3. `all_pass` → 自动调用 approve_probe，为每个探测任务创建 phase="collect" 全量任务，策略 → collecting
4. `partial_pass/fail` → 用户可 `approve-probe`（跳过审查直接全量）或 `refine-probe`（替换关键词，probe_round++，最多 3 轮）

### ③ 数据就绪 (collecting → ready)

1. 前端轮询 `collection-status`，爬虫采集全量数据（50 条 + 评论）
2. 所有全量任务分析完成后自动按 slice_blueprint 创建切片
3. 切片就绪后自动运行 coverage_check_chain 验证覆盖度
4. `overall_ready=true` → 状态 → ready
5. 用户可 `adjust-slices` 微调切片配置（触发重新验证）

### ④ 产出生成 (ready → completed)

Phase 1 → Phase 2 → Phase 3，层层递进，每步需上一步完成。

## LLM Chain

7 条 Chain 位于 `langchain/chains/strategy_*_chain.py`。

| Chain | 角色 | 触发时机 |
|-------|------|---------|
| brief_parser_chain | Brief 摄入 + 渠道分发判断 | 新建策略时（`parse-brief` 端点） |
| research_design_chain | 研究规划师（接收社媒 channel_brief） | ① |
| probe_review_chain | 数据质检员 | ② |
| coverage_check_chain | 覆盖度验证 | ③ |
| phase1_chain | 洞察分析师 | ④ |
| phase2_chain | 策略师 | ④ |
| phase3_chain | 创意总监 | ④ |

Phase 1/2/3 Chain 均注入 `research_design` 中的 research_questions 作为分析上下文。

## Agent 协议

云端通过 Agent API 向爬虫下发任务，爬虫轮询获取并执行：

```
爬虫轮询 → GET /api/v1/agent/tasks/pending
         → 返回 status="pending" 的任务
         → 接受任务 → 采集 → 上传结果 → status="completed"
```

任务类型：
- **探测任务**（phase="probe"）：max_pages 限制翻页，跳过评论，约 20 条
- **全量任务**（phase="collect"）：采集完整数据（50 条 + 评论）
- **普通任务**：一次性采集到 max_notes_count 指定数量

## Important Notes

- Strategy 通过 `strategy_slices` 关联切片，切片由 `_create_auto_slices` 按 `slice_blueprint` 自动创建
- `confirm_research` 为每个策略创建一个 Monitor，所有任务放同一 Monitor
- `_task_dimension_map` 存在 `research_design` 中，记录 task_id → dimension_name 映射，供自动建切片使用
- `probe-status` 和 `collection-status` 是轮询端点，全部完成后自动触发下游逻辑（LLM 审查/建切片/覆盖度验证）
- Word 导出依赖 `python-docx`
