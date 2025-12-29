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

## 1.1 情感评分体系说明 (Sentiment Scoring System) [重要设计决策]

本项目采用**双重情感评分体系**，以平衡宏观趋势的敏锐度与微观提取的稳定性：

*   **宏观初筛 (Screening Phase)**: 采用 **5级评分 (-2 ~ +2)**
    *   **范围**: `-2`(强烈负面), `-1`(轻度负面), `0`(中性), `1`(轻度正面), `2`(强烈正面)
    *   **用途**: 计算 **NSR (净情感率)**、**SERP 健康度**、**四象限分析**。
    *   **设计意图**: 在宏观层面，必须区分"普通吐槽"与"严重公关危机"，以及"一般好评"与"品牌狂热"，以准确反映舆情烈度。

*   **微观提取 (Extraction Phase)**: 采用 **3级评分 (-1 ~ +1)**
    *   **范围**: `-1`(负面), `0`(中性), `1`(正面)
    *   **用途**: **实体画像**、**观点聚合**、**IPA 产品诊断**。
    *   **设计意图**: 在提取具体实体和细粒度观点时，降低颗粒度能显著减少 LLM 的幻觉和分类不稳定性，确保聚合结果的准确性。痛点即为负面，爽点即为正面，无需过度区分程度。

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
        *   `source_comments`: 来源评论编号列表（仅评论提取）
        *   `support_score`: 支持度分数（仅评论提取，来源评论点赞数之和）
    *   `general_opinions`: 通用观点列表（category, opinions, sentiment）。
        *   评论提取时额外包含 `source_comments` 和 `support_score`。
    *   `summary`: 内容摘要。

### 3.1 评论来源追踪与支持度计算

评论深度分析采用**来源追踪机制**，解决"高互动原文的低赞评论观点权重过高"问题：

*   **输入格式**：评论以 `评论[编号]: 内容` 格式发送给 LLM。
*   **LLM 输出**：每个实体/观点包含 `source_comments` 字段，标注来源评论编号。
*   **支持度计算**（程序端完成）：
    ```python
    # 构建编号到点赞数的映射
    likes_map = {1: 235, 2: 89, 3: 12, ...}
    
    # 计算支持度 = 来源评论点赞数之和
    support_score = sum(likes_map[idx] for idx in source_comments)
    ```
*   **设计理念**：LLM 只负责语义理解和来源标注，程序负责精确的数值计算。

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

#### 4.3.0 共享工具模块 (Shared Utils)

实体聚合和观点聚合共用一套工具函数，位于 `aggregation/utils.py`：

```python
# 综合评分计算：结合影响力(heat)和讨论广泛性(mentions)
def calculate_score(heat: float, mentions: int) -> float:
    return math.log(heat + 1) * math.log(mentions + 1)

# 帖子影响力计算
def calculate_impact_score(cii: float, value_score: float | None) -> float:
    quality_factor = 0.5 + (value_score or 5.0) / 10.0
    return cii * quality_factor

# 评论权重计算（区分原文和评论的权重）
COMMENT_WEIGHT_BASE_FACTOR = 0.1

def calculate_comment_weight(support_score: int, post_impact: float) -> float:
    """
    评论权重 = post_impact × 0.1 × log10(support_score + 1)
    
    权重示例（假设 post_impact = 1000）：
    - support_score=1000 → 300 (原文的 30%)
    - support_score=100  → 200 (原文的 20%)
    - support_score=10   → 100 (原文的 10%)
    - support_score=0    → 0   (无权重)
    """
    if support_score <= 0:
        return 0.0
    return post_impact * COMMENT_WEIGHT_BASE_FACTOR * math.log10(support_score + 1)

# 名称归一化：去除空格、转小写
def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name.lower())

# 相似度判断：支持完全包含和字符相似度
def are_similar(name1: str, name2: str, threshold: float = 0.8) -> bool:
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if n1 == n2: return True
    if n1 in n2 or n2 in n1: return True
    return SequenceMatcher(None, n1, n2).ratio() >= threshold

# 构建相似度映射：按 score 排序，高分优先成为标准名称
def build_similarity_mapping(items: list[dict], threshold: float = 0.8) -> dict[str, str]:
    ...
```

