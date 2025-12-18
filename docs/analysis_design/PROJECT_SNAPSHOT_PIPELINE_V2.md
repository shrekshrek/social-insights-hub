# 项目级快照聚合分析流程（落地方案 v2）

> 本文档描述 **Project Snapshot（项目级快照）** 的当前落地实现与后续迭代计划，目标是让“多任务（多平台/多关键词）”的整合分析 **可复现、可解释、可对比**。
>
> - 任务级聚合输出是项目级快照的唯一主输入（不回扫原始帖子重新抽取）。
> - 项目级快照分两阶段：**Stage 1 同步硬聚合（秒级）** + **Stage 2 异步 LLM 增强（分钟级）**。

---

## 1. 背景与目标

### 1.1 背景
- 项目由多个任务组成：每个任务是「某平台 + 某关键词」的切片（通常 ~100 篇搜索文章）。
- 任务级聚合已经产出了结构化结果（包含实体、观点、属性、以及 `original_terms` 证据链），但跨任务/跨平台的对比仍需要项目级整合。

### 1.2 目标（项目级快照必须回答）
- **全景**：项目整体声量、平台/关键词构成、全局情绪基线。
- **榜单**：项目级 Top 实体 / Top 观点（跨任务合并后），并可追溯来源任务与帖子样本。
- **对比**：平台/关键词的差异（实体/观点/类目维度）。
- **可解释**：每个合并后的条目都能说明“为什么合并”“原始叫法是什么”（`original_terms`）以及“来自哪些帖子/任务”。

---

## 2. 输入数据（唯一主输入）与口径

### 2.1 数据来源
项目级快照只使用 `DataTask.analysis_result` 里的 canonical 字段：
- **实体**：`analysis_result.aggregated_entities`
- **观点**：`analysis_result.aggregated_opinions`

> 规范口径：**不使用** `insights.top_entities/top_topics` 作为项目级兜底输入；若 canonical 缺失，应要求重跑任务级聚合修复源数据。

### 2.2 关键字段说明

#### 实体（`aggregated_entities[]`）关键字段
- **`name`**：展示名称（任务级已做过一定程度的归一化/聚类）
- **`type` / `role`**：实体类型与角色（可能受上下文影响而跨任务不一致）
- **`mentions` / `heat` / `score`**：强度指标
- **`post_ids`**：任务内关联帖子
- **属性项（建议必须保留）**：`features/issues/expectations/audience/scenarios/market_factors/competitors`  
  - 每项包含：`text`、`post_ids`，以及可选的 `original_terms`

#### 观点（`aggregated_opinions[]`）关键字段
- **`name`**：聚合后的观点短语
- **`category`**：观点类目（任务间可能不一致，需要项目级对齐）
- **`sentiment` / `mentions` / `heat` / `score`**
- **`post_ids`**
- **`original_terms`（可选）**：当任务级发生合并时，记录“标准名”对应的原始表达及频次

### 2.3 `original_terms` 的作用（项目级必须保留）
`original_terms` 是项目级分析的“证据链核心”：
- **解释合并**：告诉用户为什么“标准词条”成立（它由哪些原词合并而来）
- **跨平台语境**：同一个标准词在不同平台可能有不同说法（例如“抗黄变/不发黄/耐黄”）
- **辅助 LLM**：Stage 2 的 LLM 归并与总结可以直接基于 `original_terms` 做语义聚类（成本更低、可解释性更高）

---

## 3. 输出结构（当前快照结果结构）

项目级快照输出建议保持稳定的顶层结构：
- **`meta`**：范围与诊断（可复现与排错）
- **`overview`**：项目全景（声量/分布/全局情绪）
- **`details`**：榜单与可追溯明细（实体/观点）
- **`topic_aspects`**：类目维度聚合（用于“多维对比分析（类目）”）

> 实现文件参考：`backend/src/social_media/analysis/project_snapshot.py`

---

## 4. Stage 1：同步硬聚合（已落地，需补全属性聚合）

### 4.1 核心原则
- **快**：纯规则/统计合并，不依赖 LLM。
- **稳**：任何时候都能生成可用的“基础快照”。
- **可解释**：保留 `original_terms` 与来源追溯（`source_tasks` / `post_ids_sample`）。

### 4.2 实体合并策略（v2：按名称合并）
#### 4.2.1 合并键
- **实体 key = `normalize_name(name)`**（不包含 `type/role`）  
  - 目的：解决同一实体在不同上下文被识别为“品牌/产品”而分裂成两条的问题（例如 XPEL）。

