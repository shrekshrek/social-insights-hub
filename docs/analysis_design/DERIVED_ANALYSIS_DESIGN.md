# 衍生分析设计方案 (Derived Analysis Design)

本文档基于 `aggregated_entities` (Top 40) 和 `aggregated_opinions` (Top 60) 的清洗数据，详细定义 **四类高价值整合分析** 的实现逻辑。

本方案针对 **小样本高密度数据 (Small Data, High Density)** 进行了优化，引入了动态阈值和降级策略，以确保洞察的可靠性。

## 1. 分析模块总览

| 模块名称 | 英文标识 | 核心价值 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **产品力诊断** | `ipa_analysis` | 识别优劣势，指导产品迭代 | 研发、产品经理 |
| **关联网络** | `context_graph` | 挖掘"人-货-场"营销机会 | 市场营销、内容创作 |
| **竞品雷达** | `competitor_radar` | 多维度参数级对标 | 竞对分析、策略制定 |

---

## 2. 模块详细设计

### 2.1 产品力诊断 (IPA Analysis)
**Importance-Performance Analysis (重要性-表现分析)**

*   **输入数据**：
    *   `aggregated_entities` 中 `type="产品属性"` 或 `category="属性"` 的实体。
    *   `aggregated_opinions` 中的话题。
*   **坐标系定义**：
    *   **X轴 (重要性)**：`score` (综合评分) 或 `mentions` (声量)。
    *   **Y轴 (表现)**：`sentiment` (派生情感值, -1 ~ 1)。
*   **象限划分**：
    *   **Q1 优势区 (High Importance, High Performance)**：继续保持 (Keep Up)。
    *   **Q2 改进区 (High Importance, Low Performance)**：重点改进 (Concentrate Here)。
    *   **Q3 维持区 (Low Importance, Low Performance)**：次要改进 (Low Priority)。
    *   **Q4 机会区 (Low Importance, High Performance)**：过度供给/潜在卖点 (Possible Overkill)。
*   **小样本策略**：
    *   仅展示 `mentions >= 3` 的数据点，过滤极端情感噪点。
*   **输出结构**：
    ```json
    {
      "quadrants": {
        "strength": [{"name": "外观", "x": 1200, "y": 0.8}, ...],
        "improvement": [{"name": "续航", "x": 1500, "y": -0.6}, ...],
        "opportunity": [{"name": "快充", "x": 300, "y": 0.9}, ...],
        "maintain": [{"name": "包装", "x": 100, "y": -0.2}, ...]
      }
    }
    ```

### 2.2 "人-货-场" 关联网络 (Context Graph)
基于 `post_ids` 的共现 (Co-occurrence) 分析，构建以核心实体为中心的星形网络。

*   **输入数据**：
    *   **中心节点**：用户选中的 Target 实体 (如 "iPhone 16")。
    *   **关联节点候选**：
        *   **人 (Audience)**：`category="人群"` 的实体。
        *   **场 (Scenario)**：`category="场景"` 的实体。
        *   **货 (Feature/Issue)**：`category="属性"` 或 `category="问题"` 的实体。
*   **计算逻辑**：
    *   计算 Jaccard 相似度系数：$ J(A,B) = \frac{|A \cap B|}{|A \cup B|} $
    *   其中 $A, B$ 为两个实体的 `post_ids` 集合。
*   **小样本策略**：
    *   不构建全网图，仅构建 **Top 1 实体** 的 1-hop 星形网络。
    *   仅展示关联度 Top 3 的场景和人群。
*   **输出结构**：
    ```json
    {
      "center_node": "iPhone 16",
      "nodes": [
        {"name": "大学生", "type": "audience", "weight": 0.45, "post_ids": [...]},
        {"name": "打游戏", "type": "scenario", "weight": 0.38, "post_ids": [...]},
        {"name": "发热", "type": "issue", "weight": 0.60, "post_ids": [...]}
      ],
      "edges": [
        {"source": "iPhone 16", "target": "大学生", "value": 0.45},
        ...
      ]
    }
    ```

### 2.3 精细化竞品雷达 (Competitor Radar)
基于归一化后的标准属性维度进行对比。

*   **输入数据**：
    *   `role="Target"` 的实体 (本品)。
    *   `role="Competitor"` 的实体 (竞品)。
    *   属性维度：基于 `category` 或 `parent` 聚合的通用维度 (如：价格、性能、外观、服务)。
*   **计算逻辑**：
    *   对每个维度，计算该实体下属所有属性词的加权情感均值。
    *   $ DimensionScore = \text{Avg}(Sentiment \times \log(Heat)) $
*   **小样本策略 (自动降级)**：
    *   **Mode A (Radar)**: 若竞品 `mentions >= 5` 且 维度覆盖率 >= 3，展示雷达图。
    *   **Mode B (Bar)**: 若数据不足，降级为简单的“正负面占比”对比柱状图。
*   **输出结构**：
    ```json
    {
      "mode": "radar", // or "bar"
      "dimensions": ["价格", "性能", "外观", "服务"],
      "series": [
        {
          "name": "本品",
          "data": [0.8, 0.6, 0.9, 0.4] // 归一化后的维度得分 (0-1)
        },
        {
          "name": "竞品A",
          "data": [0.5, 0.8, 0.7, 0.6]
        }
      ]
    }
    ```

## 3. 实现规划

### 3.1 数据层 (Backend)
这些分析属于 **后处理 (Post-processing)**，不需要新的 LLM 调用，纯 Python 逻辑计算。
建议在 `OpinionAggregationTask` 完成后，或者作为独立的 API 端点按需计算。

### 3.3 展示层 (Frontend)
*   **Dashboard**: 核心展示 IPA 象限图和竞品雷达。
*   **Entity Detail**: 点击实体时，展示关联网络。