**设计优势**：
- 代码复用：避免实体/观点模块重复实现
- 逻辑一致：确保归一化规则统一
- **权重分离**：原文和评论使用不同的权重计算，避免低赞评论观点权重过高
- 易于维护：单点修改影响全局

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
        # 权重与情感派生计算
        "total_impact": float,    # 权重累加（原文用 impact，评论用 comment_weight）
        "total_weight": float,    # 对数平滑权重（用于情感计算）
        "sentiment_weighted_sum": float,  # Σ(sentiment * smoothed_weight)
        "positive_count": int,   # 正面提及次数
        "negative_count": int,   # 负面提及次数
        "neutral_count": int,    # 中性提及次数
        "impact_added_posts": set,  # 已贡献权重的帖子ID（避免重复累加）
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
    
    **权重计算逻辑**：
    - **原文实体**：`entity_weight = calculate_impact_score(cii, value_score)`
    - **评论实体**：`entity_weight = calculate_comment_weight(support_score, post_impact)`
    - **情感计算**：使用对数平滑权重 `log10(max(impact, 1)) + 1` 避免超高热度帖子主导情感

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
    4.  **三重指标与综合评分**：
        *   **Heat (热度)**：$\sum CII_p$（每帖只贡献一次，避免重复累加）。
        *   **Mentions (频次)**：$Count(Unique\_Posts)$（唯一帖子数）。
        *   **Score (综合评分)**：$Heat \times \log(Mentions + 1)$
        *   *策略*：排序统一使用 `Score`，综合考虑影响力（Heat）和讨论广泛性（Mentions）。
        *   *设计意图*：避免"偶然爆款"（高 Heat 低 Mentions）压过"普遍共识"（中 Heat 高 Mentions）。
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
        "top_entities": [...],        # 综合评分排名前N的实体列表（展示用，按 score 排序）
        "target_entities": [...],     # 本品实体列表（按 score 排序）
        "competitor_entities": [...], # 竞品实体列表（按 score 排序）
        "aggregated_entities": [...], # 完整融合数据（数组格式，用于项目级分析和派生计算）
        "llm_token_stats": {...},     # LLM token 使用统计（如果调用了 LLM）
    }
    ```

### 4.4 观点聚合 (Opinion Aggregation)

观点聚合处理 LLM 提取的 `general_opinions`，按 **category + sentiment** 分组。

*   **设计理念：按情感分组**
    *   观点的情感是**独立维度**：同一话题的正面/负面观点是对立声音
    *   例如：话题"价格"下，"价格实惠"(正面) 和 "价格太贵"(负面) 必须分开统计
    *   **分组键**：`{category}|{sentiment}`（如 `价格|-1`, `价格|1`）

*   **观点数据结构**：
    ```python
    opinion_data[f"{category}|{sentiment}"] = {
        "category": str,           # 话题类别
        "sentiment": int,          # 情感值 (-1, 0, 1)
        "total_impact": float,     # 权重累加（区分原文/评论权重）
        "impact_added_posts": set, # 已贡献权重的帖子ID
        "post_sources": set,       # 从帖子原文提取的帖子ID
        "comment_sources": set,    # 从评论提取的帖子ID
        "post_ids": set,           # 所有涉及的帖子ID
        "opinions": dict,          # 具体观点 {text: set(post_ids)}
    }
    ```

*   **聚合逻辑**：
    1.  **分组键生成**：`key = f"{category}|{sentiment}"`
    2.  **权重计算**（关键更新）：
        - **原文观点**：使用 `post_impact = calculate_impact_score(cii, value_score)`
        - **评论观点**：使用 `comment_weight = calculate_comment_weight(support_score, post_impact)`
    3.  **热度累加**：每帖只贡献一次权重（通过 `impact_added_posts` 去重）
    4.  **来源标记**：区分帖子原文 vs 评论来源
    5.  **观点收集**：记录具体观点文本及其来源帖子

*   **输出结构**：
    ```python
    return {
        "opinions": [...],             # 聚合后的观点列表（按 score 排序）
        "llm_token_stats": {...},      # LLM token 使用统计（如果调用了 LLM）
    }
    ```

    每个展示项包含：
    ```python
    {
        "name": str,                     # 观点名称
        "category": str,                 # 话题类别
        "heat": float,                   # 热度（CII累加）
        "mentions": int,                 # 唯一帖子数
        "score": float,                  # 综合评分 = heat × log(mentions + 1)
        "sentiment": int,                # 情感值 (-1, 0, 1)
        "source_distribution": {         # 来源分布
            "post": float,               # 帖子来源占比
            "comment": float             # 评论来源占比
        },
        "post_ids": [int, ...],          # 帖子ID列表（用于追溯）
        "post_source_count": int,        # 帖子来源数量
        "comment_source_count": int,     # 评论来源数量
    }
    ```

### 4.5 核心指标计算
基于清洗后的 **Target** 数据桶计算：

1.  **NSR 净情感率 (Net Sentiment Rate)**
    *   **公式**：$ NSR = \frac{\sum (Sentiment_i \times CII_i)}{\sum CII_i} $
    *   *范围*：[-2, +2]
2.  **SERP 搜索健康度 (SERP Health Index)**
    *   **公式**：$ SHI = \text{Normalize}( \text{AvgWeightedSentiment}(\text{Top 20 Posts}) ) $
    *   *作用*：评估搜索结果首屏观感。

### 4.6 派生分析 (Derived Analysis) - "先融合，后派生"架构

派生分析采用**"先融合，后派生"**架构：先完成 `aggregated_entities` 和 `aggregated_opinions` 的基础聚合，再从中派生高级洞察。

```
┌─────────────────────────────────────────────────────────────────┐
│                     LLM 深度分析结果                             │
│  (entities, general_opinions, from posts & comments)            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                    基础聚合层 (Primary Aggregation)               │
│  ┌─────────────────────┐     ┌─────────────────────┐             │
│  │ aggregate_entities  │     │ aggregate_opinions  │             │
│  │ (按 canonical_name) │     │ (按 category|sent)  │             │
│  └──────────┬──────────┘     └──────────┬──────────┘             │
│             │                           │                         │
│             ▼                           ▼                         │
│  ┌─────────────────────┐     ┌─────────────────────┐             │
│  │aggregated_entities  │     │aggregated_opinions  │             │
│  │(完整实体融合数据)    │     │(完整观点融合数据)    │             │
│  └──────────┬──────────┘     └──────────┬──────────┘             │
└─────────────┼───────────────────────────┼─────────────────────────┘
              │                           │
              ▼                           ▼
