# Feature Inventory: 策略研究 (`src/strategies/`)

> 盘点日期:2026-04-20
> 目的:为 ADR-001 架构决策提供事实基础。策略是**下游消费者**,本盘点重点回答:**"前 3 个模块的哪些字段被真正消费?"**。
> **本文档只做盘点,不下架构结论**。

## TL;DR

策略研究是整个系统的**下游汇总点**,消费社媒/新闻/Research Agent 三个上游模块的产出,通过 4 阶段状态机驱动,产出 3 条路径的分析结果(campaign_strategy / market_report / full_strategy)。

**最重要的发现**:

1. **`insight_chain` 是 SocialSlice 结构化字段的重度消费者**,读 `foundation.aligned_entities/topics` + `layers.landscape.sov_ranking` + `layers.intent.topic_radar(pains/gains/controversies)` + `layers.focus.swot/gap` 多达 18 个字段路径
2. **`agenda_map_chain` / `landscape_chain` 消费 NewsSlice 的 `result_data.insight[]`**,新闻 pipeline 的 narrative 结构直接进入 prompt
3. **`strategic_brief_chain` 有硬耦合的 evidence_refs**,引用 Landscape 的 `agenda_map_battle_ref` / `agenda_map_narrative_ref` 做跨 stage 回链,前端可点击跳转
4. **级联清空语义**严格:重新生成上游 stage 会清空所有下游结果,full_strategy 更会跨路径清空(重生成 Landscape 会清空 insight/brand_role/big_idea)
5. **APScheduler 2 min 轮询驱动状态推进**,用户全程留在策略页面,无需手动触发

---

## 1. 4 阶段状态机

### 1.1 拓扑

```
draft
  ↓ [design-research]
planned
  ↓ [confirm-research: 创建 Monitor + probe 任务]
probing
  ↓ [approve-probe 或 all_pass 自动: 创建 collect 任务]
collecting
  ↓ [自动建切片 + coverage_check]
ready
  ├─ [campaign_strategy] → insight_done → brand_role_done → completed
  ├─ [market_report]     → agenda_map_done → landscape_done → completed
  └─ [full_strategy]     → agenda_map_done → landscape_done ───┐
                                                                ↓
                                                   (Insight → Brand Role → Big Idea)
                                                                ↓
                                                            completed
```

### 1.2 STATUS_ORDER 共享值设计

`insight_done` 和 `agenda_map_done` 都是 order 5;`brand_role_done` 和 `landscape_done` 都是 order 6。这让跨路径的 `>= ready` / `>= insight_done` 等比较依然有效。

### 1.3 级联清空语义(关键)

在 [`strategies/service.py`](../../backend/src/strategies/service.py) 的 `edit_*_result` 和 `generate_*` 函数中严格执行:

| 重新生成 | 清空的下游字段 |
|---------|------------- |
| Insight | brand_role_result, big_idea_result |
| Brand Role | big_idea_result |
| Agenda Map | landscape_result, strategic_brief_result, **(full_strategy 额外)** insight/brand_role/big_idea_result |
| Landscape | strategic_brief_result, **(full_strategy 额外)** insight/brand_role/big_idea_result |

**编辑任何层级同样触发下游级联清空**(避免上下游数据不一致)。

这意味着:**任何重构必须保持这个语义**,否则前端会看到"已完成的下游 stage 用的是过期上游数据"。

---

## 2. 10 条策略 LLM Chain

目录:[`backend/src/llm/chains/strategy/`](../../backend/src/llm/chains/strategy/)

### 2.1 共用链(5 条)

| Chain | 核心职责 | 触发时机 | 输入 | 输出 |
|-------|--------|--------|-----|-----|
| `brief_parser_chain` | 解析 Brief + 判断四渠道适配 | `parse-brief` 端点 | brand_brief 文本 | subject, analysis_goal, constraints, channel_plan[] |
| `research_design_chain` | 研究规划:问题 + 关键词 + 切片蓝图 | design-research | brief + channel 判断 | research_questions[], data_plan{social/news}, slice_blueprint[] |
| `social_probe_review_chain` | 社媒探测质检(规则 + LLM 混合) | probe 阶段自动 | social task analysis_result | pass/fail/confidence |
| `news_probe_review_chain` | 新闻探测质检(单任务并行) | probe 阶段自动 | news task meta + snippet 列表 | pass/fail + 人工核查提示 |
| `coverage_check_chain` | 覆盖度验证:研究问题 vs 数据匹配 | 建切片后自动 | slice 汇总 + research_questions | overall_ready, gaps[] |

