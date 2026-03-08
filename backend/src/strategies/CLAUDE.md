# Strategies 模块

策略定义模块：4 阶段流程（监测规划→数据采集→数据评估→策略生成），AI 辅助完成从需求到创意的完整策略推导。

## Public Interface

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/strategies` | 创建策略（关联切片 + 可选 Brief） |
| GET | `/strategies` | 策略列表 |
| GET | `/strategies/{id}` | 策略详情（含所有 Phase 结果） |
| PUT | `/strategies/{id}` | 更新名称/Brief |
| DELETE | `/strategies/{id}` | 删除策略 |
| POST | `/strategies/{id}/consult` | AI 生成监测方案 |
| POST | `/strategies/{id}/confirm-plan` | 确认方案→一键创建监测+任务 |
| POST | `/strategies/{id}/slices` | 批量关联切片 |
| DELETE | `/strategies/{id}/slices/{slice_id}` | 移除关联切片 |
| POST | `/strategies/{id}/evaluate` | AI 评估切片充分性 |
| POST | `/strategies/{id}/confirm-supplementary` | 确认补充采集建议 |
| GET | `/strategies/{id}/supplementary-status` | 补充采集进度 |
| POST | `/strategies/{id}/confirm-ready` | 确认数据就绪 |
| POST | `/strategies/{id}/generate/phase{1,2,3}` | 生成对应阶段 |
| PUT | `/strategies/{id}/phase{1,2,3}` | 编辑对应阶段结果 |
| GET | `/strategies/{id}/export` | 导出 Word 文档 |

### 权限

`strategy` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### 核心表

- `strategies`: 顶级实体，含 `brand_brief` / `consultation_rounds` / `slice_plan` / `evaluation_result` / `phase{1,2,3}_result` (均 JSONB) + `status` + `suggested_monitor_ids`
- `strategy_slices`: 关联表（strategy_id → slice_id），切片可来自任意监测
- `strategy_references`: 外部文档上传（Phase 3 预留，当前未启用）

### 状态流转

```
briefing → consulting → monitors_created → slices_ready → phase1_done → phase2_done → completed
```

- `briefing`: 初始状态，有 Brief 但未生成方案
- `consulting`: AI 已生成监测方案
- `monitors_created`: 用户确认方案，监测+任务已创建
- `slices_ready`: 用户确认数据就绪，解锁 Phase 1
- `phase1_done` / `phase2_done` / `completed`: 策略生成各阶段

## 切片分析模式

切片是数据分析的基本单元，策略模块的所有 Chain 都需要理解两种模式：

### 品牌聚焦切片（有 subject）

- `subject` 是分析主体（品牌/产品名），如"大魔王"、"元气森林"
- 包含 Focus 层（SWOT、竞品对比、产品健康度）
- 实体按角色分类：Target（本品）、Competitor（竞品）、Context（其他）
- 适用于：品牌诊断、竞品分析、产品口碑分析

### 大盘分析切片（无 subject）

- 没有特定分析主体，不生成 Focus 层
- 所有实体均为 Context 角色
- 适用于：行业趋势、市场大盘、场景研判、消费者需求洞察

### 切片模式在各 Chain 中的体现

| Chain | 如何使用切片模式 |
|-------|-----------------|
| Consult | `slice_plan` 输出含 `subject` 字段，指导用户创建正确模式的切片 |
| Evaluate | 传入 `mode`/`subject`/`has_focus_layer`，从组合角度判断充分性，不误判大盘切片 |
| Phase 1/2/3 | 传入 `mode`/`subject`，让 LLM 区分多切片数据的来源上下文 |

## 4 阶段流程

### A. 监测规划

1. Consult Chain 基于 Brief 生成 `monitor_suggestions` + `slice_plan`（含 subject）+ `understanding_summary`
2. 用户可编辑方案（调整关键词/平台/切片建议/切片主体）
3. `confirm_plan` 一键创建一个 Monitor + 所有 keyword×platform 任务（auto_analyze=True）

### B. 数据采集

任务自动采集+分析，用户前往监测页面查看进度并创建切片。

### C. 数据评估

1. 用户关联切片到策略
2. Evaluate Chain 评估充分性（名单级摘要，非完整分析）
3. 不足时输出 `supplementary_suggestions`（采集建议）+ `supplementary_slice_plan`（切片建议，含 subject）
4. 用户确认补充 → 在同一 Monitor 创建新任务 → 轮询进度 → 完成后引导创建切片并重新评估
5. `confirm_ready` 推进到 slices_ready

### D. 策略生成

Phase 1 → Phase 2 → Phase 3，层层递进，每步需上一步完成。

## LLM Chain 数据流

5 条 Chain 位于 `langchain/chains/strategy_*_chain.py`。

### Chain 总览

| Chain | 角色 | 模型 | 输入 | 输出 |
|-------|------|------|------|------|
| Consult | 规划师 | chat | Brief + 用户补充 | understanding_summary + monitor_suggestions + slice_plan(含subject) |
| Evaluate | 质检员 | chat | Brief + slice_plan + 切片名单级摘要(含mode/subject) | score + gap_analysis + supplementary_suggestions + supplementary_slice_plan(含subject) |
| Phase 1 | 洞察分析师 | reasoner | Brief + 咨询摘要 + 评估摘要 + 切片完整数据(含mode/subject) | social_tensions + brand_opportunities |
| Phase 2 | 策略师 | reasoner | Brief + 咨询摘要 + Phase1 + KOL/平台数据(含mode/subject) | brand_social_role + social_strategy |
| Phase 3 | 创意总监 | reasoner | Brief + 咨询摘要 + Phase1+2 + 内容特征(含mode/subject) | big_idea + content_strategy |

### 关键设计决策

1. **不使用切片报告作为输入**：报告是对结构化数据的 LLM 叙事总结，避免 LLM→LLM 二手信息传递
2. **每个 Phase 精选不同字段**：控制 token 量（~30K），按产出目标选择数据
3. **空字段兼容**：所有 Chain 的 format 函数对缺失字段返回空/跳过，不报错
4. **评估链传名单而非数值**：只传实体 name/role、话题 name/category 等，够判断覆盖度，不做深度分析
5. **understanding_summary 贯穿全链**：咨询链输出的需求理解摘要，存入 consultation_rounds，Phase 1/2/3 均可引用
6. **切片模式贯穿全链**：所有 Chain 传入 `mode`（品牌聚焦/大盘分析）+ `subject`，确保 LLM 正确理解每个切片的定位和数据来源

### Evaluate Chain 读取的切片字段

名单级摘要（判断覆盖度，非分析）：
- `meta.subject`（品牌聚焦主体，空=大盘分析）, `meta.competitors`, `meta.scope.keywords`
- `AnalysisSlice.name`（切片命名，由 service 层 `load_slice_data_with_names()` 额外传入）
- `overview.total_posts`, `unique_platform_volume`
- `aligned_entities[:10]` → name, role（品牌切片有 Target/Competitor/Context；大盘切片全为 Context）
- `aligned_topics[:15]` → name, category
- `sov_ranking[:10]` → name
- `topic_radar.pains/gains/controversies` → name
- `layers.focus` 存在性 → `has_focus_layer`（仅品牌聚焦切片有）

评估链理解两种切片模式，从组合角度判断数据充分性。

### Phase 1 读取的切片字段（洞察层）

Social Tension 来源：`topic_radar.pains` / `controversies` / `unmet_needs` / `aligned_topics`
Brand Opportunity 来源：`sov_ranking` / `focus.swot`(+delta) / `focus.gap` / `topic_radar.gains` / `entities.top_issues`

### Phase 2 读取的切片字段（策略层）

`kol_voices` / `overview.unique_platform_volume` / `platform_dna`(name/role/platform_shares)

> 已移除 `time_distribution`：采集样本的时间分布可能误导 LLM 的节奏建议

### Phase 3 读取的切片字段（创意层）

`kol_voices` / `topic_aspects` / `aligned_entities[:20].top_features`

> 已移除 `ipa_analysis`：切片级 IPA 计算已删除（维度不一致 + 与现有数据冗余）

## 补充采集闭环

当评估 score < 0.6 时：
1. 评估链输出 `supplementary_suggestions`（采集建议）+ `supplementary_slice_plan`（切片建议，含 subject）
2. `confirm_supplementary` 在现有 Monitor 上创建新任务，任务 ID 存入 `evaluation_result.pending_supplementary_task_ids`
3. 前端轮询 `supplementary-status` 端点查进度
4. 完成后引导用户创建/调整切片 → 回来关联 → 重新评估（可循环）
5. 无需 DB 迁移，所有状态存在 `evaluation_result` JSONB 中

## Important Notes

- Strategy 是与 Monitor 平级的顶级实体，通过 `strategy_slices` 关联任意监测的切片
- `confirm_plan` 为每个策略创建一个 Monitor，所有任务放同一 Monitor 便于交叉分析
- 生成 Phase 2 要求 Phase 1 已完成（status >= phase1_done），Phase 3 同理
- `service.py` 中 `load_slice_data()` 直接读切片 `result_data` JSONB 字段，不回查帖子数据库
- `load_slice_data_with_names()` 额外返回切片名称，专供评估链使用
- Word 导出依赖 `python-docx`，仅在 Docker 容器内安装
- `consultation_rounds` 覆盖式存储，只保留最新一次咨询结果
