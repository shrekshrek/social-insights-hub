# ADR-003：新闻模块分析重构（两层职责 + 双段 LLM + 策略契约对齐）

> 决策日期：2026-04-30
> 状态：**Accepted**
> 相关实现：
> - `backend/src/news_media/tasks/service.py`、`backend/src/news_media/tasks/tasks.py`
> - `backend/src/news_media/analysis/service.py`、`backend/src/news_media/analysis/tasks.py`
> - `backend/src/llm/chains/news/insight_chain.py`（拆分为 Pass 1 / Pass 2）
> - `backend/src/llm/chains/strategy/brand_strategy/insight_chain.py:_format_news_media_section`（消费契约切换）
> - `frontend/layers/news-media/pages/news-media/tasks/[id]/index.vue`、`.../slices/[id]/index.vue`
> - `frontend/layers/news-media/types/index.ts`

---

## 背景

新闻 task 层和 slice 层调用的是**同一条** `news/insight_chain`，只是池子不同（task = 单关键词召回，slice = 多 task 合并）。这造成三个问题：

1. **两层不是分层、是重复**：slice 没有 task 算不出来的"新分析维度"，只是合并文章池后再跑一遍同一份报告。
2. **task 层 insight 不可信**：单 task 文章数 5–10 篇时，让 LLM 产 narratives / competitive_landscape / positioning_summary 是统计基础不足下的"凑话术"，且高度受关键词偏置。
3. **新闻 slice → 策略下游违背"只下流结构化数据"原则**：`_format_news_media_section` 把 LLM 散文（`narratives.summary` / `coverage.summary` / `competitive_landscape.positioning_summary` / `coverage.media_coverage_index` 主观打分）打包给策略层 LLM，造成"AI 偏见叠加 + 黑盒嵌套"。社媒侧 `format_slice_data_for_insight` 已经走对了"只给 `foundation` + `layers` 结构化数据"的模式，新闻侧需对齐。

---

## 决策

### 一、贯穿原则

1. **SQL 能算的不让 LLM 算**。LLM 只做"非确定性、有事实锚、不可被 SQL 替代"的工作（变体归一 / role 判定 / quote 抽取 / event 聚类 / speaker 分级）。
2. **slice 层 LLM 分两段**：
   - **Pass 1（清洗归一抽取）**：结构化输出，下流给策略与页面共享
   - **Pass 2（解读综述）**：散文输出，仅 slice 页面使用
   - Pass 2 必须基于 Pass 1 的结构化输出 + 代表性标题，不直接读全文
3. **策略下游只消费结构化数据**，不消费任何 LLM 散文。和社媒已走通的 `foundation/layers` 模式对齐。
4. **所有 LLM 产出必须挂 `article_id`(s) 可下钻**，无法回到原文证据的产出不进 schema。
5. **时间是新闻分析一等公民**——所有指标都要有时序版本。

### 二、两层职责

| 层 | 角色 | 内容 | LLM 调用 |
|---|---|---|---|
| **Task** | 原料质检 + 单元描述 | tagging（per-article）+ task.stats 描述统计 | tagging（已有） |
| **Slice** | 综合分析 | Pass 1（归一抽取聚类）+ SQL 派生 + Pass 2（散文） | Pass 1 + Pass 2 |

Task 层**不调** insight。slice 层 Pass 1 取代当前 `news/insight_chain`。

### 三、Slice 层流程（4 步）

```
Step 1：合并 + URL 去重 + 过滤 relevance=low（SQL）
Step 2：Pass 1 LLM → entities + quotes + event_clusters
Step 3：SQL 派生 → entity 多维 sentiment + competitive 投影 + source_pyramid
Step 4：Pass 2 LLM → briefing + event_title
```

事件聚类合并在 Pass 1 里（不引入 embedding），命名留给 Pass 2。

### 四、Schema 摘要

#### Task `task.stats`

```typescript
{
  articles_total, articles_high, articles_medium, articles_low,
  source_tier_distribution: { tier1, tier2, tier3, wechat_mp },
  search_source_distribution: { baidu, sogou, wechat_mp },
  article_type_distribution: { report, opinion, pr, analysis },
  sentiment_distribution: { positive, neutral, negative },
  sentiment_overall: number,
  sentiment_by_tier: { tier1, tier2, tier3, wechat_mp },   // ★ 新增
  coverage_by_day: [{ date, count, sentiment_avg }],       // ★ 新增
  top_entities_raw: [{ name, mention_count }] (10),        // 原始计数，未归一
  top_quotes: [{ speaker, quote, source_name, source_tier, article_id }] (5)
}
```

#### Slice 描述层（Step 1，SQL）

```typescript
descriptive = {
  articles_total, articles_unique, articles_filtered,
  source_tier_distribution, search_source_distribution,
  sentiment_distribution, sentiment_overall, sentiment_by_tier,
  article_type_distribution,
  cross_task_overlap: {
    distribution: { single_task, two_tasks, three_plus },
    high_overlap_articles: [{ url, task_ids[], title, article_id }] (top 20)
  },
  coverage_timeseries: [{ date, count, count_by_tier }],
  sentiment_timeseries: [{ date, sentiment_avg, sentiment_weighted_by_tier }]
}
```

#### Slice Pass 1 输出（Step 2，LLM）

```typescript
entities = [{
  name: string,                          // 规范化后
  role: 'target' | 'competitor' | 'context',
  mention_count, source_count, cross_task_count,
  article_ids: number[],
  representative_article_ids: number[]
}]

quotes = [{
  speaker, speaker_role: 'official'|'executive'|'analyst'|'kol'|'other',
  quote, article_id, source_name, source_tier, published_at, context
}]

event_clusters = [{
  cluster_id, article_ids, article_count,
  in_task_ids: number[]                  // 跨 task 一致性证据
  // first_reported_at / peak_date / tier_weighted_score 由 Step 3 SQL 派生
  // event_title / dominant_frame 由 Step 4 LLM 写
}]
```