### 2.2 `campaign_strategy` 路径(3 层)

| Chain | 层级 | 输入 | 输出 |
|-------|-----|-----|-----|
| `insight_chain` | L1 洞察 | SocialSlice(主源)+ news_media_section(补充)+ research_findings | social_tensions[], brand_opportunities[] |
| `brand_role_chain` | L2 品牌角色 | insight_result + research_findings + creative_references | role, strategy, differentiation |
| `big_idea_chain` | L3 创意 | brand_role_result + creative_references + research_findings | big_idea, content_strategy |

### 2.3 `market_report` 路径(3 层)

| Chain | 层级 | 输入 | 输出 |
|-------|-----|-----|-----|
| `agenda_map_chain` | L1 媒体议程图 | NewsSlice(主源)+ research_findings | narrative_map, agenda_battles, media_voice_patterns, attention_gaps |
| `landscape_chain` | L2 竞争格局 | agenda_map_result + 原始 NewsSlice + research_findings | players[](role, media_sov_pct, media_sentiment), positioning_map, discourse_battles(**必须 ref agenda_battles**) |
| `strategic_brief_chain` | L3 战略简报 | **只用 agenda_map + landscape,禁新数据** | executive_summary, strategic_priorities(evidence_refs), opportunities, risks_and_threats, recommended_positioning |

### 2.4 `full_strategy` 特殊点

顺序执行:`agenda_map → landscape → insight → brand_role → big_idea`(5 层)。

Insight 阶段以 `landscape_result` JSON 作为 `{news_media_section}` 注入,**取代原始 news slices**——即"消费者洞察基于完整竞争格局背景"。

**不支持生成 Strategic Brief**(返回 409)。

---

## 3. 上游字段消费矩阵(本盘点核心)

### 3.1 SocialSlice `result_data` 字段消费表

主要消费者:`insight_chain`(campaign_strategy L1)。

Formatter 入口:[`insight_chain.py::format_slice_data_for_insight()`](../../backend/src/llm/chains/strategy/brand_strategy/insight_chain.py)

| 字段路径 | 消费链 | 用途 | 必要性 |
|---------|-----|-----|------|
| `SocialSlice.subject`（表列） | insight | 区分品牌聚焦 vs 大盘切片 | 🔴 必需 |
| `SocialSlice.competitors`（表列） | insight | 竞品列表背景 | 🟡 可选 |
| `foundation.aligned_entities[0:50]` | insight | 实体热度 + 情感 | 🔴 必需 |
| `foundation.aligned_entities[].original_terms[0:5]` | insight | 用户原话(Top 5 实体) | 🟡 强烈推荐(evidence 引用) |
| `foundation.aligned_entities[].organic_sentiment` | insight | 非推广情感(真实痛点) | 🔴 必需 |
| `foundation.aligned_topics[0:30]` | insight | 话题热度 + 情感 | 🔴 必需 |
| `layers.landscape.sov_ranking[0:10]` | insight | 品牌声量 + 情感(四象限) | 🔴 必需 |
| `layers.landscape.sov_ranking[].role` | insight | 竞争角色标签 | 🟡 可选 |
| `layers.intent.topic_radar.pains[0:10]` | insight | **痛点话题(Tension 核心)** | 🔴 必需 |
| `layers.intent.topic_radar.pains[].organic_sentiment` | insight | 真实痛点信号 | 🔴 必需 |
| `layers.intent.topic_radar.controversies[0:8]` | insight | 两极话题 + 均衡度(撕裂) | 🔴 必需 |
| `layers.intent.topic_radar.controversies[].polar_total` | insight | **样本量校准**(<10 低信度) | 🔴 必需 |
| `layers.intent.topic_radar.gains[0:5]` | insight | 正向话题 | 🟡 可选 |
| `layers.intent.unmet_needs` | insight | 未满足需求(Opportunity) | 🟡 强烈推荐 |
| `layers.intent.context_analysis.audiences[0:8]` | insight | 受众画像 + 热度 | 🟡 可选 |
| `layers.intent.topic_aspects[0:5]` | insight | 话题分类维度(宏观) | 🟡 可选 |
| `layers.focus.swot[*][0:5]` | insight | SWOT 维度差异(delta) | 🟡 可选 |
| `layers.focus.gap.dimensions[0:5]` | insight | 竞品强/己方弱维度 | 🟡 可选 |