#### 4.2.2 `type/role` 处理
- 聚合时记录 `type_counts` / `role_counts`（频次统计）
- 展示字段使用众数：`main_type` / `main_role`
- **建议额外输出**：
  - `type_breakdown`: `{"品牌": 20, "产品": 10}`
  - `role_breakdown`: `{"competitor": 18, "target": 2}`
  - UI 可显示 “混合” 提示，避免只展示众数造成误导

### 4.3 观点合并策略
- **观点 key = `normalize_name(name) + '|' + category`**
- 情绪字段采用加权平均（权重 = mentions）
- 产出 `platform_distribution` / `keyword_distribution`

### 4.4 必须补齐：实体属性的项目级聚合（Stage 1）
> 目的：让项目级不仅有“谁更热”，还有“为什么热/哪里好/哪里差”的可用画像。

#### 4.4.1 属性聚合对象
对每个项目级实体，聚合以下字段（若任务级提供）：
- `features` / `issues` / `expectations`
- `audience` / `scenarios` / `market_factors` / `competitors`

#### 4.4.2 属性的物理合并口径（不使用 LLM）
对每个属性项（例如 feature 的 `text`）：
- **mentions_weight**：优先用 `len(post_ids)`（去重后）作为计数
- 累计：
  - `count`（该属性被多少唯一帖子提及）
  - `post_ids_sample`（可追溯样本）
  - `original_terms`（如果任务级携带，则一并累计频次）
  - `platform_distribution` / `keyword_distribution`（与实体/观点一致）

#### 4.4.3 属性展示建议
- Stage 1 直接输出 `top_features/top_issues/...`（各取 Top K，例如 10）
- 允许 UI 展开查看 `original_terms`（解释与语境）

---

## 5. Stage 2：异步 LLM 增强（规划）

### 5.1 为什么需要 LLM（项目级的“软”问题）
- **跨任务类目不统一**：同一含义的 `category` 在不同任务中叫法不同（外观/颜值/设计）
- **属性同义冗余**：物理合并后属性词条会堆积（抗黄变/不发黄/耐黄）
- **洞察表达**：需要从“结构化统计”生成可读总结（对比、差异、建议）

### 5.2 任务 A：类目对齐（Category Alignment）
输入：
- 全部出现过的 `category` 列表及频次、示例观点 `name`（Top N）
输出：
- `category_map`: 原 category → 标准维度（5~8 个）
- 更新快照：
  - `topic_aspects` 重新聚合到标准维度
  - `details.top_topics[].category` 也可映射到标准维度（可选）

### 5.3 任务 B：实体属性清洗（Entity Attribute Cleaning）
范围控制：
- 只对 Top N 实体（例如 10~20）做，避免 token 失控
输入：
- 每个实体的属性词条（含 count、`original_terms`、跨平台/关键词分布摘要）
输出：
- 同义聚类后的短列表（保留频次与证据链），例如：
  - “抗黄变”聚类到：{“抗黄变”: 120, 原词: [“不发黄”: 30, “耐黄”: 20, ...]}

### 5.4 任务 C：洞察生成（Insight Summary）
输入：
- `overview`、对齐后的 `topic_aspects`、Top 实体/观点及其分布/属性聚合
输出：
- 面向用户的总结文本（全景、对比、差异化、风险点、机会点）

---

## 6. 评估：是否真正体现“聚合分析价值”

### 6.1 价值成立的判据（必须满足）
- **跨平台/跨关键词差异可见**：同一实体的“优势/槽点”在不同平台/关键词有明显结构差异（由 distribution 与属性支撑）
- **榜单可解释**：Top 实体/观点能给出 `original_terms` 与帖子样本（不是黑箱）
- **输出可复现**：`meta.scope.included_task_ids` 完整记录

### 6.2 常见失败模式与对策
- **失败：只剩榜单**（没有属性/类目对齐/证据链）  
  - 对策：补齐 Stage 1 属性聚合与 `original_terms` 输出
- **失败：类目对比乱**（category 太散）  
  - 对策：优先落地 Stage 2-A 类目对齐

---

## 7. 落地里程碑（建议）

### Milestone 1（必须）
- Stage 1：实体/观点聚合 + 分布 + 诊断（已落地）
- Stage 1：**实体属性聚合补齐**（待实现）
- UI：展示实体/观点榜单与分布（已落地）

### Milestone 2（推荐）
- Stage 2-A：类目对齐（LLM）
- Stage 2-B：Top 实体属性清洗（LLM）

### Milestone 3（可选）
- Stage 2-C：洞察生成（LLM）
- 可配置：Top N、Top K、触发策略（自动/手动）


