# 任务级深度分析方案 (Task Analysis Detail)

本文档详细描述**任务级 (Task Level)** 的深度分析逻辑。任务级分析针对单次采集的数据（单平台+单关键词+有限样本），核心目标是进行**数据清洗**、**质量评估**和**微观洞察**。

## 1. 分析流程总览

```mermaid
graph TD
    Raw[原始采集数据 Top 50-100] --> A[数据清洗与初筛]
    A --> |有效样本| B{分析深度?}
    B --> |Light| B_Light[仅分析 Top 5 帖子]
    B --> |Deep| B_Deep[全量深度分析]
    B_Light & B_Deep --> C[指标计算与加权 (Aggregator)]
    C --> D[核心洞察生成]
    D --> Output[Task Analysis Result]

    subgraph Step1_Screening
    A1[反垃圾过滤]
    A2[相关性校验]
    A3[CII计算]
    end

    subgraph Step2_Extraction
    B1[实体提取]
    B2[观点提取]
    B3[摘要生成]
    end

    subgraph Step3_Aggregation
    C1[多维加权聚合]
    C2[舆论焦点地图]
    C3[JSON结果组装]
    end
```

---

## 2. 步骤一：数据清洗与质量评估

在进行深度分析前，必须剔除无效数据，并评估本次采集的信噪比。

### 2.1 过滤逻辑 (Filtering Logic)

*   **输入**：初筛链 (`screening_chain`) 的输出结果。
*   **规则**：
    1.  **垃圾剔除**：`spam_score > 6` → 标记为 `SPAM` (丢弃)。
    2.  **无关剔除**：`relevance_score < 4` → 标记为 `IRRELEVANT` (丢弃)。
    3.  **有效样本**：剩余数据记为 `valid_posts`。
    4.  **时效性过滤**：根据 `time_range` 参数（如 `last_7_days`, `last_30_days`），基于 `published_at` 字段进行二次筛选。确保分析结果反映指定时间窗口内的舆情状态。

### 2.3 数据增强与预计算 (Data Enrichment) [优化]

在初筛完成后，立即对单条数据进行**CII 互动指数**计算，将指标固化到数据库，为后续筛选和排序提供权重依据。

1.  **CII 互动指数 (Content Interaction Index)**：
    *   **公式**：$ RawScore = (Likes \times 1) + (Comments \times 2) + (Shares \times 5) + (Collected \times 3) $
    *   **平滑**：$ CII = \log_{10}(RawScore + 1) \times 10 $
    *   *作用*：后续所有加权分析的基础权重。

---

## 3. 步骤二：结构化提取 (Extraction)

本步骤调用 LangChain 对有效样本进行深度内容提取。

*   **输入**：经过清洗且 **按 CII 倒序排列** 的 `valid_posts`（优先分析高影响力内容）。
*   **执行逻辑**：
    *   对每一篇帖子调用 `post_extraction_chain`。
    *   对高价值帖子的评论调用 `comment_extraction_chain`。
*   **核心产出**：
    *   `entities`: 实体列表，每个实体包含：
        *   `name`: 实体名称
        *   `type`: 实体类型（品牌/产品/服务/人物/其他）
        *   `sentiment`: 情感值 (-1, 0, 1)
        *   `features`: 特性/功能/优点列表
        *   `issues`: 问题/缺点/不满列表
        *   `expectations`: 改进期望/建议列表
        *   `audience`: 目标人群列表
        *   `scenarios`: 使用场景/用途列表
        *   `market_factors`: 价格/促销/渠道列表
        *   `competitors`: 竞品对比列表
    *   `general_opinions`: 通用观点列表（category, opinions, sentiment）。
    *   `summary`: 内容摘要。

---

## 4. 步骤三：核心指标计算算法 (Aggregator Logic)

本步骤在 LLM 提取完成后，执行最终的统计聚合。由于 CII 等基础指标已在 Step 1 完成，此处主要处理**加权聚合**。

### 4.1 基础指标聚合
*   **营销浓度**：统计 `spam_score >= 4` 的帖子占比。
*   **平均 CII**：计算 `valid_posts` 的 CII 均值。
*   **舆论反差度 (Sentiment Conflict)**：计算 `Post_Sentiment` 与 `Comment_Sentiment` 的平均偏差。若偏差过大，提示“翻车”风险。

