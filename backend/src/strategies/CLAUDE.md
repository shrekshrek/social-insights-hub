# Strategies 模块

策略定义模块：基于切片数据，AI 3 阶段生成社交传播策略（洞察→策略→创意）。

## Public Interface

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/strategies` | 创建策略（关联切片 + 可选 Brief） |
| GET | `/strategies` | 策略列表 |
| GET | `/strategies/{id}` | 策略详情（含所有 Phase 结果） |
| PUT | `/strategies/{id}` | 更新名称/Brief |
| DELETE | `/strategies/{id}` | 删除策略 |
| POST | `/strategies/{id}/generate/phase{1,2,3}` | 生成对应阶段 |
| PUT | `/strategies/{id}/phase{1,2,3}` | 编辑对应阶段结果 |
| GET | `/strategies/{id}/export` | 导出 Word 文档 |

### 权限

`strategy` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### 核心表

- `strategies`: 顶级实体，含 `brand_brief` (JSONB) + `phase{1,2,3}_result` (JSONB) + `status` 枚举
- `strategy_slices`: 关联表（strategy_id → slice_id），切片可来自��意项目
- `strategy_references`: 外部文档上传（Phase 3 预留，当前未启用）

### 状态流转

`draft` → `phase1_done` → `phase2_done` → `completed`

生成 Phase N 时自动更新状态。编辑已完成的 Phase 不改变状态。

## LLM Chain 数据依赖

3 条 Chain 位于 `langchain/chains/strategy_phase{1,2,3}_chain.py`。

### 关键设计决策

1. **不使用切片报告作为输入**：报告是对结构化数据的 LLM 叙事总结，避免 LLM→LLM 二手信息传递
2. **每个 Phase 精选不同字段**：控制 token 量（~30K），按产物目标选择数据
3. **空字段兼容**：所有 Chain 的 format 函数对缺失字段返回空/跳过，不报错

### Phase 1 读取的切片字段（洞察层）

Social Tension 来源：`topic_radar.pains` / `controversies` / `unmet_needs` / `aligned_topics`
Brand Opportunity 来源：`sov_ranking` / `focus.swot`(+delta) / `focus.gap` / `topic_radar.gains` / `entities.top_issues`

### Phase 2 读取的切片字段（策略层）

`kol_voices`⚠️ / `time_distribution`⚠️ / `overview.unique_platform_volume` / `platform_dna`(name/role/platform_shares)

### Phase 3 读取的切片字段（创意层）

`kol_voices`⚠️ / `ipa_analysis`⚠️ / `topic_aspects` / `aligned_entities[:20].top_features`

> ⚠️ 标记字段待切片流水线补全，方案见 `docs/plans/2026-03-05-slice-pipeline-enrichment-design.md`

## Important Notes

- Strategy 是与 Project 平级的顶级实体，通过 `strategy_slices` 关联任意项目的切片
- 生成 Phase 2 要求 Phase 1 已完成（status >= phase1_done），Phase 3 同理
- `service.py` 中 `_load_slice_data()` 直接读切片 `result_data` JSONB 字段，不回查帖子数据库
- Word 导出依赖 `python-docx`，仅在 Docker 容器内安装
