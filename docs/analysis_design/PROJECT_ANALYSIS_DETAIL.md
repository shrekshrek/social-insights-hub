# 项目级多任务整合分析方案（工程细化版）

> 本文档是任务级深度分析方案的上层设计，面向“一个项目包含多个任务”的 **Project-Level Analysis**。
>
> - 任务级分析产物详见：`docs/analysis_design/TASK_ANALYSIS_DETAIL.md`
> - 衍生分析（IPA/关联网络/竞品雷达）详见：`docs/analysis_design/DERIVED_ANALYSIS_DESIGN.md`
>
> **本设计的关键新增点**：
> - **默认全量**：项目级分析默认覆盖项目下所有任务（子任务）。
> - **可选过滤层**：同一项目支持按条件（时间/平台/关键词等）生成“子集分析”用于对比。
> - **项目级归一化字典**：由于任务间归一化不稳定，引入“字典沉淀 + 增量更新（仅字典）”，LLM 只做裁判而非全量重跑。

---

## 1. 目标与约束

### 1.1 目标
- **跨任务融合**：将各任务的 `aggregated_entities` / `aggregated_opinions` 在项目级再次归并，产出稳定的项目级 Top 实体/话题、结构洞察、趋势与对比视图。
- **可追溯**：任何项目级条目都能追溯到 `task_id` 与 `post_ids`（必要时进一步到平台与原文）。
- **轻量健壮**：利用小样本特性（单任务~100篇），采用“全量重算”策略，确保数据绝对一致。

### 1.2 约束
- **默认全量**：默认分析范围为项目下全部任务数据，不做时间窗限制（但过滤层可选）。
- **任务间归一化不稳定**：不同任务内的 canonical/alias 可能不一致，需项目级字典兜底。
- **轻量重算优先**：因数据量级较小（单任务~100篇），优先采用“手动生成快照 + 全量重算”而非复杂增量（增量仅用于字典）。

---

## 2. 输入数据与优先级

项目级分析的主数据源来自任务级分析结果（存储在 `DataTask.analysis_result`）。

### 2.1 一等输入（强烈推荐）
- `analysis_result.aggregated_entities`：任务内已融合实体（含 `post_ids`、`original_terms`、维度项与来源追溯）
- `analysis_result.aggregated_opinions`：任务内已融合观点（含 `post_ids`、`original_terms`）
- `analysis_result.meta`：`task_id`、`analyzed_at`、`keywords`、`data_volume` 等

> 设计原则：**项目级不从原始帖子重新抽取实体/观点**，只对“聚合物”再聚合。

### 2.2 二等输入（补充/展示）
- `analysis_result.insights.top_entities / top_topics`
- `analysis_result.charts.*` 与 `freshness`

> 二等输入可用于快速展示或复用任务级图表，但不作为跨任务再聚合的主料。

---

## 3. 默认全量 + 可选过滤层（Project Scope）

### 3.1 默认全量
项目级分析的默认范围为：
- 项目 `project_id` 下所有任务（已完成聚合分析的任务）
- 每个任务使用其最新一次 `analysis_result`（或按版本号/时间戳取最新）

### 3.2 可选过滤层（子集分析）
在不改变默认全量的前提下，提供可选过滤条件，生成项目的“切片分析（Slice Analysis）”：
- **按时间**：按任务的 `meta.analyzed_at` 或任务的数据 `published_at`（若可取）
- **按平台**：微博/小红书/抖音/B站等（基于任务平台字段或原始帖子 platform）
- **按关键词组**：同一项目可能包含不同关键词任务，用于对比“认知差异”
- **按实体角色**：只看 target / competitor / other（实体维度）
- **按情感**：只看负面 / 正面（观点维度）

### 3.3 过滤层产出与对比方式
本项目采用“**任务列表勾选**”作为过滤与对比的最小交互单元：
- 用户在项目级任务列表中（本地筛选后）勾选多个任务。
- 点击“生成快照”，后端按 `task_ids[]` 将这些任务做合并分析并保存为一份快照结果。

> 说明：由于单任务样本量上限约 100 篇，项目级总量通常 < 10k，不需要额外的 URL query 筛选协议与缓存切片；用“勾选任务”即可满足对比与复现。

---

## 4. 项目级归一化字典（Project Dictionary）

### 4.1 背景
任务级的 `build_similarity_mapping` 是“任务内归一化”，跨任务时仍会出现：
- 同义不同名：`iPhone16` / `苹果16` / `iPhone 16`
- 粒度不一致：`续航` vs `续航能力` vs `电池`
- 观点表达差异：`价格贵` vs `定价太高`（但都属于“价格-负面”）

因此项目级必须引入“稳定映射”，避免项目级统计被拆分。

### 4.2 设计目标
- **稳定**：相同 alias 在项目内永远映射到同一 canonical（版本可控）
- **增量**：新 alias 出现时才触发 LLM 裁决
- **可审计**：保存裁决理由/置信度/时间/模型版本

### 4.3 流程：候选聚类（程序）→ LLM 裁决（少量）→ 字典沉淀（持久化）
1. **候选收集**：拉平项目下所有任务的 `aggregated_entities.name` 与 `original_terms[].text`（观点同理）
2. **程序预聚类**（非 LLM）：
   - 规则标准化：空格/大小写/全半角/括号/常见后缀
   - 字符相似度：SequenceMatcher / 编辑距离
   - 业务规则：型号数字、品牌词、同义词表（可配置）
3. **LLM 裁决**（对“疑似同义簇”做判断）：
   - 输入：簇内候选 + 任务上下文（可选：category/type/role）
   - 输出：`canonical_name`、`aliases[]`、`confidence`、`rationale`
4. **写入字典表**：
   - alias → canonical_id（实体/观点分别建表）
   - 同时记录来源任务、模型版本、置信度