### 4.2 时效性分布 (Time Distribution)
*   **逻辑**：统计 `published_at` 的分布。
*   **价值**：评估本次采集内容的**新鲜度**。

### 4.3 实体聚合与主体过滤 (Entity Aggregation & Subject Filtering) [关键分水岭]
为了防止"竞品好评"被误算为"本品好评"，在此处进行实体聚合与清洗。后续所有分析基于清洗后的数据。

*   **设计理念：只按 canonical_name 分组，情感派生计算**
    *   **观点 vs 实体的本质区别**：
        *   观点的情感是**独立维度**：同一话题的正面/负面观点是对立声音（如"价格实惠" vs "价格太贵"），必须分开统计。
        *   实体的情感是**派生值**：情感来自 `features`（天然正面）和 `issues`（天然负面）的对比，不是独立维度。
    *   **方案**：只按 `canonical_name` 分组，同一实体的所有提及合并。
    *   **情感派生**：`sentiment = Σ(sentiment * cii) / Σ cii`（CII 加权情感值，范围 [-1, 1]）。
    *   **效果**：用户看到实体的完整画像，而非被分散的正面/负面/中性三条记录。

*   **实体数据结构**：
    ```python
    entity_data[canonical_name] = {
        "name": str,           # 显示名称
        "canonical_name": str, # 标准化名称
        "type": str,           # 实体类型
        # 情感派生计算
        "sentiment_weighted_sum": float,  # Σ(sentiment * cii)
        "positive_count": int,   # 正面提及次数
        "negative_count": int,   # 负面提及次数
        "neutral_count": int,    # 中性提及次数
        "total_cii": float,    # CII累加（去重后）
        "cii_added_posts": set,  # 已贡献CII的帖子ID（避免重复累加）
        "post_sources": set,     # 从帖子原文提取的帖子ID
        "comment_sources": set,  # 从评论提取的帖子ID
        "post_ids": set,         # 所有涉及的帖子ID
        # 实体维度信息（完整聚合，带帖子追溯）
        "features": dict,      # 特性/功能/优点 {label: set(post_ids)} - 天然正面
        "issues": dict,        # 问题/缺点/不满 {label: set(post_ids)} - 天然负面
        "expectations": dict,  # 改进期望/建议 {label: set(post_ids)}
        "audience": dict,      # 目标人群 {label: set(post_ids)}
        "scenarios": dict,     # 使用场景/用途 {label: set(post_ids)}
        "market_factors": dict,# 价格/促销/渠道 {label: set(post_ids)}
        "competitors": dict,   # 竞品对比 {label: set(post_ids)}
    }
    ```

*   **聚合逻辑（纯代码实现）**：
    1.  **实体归一化 (Normalization)**：
        *   **相似度合并**：相似度 ≥ 0.8 的实体名称合并到同一 `canonical_name`。
        *   **只按名称分组**：不再按情感分组，同一实体的所有提及合并。
    2.  **情感统计**：
        *   记录 `positive_count`, `negative_count`, `neutral_count` 用于展示情感分布。
        *   累加 `sentiment_weighted_sum = Σ(sentiment * cii)` 用于计算加权情感。
    3.  **来源标记**：
        *   `post_sources`: 从帖子原文提取该实体的帖子ID集合。
        *   `comment_sources`: 从评论提取该实体的帖子ID集合。
        *   用于分析"博主观点"与"大众观点"的差异。
    4.  **双重加权**：
        *   **Heat (热度)**：$\sum CII_p$（每帖只贡献一次，避免重复累加）。
        *   **Mentions (频次)**：$Count(Unique\_Posts)$（唯一帖子数）。
        *   *策略*：排序时优先使用 `Heat`，但需保留 `Mentions` 辅助判断"偶然爆款"与"普遍共识"。
    5.  **维度聚合**：
        *   对 `features`, `issues`, `expectations`, `audience`, `scenarios`, `market_factors`, `competitors` 七个维度分别记录来源帖子ID。
        *   每个维度项记录包含该信息的帖子ID集合，支持追溯。
        *   输出时按帖子数排序，取 Top 5 高频项展示。
    6.  **派生情感计算**：
        *   `sentiment = sentiment_weighted_sum / total_cii`（CII 加权）。
        *   范围 [-1, 1]，正值偏正面，负值偏负面。
    7.  **角色分类**：
        *   **Target**：`entity.name` 包含任务关键词（忽略大小写）。
        *   **Competitor**：收集 Target 实体的 `competitors` 字段提及的名称，或预设白名单匹配。
        *   **Other**：非目标/竞品的其他实体（人物、场景词等，仍有分析价值）。

