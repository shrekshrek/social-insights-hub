# Feature Inventory: 社媒监控 (`src/social_media/`)

> ⚠️ **存档（时点快照）**：本文档是 ADR-001 Phase 0 时期（2026-04）的事实盘点，仅供决策溯源，**不随代码更新**。模块现状以代码与各级 CLAUDE.md 为准（已知漂移示例：新闻链已拆 pass1/pass2 并新增 themes 议题层）。

> 盘点日期:2026-04-20
> 目的:为 ADR-001 架构决策提供事实基础。**本文档只做盘点,不下架构结论**。

## TL;DR

社媒监控不是简单的"NLP pipeline",而是一套**结构化数据生成体系**,前端 10+ 个图表组件、3 份 Markdown 报告、task-level 与 slice-level 两层分析视图都重度依赖 pipeline 产生的特定字段。

**关键发现**:
- 前端有约 **15 个硬依赖字段路径**,去掉 pipeline 后这些组件全部失效
- `spam_score` 驱动的 **organic/promo 分层**是 pipeline 的独特价值,LLM-native 一把梭做不到
- 9 条链**不是平行关系**,而是分 3 个 stage 的流水线(screening → 深度提取 → 聚合/归一/报告)
- 没有社媒相关 APScheduler 定时任务(全部用户触发)

---

## 1. LLM Chain 清单(9 条)

按使用阶段分组,不是按文件顺序。

### 1.1 Stage 1: 数据清洗与提取(3 条)

#### `screening_chain.py`
- **职责**:批量对原文评分(广告度/价值/相关度/情感)
- **输入**:`settings.CELERY_AI_POSTS_BATCH_SIZE` 帖/批(当前配置 **15**)× (`post_id`, `title`, `content`) + 项目关键词
- **输出**:`spam_score` (0-10) / `value_score` (0-10) / `relevance_score` (0-10) / `sentiment` (-2~+2)
- **调用频次**:每批 15 帖一次,总帖数 / 15 次调用
- **调用方**:[`screening_tasks.py:_analyze_batch_posts`](../../backend/src/social_media/analysis/celery_tasks/screening_tasks.py)
- **🔑 独有价值**:`spam_score` 是后续所有"有机/推广分层"分析的唯一来源——LLM-native 一把梭做不到给每帖一个独立的广告度评分

#### `post_extraction_chain.py`
- **职责**:从原文提取实体 + 通用观点 + 摘要
- **输入**:单帖 `title + content`
- **输出**:
  ```
  entities[]: {name, type, sentiment, features[], issues[], expectations[],
               audience[], scenarios[], market_factors[], competitors[]}
  general_opinions[]: {category, opinions[], sentiment}
  summary: string
  ```
- **调用频次**:通过 screening 的每帖一次(深度分析阶段)
- **🔑 独有价值**:9 维实体属性(features/issues/expectations 等)是结构化数据基础,驱动 IPA/雷达等图表

#### `comment_extraction_chain.py`
- **职责**:从评论提取实体 + 观点,含**溯源编号**
- **输入**:原文 context(仅辅助理解)+ 编号化评论列表
- **输出**:同上 + `source_comments: [1, 2, 3]` 追溯字段
- **调用频次**:每帖一次(批处理该帖所有评论)
- **🔑 独有价值**:`source_comments` 让任一观点可反向定位到具体评论,前端"PostListModal"依赖

### 1.2 Stage 2: 归一化(4+1 条)

#### `entity_normalization_chain.py`(两阶段)
- **职责**:合并同义实体 + 打 Role/Parent 标签
- **两阶段设计**:Merge(初步) + Review(审计跨品类错误)
- **输出**:`{entities: [{name, original_names[], role: Target|Competitor|Context, parent}]}`
- **调用频次**:任务级聚合 1 次 + 项目级切片 Stage2 1 次(两阶段意味着 2×)
- **🔑 独有价值**:**Role 标签驱动 SOV 分组、SWOT 对比**,前端通过 `role == "Target"` 等过滤显示

