# Feature Inventory: 新闻监控 (`src/news_media/`)

> ⚠️ **存档（时点快照）**：本文档是 ADR-001 Phase 0 时期（2026-04）的事实盘点，仅供决策溯源，**不随代码更新**。模块现状以代码与各级 CLAUDE.md 为准（已知漂移示例：新闻链已拆 pass1/pass2 并新增 themes 议题层）。

> 盘点日期:2026-04-20
> 目的:为 ADR-001 架构决策提供事实基础。**本文档只做盘点,不下架构结论**。

## TL;DR

新闻监控模块比社媒监控**明显轻量**——只有 2 条 LLM 链,无 Stage 1/2/3 流水线,前端依赖的字段也少得多。

**关键发现**:
- `NEWS_TAGGING`(逐篇标注,6 维元数据)+ `NEWS_INSIGHT`(切片级聚合,5 维洞察)是**唯二**的 LLM 链
- `NEWS_INSIGHT` 的输出(narratives/entities/key_quotes 等)**结构相对自由**,接近 LLM-native 的自然叙事——潜在重构门槛低于社媒
- **Probe / Collect 两阶段设计**是核心特色:probe 纯搜索(无 LLM),collect 才做全文+标注
- 两个真实使用场景:**独立监测**(用户直接建 NewsMonitor)vs **策略绑定**(strategy.news_monitor_id 自动创建)
- 有一个 APScheduler 定时任务 `news_task_watchdog` 负责超时回收

---

## 1. LLM Chain 清单(2 条)

### 1.1 `NEWS_TAGGING` — 逐篇标注链

文件:[`backend/src/llm/chains/news/tagging_chain.py`](../../backend/src/llm/chains/news/tagging_chain.py)

- **核心职责**:批量给新闻打 6 维结构化标注
- **输入**:
  - `analysis_goal`:研究背景,用于 context 化标注
  - `subject`:研究主体(非空时 `target` role 硬绑定到此;空则所有实体归 `context`)
  - `competitors`:已知竞品列表(见 §1.3 三种 role 归类模式)
  - `article_count`:本批文章数(当前配置 **10 篇**)
  - `articles_content`:格式化的文章内容(title/source/snippet 或 full_text 截断 2000 字)
- **输出**(JSON 数组,每文一条):
  - `relevance`: high / medium / low
  - `sentiment`: -2 ~ 2 整数
  - `article_type`: report / opinion / pr / analysis
  - `mentioned_entities`: `[{name, role: target/competitor/context}]`(role 归类规则见 §1.3)
  - `key_quotes`: `[{speaker, quote}]`
  - `summary`:一句话摘要(≤80 字)
- **调用频次**:每文 1 次,以 **10 篇/批** 批处理(由 `settings.CELERY_AI_NEWS_TAGGING_BATCH_SIZE` 配置,默认 10)
- **执行阶段**:**仅 collect 阶段**(probe 阶段不调)
- **调用方**:
  - [`tasks/tasks.py::_async_run_collect()`](../../backend/src/news_media/tasks/tasks.py)(collect 流水线)
  - [`tasks/service.py::_tag_articles_batch()`](../../backend/src/news_media/tasks/service.py)(通用批处理)
- **🔑 独有价值**:
  - **下游字段的唯一来源**:`NewsArticle.relevance/sentiment/article_type/mentioned_entities/key_quotes/summary` 全部依赖它
  - **前端过滤器硬依赖**:任务详情页的 relevanceFilter / tierFilter 直接消费 `article.relevance` / `article.source_tier`
  - **成本分层设计**:probe 不调用→低成本探测,collect 才调用→深度分析,反映"快速验证 vs 全量标注"的业务权衡

### 1.2 `NEWS_INSIGHT` — 切片级聚合分析链

文件:[`backend/src/llm/chains/news/insight_chain.py`](../../backend/src/llm/chains/news/insight_chain.py)

- **核心职责**:汇总已标注文章,输出 5 类全局洞察
- **输入**:
  - `analysis_goal`, `subject`
  - `competitors`:已知竞品列表(见 §1.3 三种 role 归类模式)
  - `article_count`
  - `tagged_articles`:已标注文章的格式化字符串
  - source_tier 分层统计(tier1/tier2/tier3/wechat_mp 各自数量)