*   **输出结构**：
    ```python
    return {
        "top_entities": [...],        # 热度排名前N的实体列表（展示用）
        "target_entities": [...],     # 本品实体列表
        "competitor_entities": [...], # 竞品实体列表
        "aggregated_entities": {...}, # 完整融合数据（用于项目级分析）
    }
    ```

### 4.4 核心指标计算
基于清洗后的 **Target** 数据桶计算：

1.  **NSR 净情感率 (Net Sentiment Rate)**
    *   **公式**：$ NSR = \frac{\sum (Sentiment_i \times CII_i)}{\sum CII_i} $
    *   *范围*：[-2, +2]
2.  **SERP 搜索健康度 (SERP Health Index)**
    *   **公式**：$ SHI = \text{Normalize}( \text{AvgWeightedSentiment}(\text{Top 20 Posts}) ) $
    *   *作用*：评估搜索结果首屏观感。

### 4.5 深度洞察挖掘 (Deep Insights)
基于清洗后的 **Target** 数据桶挖掘，并综合运用 **Heat** 和 **Mentions** 双重指标：

1.  **舆论焦点地图 (Focus Map)**
    *   **展示内容**：高热度的 **"实体+属性" 关键词** (来源于 `entities.name`, `features`, `issues`, `general_opinions`)。
    *   **排序逻辑**：默认按 `Heat` (影响力) 降序，展示 Top 10。
    *   **展示逻辑**：气泡大小 = `Heat`，颜色深浅 = `Mentions` (频次)。
    *   *目的*：一眼识别“大家都在讨论什么具体点”（如 "发热" 或 "外观"）。

2.  **情感-互动四象限 (Quadrant)**
    *   **展示内容**：具体的 **帖子 (Posts)**。每个点代表一篇帖子。
    *   **X轴**：帖子情感分 ($Sentiment$)。
    *   **Y轴**：帖子互动指数 ($CII$)。
    *   *价值*：快速定位需要处理的**具体内容**（如：点击右上角 Q2 区域的点，找到高赞好评贴进行转发）。

3.  **KANO 需求分层 (双维判定)**
    *   **展示内容**：分类后的 **特性/痛点关键词**。
    *   **基本型 (Must-be)**：`High Mentions` (普遍) + `Negative Sentiment` (痛点)。**展示高频痛点**（如 "发热"）。
    *   **兴奋型 (Attractive)**：`Low Mentions` (稀缺) + `High Avg_CII` (高共鸣) + `Positive Sentiment`。**展示惊喜功能**（如 "微距"）。
    *   **期望型 (One-dimensional)**：`High Mentions` (普遍) + `High Expectations`。**展示用户愿望**（如 "降价"）。

4.  **场景与人群画像 (置信度过滤)**
    *   **展示内容**：`Scenarios` 和 `Audience` 标签，附带 Heat/Mentions。
    *   **过滤门槛**：仅保留 `Mentions >= 2` 的标签。
    *   *理由*：排除“偶然爆款”带来的标签偏差，确保画像具有统计学上的代表性。

### 4.6 营销渗透率 (Marketing Penetration)
*   **自来水占比**：`spam_score < 4` 的帖子占比。

---

## 5. 数据结构输出定义

任务级聚合分析的结果将存入 `DataTask.analysis_result` JSON 字段。

聚合分析通过独立 API 触发：`POST /api/v1/social-media/analysis/tasks/{task_id}/aggregate`

