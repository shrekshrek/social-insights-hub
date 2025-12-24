# 项目级快照分析流水线 (Project Snapshot Pipeline - Final)

> **版本**: Final-Plus (Corrected Version 8)
> **核心理念**: 数据同源 + 分层计算 + **原话引用**
> **修正重点**: 明确 Focus 层的条件触发逻辑，优化流程图和 JSON 结构，体现“配置即触发”的交互原则。

## 1. 核心架构设计

### 1.1 架构原则
1.  **原话引用 (Direct Quote)**：利用 `original_terms` 中的长句作为定性分析依据，确保 AI 洞察有据可依。
2.  **平台公平 (Platform Fairness)**：引入平台权重系数，防止高流量平台淹没高价值平台。
3.  **全量计算 (All-in-One)**：一次执行，产出三层报告，无需模式选择。
4.  **配置即触发 (Configuration as Trigger)**：Landscape/Topic 层默认全开；Focus 层仅在配置 Subject 后触发。

### 1.2 流水线总览

```mermaid
graph TD
    User[用户配置: Tasks + Optional(Subject/Competitors)] --> Step0[Step 0: 数据加载]
    Step0 --> Step1[Step 1: 加权聚合]
    Step1 --> Step2[Step 2: 智能归一化]
    
    subgraph DataFoundation [数据底座]
        Step2 --> AlignedData[清洗后的全量数据]
    end
    
    AlignedData --> Layer1[Step 3.1: Landscape 大盘层]
    AlignedData --> Layer2[Step 3.2: Topic 话题层]
    
    %% 条件触发逻辑
    AlignedData -.Has Subject?.-> CheckSubject{Subject Configured?}
    CheckSubject -- Yes --> Layer3[Step 3.3: Focus 聚焦层]
    CheckSubject -- No --> SkipFocus[跳过 Focus 层]
    
    Layer1 & Layer2 --> AI_Context[AI 上下文组装]
    Layer3 -.-> AI_Context
    
    AI_Context --> Report1[Step 4.1: LLM 行业分析]
    AI_Context --> Report2[Step 4.2: LLM 话题洞察]
    AI_Context -.-> Report3[Step 4.3: LLM 战略诊断]
    
    Report1 & Report2 & Report3 --> FinalJSON[最终产物]
```

---

## 2. 流水线步骤详解 (Implementation Spec)

### 输入参数契约 (Input Contract)
触发分析任务时，必须传入以下参数：
*   `task_ids` (List[int]): 参与分析的任务 ID 列表。
*   `subject` (str | None): 用户定义的主体品牌/产品（如 "XPEL"）。**用于 Role 仲裁和 Focus 层出发。若为空，则跳过 Focus 层分析。**
*   `competitors` (List[str] | None): 用户定义的竞品列表（如 ["3M", "威固"]）。用于 Role 仲裁。

### Step 0: 数据加载 (Data Loading)
*   **输入**：`task_ids`
*   **操作**：
    1.  读取每个 Task 的 `analysis_result` JSON。
    2.  **提取关键数据**：
        *   `metrics`: 基础指标。
        *   `aggregated_entities/opinions`: **保留 `original_terms` 字段**。
        *   **截断策略**：为防止内存溢出，每个实体/观点保留 **Top 20** 条最有代表性（长度优先）的 `original_terms`。
    3.  **跨任务去重**：
        *   基于 `(platform, post_id_on_platform)` 进行去重。
        *   **冲突处理**：取提取结果的**并集 (Union)**，Heat 按去重后帖子累加（反映总体影响力）。

### Step 1: 加权聚合 (Weighted Aggregation)
*   **输入**：去重后的原始 Items。
*   **平台归一化**：
    *   `Normalized_Heat = Raw_CII * Platform_Weight`。
    *   **默认权重**：
        *   `bilibili`: 1.5
        *   `xhs`: 1.0
        *   `douyin`: 0.8
        *   `weibo`: 0.6
*   **时效性统计**：
    *   统计以下字段用于展示数据新鲜度：
        *   `last_7_days_count`: 最近7天内容数。
        *   `last_30_days_count`: 最近30天内容数。
        *   `avg_age_days`: 内容平均发布天数。

### Step 2: 智能归一化 (Normalization)