**结论**:insight_chain 消费了 **18 个字段路径**,其中 **10 个是必需的**。没有 SocialSlice 的结构化 layers,insight_chain 直接跑不起来。

### 3.2 NewsSlice `result_data` + `stats` 字段消费

主要消费者:`agenda_map_chain`、`landscape_chain`、`insight_chain`(补充段落)、`coverage_check_chain`。

| 字段路径 | 消费链 | 用途 |
|---------|-----|-----|
| `result_data.narratives[].theme` | agenda_map(主数据源) | 叙事主题框架 |
| `result_data.narratives[].sentiment` | agenda_map | 媒体态度 |
| `result_data.narratives[].summary` | agenda_map | 叙事描述 |
| `result_data.narratives[].representative_titles` | agenda_map | 代表性文章 |
| `result_data.entities[]` | agenda_map, landscape | 实体 + role 标签 |
| `result_data.competitive_landscape` | landscape | 竞品格局 |
| `result_data.key_quotes[]` | agenda_map, landscape | 关键引述 |
| `result_data.coverage.*` | agenda_map | 媒体覆盖指数 |
| `stats.source_tier_distribution` | landscape | 权威等级分布 |
| `stats.sentiment_overall` | landscape, coverage_check | 整体情感 |
| `stats.top_entities` | coverage_check | 实体覆盖验证 |

**结论**:新闻 chain 的输出结构**直接进入**策略 chain 的 prompt。narratives 和 entities 的字段语义(theme/sentiment/role)是硬契约。

### 3.3 ResearchTask `result_data` 字段消费

通过 [`research_findings.py`](../../backend/src/llm/chains/strategy/research_findings.py) 的 **5+2 个 formatter** 按 stage 分层注入,已在 `research_agent.md` inventory 中详述。

策略侧调用入口:[`service.py::_retrieve_research_findings`](../../backend/src/strategies/service.py):取最新已完成的 industry profile task。

| 消费 stage | Token 预算 | 读什么字段 |
|---------|----------|---------|
| Insight | ~1.5K | findings_by_question 全量 + information_gaps |
| Agenda Map | ~1.5K | 同上(校验媒体 vs 行业事实) |
| Brand Role | ~800 | synthesis 全文 + high-confidence 数据点 |
| Landscape | ~800 | synthesis + 所有数据点(量化重) |
| Big Idea | ~400 | high/medium 答案首句压缩 |
| Strategic Brief | ~400 | high-confidence 要点 |

创意研究(profile=creative)额外 2 个 formatter 注入 `{creative_references}`。

**结论**:Research Agent 的接口已经是解耦设计,任何重构不影响策略侧。

### 3.4 跨策略 stage 的引用耦合

| 引用方 | 引用字段 | 被引用方 | 耦合强度 |
|-------|-------|-------|-------|
| discourse_battles[].agenda_map_battle_ref | 指向 agenda_battles[i] | landscape | 🔴 硬 |
| strategic_priorities[].evidence_refs | 指向 agenda_map/landscape 结构化字段 | strategic_brief | 🔴 硬 |
| proof_points[].agenda_map_narrative_ref | 指向 narrative_map[i] | strategic_brief.recommended_positioning | 🔴 硬 |

**这是 LLM-native 一把梭最难复制的部分**。strategic_brief 的结构明确要求每条优先级/机会都有对应的上游字段引用,前端 UI 用这些引用做跨 stage 跳转。