┌───────────────────────────────────────────────────────────────────┐
│                    派生分析层 (Derived Analysis)                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐     │
│  │derive_context   │ │perform_ipa      │ │analyze_         │     │
│  │_analysis        │ │_analysis        │ │competition      │     │
│  │(场景+人群)       │ │(产品诊断)        │ │(竞品分析)        │     │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘     │
└───────────────────────────────────────────────────────────────────┘
```

**架构优势**：
1. **数据一致性**：所有派生分析使用相同的归一化实体数据
2. **可追溯性**：每个维度都保留 `post_ids`，支持反向追溯
3. **复用性**：`aggregated_entities` 可用于项目级跨任务分析

#### 4.6.1 场景与人群画像派生 (derive_context_analysis)

从 `aggregated_entities` 派生场景和人群画像：

*   **输入**：`aggregated_entities`（已完成实体归一化）
*   **派生逻辑**：
    ```
    对于每个归一化实体：
      - 遍历 entity.scenarios → 累加场景热度，关联该实体的 issues/features
      - 遍历 entity.audience  → 累加人群热度，关联该实体的 market_factors/features
    ```
*   **输出**：
    ```python
    {
        "scenarios": [
            {
                "label": "游戏",
                "heat": 3000,
                "mentions": 25,
                "associated_issues": ["发热", "掉帧"],    # 关联问题
                "associated_features": ["120Hz高刷"],     # 关联特性
            }
        ],
        "audiences": [
            {
                "label": "学生党",
                "heat": 2000,
                "mentions": 15,
                "preferences": ["性价比", "教育优惠"],    # 关联偏好
            }
        ]
    }
    ```
*   **置信度过滤**：仅保留 `mentions >= 2` 的标签

#### 4.6.2 竞品分析派生 (analyze_competition)

从 `entity_stats` 派生竞品对比分析：

*   **输入**：`entity_stats`（含 target_entities, competitor_entities）
*   **输出**：
    ```python
    {
        "top_competitors": ["竞品A", "竞品B"],
        "target_sentiment": 0.6,        # 本品平均情感
        "competitor_sentiment": 0.4,    # 竞品平均情感
        "comparison_sentiment": 0.2,    # 对比优势
        "competitor_details": [
            {
                "name": "竞品A",
                "sentiment": 0.5,
                "heat": 2000,
                "mentions": 8,
                "top_features": ["性价比高"],
                "top_issues": ["拍照一般"],
            }
        ]
    }
    ```

### 4.7 直接聚合分析 (Direct Aggregation)

以下分析直接从 `posts_data` 聚合，不依赖派生层：

1.  **情感-互动四象限 (Quadrant)**
    *   **数据源**：`posts_data`（每篇帖子的 sentiment 和 CII）
    *   **X轴**：帖子情感分 ($Sentiment$)
    *   **Y轴**：帖子互动指数 ($CII$)
    *   **象限划分**：Q1爆雷区、Q2品牌区、Q3吐槽区、Q4小众区

2.  **KOL 声音提取**
    *   **数据源**：`posts_data`（高 CII 帖子）
    *   **逻辑**：选取 CII Top 5 的帖子作为 KOL 声音

3.  **时间分布与新鲜度**
    *   **数据源**：`posts_data`（published_at 字段）
    *   **输出**：时间分布图、最近7/30天帖子数、平均发布天数

### 4.8 营销渗透率 (Marketing Penetration)
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
    // 实体排行（只按名称分组，情感为派生值，按 score 排序）
    "top_entities": [
      {
        "name": "iPhone 16",
        "type": "产品",
        "role": "target",           // target / competitor / other
        "heat": 4500,               // Σ CII (去重后)
        "mentions": 15,             // 唯一帖子数
        "score": 12532.5,           // 综合评分 = heat × log(mentions + 1)
        "sentiment": 0.35,          // 派生情感值 [-1, 1]，CII 加权
        "sentiment_distribution": {"positive": 10, "negative": 3, "neutral": 2}, // 情感分布
        "source_distribution": {"post": 0.3, "comment": 0.7},
        "top_features": ["外观好看", "拍照清晰", "续航持久"],
        "top_issues": ["发热严重", "价格高"],
        "top_expectations": ["降价", "改善散热"],
        "post_ids": [101, 102, 103, 105, 108]  // 帖子ID列表（用于追溯）
      }
    ],
    "target_entities": [...],     // 本品实体列表（按 score 排序）
    "competitor_entities": [...], // 竞品实体列表（按 score 排序）

    // 观点排行（按 name+sentiment 分组，按 score 排序）
    "top_topics": [
      {
        "name": "价格",             // 观点名称
        "category": "价格",         // 话题类别
        "sentiment": -1,            // 固定情感值 (-1, 0, 1)
        "heat": 4500,
        "mentions": 15,
        "score": 12532.5,           // 综合评分 = heat × log(mentions + 1)
        "source_distribution": {"post": 0.2, "comment": 0.8}, // 80% 来自评论，说明是用户痛点而非博主痛点
        "post_ids": [101, 102, 105, 108],  // 帖子ID列表（用于追溯）
        "post_source_count": 3,
        "comment_source_count": 12
      },
      {
        "name": "发热",
        "category": "质量",
        "sentiment": -1,
        "heat": 3200,
        "mentions": 12,
        "score": 8191.2,
        "source_distribution": {"post": 0.5, "comment": 0.5},
        "post_ids": [103, 105, 108],
        "post_source_count": 6,
        "comment_source_count": 6
      },
      {
        "name": "外观",
        "category": "设计",
        "sentiment": 1,
        "heat": 5000,
        "mentions": 20,
        "score": 15197.5,
        "source_distribution": {"post": 0.6, "comment": 0.4},
        "post_ids": [101, 102, 103],
        "post_source_count": 12,
        "comment_source_count": 8
      }
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

  // 完整融合数据（数组格式，按 score 排序，用于项目级再分析）
  // 限制：保留 Top 60 个实体
  "aggregated_entities": [
    {
      "name": "iPhone 16",
      "role": "Target",            // Target/Competitor/Context/Other
      "category": "产品名",         // 实体类别 (如：品类词、属性词)
      "parent": "智能手机",         // 归属父类
      "type": "产品",
      "sentiment": 0.35,           // 派生情感值 [-1, 1]，CII 加权
      "sentiment_distribution": {"positive": 10, "negative": 3, "neutral": 2}, // 情感分布
      "heat": 4500,
      "mentions": 15,
      "score": 12532.5,            // 综合评分 = heat × log(mentions + 1)
      "post_source_count": 5,
      "comment_source_count": 10,
      "post_ids": [101, 102, 103, 105, 108],
      
      // 原始词条信息（只有真正发生合并时才保留）
      "original_terms": [
         {"text": "iPhone16", "count": 10},
         {"text": "苹果16", "count": 5}
      ],

      // 实体维度信息（带帖子追溯，用于项目级再融合）
      // 清洗策略：Top 3 实体全量清洗，Top 4-10 核心字段清洗，其余保留 Raw Top 20
      "features": [  // 天然正面
        {"text": "外观好看", "count": 3, "post_ids": [101, 102, 105]},
        {"text": "拍照清晰", "count": 2, "post_ids": [102, 108]}
      ],
      "issues": [    // 天然负面
        {"text": "发热严重", "count": 2, "post_ids": [103, 105]}
      ],
      "expectations": [
        {"text": "降价", "count": 5, "post_ids": [101, 102, 103, 105, 108]}
      ],
      "audience": [
        {"text": "年轻人", "count": 2, "post_ids": [101, 102]}
      ],
      "scenarios": [
        {"text": "日常拍照", "count": 2, "post_ids": [101, 105]}
      ],
      "market_factors": [
        {"text": "价格高", "count": 3, "post_ids": [101, 102, 103]}
      ],
      "competitors": [
        {"text": "华为", "count": 2, "post_ids": [103, 105]}
      ]
    }
  ],
  
  // 完整融合数据（数组格式，按 score 排序，用于项目级再分析）
  // 限制：保留 Top 60 个话题
  "aggregated_opinions": [
    {
      "name": "价格",              // 观点名称
      "category": "价格",          // 话题类别
      "sentiment": -1,
      "heat": 4500,
      "mentions": 15,
      "score": 12532.5,            // 综合评分 = heat × log(mentions + 1)
      "source_distribution": {"post": 0.2, "comment": 0.8},
      "post_source_count": 3,
      "comment_source_count": 12,
      "post_ids": [101, 102, 105, 108],
      
      // 原始词条信息（只有真正发生合并时才保留）
      "original_terms": [
         {"text": "定价", "count": 10},
         {"text": "售价", "count": 5}
      ]
    }
  ]
}
```