#### `attribute_normalization_chain.py`
- **职责**:对实体的 features/issues/expectations 等 7 个维度各自聚类
- **输出**:`{clusters: [{name, original_terms[]}]}`
- **调用频次**:任务级 7 次 + 项目级 7 次 = **14 次/切片**
- **🔑 独有价值**:图表标签的标准化(如"发热"/"烫手"/"温度高"合并为"发热严重",前端 IPA 图 Y 轴需要稳定标签)

#### `category_normalization_chain.py`
- **职责**:观点类别归一("单价/售价/费用"→"价格")
- **调用频次**:任务级 1 次 + 项目级 1 次
- **🔑 独有价值**:建立项目级统一类别体系,是观点雷达 / 话题分析的底层词汇表

#### `opinion_normalization_chain.py`
- **职责**:同类别内观点语义归纳("太贵/买不起/性价比低"→"定价过高")
- **调用频次**:每类别 1 次(通常 5-15 个类别)
- **🔑 独有价值**:保留情感极性的聚类——输出必须和输入情感一致,前端情感分析依赖这点

#### `monitor_entity_merge_chain.py`(项目级专用,两阶段)
- **职责**:跨任务聚合后的实体再归一(subject/competitors 强制 Role 校验)
- **调用频次**:项目级切片 Stage2,两阶段 × 1 = 2 次
- **🔑 独有价值**:**严格防止跨品类错误合并**(如"华为手机"和"华为冰箱" merge 为一个实体),第二阶段 review 专门拆分这类错误

### 1.3 Stage 3: 报告生成(3 条,纯 Markdown 输出)

#### `monitor_slice_reports_chain.py` - Landscape Report
- **职责**:撰写市场格局分析(500-700 字 Markdown)
- **输入**:完整的 `landscape` layer 数据 + top entities + 用户原话 evidence
- **输出**:Markdown 文本(执行摘要 → 竞争格局 → 关键趋势)
- **🔑 独有价值**:用"麦肯锡金字塔原理"——结论先行 + 数据支撑

#### Topic Report
- **职责**:深度痛点/爽点/争议/未满足需求洞察(600-900 字)
- **输出**:执行洞察 → 痛点深潜 → 未被满足的需求 → 爽点驱动力 → **反直觉信号**
- **🔑 独有价值**:用 Jobs-to-be-Done 思维 + "吐槽 vs 放弃"区分

#### Focus Report
- **职责**:品牌方 Target vs 竞品的战略诊断(800-1200 字)
- **生成条件**:**仅当 subject + competitors 都非空时**
- **输出**:战略仪表盘(含数据对称性预警)→ SWOT → 差异化雷达 → 战略行动建议
- **🔑 独有价值**:**数据不对称风控**(竞品数据量少时警示"竞品口碑可能优于数据所示"),避免误判

---

## 2. 数据模型

### 2.1 核心模型

| 表 | 关键字段 | 关系 |
|---|---------|------|
| `social_monitors` | id, name, user_id, start_date, end_date, deep_analysis_settings | → tasks (1:N) |
| `social_tasks` | id, monitor_id, platform_id, keywords, status, posts_count, comments_count, analysis_result(JSON), auto_analyze | → posts, comments (1:N) |
| `social_posts` | id, task_id, platform_id, post_id_on_platform, title, content, likes_count, comments_count, collected_count, cii(计算) | → comments (1:N), post_analysis (1:1) |
| `social_comments` | id, post_id, task_id, comment_id_on_platform, parent_comment_id, content, likes_count | |
| `post_analysis` | id, post_id(unique), spam_score, value_score, relevance_score, sentiment(-2~+2), cii, post_deep_result(JSON), comment_deep_result(JSON) | ← post (1:1) |
| `social_slices` | id, monitor_id, name, status, included_task_ids[], **subject**, **competitors[]**, **result_data(JSON)**, **stats(JSON)** | 无 FK 到 task。subject/competitors 是切片**配置**（一等列），与分析产物 result_data 解耦 |

### 2.2 `SocialSlice.result_data` 关键结构(前端重度消费)