#### Job 1: 实体归一化 (Entity Normalization)
*   **关键变更**：**不可直接复用任务级 Chain**。
*   **策略**：程序化预聚类（降噪） + **专用合并 Chain**（最终裁判）。
*   **Layer 1 (Programmatic Pre-clustering)**：
    *   使用字符相似度阈值 (0.9) 进行预聚类，减少送入 LLM 的实体数量。
    *   *设计原则：KISS（Keep It Simple）。程序化阶段宁可漏合并（LLM 能补救），也不能误合并（LLM 难拆开）。*
*   **Layer 2 (New Project Merge Chain)**：
    *   **开发新 Chain**: `project_entity_merge_chain`。
    *   **输入截断**：仅选取 **Top 200 高热实体** 进入 LLM 归一化，长尾实体不参与合并。
    *   **Prompt 分支策略 (Branching Logic)**：
        *   **Case A (Subject存在)**：启用 **Role 仲裁模式**。Prompt: "主体是 {subject}，请强制标记为 Target；竞品 {competitors} 标记为 Competitor。"
        *   **Case B (Subject为空)**：启用 **去 Role 模式**。Prompt: "无特定主体，请将所有品牌/产品统一标记为 Context，**严禁使用 Target/Competitor 标签**。"
    *   **关键输出要求**：
        *   **Entity Name**: 标准化实体名。
        *   **Parent Name**: **同步归一化父级品牌**（如将 "特斯拉"/"Tesla" 统一为 "Tesla"），若原数据缺失需尝试补全。
            * 口径约定：对"品牌"实体，`parent` 使用哨兵值 `"Self"` 表示"品牌自身"（消费/聚合时等价于实体名本身）；对"产品"实体，`parent` 填其归属品牌名；通用词/场景为空字符串。
    *   **输出**：`entity_mapping` 和 `tags` (Role/Parent)。
*   **后置处理**：
    *   **原话合并**：合并 `original_terms` 列表并截断 Top 20（长度优先）。
    *   **属性合并**：`features/issues` 等属性列表，直接物理合并（Set Union）。

#### Job 2: 观点归一化 (Opinion Normalization) - *修正版*
*   **策略**：先对齐 Category，再合并 Opinion Name。
*   **Step A: Category 对齐**
    *   使用 `category_normalization_chain`。
    *   输入：所有任务的 Category 列表。
    *   输出：`Category Mapping` (如 "费用" -> "价格")。
*   **Step B: Opinion Name 聚类**
    *   **输入对象**：任务级的标准观点名称。
    *   使用 `opinion_normalization_chain`。
    *   输入：某 Category 下的所有 Opinion Names 及其频次。
    *   输出：`Cluster Mapping`。
*   **后置处理**：
    *   物理合并被聚类在一起的观点的 `Heat` 和 `original_terms`。

### Step 3: 分层指标计算 (Layered Analysis)

> **核心原则**: 所有指标必须 **可追溯 (Traceable)**。点击任意图表数据点，需能展示支撑该数据的 `original_terms` (用户原话) 和来源 `post_info`。

#### 3.1 大盘层 (Landscape Layer)
*   **视角**：上帝视角（包含所有玩家）。
*   **准入规则**：**全量实体** (Target + Competitor + Context)。
*   **核心指标**：
    *   **SOV 排行榜 (Share of Voice)**：
        *   维度：`Normalized_Heat` (声量) + `Post_Count` (提及帖数)。
        *   *目的：识别“虚火”（高热低帖）与“实火”（高热高帖）。*
    *   **集团军声量 (Share of Group)**：
        *   逻辑：基于归一化后的 `Parent Name` 进行聚合（如：Tesla = Model 3 + Model Y + Cybertruck）。
        *   *目的：对比品牌家族/集团的整体市场统治力。*
    *   **平台阵地 DNA**：Top 品牌在各平台的声量占比分布。
    *   **行业象限**：Top 50 实体的 [热度 x 情感] 散点图。
        *   *支持点击散点查看该实体的高频评价。*

#### 3.2 话题层 (Topic Layer)
*   **视角**：产品经理 / 舆情官。
*   **准入规则**：全量话题（不区分实体归属）。
*   **核心指标**：
    *   **核心话题雷达**：
        *   **痛点 (Pains)**: 负面情绪主导的观点簇。
        *   **爽点 (Gains)**: 正面情绪主导的观点簇。
        *   **争议点**: 好评差评并存的话题（如“价格”）。
    *   **未被满足的需求 (Unmet Needs)**：
        *   定义：行业内普遍存在的**高频负面话题**（即所有玩家都在被吐槽的点）。
        *   *价值：这是新产品切入的最佳机会点。*

