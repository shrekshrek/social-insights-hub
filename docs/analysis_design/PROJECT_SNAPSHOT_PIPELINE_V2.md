# 项目级快照分析流水线 (Project Snapshot Pipeline)

> **目标**：将多个独立任务（切片）的分析结果，通过清洗、对齐、重构，整合成一个全域视角的、口径统一的分析快照。

## 1. 核心理念

项目级分析不是简单的多任务数据叠加，而是**重构全域上帝视角**。
为了消除跨任务的“语言隔阂”（不同任务对同一实体/观点的表述差异），我们采用**严格的串行流水线**：
**先做归一（实体归一 + 观点归一，可并行启动；观点归一内部包含类目对齐） $\to$ 再做程序化衍生分析 $\to$ 最后做全局 LLM 总分析**。

## 2. 流水线步骤详解 (Execution Flow)

流水线由 `ProjectSnapshotTask` 触发，`Orchestrator` 负责编排。

### Step 1: 实体归一化 (Entity Normalization)
*   **目的**：合并跨任务的同义实体（如 "Tesla" / "特斯拉"），确立全域标准实体 ID。
*   **输入**：所有任务的 Top Entities (name, type, score, hint)。
*   **处理**：
    1.  **程序预聚类** (Programmatic Pre-clustering)：基于字符串相似度快速合并，降低 LLM Token 消耗。
    2.  **LLM 归一化** (Entity Normalization Chain)：两阶段（初步归一 + 复查），处理语义别名。
    3.  **Fallback**：如果 LLM 失败，沿用程序预聚类结果。
*   **输出**：
    *   `entity_mapping` (原始名称 $\to$ 标准名称)。
    *   `entities_aligned` (合并后的实体列表，含重新累加的 heat/mentions)。
*   **记录**：创建独立的 **`AnalysisJob (ENTITY_NORMALIZATION)`**。

### Step 2: 观点归一化 (Opinion Normalization)
*   **目的**：在标准类目下，合并同义观点短语（如 "贵" / "价格高"）。
*   **输入**：所有任务的 Top Topics（包含 `category` 与 `name` 等字段）。
*   **处理**：
    1.  **类目对齐（内置）**：将松散类目映射到统一维度（如“价格/费用/预算” $\to$ “价格”）。
        - **LLM**：`category_normalization_chain`
        - **Fallback**：Identity Map（LLM 不可用时仍可继续）
    *   **分组并行**：按标准类目分组。
    *   **程序预聚类**：组内先做字符串相似度合并。
    *   **LLM 归一化** (Opinion Normalization Chain)：组内进行语义合并。
*   **输出**：
    *   `topic_mapping` (原始短语 $\to$ 标准短语)。
    *   `topics_aligned` (合并后的观点列表)。
*   **记录**：创建独立的 **`AnalysisJob (OPINION_NORMALIZATION)`**。

### Step 3: 程序化衍生分析 (Derived Program Analysis)
*   **目的**：在“归一后的口径”上，计算并生成所有结构化分析结果（用于前端图表/表格）。  
*   **输入**：`entities_aligned`, `topics_aligned`（来自 Step 1/2 的归一结果）。
*   **处理**（示例，不限于此）：
    - **归因/驱动因素重构（Drivers / Attribute Clustering）**：在标准实体内部聚类属性，生成“实体 $\times$ 维度”矩阵（`attribute_normalization_chain`）。
    - **全局指标重算（Insights Recalculation）**：基于 `topics_aligned` 重新计算类目聚合、分布统计等。
*   **输出**：`details_aligned`（最终展示用的对齐列表与聚合结果）、`drivers`（矩阵/维度）等。

> 约定：归一输入的**候选池**为 Top200（实体/观点各 200），归一完成后用于展示与后续解读的**最终列表**为 Top60（`details_aligned.top_entities/top_topics`）。

### Step 4: 全局 LLM 总分析 (Executive Summary)
*   **目的**：扮演分析师，基于清洗后的数据产出洞察报告。
*   **输入**：全局归一完成后的所有产出（概览、差异、对齐后的排行、归因矩阵）。
*   **处理**：**LLM Analyst** (`project_snapshot_summary_chain`)。
*   **输出**：
    *   执行摘要 (Executive Summary)。
    *   平台/关键词差异洞察。
    *   核心驱动因素分析。
    *   风险与机会建议。
*   **记录**：创建独立的 **`AnalysisJob (PROJECT_SNAPSHOT_SUMMARY)`**。

## 3. 数据结构 (Snapshot Result Schema)

```json
{
  "meta": { ... },
  "overview": { ... },  // 原始合并结果（未做全局归一）
  "charts": { ... },    // 原始合并结果（未做全局归一）
  "stage2": {
    "status": "completed",
    "steps": {
      "category_alignment": { "status": "completed", "used": true },
      "alias_entities": { "status": "completed", "job_id": 123 },
      "alias_topics": { "status": "completed", "job_id": 124 },
      "drivers": { "status": "completed" },
      "insights": { "status": "completed" },
      "summary": { "status": "completed", "job_id": 125 }
    },
    "category_alignment": { "category_map": {...} },
    "alias_normalization": {
      "entities": { "entity_mapping": {...}, "after_count": 50 },
      "topics": { "topic_mapping": {...}, "after_count": 80 }
    },
    "drivers": { "entity_matrix": [...], "dimensions": [...] },
    "details_aligned": {
      "top_entities": [...], // 全局归一后的最终实体排行
      "top_topics": [...],   // 全局归一后的最终观点排行
      "topic_aspects_aligned_v2": [...]
    }
  },
  "stage3": {
    "status": "completed",
    "summary": {
      "executive_summary": "...",
      "differences": [...],
      "drivers": [...]
    }
  }
}
```

### 字段含义说明（避免混淆）

- **`details.top_entities / details.top_topics`**：快照生成时的“原始合并结果”（跨任务聚合后的列表，但**尚未做全局归一**）。这部分是全局归一流程的输入。
- **`stage2.details_aligned.top_entities / top_topics`**：全局归一流程完成后的“最终结果”（同义项已合并、类目已对齐、指标已重算）。这部分是前端主要展示与总结的依据。

### 字段命名与产品口径映射（推荐读法）

- **原始合并结果**：
  - `overview` / `charts` / `details.top_entities` / `details.top_topics`
- **全局归一结果**（最终展示口径）：
  - `stage2.details_aligned.*`、`stage2.drivers`、`stage2.alias_normalization.*`
- **全局 LLM 总分析**：
  - `stage3.summary`

## 4. 任务与计费 (Jobs & Billing)

一次项目快照生成会产生以下计费点（AnalysisJob）：

1.  **实体归一化任务** (`entity_normalization`):
    *   消耗：Step 1（实体归一中的 LLM 归一化）。
2.  **观点归一化任务** (`opinion_normalization`):
    *   消耗：Step 2（观点归一，包含“类目对齐 + 观点归一”的 LLM 消耗）。
3.  **快照总结任务** (`project_snapshot_summary`):
    *   消耗：Step 4（全局 LLM 总分析）。

*注：Step 3 的程序化衍生分析中，Drivers 可能包含 LLM 聚类；如未来需要精确分摊成本，可单独拆出 AnalysisJob。*