```
# subject / competitors 已从 result_data.meta 升格为 social_slices 表列；
# result_data.meta 仅存"分析时刻元数据"。
result_data = {
  meta:       { monitor_id, generated_at, weights_used, scope{ keywords[] }, task_diagnostics, ... },
  foundation: {
    aligned_entities[]: { name, role, parent, heat, sentiment,
                          organic_heat, promo_heat, organic_sentiment, promo_sentiment,
                          spam_distribution{ high_spam{total,post,comment}, low_spam{...} },
                          sentiment_distribution{ positive, negative, neutral },
                          top_features[], top_issues[], top_expectations[],
                          source_tasks[], post_ids_sample[], platform_distribution{} },
    aligned_topics[]:   { name, category, heat, sentiment, organic_heat, promo_heat, ... },
    drivers: {
      dimensions_top[],
      entity_matrix[]: { entity, dimensions{ 价格{mentions,pos,neg,sentiment}, ... } }
    }
  },
  layers: {
    landscape: { overview{total_volume,nsr,platform_volume},
                 sov_ranking[], group_share[], platform_dna[], industry_quadrant[] },
    topic:     { topic_aspects[], topic_radar{pains[], gains[], controversies[]},
                 unmet_needs[] },
    focus:     { swot{strengths[],weaknesses[],opportunities[],threats[]},
                 product_line_health[], platform_scissors{by_platform[]}, gap_analysis[] }
  },
  reports: {
    landscape_report: { content: "Markdown..." },
    topic_report:     { content: "Markdown..." },
    focus_report:     { content: "Markdown..." }
  },
  pipeline: { stage1{...}, stage2{...}, stage3{...} }  // 进度追踪
}
```

**⚠️ 关键观察**:`organic_*` / `promo_*` 字段对**无处不在**。前端 Tab 切换(全部/有机/推广)依赖这些字段对;没有 spam_score 就产生不出这些对。

---

## 3. 前端硬依赖清单

### 3.1 图表组件依赖矩阵

| 前端组件 | 所在页面 | 依赖字段路径 |
|---------|--------|-----------|
| 四象限图 (Sentiment×CII) | task analysis | `post_analysis.sentiment`, `post_analysis.cii` |
| 时间分布 | task analysis | `post.published_at` |
| IPA 气泡图 | task analysis | `aggregated_topics[].mentions/sentiment/heat` |
| 实体排行 | task analysis | `analysis_result.entities[].name/sentiment/top_*` |
| 深度分析 Modal | task analysis | `post_analysis.post_deep_result/comment_deep_result` |
| **SOVRankingChart** | slice analysis | `layers.landscape.sov_ranking[].{name,heat,mentions,share,spam_distribution,post_ids_sample}` |
| **GroupShareTable** | slice analysis | 同上 + `organic_heat, promo_heat, sentiment, organic_sentiment` |
| **PlatformDNAChart** | slice analysis | `layers.landscape.platform_dna[]` 或 `platform_dna_grouped[]` |
| **IndustryQuadrantChart** | slice analysis | `layers.landscape.industry_quadrant[].{name,heat,sentiment,organic_*,promo_*}` |
| **TopicRadarChart** | slice analysis | `layers.topic.topic_radar.{pains,gains,controversies}[].{name,heat,sentiment,original_terms}` |
| **SWOTMatrixChart** | slice analysis | `layers.focus.swot.{strengths,weaknesses,opportunities,threats}[].delta` |
| **ProductLineHealthTable** | slice analysis | `layers.focus.product_line_health[].{name,heat,contribution,sentiment,top_pain}` |
| **PlatformScissorsChart** | slice analysis | `layers.focus.platform_scissors.by_platform[].{subject_share,industry_share,delta}` |
| **GapAnalysisChart** | slice analysis | `layers.focus.gap_analysis[]` |
| **MarkdownRenderer** × 3 | slice analysis | `reports.{landscape,topic,focus}_report.content` |

### 3.2 架构契约(前端隐含的硬约束)

