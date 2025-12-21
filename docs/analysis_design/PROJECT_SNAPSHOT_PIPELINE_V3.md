# 项目级快照分析流水线 V3（多平台 × 多关键词 × 多任务）(Project Snapshot Pipeline)

> **目标**：用户多选任务生成一个“项目快照”，在**平台/关键词/时间窗**都可能不同的情况下，仍能给出**口径统一、可追溯证据**的整合分析。

## 1. 核心原则

1. **先拼图，后解释**：先用程序化逻辑把多任务数据拼成“结构化摘要”（带证据指针），再让 LLM 做归因/叙事/策略。
2. **稳定轴优先**：项目级对齐优先级是 `品牌/品类`、`话题维度(category)`、`平台`、`时间`，而不是 task 内的 `role(Target/Competitor)`。
3. **证据可回溯**：每个结论必须能回溯到一组帖子（至少样本），并能标注来自哪个任务/平台/关键词。
4. **不强行全局 Target**：多关键词任务合并时，task-level `role` 会漂移；项目级应提供“模式化视角”，按模式再计算 project-level role。

## 2. 快照模式（产品侧强建议）

生成快照时，用户选择一个模式（或默认自动判定）：

| 模式 | 适用场景 | 主轴 | `Target/Competitor` 口径 |
|---|---|---|---|
| **Landscape（品牌对比）** | 选了多个品牌词任务（XPEL/3M/威固…） | `品牌/系列(parent)` | **不输出全局 Target**，只做品牌维度对比 |
| **Focus（单品牌聚焦）** | 用户指定 1 个主体品牌 | `主体品牌 vs 其它品牌` | project-level 重算：主体=Target，其它=Competitor |
| **Intent（类目/意图）** | 选了泛词/类目词 + 若干品牌词 | `意图/需求 → 品牌承接` | 不依赖 task role，改用“类目-品牌”承接关系 |

> 说明：task-level role 仍可保留为 `role_breakdown`（弱信号），用于解释“该任务语境下主体是谁”，但不作为项目级真值。

### 2.1 会生成 3 种不同的结果吗？

不是“3 套完全不同的数据结构”，而是**同一套快照结构**（步骤0–步骤4）在步骤3/步骤4 的“重点与附加模块”不同：

- **公共输出（所有模式都有）**：去重统计、全局 buckets（实体/话题）、平台/关键词分布、象限、基础榜单、（可选）归一化与对齐后的榜单。
- **Landscape**：强调品牌版图（SOV）、品牌间差异点、跨平台对比；不强行计算全局 Target。
- **Focus**：强调“主体品牌”的问题/优势/竞品对比，并输出 `project_role`（Target/Competitor）与置信度/证据样本。
- **Intent**：强调“需求/意图 → 品牌承接”，输出需求维度下的品牌占位、对应卖点/痛点与证据样本。

### 2.2 自动判定（推荐规则）

自动判定的目标是给用户一个**默认推荐**，且必须允许用户手动覆盖。建议规则尽量“可解释、可复现”：

1. **任务分类**（brand-task vs intent-task）
   - `brand-task`：任务关键词（或任务名）是单一品牌词的概率高。
     - 典型特征：关键词数量=1、词形短（如 “XPEL/3M/威固/龙膜”）、且在该任务的 `aggregated_entities` 中能找到同名品牌实体/或其 `tags.parent` 作为主品牌归属（弱信号）。
   - `intent-task`：关键词是类目词/泛需求词、或多关键词组合。
     - 典型特征：关键词数量>1，或包含“车膜/窗膜/车衣/贴膜”等泛词，或 `aggregated_entities` 出现多个品牌且无明显单一主品牌集中。

2. **品牌簇与占比**
   - 从 `brand-task` 提取候选品牌（按归一化名称去重），得到 `brand_clusters`。
  - 计算 `brand_coverage`：brand-task 数量占比；以及 `brand_heat_share`：brand-task 对总 heat/mentions 的贡献占比（用步骤1汇总即可算）。

