# 新闻监测数据分析流水线方案

> 最终方案，基于社媒流水线对比分析 + 行业最佳实践 + 多轮讨论确定。

## 一、设计原则

| 原则 | 说明 |
|------|------|
| 量少质重 | 新闻 30-50 篇 vs 社媒 500 篇，分析策略完全不同 |
| LLM 预算集中 | 轻量逐篇标注 + 一次整体分析，而非逐篇重度提取再聚合 |
| 研究目标驱动 | 相关性判断基于 `analysis_goal`（可能是实体、话题、事件），不硬编码为实体匹配 |
| 无 spam 维度 | 新闻经编辑审核无水军，用 `source_tier`（来源权威度）替代社媒的 `spam_distribution` |
| 覆盖面 > 互动量 | 核心指标是 MCI（媒体报道指数），不是 CII（互动指数） |

## 二、与社媒流水线的差异对比

| 环节 | 社媒 | 新闻 | 原因 |
|------|------|------|------|
| 数据采集 | 爬虫抓帖子 → `SocialPost` + `SocialComment` | SerpAPI 搜索 → Crawl4AI 抓全文 → `NewsArticle` | 数据来源不同 |
| 初筛（screening） | 独立阶段，screening_chain 逐帖打分 | **不需要独立阶段**，相关性判断内置在逐篇解析中 | 量小，无水军 |
| 逐篇分析 | 重度 — post_extraction_chain 完整提取实体/观点/摘要 | **轻量** — 相关性 + 情感 + 类型 + 实体名单 + 引述 + 摘要 | 30 篇可整体分析，无需逐篇深挖 |
| 聚合分析 | entity/opinion_normalization 两轮 LLM | **一次整体分析** — 直接输入全部文章的标注结果 | 数据量可一次性喂入 LLM |
| 去重 | platform + post_id_on_platform | **URL 归一化**（Crawl4AI 前处理） | 新闻按链接去重 |
| 质量维度 | spam_distribution（4D：高推广/低推广 × 帖子/评论） | **source_tier_distribution**（tier1/tier2/tier3） | 新闻的质量维度是来源权威性 |
| 评论层 | SocialComment 独立表 | **不需要** | 新闻评论不是分析重点 |
| 核心指标 | CII（互动指数）、NSR（净情感比） | **MCI**（媒体报道指数 = 文章数 × 来源权重）、情感分布 | 新闻价值在覆盖面 |
| 特有分析 | — | 引述提取、叙事聚类、文章类型分类 | 新闻特有的高价值信号 |

## 三、数据模型

### 3.1 现有模型（保持不变）

- `NewsMonitor` — 新闻监测项目
- `NewsTask` — 新闻采集任务（含 phase/status/analysis_result）

### 3.2 新增模型

```python
class NewsArticle(Base):
    """新闻文章 — 对标社媒的 SocialPost"""
    __tablename__ = "news_articles"

    id: int                          # PK
    task_id: int                     # FK → news_tasks.id, ondelete CASCADE
    url: str                         # 文章链接（唯一索引，用于去重）
    title: str                       # 标题
    snippet: str | None              # SerpAPI 返回的摘要
    full_text: str | None            # Crawl4AI 抓取的全文（probe 阶段为 NULL）
    source_name: str                 # 来源媒体名称
    source_tier: str                 # 来源等级: tier1 / tier2 / tier3
    author: str | None               # 作者（如果可获取）
    published_at: datetime | None    # 发布时间
    image_url: str | None            # 配图链接

    # 逐篇轻量分析结果
    relevance: str | None            # high / medium / low（与研究目标的相关程度）
    sentiment: float | None          # 情感分 -1 ~ 1
    article_type: str | None         # report / opinion / pr / analysis
    mentioned_entities: list | None  # JSON: 提及的实体名单 [{name, role}]
    key_quotes: list | None          # JSON: 关键引述 [{speaker, quote}]
    summary: str | None              # 一句话摘要

    raw_data: dict | None            # SerpAPI 原始响应（保留原始数据）
    created_at: datetime
    updated_at: datetime
```

**设计说明：**

- 逐篇分析字段（relevance ~ summary）直接放在 `NewsArticle` 上，不单独建 `NewsArticleAnalysis` 表。原因：新闻只有一轮轻量分析，不像社媒有 screening + deep + aggregation 三阶段，不需要独立追踪。
- `raw_data` 保留 SerpAPI 原始响应，遵循行业最佳实践（MEO 模式：存原始 JSON，支持未来重新解析）。
- `full_text` 仅用于内部 LLM 分析，前端不展示全文（版权合规，展示标题+摘要+链接回原文）。

## 四、完整流水线

### 4.1 Probe 阶段（快速验证，无全文抓取）