#### 3.3 聚焦层 (Focus Layer) - *条件触发*
*   **视角**：战略官（我 vs 敌）。
*   **准入规则**：**仅限 Target 和 Competitor**。
*   **触发条件**：`Subject` 不为空。
*   **核心指标**：
    *   **SWOT 矩阵**：
        *   **S (优势)**: Target 独有的高频好评。
        *   **W (劣势)**: Target 特有的高频差评。
        *   **O (机会)**: 基于 **Competitor 的劣势** (竞品被骂的点)。
        *   **T (威胁)**: 基于 **Competitor 的优势** (竞品被夸的点)。
    *   **产品线健康度 (Product Line Health)**：
        *   逻辑：下钻分析 Subject 旗下的子实体（如 Model 3 vs Model Y）。
        *   维度：各子实体的声量贡献度 + 情感净值 + Top 1 痛点。
        *   *目的：精准定位问题源头（是品牌通病还是单品硬伤？）。*
    *   **平台剪刀差**：`Subject` 在各平台的份额 vs 行业平均份额。
    *   **Gap 分析**：竞品有的核心优势（High Frequency & High Sentiment），而我方缺失的。

#### 3.4 前端可视化建议 (Visualization Layer)
*   **设计原则**：从“展示型”转向“分析型”，强调效能分析与机会发现。
*   **Landscape 层**：
    *   **SOV 效能矩阵 (Efficiency Matrix)**：
        *   替代传统散点图。X轴=`Post_Count` (投入/声量), Y轴=`Normalized_Heat` (产出/热度)。
        *   **分区**：划分为高效区 (High Heat, Low Post) / 低效区 / 虚火区。
        *   **交互**：Hover 显示 CPI (Cost Per Interaction) 效能倍数。
    *   **集团份额透视 (Hierarchical Table)**：
        *   替代旭日图。使用树形表格 (Tree Table)。
        *   展示 `Parent` -> `Entity` 的层级贡献度，一眼识别集团内的“拖油瓶”与“顶梁柱”。
*   **Topic 层**：
    *   **痛点/爽点分布图 (Sentiment-Volume Bubble)**：
        *   X轴=声量, Y轴=情感净值。
        *   **机会区 (Unmet Needs)**：**右下角 (高频+负面)**，使用虚线框高亮。
        *   **护城河 (Moats)**：**右上角 (高频+正面)**。
    *   **话题详情侧边栏 (Drill-down Slideover)**：
        *   点击气泡触发。
        *   内容：趋势微型图 + LLM 观点摘要 + 佐证原帖 (Evidence)。
*   **Focus 层**：
    *   **动态 SWOT 映射 (Dynamic SWOT Tornado)**：
        *   使用龙卷风图 (Tornado Chart) 对比 Target vs Competitor 在同一话题维度的表现。
        *   **逻辑**：Target 负面极低 & Competitor 负面极高 -> 自动标记为 **O (机会)**。
    *   **平台剪刀差 (Platform Gap)**：
        *   双线雷达图或差异柱状图，重点渲染 **Gap 阴影区域**。

---

## 3. Step 4: 并行 AI 报告 (Parallel AI Reporting)

**关键策略**：
1.  **角色分离 (Persona Separation)**：三个 Agent 分别扮演不同角色（分析师、产品经理、战略顾问）。
2.  **证据注入 (Evidence Injection)**：Prompt 中必须直接注入清洗后的 `original_terms`，并要求 AI 在报告中 **显式引用**（如“正如用户所说...”）。

### 4.1 行业格局报告 (Landscape)
*   **角色**: 资深市场分析师。
*   **Input**: 
    *   SOV 排行榜 (含 Post Count)。
    *   Top 3 品牌的平台分布数据。
    *   **Top 3 品牌的高频正面/负面观点摘要**。
*   **Output**: 宏观市场综述。
    *   *要求：定义市场阶段（垄断/竞争/分散），总结头部玩家的核心品牌心智。*

### 4.2 话题洞察报告 (Topic)
*   **角色**: 敏锐的产品经理。
*   **Input**: 
    *   核心话题雷达数据。
    *   **Top 5 痛点 (Pains) 的 original_terms (用户原话)**。
    *   **Top 5 爽点 (Gains) 的 original_terms**。
    *   **未满足需求 (Unmet Needs) 的相关原话**。