3. **判定规则（从强到弱）**
   - **Focus**：`brand_clusters == 1` 且 `brand_heat_share >= 0.55`（或 brand-task 数量占比 >= 0.6）。
   - **Landscape**：`brand_clusters >= 2` 且 `brand_heat_share >= 0.6`（品牌对比成为主问题）。
   - **Intent（兜底）**：其它情况（尤其是 intent-task 占主导，或 brand 与 intent 混杂但无明显单一品牌主导）。

4. **平局/混合的处理**
  - 若 `brand_clusters >= 2` 且 intent-task 也很多：默认仍选 **Landscape**，但步骤3同时输出“Intent 承接”作为附加模块。
   - 若 `brand_clusters == 1` 但 intent-task 很多且 `brand_heat_share < 0.55`：默认选 **Intent**，并在 Intent 中标注该品牌作为“候选聚焦品牌”（供用户一键切换 Focus）。

## 3. 输入数据（来自任务级聚合结果）

项目快照只依赖每个任务的 `DataTask.analysis_result` 里的 canonical 字段：

- `aggregated_entities`（Top40，含 `post_ids` 与属性桶）
- `aggregated_opinions`（Top60，含 `post_ids` 与来源分布）
- `meta/metrics/charts/freshness`（用于总体声量/象限/时效）

## 4. 流水线总览（独立方案的步骤编号）

```mermaid
flowchart TD
  U[用户选择任务 + 模式] --> S0[步骤0: 选集与去重计划]
  S0 --> S1[步骤1: 程序拼图预聚合<br/>(跨任务 buckets + 分布 + 证据)]
  S1 --> S2[步骤2: 项目级归一化<br/>(实体别名/话题别名/类目对齐)]
  S2 --> S3[步骤3: 派生分析<br/>(DNA/对比/承接/风险/网络)]
  S3 --> S4[步骤4: LLM 总结（可选）<br/>(叙事/归因/策略)]
```

## 5. 步骤0：选集与去重计划（多任务重复内容）

跨任务可能重复抓到同一帖子（尤其是不同关键词都命中同一内容）。项目级建议使用**跨任务唯一证据 ID** 去重：

- 推荐：`(platform, post_id_on_platform)`（见 `SocialPost.post_id_on_platform`）
- 退化：`(task_id, post_id)`（实现简单但可能重复计权）

输出建议包含：

- `dedup_mode`：`platform_post_id` / `task_post_id`
- `raw_evidence_count`：所有任务证据之和
- `unique_evidence_count`：去重后唯一证据数

## 6. 步骤1：程序拼图预聚合（跨任务 buckets）

目标：把任务级 `aggregated_entities/aggregated_opinions` 合并成项目级 buckets，并保留可解释与可追溯的信息。

**输出建议**：

- `platform_distribution / keyword_distribution`：按 mentions 加权的贡献分布
- `post_ids_sample`：样本证据（用于 UI 回溯/LLM 总结）
- `quadrant`：按全局 `avg_cii` 重新计算象限标签（统一口径）
- `topic_aspects`：按 `category` 汇总观点维度（heat/情感/分布）
- `entity_graph`：TopN 实体共现网络（用于竞争格局/叙事团簇）

> 说明：这一步尽量纯程序化，保证稳定可复现。

## 7. 步骤2：项目级归一化（让跨任务可比）

目标：消除跨任务的“语言隔阂”（同义实体/同义观点/类目漂移），产出 `details_aligned` 作为**统一展示口径**。

### 7.1 实体别名归一（Entity Alias）

目的：合并跨任务同义实体，产出 `entity_mapping` 与 `entities_aligned`。

建议策略：
1. 程序预聚类（字符串相似度）降低候选规模
2. LLM 归一（同义合并）
3. 输出 `role_breakdown/type_breakdown`，不要直接输出“唯一 role”

### 7.2 观点别名归一（Opinion Alias）

目的：先做类目对齐，再在类目内合并同义观点短语，产出 `topic_mapping_by_category` 与 `topics_aligned`。