1. **`result_data.layers` 三层必须存在**(即使为空也需 key 在位)
2. **`spam_distribution` 结构**:若某数据点有,必须含 `high_spam/low_spam`,各含 `total/post/comment` 三个数
3. **`organic_*` 与 `promo_*` 字段对**:Tab 切换依赖成对出现
4. **`source_tasks` 和 `post_ids_sample`**:溯源弹窗 PostListModal 需要

### 3.3 LLM-native 架构的"炸裂"清单

如果用 LLM 一次性分析替代 pipeline,**以下前端功能会全部失效**:
- 所有结构化图表(SOV/象限/雷达/SWOT/产品线/剪刀差/Gap),约 10 个组件
- 3 份 Markdown 战略报告
- 有机/推广 Tab 切换(依赖 spam_score 分层)
- 溯源能力(依赖 source_tasks + post_ids_sample)
- 跨任务聚合(slice 层级的一切)

**结论性事实(非主观判断)**:LLM-native 一把梭**不能替代社媒监控的产出**。它能产生"洞察文本",但产生不了前端依赖的结构化数据矩阵。

---

## 4. 任务图

### 4.1 Celery Task 清单

注册于 [`src/celery_app.py`](../../backend/src/celery_app.py) 的 `include` 列表:
- `screening_tasks`
- `deep_analysis_tasks`
- `aggregation_tasks`
- `monitor_slice_tasks`

### 4.2 任务依赖流

```
# Task-level 分析流(用户触发)
POST /tasks/{id}/screening
  → screening_coordinator (AnalysisJob: SCREENING)
  → screening_batch_subtask × N (15帖/批,由 `CELERY_AI_POSTS_BATCH_SIZE` 配置)
  → finalizer (标记完成)
  → [可选 auto-trigger] deep_posts_coordinator

POST /tasks/{id}/deep-posts
  → deep_posts_coordinator (AnalysisJob: POST_DEEP_ANALYSIS)
  → deep_posts_single_subtask × N
  → finalizer → run_aggregation_task()

POST /tasks/{id}/deep-comments
  → deep_comments_coordinator
  → deep_comments_single_subtask × N
  → finalizer → run_aggregation_task()

run_aggregation_task (Celery)
  → orchestrator.aggregate_task_analysis()
    ├─ Entity Normalization (两阶段)
    ├─ Attribute Normalization × 7 维度
    ├─ Opinion Normalization × n 类别
    ├─ Insights 计算(本地,无 LLM)
    └─ 写入 SocialTask.analysis_result

# Project-level slice 流(手动创建切片)
POST /monitors/{id}/slices + trigger_analysis
  → run_monitor_slice_task (Celery)
  → orchestrator.run_monitor_slice_pipeline_sync()
    ├─ Stage 1: 本地合并 → foundation
    ├─ Stage 2: LLM 归一化
    │   ├─ Entity Normalization (两阶段)
    │   ├─ Opinion Normalization
    │   ├─ Category Normalization
    │   ├─ drivers_synthesis (本地,无 LLM)
    │   └─ 写入 result_data.layers
    └─ Stage 3: LLM 报告
        ├─ Landscape Report
        ├─ Topic Report
        ├─ Focus Report(可选)
        └─ 写入 result_data.reports
```

### 4.3 APScheduler

**社媒模块没有任何定时任务**。APScheduler 只负责策略/新闻/KB 相关的轮询,不涉及社媒。全部分析都是用户主动触发或由前面的 task finalizer 链式调用。

### 4.4 AnalysisJob 类型映射

| `analysis_type` | 创建时机 | 创建方 |
|----------------|---------|-------|
| `SCREENING_POSTS` | /screening 端点 | screening_coordinator |
| `DEEP_POSTS` | /deep-posts 端点 | deep_posts_coordinator |
| `DEEP_COMMENTS` | /deep-comments 端点 | deep_comments_coordinator |
| `ENTITY_NORMALIZATION` | 聚合/Stage2 | aggregation / monitor_slice orchestrator |
| `ATTRIBUTE_NORMALIZATION` | 聚合(每维度) | aggregation orchestrator |
| `OPINION_NORMALIZATION` | 聚合/Stage2 | 同上 |
| `CATEGORY_NORMALIZATION` | Stage2 | monitor_slice orchestrator |
| `MONITOR_ENTITY_MERGE` | Stage2 | 同上 |
| `MONITOR_SLICE_SUMMARY`(3 种报告共享) | Stage3 | 同上 |