- **输出**(JSON 对象):
  ```
  coverage:            { media_coverage_index (0-100), intensity, trend, summary }
  sentiment:           { overall (加权), distribution, by_source_tier }
  narratives:          [{ theme, article_count, sentiment, summary, representative_titles }] × ≤5
  entities:            [{ name, role, mention_count, sentiment, source_count, key_claims }] × ≤15
  competitive_landscape: { positioning_summary, entities_mentioned }  // 仅当有 competitor 时
  key_quotes:          [{ speaker, quote, source_name, context }] × ≤5
  ```
- **调用频次**:每切片 1 次
- **调用方**:
  - [`analysis/service.py::run_slice_analysis()`](../../backend/src/news_media/analysis/service.py)(NewsSlice 创建时自动触发)
  - [`strategies/service.py::_run_news_probe_review_one()`](../../backend/src/strategies/service.py)(策略 probe 审查)
- **🔑 独有价值**:
  - **按 source_tier 加权情感**:tier1 权威媒体的情感权重更高,简单算术平均做不到
  - **叙事聚类**:从 20+ 篇文章里归纳 ≤5 个代表性主题——需要段落级语义聚类
  - **竞品格局识别**:基于 mentioned_entities 的 role 字段自动识别竞品位置
  - 但整体**输出自由度较高**——narratives/entities 主要是自然语言摘要,结构化程度低于社媒切片的 SOV/象限等量化指标

### 1.3 实体 role 归类机制(tagging + insight 共同遵守)

新闻 pipeline 没有社媒侧的多层实体归一化链路(`monitor_entity_merge_chain` 两阶段 Merge + Review)。为保证 `NewsSlice.entities.role` 对下游 `landscape_chain` 可靠(该 chain 有硬规则"禁止改判 role,以输入为准"),由 **prompt 硬规则 + 代码兜底 `_enforce_entity_roles`** 共同保证。

**三种运行模式**(触发条件由 subject / competitors 参数组合决定):

| 模式 | 触发 | 行为 |
|------|------|------|
| 独立监测 | `subject == ""` | 所有实体 role=context,不做 target/competitor 区分 |
| 显式列表 | `subject` 非空 + `competitors` 非空 | 严格按列表归类:name==subject→target;name∈competitors→competitor;列表外强制 context |
| 自动发现 | `subject` 非空 + `competitors` 空 | LLM 自判同品类/场景级竞品归 competitor;代码仅强制 target 只能是 subject |

**subject / competitors 的来源**:

| 调用路径 | subject 来源 | competitors 来源 |
|---------|-------------|-----------------|
| Celery `run_news_collect_task` (tagging 阶段) | `brand_brief.subject`(策略场景传入)或 `""`(独立场景) | `slice_blueprint[].competitors` 的 union(策略场景)或 `[]`(独立场景) |
| `strategies/_create_strategy_news_slice` (insight 阶段) | `slice_blueprint[].subject`(每切片独立一对) | `slice_blueprint[].competitors`(每切片独立一对) |
| `news_media/analysis/service.run_slice_analysis` (独立 slice insight) | `""` | `[]` |

**代码兜底 `_enforce_entity_roles`**([`backend/src/news_media/tasks/service.py`](../../backend/src/news_media/tasks/service.py)):

1. **role 硬校验**:case-insensitive exact 优先,substring 兜底(处理"绿米联创Aqara" → "Aqara"这类品牌+附加词变体),patterns 按长度降序避免短名误匹配(如 "AppleCare" 不被归到 "Apple")
2. **subject + competitors 的变体条目合并**:mention_count 累加 / sentiment 加权平均 / source_count 取 max / key_claims 去重截断 3 条
3. **context 实体不合并**:未在 subject/competitors 列表内的实体保持 LLM 原样(不归一其变体),仅强制 role=context
4. **entities 重排**:target → competitor(mention 降序)→ context(mention 降序)
5. **同步重建 `competitive_landscape.entities_mentioned`**:保持和合并后 entities 一致

**为什么需要代码兜底(而非纯 prompt 指令)**:

- LLM 偶发不完美归一(同时返回 "Aqara" + "绿米联创Aqara" 两个实体条目),代码合并避免 entities 列表分裂
- 显式模式下 LLM 偶发把 mention_count 最多的品牌误标 target(新闻里该品牌是报道焦点但非研究主体),代码强制覆写
- 独立场景 LLM 可能误判某实体为 target/competitor,代码强制全 context

---

## 2. 搜索源与采集架构

### 2.1 搜索器清单([`src/news_media/tasks/news_search/`](../../backend/src/news_media/tasks/news_search/))

三个渠道**统一通过 [`_crawl4ai_client.fetch_via_crawl4ai`](../../backend/src/news_media/tasks/news_search/_crawl4ai_client.py)** 调用 Crawl4AI(底层 Playwright headless 浏览器,会执行 JS),取 `cleaned_html` 后用 **Python 正则**抽结构化块。差异只在 wait 策略和超时上:

| 搜索器 | 数据源 | wait_until | 解析锚点 | 备注 |
|------|------|--------|---------|-----|
| `baidu_crawler` | www.baidu.com 资讯页 | `None`(只等 DOMContentLoaded) | `.result-op.c-container` | SSR 渲染,不依赖 JS,早返回省时;主力中文源 |
| `sogou_crawler` | news.sogou.com | `networkidle` | `.vrwrap` | JS 延迟反爬必须等 networkidle |
| `wechat_mp_crawler` | weixin.sogou.com 微信入口 | `networkidle` | `<li id="sogou_vr_..._box_X">` | 时间解析优先吃渲染后 `<span class="s2">YYYY-M-D</span>`(crawl4ai 剥 `<script>`,`timeConvert(...)` 永远匹配不到,留作降级) |

**为什么不用 markdown / LLM 解析**:搜索结果页结构稳定、字段密集,正则便宜准确;markdown 转换会把"标题/来源/时间/摘要"打散成单独的 link/text 节点,反而难还原。

各搜索器返回字段结构统一:`{title, url, snippet, source_name, published_at, image_url, raw_data}`。

### 2.2 `source_tier` 分层(硬编码规则)

实现位置:[`aggregator.py::classify_source_tier()`](../../backend/src/news_media/tasks/news_search/aggregator.py)

- **tier1**:新华网/社、人民日报、央视、中国日报、经济日报、光明日报、澎湃等
- **tier2**:第一财经、财新、21 世纪经济报道、界面、36氪、虎嗅、新浪/腾讯/网易财经等
- **tier3**:其他
- **wechat_mp**:独立标记(search_source="wechat_mp")

**判定机制**:字符串包含匹配 `_SOURCE_TIERS` 字典。**不使用 LLM**,是静态规则。

### 2.3 URL 去重([`aggregator.py::_normalize_url()`](../../backend/src/news_media/tasks/news_search/aggregator.py))

- 保留身份参数:`id, url, docid, nid, aid, artid, newsid`
- 删除追踪参数:`utm_*, from, wfr, for, spider, spm 等`
- 参数顺序不影响判同

### 2.4 Probe vs Collect 模式对比

| 维度 | Probe | Collect |
|-----|-------|---------|
| 搜索结果数 | ≤20 篇(`_PROBE_MAX_RESULTS`) | ≤30 篇(`max_results=30`) |
| 全文抓取 | ❌ 无 | ✅ Crawl4AI 并发(=5) |
| 逐篇标注 | ❌ 无 | ✅ NEWS_TAGGING,10 篇/批(`CELERY_AI_NEWS_TAGGING_BATCH_SIZE`) |
| 任务 `analysis_result` | ✅ meta 统计(来源分布等) | ❌ 不用(迁移到 NewsSlice) |
| 触发场景 | 策略 probe 阶段 / refine 关键词 | 策略 collect / 独立 monitor collect |
| 成本 | 极低(仅搜索 + 爬虫) | 中等(爬虫 + LLM) |

**核心设计意图**:让用户能**廉价地验证关键词有效性**,再投入大量成本做全量分析。

---

## 3. 数据模型

### 3.1 核心模型

| 表 | 关键字段 |
|---|---------|
| `news_monitors` | id, name, user_id, participants(M2M) |
| `news_tasks` | id, name, keywords, monitor_id, **strategy_id**, **phase**(probe\|collect, NOT NULL DEFAULT 'collect'；独立 monitor 一律 'collect'), status, search_params, articles_count, analysis_result, auto_analyze, started_at, completed_at |
| `news_articles` | 见下 |
| `news_slices` | id, monitor_id, name, status, **included_task_ids**[], **result_data**, **stats** |