#### Slice 派生层（Step 3，SQL）

```typescript
// entity 多维 sentiment
entities[].sentiment_avg
entities[].sentiment_weighted_by_tier
entities[].sentiment_by_tier
entities[].top_quote_ids
entities[].timeline                      // 仅 target + competitor

// 媒介格局
media_landscape = {
  source_pyramid: [{ tier, article_count, sentiment_avg, top_source_names, representative_titles }],
  top_sources: [{ name, count, share }] (5)
}

// 竞争层（投影 entities[role∈target+competitor]）
competitive = {
  players: [{ name, role, tier_weighted_sov, mention_count, source_count, cross_task_count, sentiment_by_tier, top_quote_ids }],
  quote_share: [{ name, quote_count, official_quote_count }]
}

// event_clusters 时间锚补全
event_clusters[].first_reported_at
event_clusters[].peak_date
event_clusters[].tier_weighted_score     // tier1×4 + tier2×2 + tier3×1 + wechat_mp×0.5
```

#### Slice Pass 2 输出（Step 4，LLM，仅页面用）

```typescript
page_synthesis = {
  briefing: { headline, key_findings: string[3-5], risks: string[0-3] },
  event_titles: { [cluster_id]: { title, dominant_frame } }
}
```

### 五、策略数据契约（SliceDataForStrategy）

通过 `GET /news-media/slices/{id}/strategy-data` endpoint 暴露，service 层投影：

**包含**：descriptive 全部 + entities + quotes + event_clusters（不含 LLM 命名）+ media_landscape + competitive。

**排除**：page_synthesis 全部（briefing / event_titles / 任何 LLM 散文）。

文章数据通过 `article_ids` 回查 `NewsArticle` 表。

### 六、不向后兼容

直接替换。改造 `_format_news_media_section`（[brand_strategy/insight_chain.py:243](../../backend/src/llm/chains/strategy/brand_strategy/insight_chain.py)）和 market_report 路径（agenda_map_chain / landscape_chain）所有消费 NewsSlice 的地方为新契约。当前 `result_data` schema 视为遗留，不保留兼容路径。

### 七、砍掉的字段（明确删除）

| 字段 | 删除理由 |
|---|---|
| `coverage.media_coverage_index` (0–100 分) | LLM 主观打分，无跨切片基准，虚假精度 |
| `coverage.intensity` (low/medium/high) | LLM 主观标签，时序图替代 |
| `coverage.trend` (rising/stable/declining) | LLM 拍脑袋判断，时序图替代 |
| `coverage.summary` | LLM 散文，移到 briefing |
| `competitive_landscape.positioning_summary` | "替分析师下结论"，违反 LLM 管证据原则 |
| `competitive_landscape.entities_mentioned` | 与 `entities[role=competitor]` 重复 |
| `entities[].key_claims` | 与 `quotes` 信息重叠，且 LLM 复述削弱可信度 |
| z-score spike detection（曾考虑） | 多数 slice 跨度短无基线；时序图自然显示突起 |
| HHI / CR3 来源集中度（曾考虑） | 经济学指标过度精装；展示 top sources 即可 |
| `agenda_position` 标签（曾考虑） | 把"看金字塔"硬塞个标签；可视化已传达 |
| `sentiment_excluding_pr` 字段（曾考虑） | 多一套并行 sentiment 字段；前端按 article_type 过滤即可 |
| 跨 task 诊断层（entity_role_conflicts / task_contribution，曾考虑） | 一年用一次的 QA 工具，发现真有需要再加 |
| Pass 2 narratives 输出（曾考虑） | 与 event_clusters 职责重叠 |
| embedding 模型 + 层次聚类（曾考虑） | LLM 直接做语义聚类更准；不引入新基础设施 |

---

## 实施分期

| Phase | 内容 | 状态 |
|---|---|---|
| **P1** | Task 层 stats 富化（sentiment_by_tier / coverage_by_day / article_type_distribution / top_entities_raw / top_quotes）+ task 详情页清死代码 + 加 Quote Wall / Source Pyramid / 时序柱状图 | 进行中 |
| **P2** | Slice 重构：Step 1（描述层 SQL）+ Step 2（Pass 1 LLM 重写）+ Step 3（派生 SQL）+ Step 4（Pass 2 LLM）；slice 详情页重做 | 待开始 |
| **P3** | 策略数据契约 endpoint + 改造 strategies 模块所有 NewsSlice 消费点（brand_strategy + market_report 三条 chain）使用新契约；不留兼容 | 待开始 |

---

## 风险与边界

1. **不向后兼容**：现有 NewsSlice 行的 `result_data` schema 老化，P3 完成后需重跑历史 slice 才能正常 strategies 消费。如有用户保留中的 slice 需要保留，提前导出。
2. **`_compute_stats` 当前签名**：[news_media/analysis/service.py:_compute_stats](../../backend/src/news_media/analysis/service.py) 在 P2 整合到 Slice 描述层时统一重写；P1 不动。
3. **Pass 1 / Pass 2 单向依赖**：Pass 2 不可"修正" Pass 1（不能改 entity role / 合并 cluster）。代码注释和 PR 模板中明确，避免后续混回一锅。
4. **`role=target` 硬约束保留**：`subject` 为空时全部 context；非空时严格按 list；`_enforce_entity_roles` 代码层兜底逻辑沿用，挪到 Pass 1 后处理。