---

## 5. 监测场景的真实使用

### 5.1 三个主要页面

1. **监测项目列表** (`/social-media/monitors`) — 项目 CRUD
2. **任务级分析** (`/monitors/[id]/tasks/[taskId]/analysis`) — 单任务 1000+ 帖的分析结果
3. **项目级切片分析** (`/monitors/[id]/analysis`) — 跨任务合并切片的综合报告

### 5.2 典型用户工作流

| 场景 | 使用的数据层 | 关键页面 |
|------|-----------|--------|
| 快速舆情监测(新品发布) | Task-level | task analysis 四象限 → 找爆雷区 |
| 竞品对标(季度评审) | Slice-level | project analysis → 切片对标 SOV + SWOT → 导出报告 |
| 话题洞察(产品改进) | Slice-level | project analysis → topic_radar → Topic Report |

### 5.3 task-level vs slice-level 的价值区分

- **task-level**:单次采集的"快速响应"视角。四象限找爆雷、实体排行找舆论焦点、深度分析 Modal 看单帖详情。
- **slice-level**:跨任务的"战略分析"视角。SOV 排行、SWOT 矩阵、产品线健康、Markdown 战略报告。适合月度/季度决策。

这两层**不是冗余**,是不同决策周期的工具。

---

## 6. 关键发现摘要(对架构决策的事实输入,非结论)

### 6.1 社媒 pipeline 的不可替代价值

1. **spam_score 驱动的 organic/promo 分层**——LLM 一把梭做不到给每帖独立打广告度评分
2. **结构化字段矩阵**(entities[]、topics[]、各维度聚类)——驱动 10+ 个前端图表,无法用自由文本替代
3. **Role/Parent 标签系统**——SOV 分组、SWOT 对比都基于 role
4. **跨任务聚合切片**——task-level 分析完全做不到的"项目级"视角
5. **3 份 Markdown 报告的专业结构**——Landscape/Topic/Focus 分别是市场分析、用户洞察、战略诊断,服务不同决策场景
6. **数据不对称风控**——Focus Report 会主动预警"竞品数据少,结论可能偏差",这是领域 know-how 固化

### 6.2 可能存在的优化空间(未验证,需后续实验)

- `attribute_normalization_chain` 被调用 **14 次/切片**(任务 7 + 切片 7)。这 14 次的 system prompt 是否能合并成一次批量调用?
- `opinion_normalization_chain` 按每类别一次,通常 5-15 次/切片。能否批处理?
- `comment_extraction_chain` 每帖一次,3000+ 评论时成本可观。top N 采样是否够用?
- Stage 2 的"两阶段实体归一化"(Merge + Review)——Review 阶段的必要性在 DeepSeek V3.2 能力下是否仍有?

这些**都是 inventory 后的假设,不做架构决策**。等全部 4 个模块 inventory 完成后再综合评估。

### 6.3 前期修改的复盘

v3 阶段我为了 Prompt Caching 修改了 `entity_normalization_chain` 和 `monitor_entity_merge_chain` 的 SYSTEM → USER 位置,现在 inventory 证实这两条链**有独立价值**(Role/Parent 标签驱动前端 SWOT 等),不应被砍。

**但需要做一次对比测试**:修改前后的输出质量是否一致?两阶段设计(Merge + Review)的严格性是否被削弱?

---

## 后续工作

1. ✅ 本文档完成
2. ⏭️ **下一步**:新闻监控 inventory (`docs/inventory/news_media.md`)
3. ⏭️ 然后:专题研究 (`docs/inventory/research_agent.md`)
4. ⏭️ 最后:策略研究 (`docs/inventory/strategies.md`) — 分析它如何消费前 3 个模块的产出
5. 4 份完成后,在 ADR-001 Phase 1 重新评估架构选项