```json
{
  "meta": {
    "task_id": 123,
    "analyzed_at": "2023-10-27T10:00:00Z",
    "keywords": ["iPhone", "苹果手机"],
    "data_volume": {
      "total": 100,              // 总帖子数
      "screened": 85,            // 已初筛数量
      "deep_analyzed": 50,       // 已深度分析帖子数
      "comment_analyzed": 30     // 已分析评论的帖子数
    }
  },
  "metrics": {
    "nsr": 0.45,            // 加权净情感率 [-1, 1]
    "avg_cii": 24.5,        // 平均互动指数
    "serp_health": 65,      // 搜索健康度 (0-100)
    "marketing_analysis": {
      "promotion_ratio": 0.15,  // 营销内容占比
      "organic_ratio": 0.85,    // 自然内容占比
      "promotion_count": 12,
      "organic_count": 73
    },
    "sentiment_conflict": {
      "avg_conflict": 0.35,     // 平均舆论反差度
      "conflict_direction": "comment_positive", // 反差方向
      "high_conflict_count": 5, // 高反差帖子数
      "risk_level": "medium"    // 风险等级 (low/medium/high)
    }
  },
  "charts": {
    "quadrant": [
      {"post_id": 101, "x": -0.8, "y": 45, "quadrant": "Q1_danger", "label": "发热严重"},
      {"post_id": 102, "x": 0.9, "y": 30, "quadrant": "Q2_brand", "label": "拍照好看"}
    ],
    "quadrant_summary": {
      "Q1_danger": 5,    // 爆雷区：高互动+负面
      "Q2_brand": 12,    // 品牌区：高互动+正面
      "Q3_complaint": 8, // 吐槽区：低互动+负面
      "Q4_niche": 15,    // 小众区：低互动+正面
      "neutral": 10      // 中性区
    },
    "time_distribution": [
      {"date": "2023-10-01", "count": 5}, // 仅用于展示内容的时效性分布，不做趋势解读
      {"date": "2023-10-02", "count": 12}
    ]
  },
  "freshness": {
    "last_7_days": 25,   // 最近7天的帖子数
    "last_30_days": 65,  // 最近30天的帖子数
    "avg_age_days": 15.5 // 平均发布天数
  },
  "insights": {
    // 实体排行（只按名称分组，情感为派生值）
    "top_entities": [
      {
        "name": "iPhone 16",
        "type": "产品",
        "role": "target",           // target / competitor / other
        "heat": 4500,               // Σ CII (去重后)
        "mentions": 15,             // 唯一帖子数
        "sentiment": 0.35,          // 派生情感值 [-1, 1]，CII 加权
        "sentiment_distribution": {"positive": 10, "negative": 3, "neutral": 2}, // 情感分布
        "source_distribution": {"post": 0.3, "comment": 0.7},
        "top_features": ["外观好看", "拍照清晰", "续航持久"],
        "top_issues": ["发热严重", "价格高"],
        "top_expectations": ["降价", "改善散热"]
      }
    ],
    "target_entities": [...],     // 本品实体列表
    "competitor_entities": [...], // 竞品实体列表

    // 观点排行（按 category+sentiment 分组）
    "top_issues": [
      {
        "topic": "价格",
        "sentiment": -1,            // 固定情感值 (-1, 0, 1)
        "heat": 4500,
        "mentions": 15,
        "source_distribution": {"post": 0.2, "comment": 0.8}, // 80% 来自评论，说明是用户痛点而非博主痛点
        "summary": "普遍认为定价过高"
      },
      {
        "topic": "发热",
        "sentiment": -1,
        "heat": 3200,
        "mentions": 12,
        "source_distribution": {"post": 0.5, "comment": 0.5},
        "summary": "玩游戏时背部烫手"
      }
    ],
    "top_features": [
      {"topic": "外观", "sentiment": 1, "heat": 5000, "mentions": 20, "summary": "紫色版本很惊艳"}
    ],
    "context_analysis": {
      "scenarios": [
        {
          "label": "游戏",
          "heat": 3000,
          "mentions": 25,
          "associated_issues": ["发热", "掉帧"], // 在"游戏"场景下高频出现的问题
          "associated_features": ["120Hz高刷"]   // 在"游戏"场景下高频夸赞的功能
        },
        {
          "label": "通勤",
          "heat": 5000,
          "mentions": 30,
          "associated_features": ["降噪", "续航"]
        }
      ],
      "audiences": [
        {
          "label": "学生党",
          "heat": 2000,
          "mentions": 15,
          "preferences": ["性价比", "教育优惠"] // 关联最强的 market_factors 或 features
        }
      ]
    },
    "opportunities": {
      "kano_model": {
        "must_be": [
          {"label": "发热控制", "heat": 8000, "mentions": 50, "sentiment": -0.8}, // 痛点强烈
          {"label": "降价", "heat": 6000, "mentions": 40, "sentiment": -0.6}
        ],
        "attractive": [
          {"label": "紫色外观", "heat": 5000, "mentions": 5, "sentiment": 0.9} // 惊喜点 (低频高热)
        ],
        "one_dimensional": [
          {"label": "长续航", "heat": 2000, "mentions": 30, "sentiment": 0.5} // 期望点
        ]
      }
    },
    "competition": {
      "top_competitors": ["竞品A", "竞品B"],
      "comparison_sentiment": -0.2,
      "target_sentiment": 0.6,
      "competitor_sentiment": 0.4,
      "competitor_details": [
        {
          "name": "竞品A",
          "sentiment": 0.5,
          "heat": 2000,
          "mentions": 8,
          "top_features": ["性价比高", "续航好"],
          "top_issues": ["拍照一般"]
        }
      ]
    },
    "kol_voices": [
      {"author": "数码大V", "sentiment": 0.5, "summary": "综合体验不错，但有溢价", "post_id": "p101", "cii": 45.2}
    ]
  },

  // 完整融合数据（用于项目级再分析）
  // key 格式: canonical_name（只按实体名称分组）
  "aggregated_entities": {
    "iphone": {  // 只按名称分组，不按情感分组
      "name": "iPhone 16",
      "canonical_name": "iphone",
      "type": "产品",
      "sentiment": 0.35,           // 派生情感值 [-1, 1]，CII 加权
      "sentiment_distribution": {"positive": 10, "negative": 3, "neutral": 2}, // 情感分布
      "heat": 4500,
      "mentions": 15,
      "post_source_count": 5,
      "comment_source_count": 10,
      "post_ids": [101, 102, 103, 105, 108],
      // 实体维度信息（带帖子追溯，用于项目级再融合）
      "features": [  // 天然正面
        {"text": "外观好看", "post_ids": [101, 102, 105]},
        {"text": "拍照清晰", "post_ids": [102, 108]}
      ],
      "issues": [    // 天然负面
        {"text": "发热严重", "post_ids": [103, 105]}
      ],
      "expectations": [
        {"text": "降价", "post_ids": [101, 102, 103, 105, 108]}
      ],
      "audience": [
        {"text": "年轻人", "post_ids": [101, 102]}
      ],
      "scenarios": [
        {"text": "日常拍照", "post_ids": [101, 105]}
      ],
      "market_factors": [
        {"text": "价格高", "post_ids": [101, 102, 103]}
      ],
      "competitors": [
        {"text": "华为", "post_ids": [103, 105]}
      ]
    }
  },
  "aggregated_opinions": {
    "价格|-1": {
      "category": "价格",
      "sentiment": -1,
      "heat": 4500,
      "mentions": 15,
      "post_source_count": 3,
      "comment_source_count": 12,
      "post_ids": [101, 102, 105, 108],
      "opinions": [  // 全部观点（带帖子追溯，用于项目级再融合）
        {"text": "定价过高", "post_ids": [101, 102, 105]},
        {"text": "不值这个价", "post_ids": [102, 108]},
        {"text": "性价比低", "post_ids": [105]}
      ]
    }
  }
}
```

## 6. 开发实现建议

1.  **参数透传**：确保 `time_range` 参数能从 API 传到 Celery Coordinator。
2.  **时间筛选**：在 `Coordinator` 分发子任务时，根据 `time_range` 过滤 `post_ids`。
3.  **Aggregator 扩充**：
    *   **实现主体过滤**：确保 NSR 和 KANO 分析只针对本品，隔离竞品数据。
    *   **实现 SERP 计算**：计算 Top 20 帖子的加权情感。
    *   实现共现矩阵 (Scenario-Context)。
    *   实现 KANO 分类逻辑。
    *   实现营销渗透率计算。
4.  **Prompt 优化**：修改评论提取 Prompt，支持传入 `summary` 而非 `full_text`。