---

## 4. 数据流图

### 4.1 完整流程(含 Research Agent 独立启动)

```
用户上传 Brief
  ↓ brief_parser_chain(channel_plan 判断)
POST /design-research
  ↓ research_design_chain(生成 research_questions + data_plan + slice_blueprint)
planned 状态
  ↓ POST /confirm-research(用户确认 output_type)
按渠道分别创建:
  ├─ 社媒:每 keyword×platform → SocialTask(phase=probe)
  ├─ 新闻:每 keyword → NewsTask(phase=probe),Celery 派发搜索
  ├─ [条件]industry_research 渠道 → ResearchTask(profile=industry),Celery 立即启动 LangGraph
  └─ [条件]creative_research 渠道 + campaign_strategy/full → ResearchTask(profile=creative)
probing 状态
  ↓
社媒爬虫 claim + 执行 + 上传数据 → SocialSlice 分析 pipeline 自动运行
新闻 Celery 执行搜索 + 落库卡片(无全文无标注)
  ↓ APScheduler `strategy_probe`(2 min)检测全部到达终态
自动触发 probe review:
  ├─ strategy_social_probe_review_chain(规则 + LLM 混合)
  └─ strategy_news_probe_review_chain(每任务并行 LLM)
  ↓ all_pass 自动 approve / 用户 approve / refine(<=3 轮)
collecting 状态
  ↓ 为每个 probe task 创建 phase=collect 全量任务
社媒全量爬取 + stage 1/2/3 pipeline
新闻全量 + 抓全文 + NEWS_TAGGING → NewsSlice + NEWS_INSIGHT
  ↓ APScheduler `strategy_collection`(2 min)检测全部完成
自动建切片:
  ├─ 按 slice_blueprint 分组社媒任务 → SocialSlice
  └─ 按 blueprint 分组新闻任务 → NewsSlice
  ↓ coverage_check_chain 验证
ready 状态
  ↓ 按 output_type 分叉
campaign_strategy 路径:
  POST /generate/insight → load SocialSlice + news_media_section + research_findings → insight_chain
  POST /generate/brand-role → load insight_result + research_findings + creative_references → brand_role_chain
  POST /generate/big-idea → load brand_role_result + creative_references + research_findings → big_idea_chain

market_report 路径:
  POST /generate/agenda-map → load NewsSlice + research_findings → agenda_map_chain
  POST /generate/landscape → load agenda_map_result + NewsSlice raw + research_findings → landscape_chain
  POST /generate/strategic-brief → load agenda_map + landscape(禁新数据) → strategic_brief_chain

full_strategy 路径:
  agenda-map → landscape → insight(landscape 作为 news_media_section) → brand-role → big-idea
  ↓
completed 状态
```

### 4.2 关键数据加载函数

| 函数 | 功能 | 位置 |
|------|-----|-----|
| `_load_strategy_slice_summaries` | 加载 strategy 关联的 SocialSlice(通过 social_monitor_id 隐式关联) | service.py |
| `_load_strategy_news_inputs` | 加载 strategy 关联的 NewsSlice | service.py |
| `_retrieve_research_findings` | 加载最新 industry ResearchTask | service.py |
| `_retrieve_creative_research_findings` | 加载最新 creative ResearchTask | service.py |
| `_format_news_media_section` | 把新闻切片格式化为 campaign_strategy chain 的补充段落 | insight_chain.py |

---

## 5. 前端页面与消费

### 5.1 主要页面

目录:[`frontend/layers/strategies/pages/strategies/`](../../frontend/layers/strategies/pages/strategies/)

| 页面 | 职责 |
|-----|-----|
| `index.vue` | 策略列表(名称、状态 badge、关联切片数) |
| `create.vue` | 策略创建(上传 Brief) |
| `[id].vue` | **4 阶段详情页**(核心) |

### 5.2 详情页消费的字段

1. **阶段 1 研究设计**:
   - `research_design.research_questions[]`
   - `research_design.data_plan.{social_media, news_media}.keywords/platforms`
   - `research_design.slice_blueprint[]`
   - ResearchPlanEditor 组件允许编辑后重新 confirm