5. **项目级聚合统一走字典**：
   - 所有 items 先映射 canonical，再累计 heat/mentions/score/original_terms/post_ids/source_tasks

### 4.4 观点字典的“情感维度口径”
建议：**观点 canonical key = canonical_name + sentiment**（同名但正负不同应拆分）
- 例：`价格` + `-1` 与 `价格` + `+1` 分开统计

### 4.5 字典的回滚与人工介入（可选）
可选建设一个轻量管理页：
- 查看最近 LLM 合并记录
- 支持“驳回合并 / 重新裁决 / 手工指定 canonical”

> 若短期不做管理页，至少保证字典表有 `disabled_at` 或 `version` 字段可回滚。

---

## 5. 项目级聚合逻辑（Primary → Project Aggregation）

### 5.1 聚合键
- **实体**：`entity_canonical_id`（由项目字典映射得到）
- **观点**：`topic_canonical_id + sentiment`

### 5.2 指标合并
对同一 canonical：
- `heat`：跨任务累加（必要时可加“时间衰减权重”，默认不启用）
- `mentions`：跨任务唯一帖子数（建议以 `post_id` 去重；如果任务之间 post_id 不共享命名空间，则用 `(task_id, post_id)` 作为唯一键）
- `score`：建议重新计算 `heat * log(mentions + 1)`（保持与任务级一致）
- `original_terms`：按 `text` 聚合累加 count，按 count 排序（展示层仍截断 15）
- `source_tasks`：记录来源任务统计（mentions/heat/post_ids_sample）

### 5.3 可追溯性设计
为避免项目级结果过大，建议分层保存：
- **主结果**：每个条目保留 `post_ids_sample`（例如 top 50）与 `source_tasks` 摘要
- **证据索引**：另存或按需查询接口返回全量 `post_ids`（支持分页/筛选）

---

## 6. 项目级“可选过滤层”的实现建议

### 6.1 推荐模式：任务勾选 + 手动生成快照
鉴于单任务样本量（~100篇）较小，项目级分析采用最简单稳定的交互：
- 前端展示项目下任务列表，支持本地筛选（平台/时间/关键词等）方便勾选。
- 用户勾选 `task_ids[]` 后，点击“生成合并分析快照”。
- 后端仅接收 `task_ids[]`，按任务级 `aggregated_*` 做合并分析，返回并保存一份快照。

> 仅当未来出现“项目内任务数量极大（>500）且频繁交互筛选”的场景，再考虑引入更复杂的筛选协议或缓存策略。

---

## 7. 项目级输出结构（建议）

项目级结果建议存储为“**多份快照**”，每次手动生成都产生一条记录（推荐独立 `project_analysis_results` 表）；同时可选将最新快照 id 挂到项目表便于默认展示。

每份快照结果必须包含其 `included_task_ids`，确保可复现与可审计。

项目级结果结构延续任务级：

```json
{
  "meta": {
    "project_id": 1,
    "generated_at": "2025-12-17T00:00:00Z",
    "scope": {
      "mode": "selected_tasks",
      "included_task_ids": [11, 12, 18]
    }
  },
  "insights": {
    "project_top_entities": [
      {
        "name": "iPhone 16",
        "canonical_id": "ent_xxx",
        "role": "target",
        "heat": 12345,
        "mentions": 321,
        "score": 99999,
        "sentiment": 0.32,
        "original_terms": [{"text": "iPhone16", "count": 100}, {"text": "苹果16", "count": 80}],
        "source_tasks": [{"task_id": 11, "mentions": 50}, {"task_id": 18, "mentions": 80}],
        "post_ids_sample": [{"task_id": 11, "post_id": 101}, {"task_id": 18, "post_id": 203}]
      }
    ],
    "project_top_topics": [
      {
        "name": "价格",
        "canonical_id": "top_xxx",
        "sentiment": -1,
        "heat": 8888,
        "mentions": 222,
        "score": 7777,
        "original_terms": [{"text": "定价太高", "count": 60}],
        "source_tasks": [{"task_id": 12, "mentions": 30}],
        "post_ids_sample": [{"task_id": 12, "post_id": 501}]
      }
    ]
  },
  "charts": {
    "platform_dna": { "...": "可选：按平台拆分的维度分布" },
    "trends": { "...": "可选：随任务时间/数据时间的趋势" }
  },
  "llm": {
    "dictionary_updates": {"entities": 12, "topics": 7},
    "token_stats": {"prompt_tokens": 0, "completion_tokens": 0}
  }
}
```

---

## 8. 与现有任务级/衍生分析的关系

- 任务级：负责从小样本中抽取与融合，产出 `aggregated_entities/aggregated_opinions`（项目级输入的“砖块”）
- 项目级：负责跨任务拼图与归一化稳定化，产出可比较、可追溯的“全景”
- 衍生分析：可在项目级复用（例如项目级 IPA/关联网络/竞品雷达），但建议后置在项目级基础聚合稳定之后再做

---

## 9. 分阶段落地建议（最小可用 → 完整体）

### Phase 1（必须）
- 项目级聚合：`project_top_entities` / `project_top_topics`
- 字典 v1：实体/观点 alias→canonical 映射 + 增量更新（仅字典）
- 证据钻取 API：根据 canonical_id 返回来源任务与帖子列表（分页）

### Phase 2（推荐）
- 可选过滤层：任务列表本地筛选（按平台/时间/关键词等）以便勾选生成快照
- 项目级趋势：按 analyzed_at 或数据时间聚合

### Phase 3（可选）
- 项目级衍生分析：IPA / 项目级关联网络 / 项目级竞品雷达（在地基稳定后再做）
- 轻量人工校验 UI（字典管理）