建议策略：
1. 类目对齐（category normalization）：把松散类目映射到稳定维度（如“价格/费用/预算”→“价格”）
2. 类目内并行：程序相似度合并 + LLM 语义合并

### 7.3 多关键词下的 role 问题（重要）

实体归一链里的 `role(Target/Competitor/Context)` 是围绕“锚点关键词”打的标签，跨关键词会漂移：

- **Landscape / Intent**：不要用 task-level role 做项目级结论；可保留为 breakdown 解释语境。
- **Focus**：由用户指定“主体品牌集合”，项目级重算 role（规则优先、LLM 兜底）。

## 8. 步骤3：派生分析（项目级更该回答的问题）

在 `entities_aligned/topics_aligned` 的统一口径上，推荐优先输出以下“结构化洞察”：

1. **品牌版图（SOV）**：品牌/系列的 `heat/mentions/sentiment` + 平台/关键词分布
2. **平台 DNA**：同一品牌/同一话题维度在不同平台的权重偏离（差异化投放依据）
3. **类目/意图承接（Intent 模式）**：泛词任务中的需求点 → 哪些品牌/卖点在承接
4. **风险清单**：高热负向话题/问题 + 证据集合（`post_ids_sample`）
5. **叙事团簇**：实体/话题的共现网络 + 团簇（用于“讨论结构”而非趋势拟合）

> 建议同时输出两套口径：`absolute`（总量）与 `normalized`（按任务规模/平台规模标准化），避免大任务淹没小任务。

## 9. 步骤4：LLM 总结（可选，严格输入约束）

LLM 只做“解释”，不做“裁决”：

- 输入：结构化摘要 + 证据样本（每类 TopN）
- 输出：叙事与归因（为什么在某平台更突出）、策略建议（按平台/受众差异）

避免：把全量原文直接交给 LLM（成本高、幻觉风险更大、不可复现）。

## 10. 结果数据结构（推荐读法）

无论选择哪种快照模式，**输出结构保持一致**，差异只体现在：
- 哪些模块被执行（以及是否 `skipped`）
- 哪些字段被填充（以及证据样本的选择策略）

推荐将输出分为 5 个区块，对应步骤0~4：

```json
{
  "meta": {
    "project_id": 1,
    "generated_at": "ISO",
    "mode": "landscape|focus|intent",
    "scope": {
      "included_task_ids": [1, 2, 3],
      "platforms": [],
      "keywords": []
    }
  },
  "step0_dedup": {
    "dedup_mode": "platform_post_id|task_post_id",
    "raw_evidence_count": 0,
    "unique_evidence_count": 0
  },
  "step1_merged": {
    "overview": { "total_volume": 0, "global_sentiment": 0.0, "platform_volume": {}, "keyword_volume": {} },
    "charts": { "quadrant": [], "quadrant_summary": {}, "entity_graph": {} },
    "details": { "top_entities": [], "top_topics": [], "topic_aspects": [] }
  },
  "step2_normalized": {
    "status": "completed|skipped|failed",
    "entity_alias": { "mapping": {}, "top_entities": [] },
    "opinion_alias": { "category_map": {}, "mapping_by_category": {}, "top_topics": [] }
  },
  "step3_derived": {
    "status": "completed|skipped|failed",
    "outputs": {
      "brand_landscape": {},
      "platform_dna": {},
      "intent_handoff": {},
      "risk_list": {},
      "clusters": {}
    }
  },
  "step4_summary": {
    "status": "completed|skipped|failed",
    "executive_summary": "",
    "highlights": [],
    "suggestions": []
  }
}
```

## 11. 备注：为何要有“步骤编号”？

这里只是为了把流程拆成可实现、可校验的模块，不依赖任何既有文档命名；你也可以把“步骤0~4”理解为：
- 先解决“数据重复与口径不一致”（步骤0~2）
- 再输出“可操作洞察”（步骤3）
- 最后做“解释与建议”（步骤4，可选）