### 3.2 `NewsArticle` 字段分组

**元数据(搜索即得)**:
- `url, title, snippet, source_name, source_tier, author, published_at, image_url`
- `search_source`: baidu / sogou / wechat_mp

**标注结果(仅 collect 阶段,来自 `NEWS_TAGGING`)**:
- `relevance`: high / medium / low
- `sentiment`: float (-2 ~ 2)
- `article_type`: report / opinion / pr / analysis
- `mentioned_entities` (JSON): `[{name, role}]`
- `key_quotes` (JSON): `[{speaker, quote}]`
- `summary`: 一句话摘要

**全文**:
- `full_text` (Text):Crawl4AI 抓取的完整正文,仅 collect 有

**原始数据**:
- `raw_data` (JSON):搜索引擎/爬虫原始响应,保留供未来重解析

### 3.3 `NewsSlice.result_data` 结构

```
result_data = {
  coverage: {
    media_coverage_index: 0-100,
    intensity: "low"|"medium"|"high",
    trend: "rising"|"stable"|"declining",
    summary: string
  },
  sentiment: {
    overall: float (-2~2, 加权),
    distribution: { positive, neutral, negative },
    by_source_tier: { tier1: {...}, tier2: {...}, ... }
  },
  narratives: [{                        // ≤5
    theme, article_count, sentiment,
    summary (50-100 字),
    representative_titles: [...]
  }],
  entities: [{                          // ≤15
    name, role, mention_count, sentiment,
    source_count, key_claims: [...]
  }],
  competitive_landscape: {              // 仅当有 competitor
    positioning_summary,
    entities_mentioned: [{name, mentions, sentiment}]
  },
  key_quotes: [{                        // ≤5
    speaker, quote, source_name, context
  }]
}
```

### 3.4 `NewsSlice.stats` 结构

```
stats = {
  articles_total: int,
  source_tier_distribution: {tier1, tier2, tier3, wechat_mp},
  search_source_distribution: {baidu, sogou, wechat_mp},
  sentiment_distribution: {positive, neutral, negative},
  sentiment_overall: float,
  top_entities: [{name, mention_count}] × 10
}
```

**观察**:相比社媒 slice 的 `result_data.layers.{landscape, topic, focus}` 三层复杂结构,新闻的 result_data **扁平得多**,字段自由度更高。

---

## 4. 前端消费字段

### 4.1 页面结构([`frontend/layers/news-media/`](../../frontend/layers/news-media/))

| 页面 | 路由 | 职责 |
|-----|------|------|
| 监测项目列表 | `/news-media/monitors` | NewsMonitor CRUD |
| 项目详情 | `/news-media/monitors/[id]` | 项目概览 + task 列表 |
| 任务列表 | `/news-media/tasks` | 跨项目任务 + 状态过滤 |
| 任务详情 | `/news-media/tasks/[id]` | 元数据 + 文章列表 + 任务级统计 |
| 切片详情 | `/news-media/slices/[id]` | 切片级 insight 展示 |

### 4.2 任务详情页硬依赖

```typescript
task.status, task.name, task.keywords, task.articles_count
task.started_at, task.completed_at
task.analysis_result.meta.{articles_total, articles_crawled, articles_analyzed,
                           source_tier_distribution, source_samples}

// 文章列表
articles[].{title, url, snippet, source_name, source_tier, published_at, image_url}
articles[].{relevance, sentiment, article_type, mentioned_entities, key_quotes, summary}  // collect 后有

// 过滤器
relevanceFilter ∈ {all, high, medium, low}
tierFilter ∈ {all, tier1, tier2, tier3, wechat_mp}
```

### 4.3 切片详情页硬依赖

```typescript
slice.status, slice.name
resultData.narratives[].{theme, article_count, sentiment, summary, representative_titles}
resultData.entities[].{name, role, mention_count, source_count, sentiment, key_claims}
resultData.coverage (可选)
resultData.competitive_landscape (可选)
resultData.key_quotes (可选)

stats.sentiment_overall
stats.source_tier_distribution
stats.top_entities
```