*   **Output**: 供需分析报告。
    *   *要求：深入剖析痛点背后的原因（产品缺陷 vs 服务问题），并验证未满足需求的真实性。必须引用原话佐证。*

### 4.3 战略诊断报告 (Focus) - *条件触发*
*   **触发条件**：`Subject` 不为空。
*   **角色**: 首席战略官 (CSO)。
*   **Input**: 
    *   SWOT 矩阵数据。
    *   平台剪刀差数据。
    *   **Target 自身的负面评价原话** (用于分析 Weakness)。
    *   **Competitor 的核心正面评价原话** (用于分析 Threat)。
*   **Output**: 战略行动指南。
    *   *要求：基于“敌我对比”给出 SWOT 结论，并产出 3 条具体的战术建议（Actionable Insights），涉及投放渠道、产品改进或公关方向。*

---

## 4. 最终数据结构 (Unified JSON Schema)

```json
{
  "meta": {
    "project_id": 123,
    "subject": "XPEL", // 若为 null, 则为 Landscape 模式
    "competitors": ["3M", "V-KOOL"],
    "weights_used": { "bilibili": 1.5, "xhs": 1.0 }
  },
  
  // Step 0-2: 数据底座 (含原话)
  "foundation": {
    "dedup_stats": { ... },
    "aligned_entities": [ ... ],
    "aligned_topics": [ ... ]
  },

  // Step 3: 分析分层
  "layers": {
    "landscape": {
      "sov_ranking": [ ... ], // 包含 XPEL, 3M, V-KOOL 等所有品牌
      "freshness": { "last_7_days": 10, "last_30_days": 40 }
    },
    "intent": {
      "topic_radar": { 
        "pains": ["售后维权困难", "发黄"], 
        "gains": ["高亮", "疏水"] 
      }
    },
    "focus": {
      // 若 meta.subject 为 null，此字段为 null 或不返回
      "swot": { ... },
      "platform_scissors": { ... }
    }
  },

  // Step 4: AI 报告
  "reports": {
    "landscape_report": { "content": "..." },
    "topic_report": { "content": "..." },
    "focus_report": { "content": "..." } // 若无 Focus 层，此字段内容为空字符串或 null
  }
}
```

## 5. 开发实施 Checklist

1.  **后端 (Backend)**:
    *   [ ] **新 Chain 开发**: 实现 `project_entity_merge_chain.py`，支持 **动态 Prompt 分支**（Role Arbitration vs De-role）。
    *   [ ] `aggregation_service.py`: 确保在合并 Entity/Topic 时，`original_terms` 被正确合并。
    *   [ ] `aggregation_service.py`: **实体属性合并**：直接 Set Union，不调用 LLM。
    *   [ ] `aggregation_service.py`: **观点归一化**：
        *   先调 `category_normalization_chain` 对齐大类。
        *   再调 `opinion_normalization_chain` 对齐 **Opinion Names**。
        *   最后物理合并 `original_terms`。
    *   [ ] `aggregation_service.py`: **实体归一化**：取 Top 200 调用 LLM，长尾保留。
    *   [ ] `aggregation_service.py`: **条件执行**：在执行 Step 3.3 和 Step 4.3 前检查 `subject` 是否存在。
    *   [ ] **工程防御 (Defensive Coding)**:
        *   **单条文本截断**：限制单个 `original_term` 最大长度（如 100 字符），防止 Token 溢出。
        *   **空数据熔断 (Empty Guard)**：若 Step 3 输出的核心指标数据为空或过少，直接返回默认提示，跳过 LLM 调用以节省成本。

2.  **AI Prompt**:
    *   [ ] 更新 Step 4 的 Prompt Template，增加 `{user_quotes}` 插槽。

3.  **前端 (Frontend)**:
    *   [ ] 增加“平台权重配置”入口。
    *   [ ] **报告页组件开发**:
        *   **SOV 效能矩阵**: ECharts Scatter + MarkArea (四象限背景)。
        *   **痛点/爽点分布图**: ECharts Bubble + MarkArea (Unmet Needs 高亮)。
        *   **动态 SWOT**: ECharts Custom Series 或 Bar (Tornado 布局)。
        *   **详情侧边栏**: Slideover 组件，展示 LLM 摘要 + 原话佐证。
    *   [ ] **动态 Tab 展示**：若 `focus` 数据为空，隐藏“战略诊断”Tab。