2. **阶段 2 探测结果**:
   - `probe_review_result.overall_pass`
   - 社媒/新闻各自的 probe review 结果(per-task pass/fail)
   - approve/refine 按钮

3. **阶段 3 数据就绪**:
   - `coverage_check_result.overall_ready` + gaps
   - 切片列表(来自 social_monitor_id / news_monitor_id 关联)

4. **阶段 4 产出**(按 output_type 显示不同面板):
   - **campaign_strategy**:
     - InsightContent.vue:渲染 `insight_result.social_tensions/brand_opportunities`
     - BrandRoleContent.vue:渲染 `brand_role_result.role/strategy/differentiation`
     - BigIdeaContent.vue:渲染 `big_idea_result.big_idea/content_strategy`
   - **market_report**:
     - AgendaMapContent.vue:渲染 `agenda_map_result.narrative_map/agenda_battles/...`
     - LandscapeContent.vue:渲染 `landscape_result.players/positioning_map/discourse_battles`
     - StrategicBriefContent.vue:渲染 `strategic_brief_result.strategic_priorities/opportunities`,**支持 evidence_refs 跳转**

### 5.3 前端硬依赖字段

- `strategy.status`(控制进度条和按钮启用)
- `strategy.output_type`(决定显示哪套面板)
- `strategy.research_design.research_questions[]`(在每个 stage 底部显示"本次分析回答的问题")
- `strategy.{stage}_result`(每个产出面板的主数据)
- `*_result.evidence` / `evidence_refs`(**跳转交互依赖**)

### 5.4 跨 stage 跳转交互

Strategic Brief 面板的 "strategic_priorities[i].evidence_refs" 可点击跳转到:
- Agenda Map 面板的对应 `agenda_battles[i]` 卡片
- Landscape 面板的对应 `players[i]` 或 `discourse_battles[i]`

这是**前端 UI 与后端数据结构的硬契约**,砍上游字段会让跳转失效。

---

## 6. APScheduler 任务图

### 6.1 任务清单

[`src/scheduler.py`](../../backend/src/scheduler.py)

| Job ID | 间隔 | 职责 |
|--------|-----|-----|
| `strategy_probe` | 2 分钟 | status=probing 的策略:全部 probe 任务达终态 → 触发 probe review |
| `strategy_collection` | 2 分钟 | status=collecting 的策略:全部 collect 任务完成 → 自动建切片 + coverage_check |
| `news_task_watchdog` | 5 分钟 | 新闻任务超 20 min running/pending → 标记 failed |
| `agent_timeout_reset` | 5 分钟 | 社媒 agent 超时任务回收 |

### 6.2 终态定义(关键)

**社媒 probe 任务**:`has_analysis=True`(LLM 分析完成)
**新闻 probe 任务**:`status ∈ {completed, failed}`(failed 不阻塞,probe review 会保守判 pass + 人工核查提示)

### 6.3 幂等保证

- `confirm-research` 从 probing 重试时先删旧探测任务
- `refine_probe` 软删被替换的任务
- `approve_probe` 对已 collecting 状态幂等返回

---

## 7. 关键 API 端点

[`router.py`](../../backend/src/strategies/router.py)

| 端点 | 方法 | 状态变化 | 同步/异步 |
|-----|-----|--------|--------|
| `/strategies` | POST | - → draft | 同步 |
| `/{id}/parse-brief` | POST | - | 同步(LLM) |
| `/{id}/design-research` | POST | draft → planned | 同步(LLM) |
| `/{id}/confirm-research` | POST | planned → probing | 同步(派发异步任务 + Research Agent) |
| `/{id}/probe-status` | GET | - | 同步 + 自动触发 |
| `/{id}/approve-probe` | POST | probing → collecting | 同步 |
| `/{id}/refine-probe` | POST | probing(probe_round++) | 同步 |
| `/{id}/collection-status` | GET | collecting → ready(自动) | 同步 + 自动建切片 |
| `/{id}/data-overview` | GET | - | 同步 |
| `/{id}/adjust-slices` | POST | ready(重新验证) | 同步 |
| `/{id}/generate/insight` | POST | ready → insight_done | **同步(LLM)** |
| `/{id}/generate/brand-role` | POST | insight_done → brand_role_done | **同步(LLM)** |
| `/{id}/generate/big-idea` | POST | brand_role_done → completed | **同步(LLM)** |
| `/{id}/generate/agenda-map` | POST | ready → agenda_map_done | **同步(LLM)** |
| `/{id}/generate/landscape` | POST | agenda_map_done → landscape_done | **同步(LLM)** |
| `/{id}/generate/strategic-brief` | POST | landscape_done → completed | **同步(LLM)** |
| `/{id}/{stage}` | PUT | (级联清空下游) | 同步 |
| `/{id}/export` | GET | - | 同步(Word 导出) |
| `/strategies/parse-brief` | POST | - | 同步(LLM 解析) |