### 4.4 前端硬依赖的架构契约

1. **`task.analysis_result.meta.articles_total`** 必须存在(即便 probe 失败也要填 0)
2. **`article.relevance`** / **`article.source_tier`** 必须存在,否则过滤器失效
3. **`resultData.narratives[]`** 至少有一个非空——前端切片页的主视图依赖
4. **`stats` 必须是有效 dict**,否则统计卡片炸

### 4.5 LLM-native 替代的可行性(vs 社媒)

与社媒不同,新闻监测的前端消费**大量是自然语言字段**(narratives.theme/summary、entities.key_claims、key_quotes.quote):

- ✅ 这些字段 LLM 一把梭**能自然产出**
- ❌ 但前端的 tier/relevance 过滤器、source_tier_distribution 等**仍依赖结构化标注**
- ❓ 结构化程度介于"社媒重 pipeline"和"纯 narrative"之间

这是一个**比社媒更容易重构**的模块,但仍然有结构化依赖,需要小心评估。

---

## 5. 任务图

### 5.1 Celery Task 清单

注册于 [`src/celery_app.py`](../../backend/src/celery_app.py) `include` 列表:`news_media.tasks`

| Task | 定义位置 | 触发方式 | 流程 |
|------|--------|--------|------|
| `news_media.run_probe` | [`tasks.py:28-35`](../../backend/src/news_media/tasks/tasks.py) | `router.py` 派发 / 策略 probe | 搜索 + 落库(无全文、无标注) |
| `news_media.run_collect` | [`tasks.py:60-90`](../../backend/src/news_media/tasks/tasks.py) | `/tasks/{id}/execute` / 策略 collect | 搜索 + 抓全文 + LLM 标注 + 统计 |

### 5.2 APScheduler 定时任务

| Job ID | 频率 | 职责 |
|--------|-----|------|
| `news_task_watchdog` | **5 分钟** | 回收超时(>20 min)的 running / pending 新闻任务,标记 `failed` |

注:`strategy_probe` / `strategy_collection` 虽涉及新闻任务完成检测,但归属策略模块。

### 5.3 调用关系

```
# 独立 Collect 流程
POST /monitors/{id}/tasks  (create 即派发; phase 默认 'collect',router 拒绝 phase='probe')
  → POST /tasks/{id}/execute  (仅失败重试/历史 pending 重跑)
  → router.py 检查 strategy_id IS NULL, phase != "probe"
  → Celery: run_news_collect_task.delay(task_id, tagging_job_id)
  → Worker(gevent) → _async_run_collect()
      ├─ _search_and_store_articles() 多渠道聚合 + 去重
      ├─ crawl_articles() Crawl4AI 并发抓全文
      ├─ _tag_articles_batch() NEWS_TAGGING (10/批,由 `CELERY_AI_NEWS_TAGGING_BATCH_SIZE` 配置)
      ├─ _apply_tags_to_articles() 回写标注
      └─ task.status=completed

# 独立 Slice 分析
POST /monitors/{id}/slices (含 included_task_ids)
  → create_slice() → 自动 run_slice_analysis()
      ├─ 合并文章 + URL 去重 + 低相关过滤
      ├─ _compute_stats()
      ├─ _run_insight_analysis() NEWS_INSIGHT
      └─ slice.result_data = insight, slice.stats = stats

# 策略场景(由 strategies 模块编排)
strategy_probe APScheduler (2 min)
  → 检测所有 probe task 完成 → _run_news_probe_review_one() × N
      → NEWS_INSIGHT 审查 probe 结果(有效性评分)

strategy_collection APScheduler (2 min)
  → 检测所有 collect task 完成 → _create_strategy_news_slice()
      → 按 blueprint 维度建 NewsSlice → 触发 NEWS_INSIGHT
```

---

## 6. 使用场景

### 6.1 场景 A:独立新闻监测(Standalone)

**典型用户**:品牌/公关监测,周期性采集媒体报道

**流程**:
1. 创建 NewsMonitor → 创建 NewsTask(`strategy_id=NULL`, `phase='collect'`);create 即派发,无需二次点击
2. 采集+全文+标注 → 看文章列表 + 任务级统计(失败可通过 `/tasks/{id}/execute` 重试)
3. 手动勾选多个 completed task(仅 `phase='collect'` 可选)→ 建 NewsSlice → 看切片 insight