## 6. 前端报告布局

分析报告的展示顺序经过优化，按用户关注度和数据依赖关系排列：

```
1. 热门观点（问题 vs 特性）  -- 用户最关注的核心洞察
2. IPA 产品诊断              -- 基于观点数据的产品力分析
3. 热门实体                  -- 实体画像和维度信息
4. 竞品分析                  -- 基于实体数据的对比分析
5. 场景与人群画像            -- 基于实体数据的派生分析
6. 高影响力内容 (KOL)        -- 关键意见领袖
7. 情感-互动四象限           -- 可视化分析
8. 时间分布                  -- 数据时效性
```

**设计原则**：
- 观点优先：用户最想了解的是"大家怎么说"
- IPA 紧随观点：IPA 诊断直接基于观点和实体数据
- 实体次之：实体画像提供更深入的结构化分析
- 竞品/场景人群最后：这些是派生分析，依赖实体数据

## 7. 开发实现建议

1.  **参数透传**：确保 `time_range` 参数能从 API 传到 Celery Coordinator。
2.  **时间筛选**：在 `Coordinator` 分发子任务时，根据 `time_range` 过滤 `post_ids`。
3.  **Aggregator 扩充**：
    *   **实现主体过滤**：确保 NSR 和 IPA 分析只针对本品，隔离竞品数据。
    *   **实现 SERP 计算**：计算 Top 20 帖子的加权情感。
    *   实现共现矩阵 (Scenario-Context)。
    *   实现营销渗透率计算。
4.  **Prompt 优化**：修改评论提取 Prompt，支持传入 `summary` 而非 `full_text`。
5.  **代码规范**：
    *   共享工具函数统一放在 `aggregation/utils.py`
    *   所有排序统一使用 `score` 字段
    *   LLM 归一化和程序归一化并行执行，提高效率