**所有产出 generate 端点是同步 LLM 调用**,完成后立即返回结果。这意味着每次生成用户要等几十秒到几分钟。

---

## 8. 关键发现摘要

### 8.1 策略研究是"下游薄层"

核心代码其实不多——主要是:
- 10 条 chain(每条本质是 prompt + LLM 调用)
- 数据加载 / formatter 函数
- 状态机 + 级联清空逻辑
- APScheduler 编排

**重的部分全在上游**(社媒 pipeline、新闻 NewsSlice、Research Agent LangGraph)。策略本身没什么可砍的。

### 8.2 上游字段消费是"广而不深"

- insight_chain 消费 SocialSlice 18 个字段路径,其中 10 个必需
- agenda_map_chain 消费 NewsSlice narratives + stats 的 11 个字段
- Research Agent 接口完全解耦(formatter 模式优雅降级)

**结论**:任何上游重构都必须保留 insight_chain 和 agenda_map_chain 消费的核心字段。

### 8.3 跨 stage 硬引用是重构的最大障碍

`strategic_brief.evidence_refs` → `agenda_map/landscape` 结构化字段,前端 UI 依赖此做跨 stage 跳转。如果改成 LLM 一把梭直接出一份完整报告,**这个交互就没了**——除非让 LLM 自己生成符合 schema 的 refs(理论可行,实操容易幻觉)。

### 8.4 级联清空语义是重构的"红线"

无论架构怎么改,"重新生成上游 stage 必须清空下游"的语义必须保留,否则前端会看到数据错位。

### 8.5 Research Agent 是已有的解耦典范

三个源模块里,Research Agent 的策略侧集成做得最好:
- Formatter 函数按 stage token 预算分层
- 无结果时空串降级
- 独立前端页面 + 策略嵌入两条路径

**如果要把社媒/新闻也做成类似的解耦接口,Research Agent 是参考答案**。

### 8.6 `full_strategy` 是独特约束

`full_strategy` 路径把 Landscape 结构化 JSON 塞进 Insight 的 news_media_section。这是**跨路径的 in-memory 数据传递**,任何 insight_chain 的重构必须兼容这个输入形态。

---

## 9. 先前改动的影响分析

到目前为止的改动(Prompt Caching 修复、evaluator MVP):
- 没直接碰策略 chain 代码
- evaluator 目前只评 insight_result,后续可扩展到其他 stage

**待审视的是**:社媒模块中被改 prompt 的 `entity_normalization_chain` / `monitor_entity_merge_chain`——它们产出的 `aligned_entities[].role / parent` 字段被 insight_chain 间接消费(通过 SocialSlice.foundation)。需要验证 prompt 改动没影响这些字段的输出质量。

---

## 10. 后续:4 模块 inventory 全部完成

| 模块 | 状态 | 文档 |
|------|-----|-----|
| 社媒监控 | ✅ | [social_media.md](social_media.md) |
| 新闻监控 | ✅ | [news_media.md](news_media.md) |
| 专题研究 | ✅ | [research_agent.md](research_agent.md) |
| **策略研究** | ✅ | 本文档 |

**下一步**:基于 4 份 inventory,在 ADR-001 Phase 1 重新评估架构选项(Option A-E),用评估 harness 做量化对比,形成 Phase 2 的 Accepted 决策。