**产出**:媒体覆盖指数 + 舆论倾向 + 关键叙事 + 引述 + 竞品识别

### 6.2 场景 B:策略研究中的新闻(Strategy-Bound)

**典型用户**:策略研究员,用新闻维度补充市场/行业/舆论视角

**流程**:
```
Strategy 创建 news_monitor_id
  ↓
Probe:每个关键词 × 渠道建 probe task(strategy_id 非空, phase="probe")
  ├─ 纯搜索,落库卡片
  ├─ APScheduler 每 2 min 检查完成
  └─ 完成后触发 NEWS_INSIGHT 审查 → 输出"关键词有效性"评分
  ↓
用户 Approve / Refine
  ├─ Refine: 调整关键词,新建 probe task(probe_round++)
  └─ Approve: 进入 Collect
  ↓
Collect:每个 probe task 创建对应 collect task
  ├─ 搜索 + 全文 + 标注
  ├─ APScheduler 每 2 min 检查完成
  └─ 完成后按 slice_blueprint 自动建 NewsSlice + 触发 NEWS_INSIGHT
  ↓
策略报告消费 NewsSlice insight(作为 market_report 路径主数据源)
```

**产出**:注入到策略 Agenda Map / Landscape / Strategic Brief 的"媒体视角"。

### 6.3 两个场景的差异

| 维度 | 独立监测 | 策略绑定 |
|-----|---------|--------|
| Monitor 来源 | 用户手建 | 策略自动创建 |
| 任务 `strategy_id` | NULL | 非空 |
| `phase` | 一律 `collect`(create 强制) | `probe` + `collect` 两段 |
| Slice 创建 | 用户手动勾选 task | 按 blueprint 自动建(维度分组) |
| APScheduler 介入 | 仅 `news_task_watchdog` 超时回收 | `strategy_probe` / `strategy_collection` 主动推进 |
| 产出消费者 | 前端切片页 | 策略报告引擎 |

---

## 7. 关键发现摘要(事实,非结论)

### 7.1 新闻 pipeline 的特点

1. **轻量级**:2 条 LLM 链 vs 社媒 9 条,无多层归一化
2. **输出结构相对自由**:narratives / entities / key_quotes 都是自然语言为主,**结构化程度低于社媒**
3. **两阶段设计是核心**:probe(便宜探测)+ collect(深度分析),这个语义要保留
4. **依赖独立基础设施**:Crawl4AI 全文抓取、多渠道搜索聚合、URL 去重、tier 分层——这些即便换架构也要保留

### 7.2 相比社媒,重构门槛可能更低

- 前端硬依赖字段数量明显少(约 10 个 vs 社媒 15+)
- 切片分析的输出结构自由(narratives 是叙事文本,LLM-native 能自然产出)
- 但**过滤器依赖的结构化字段**(relevance/tier)仍需保留

### 7.3 `NEWS_INSIGHT` 在策略 probe review 中的双用

同一条 chain 被:
- NewsSlice 自动触发(独立监测场景)
- 策略的 probe review 引擎调用(策略场景)

**复用程度高**,重构时要兼顾两个调用方。

### 7.4 潜在优化空间(未验证)

- ~~`NEWS_TAGGING` 现在 5 篇/批,是否能 10+ 篇/批?~~ **已落地(2026-04-20)**:提升到 10 篇/批 + 迁移到 `settings.CELERY_AI_NEWS_TAGGING_BATCH_SIZE`,详见 [ADR-001](../adr/001-analysis-architecture.md#新闻监测模块结案摘要v6)
- `NEWS_INSIGHT` 在策略 probe review 时可能过重——probe 只是关键词验证,用更轻的审查链可能够用?
- `source_tier` 目前是硬编码字典——规模扩大后能否动态学习?(长期优化)

---

## 后续

1. ✅ 社媒监控 inventory 完成
2. ✅ 新闻监控 inventory 完成
3. ⏭️ **下一步**:专题研究 (Research Agent) inventory
4. ⏭️ 最后:策略研究 inventory(下游消费者,综合分析 3 个源模块)
5. 4 份完成后,在 ADR-001 Phase 1 重新评估架构选项