```
输入：关键词 + search_params
     ↓
SerpAPI Baidu News (max=10, sort=attraction)
     ↓
按 URL 去重
     ↓
存入 NewsArticle（snippet only, full_text=NULL）
     ↓
逐篇轻量解析（基于 snippet，2组 × 5篇 = 2次 LLM 调用）
  → relevance, sentiment, article_type, mentioned_entities, summary
  → 更新 NewsArticle 对应字段
     ↓
写入 NewsTask.analysis_result（元数据摘要）:
{
  "meta": {
    "keywords": "...",
    "articles_total": 10,
    "articles_relevant": 7  // relevance=high/medium 的数量
  },
  "articles_summary": [
    { "title", "source_name", "source_tier", "relevance", "sentiment", "summary" }
  ]
}
     ↓
NewsTask.status = "completed"
返回给用户/策略审核
```

**特点：** 无 Crawl4AI 调用，成本极低（2 次 LLM + 1 次 SerpAPI），2-5 秒完成。

### 4.2 Collect 阶段（全量采集 + 分析）

```
Step 1: SerpAPI 搜索扩量
────────────────────────────────────────
SerpAPI Baidu News (max=50, 多页翻页)
  → 按 URL 去重（含 probe 已存在的文章）
  → 存入 NewsArticle（新文章）
  → 预期：30-50 篇去重后文章

Step 2: Crawl4AI 批量抓全文
────────────────────────────────────────
AsyncWebCrawler 并发抓取（semaphore 限制并发数）
  → 使用 fit_markdown（无 LLM 成本，启发式提取正文）
  → 超时 15s/篇，失败则降级用 SerpAPI snippet
  → 更新 NewsArticle.full_text
  → 预期：90%+ 成功率，30-90 秒

Step 3: 逐篇轻量解析（批量，5篇一组）
────────────────────────────────────────
每组一次 LLM 调用，输入文章全文（或 snippet），输出：
  → relevance: high / medium / low
      （判断基准：与研究目标 analysis_goal 的相关程度）
  → sentiment: -1 / 0 / 1
  → article_type: report / opinion / pr / analysis
  → mentioned_entities: [{name, role}]
  → key_quotes: [{speaker, quote}]（新闻特有高价值信号）
  → summary: 一句话摘要
  → 更新 NewsArticle 对应字段
  → 预期：6-10 次 LLM 调用

Step 4: 整体分析（一次 LLM 调用，核心价值）
────────────────────────────────────────
输入：所有 relevance=high/medium 文章的标注结果打包
  { title, source_name, source_tier, sentiment,
    article_type, mentioned_entities, key_quotes, summary }

输出 → 写入 NewsTask.analysis_result:
{
  "meta": {
    "keywords": "...",
    "articles_total": 35,
    "articles_crawled": 32,
    "articles_analyzed": 28,      // relevance=high/medium
    "source_tier_distribution": { "tier1": 8, "tier2": 15, "tier3": 9 },
    "date_range": { "earliest": "...", "latest": "..." }
  },
  "coverage": {
    "media_coverage_index": 72.5,   // 文章数 × 来源权重
    "intensity": "high",            // low / medium / high
    "trend": "rising",              // rising / stable / declining
    "daily_distribution": [
      { "date": "2026-04-01", "count": 5, "tier1_count": 2 }
    ]
  },
  "sentiment": {
    "overall": 0.3,
    "distribution": { "positive": 12, "neutral": 10, "negative": 6 },
    "by_source_tier": { "tier1": 0.5, "tier2": 0.2, "tier3": 0.1 }
  },
  "entities": [
    {
      "name": "品牌A",
      "role": "target",
      "mention_count": 25,
      "sentiment": 0.4,
      "source_count": 12,
      "key_claims": ["..."]
    }
  ],
  "narratives": [
    {
      "theme": "产品创新",
      "article_count": 8,
      "sentiment": 0.6,
      "summary": "...",
      "representative_articles": [
        { "title": "...", "source_name": "...", "date": "..." }
      ]
    }
  ],
  "competitive_landscape": {
    "entities_mentioned": [
      { "name": "竞品A", "mentions": 10, "sentiment": -0.1 }
    ],
    "positioning_summary": "..."
  },
  "key_quotes": [
    { "speaker": "CEO张某", "quote": "...", "source_name": "经济日报", "date": "..." }
  ]
}
     ↓
NewsTask.status = "completed"
```

## 五、LLM 链设计

### 5.1 news_tagging_chain（逐篇轻量标注）

**定位：** 批量处理，5 篇一组，结构化输出。

```
系统提示：
  你是新闻分析助手。研究目标：「{analysis_goal}」
  请对以下 {n} 篇文章进行结构化标注。

输入：
  文章列表 [{title, source_name, content_or_snippet}]

输出（JSON）：
  [
    {
      "article_index": 0,
      "relevance": "high",
      "sentiment": 1,
      "article_type": "report",
      "mentioned_entities": [{"name": "品牌A", "role": "target"}],
      "key_quotes": [{"speaker": "某高管", "quote": "..."}],
      "summary": "..."
    }
  ]
```

### 5.2 news_insight_chain（整体分析）

**定位：** 一次调用，全局视角，产出最终洞察。

```
系统提示：
  你是媒体分析专家。研究目标：「{analysis_goal}」
  研究主体：「{subject}」
  以下是 {n} 篇相关新闻的标注结果，请进行整体分析。

输入：
  所有 relevance=high/medium 文章的标注结果

输出（JSON）：
  {
    "coverage": { intensity, trend, daily_distribution },
    "sentiment": { overall, distribution, by_source_tier },
    "entities": [...],
    "narratives": [...],
    "competitive_landscape": {...},
    "key_quotes": [...]
  }
```

### 5.3 成本估算

| 步骤 | 调用次数 | Token 量 | 预估成本 |
|------|---------|---------|---------|
| SerpAPI | 3-5 次 | — | ~$0.05 |
| Crawl4AI | 30-50 URL | — | 免费（自部署） |
| news_tagging_chain | 6-10 次（5篇/组） | ~2K 入 + ~1K 出 /次 | ~$0.05 |
| news_insight_chain | 1 次 | ~8K 入 + ~3K 出 | ~$0.02 |
| **合计** | | | **~$0.12/次采集** |

对比社媒：screening 100 次 + deep 500 次 + aggregation 3 次 ≈ $2-5/次。新闻成本约为社媒的 1/20。

## 六、来源权威度分层

```python
# 预置中国新闻来源分层（可配置扩展）
SOURCE_TIERS = {
    "tier1": [  # 权威央媒/官媒
        "新华网", "人民日报", "央视", "中国日报", "经济日报",
        "光明日报", "环球时报", "中国新闻网", "澎湃新闻",
    ],
    "tier2": [  # 行业/门户/都市媒体
        "第一财经", "财新", "21世纪经济报道", "每日经济新闻",
        "界面新闻", "36氪", "虎嗅", "新浪财经", "腾讯新闻",
        "网易新闻", "搜狐新闻", "凤凰网",
    ],
    # tier3: 其他（默认）— 百家号、搜狐号、自媒体等
}
```

权重用于 MCI 计算：tier1 × 3, tier2 × 2, tier3 × 1。

## 七、策略流水线集成修复

### 7.1 当前断点

| 位置 | 问题 | 修复方案 |
|------|------|---------|
| `execute_news_probe()` | TODO 桩 | 实现 SerpAPI 调用 + 逐篇标注 |
| `execute_news_collect()` | TODO 桩 | 实现 SerpAPI + Crawl4AI + 标注 + 整体分析 |
| `_build_probe_task_summaries()` | 只处理社媒任务，跳过新闻 | 增加新闻分支，提取 articles_summary |
| `asyncio.ensure_future(execute_news_collect(db, ...))` | 共享请求级 AsyncSession | 为后台任务创建独立 session |
| `news_analysis_chain` | 不存在 | 新建 news_tagging_chain + news_insight_chain |

### 7.2 analysis_result 兼容性

策略下游（coverage_check_chain、phase1/2/3_chain）消费 `NewsTask.analysis_result`。新方案的结构包含：

- `entities` — 与社媒的 `aggregated_entities` 同构（name, role, mentions, sentiment）
- `narratives` — 新闻特有，社媒无对应项，phase 链需要识别
- `coverage` / `sentiment` — 与社媒的 `metrics` 类似但字段不同

需要在 `_create_auto_slices()` 中为新闻任务做适配映射，确保 AnalysisSlice 能统一处理两种数据源。

## 八、前端「新闻采集」板块

**在 `NewsArticle` 模型和 SerpAPI 对接完成后添加。** 页面结构：

| 页面 | 路径 | 功能 |
|------|------|------|
| 任务列表（全局） | `/news-media/tasks` | 跨项目查看所有新闻采集任务 |
| 任务详情 | `/news-media/tasks/[id]` | 文章列表 + 逐篇标注结果 + 整体分析报告 |

文章列表展示字段：标题（链接回原文）、来源、来源等级 badge、情感 badge、相关性、文章类型、发布时间。

**不展示全文**（版权合规），只展示标题 + 摘要 + 链接。

## 九、实施顺序

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **1. 数据模型** | 新增 `NewsArticle` 表 + Alembic 迁移 | 无 |
| **2. SerpAPI 客户端** | `serpapi_client.py`，封装 Baidu News API | 无 |
| **3. Crawl4AI 集成** | `article_crawler.py`，批量抓全文 + 失败降级 | 无 |
| **4. LLM 链** | `news_tagging_chain`（逐篇标注）+ `news_insight_chain`（整体分析） | 无 |
| **5. 实现 execute_news_probe** | SerpAPI → 存 NewsArticle → 标注 → 写 analysis_result | 1, 2, 4 |
| **6. 实现 execute_news_collect** | SerpAPI → Crawl4AI → 标注 → 整体分析 → 写 analysis_result | 1, 2, 3, 4 |
| **7. 修复策略集成** | probe_summaries 新闻分支 + session 独立化 | 5, 6 |
| **8. 前端采集板块** | 任务列表 + 文章列表 + 分析报告 | 1, 5, 6 |
