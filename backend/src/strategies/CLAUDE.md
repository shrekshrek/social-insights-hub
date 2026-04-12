# Strategies 模块

策略研究引擎：4 阶段自动化流程（研究设计→探测验证→数据就绪→产出生成），用户全程留在策略页面，系统自动编排 Monitor 创建、任务管理、切片创建。

## Public Interface

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/strategies` | 创建策略（关联切片 + 可选 Brief） |
| GET | `/strategies` | 策略列表 |
| GET | `/strategies/{id}` | 策略详情 |
| PUT | `/strategies/{id}` | 更新名称/Brief |
| DELETE | `/strategies/{id}` | 删除策略 |
| POST | `/strategies/{id}/design-research` | AI 生成研究计划 |
| POST | `/strategies/{id}/confirm-research` | 确认计划→创建 Monitor + 探测任务 |
| GET | `/strategies/{id}/probe-status` | 探测进度 + 自动审查触发 |
| POST | `/strategies/{id}/approve-probe` | 手动确认探测通过 |
| POST | `/strategies/{id}/refine-probe` | 调整关键词，创建新探测任务 |
| GET | `/strategies/{id}/collection-status` | 全量采集进度 + 自动建切片 |
| GET | `/strategies/{id}/data-overview` | 数据全景（切片 + 覆盖度） |
| POST | `/strategies/{id}/adjust-slices` | 微调切片配置 |
| POST | `/strategies/{id}/generate/{insight,brand-role,big-idea}` | brand_strategy 路径：生成对应阶段 |
| PUT | `/strategies/{id}/{insight,brand-role,big-idea}` | brand_strategy 路径：编辑阶段结果 |
| POST | `/strategies/{id}/generate/{agenda-map,landscape,strategic-brief}` | market_report 路径：生成对应阶段 |
| PUT | `/strategies/{id}/{agenda-map,landscape,strategic-brief}` | market_report 路径：编辑阶段结果 |
| GET | `/strategies/{id}/export` | 导出 Word 文档 |
| POST | `/strategies/parse-brief` | 上传 Brief 文档 AI 解析 |

### 权限

`strategy` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### 核心表

- `strategies`: 顶级实体，核心 JSONB 字段：
  - 阶段结果：`brand_brief` / `research_design` / `probe_review_result` / `coverage_check_result`
  - brand_strategy 路径：`insight_result` / `brand_role_result` / `big_idea_result`
  - market_report 路径：`agenda_map_result` / `landscape_result` / `strategic_brief_result`
  - 路由字段：`status` / `output_type`（`brand_strategy` | `market_report`，用户在 confirm-research 时显式选择）
  - 监测关联：`social_monitor_id` / `news_monitor_id`（两条路径分别对应）
- `strategy_slices`: 关联表（strategy_id → slice_id），切片由系统自动创建
- `social_tasks` / `news_tasks`: 通过 `strategy_id` FK 反向关联策略（nullable，策略任务专用）

### 状态流转

两条独立路径共享前置阶段，在 `ready` 之后按 `output_type` 分叉。`STATUS_ORDER` 中 `agenda_map_done` 与 `insight_done` 共享 order 值，`landscape_done` 与 `brand_role_done` 共享 order 值，确保 `>= ready` 等通用比较仍然有效。

```
draft → planned → probing → collecting → ready ┬─ [brand_strategy] → insight_done → brand_role_done → completed
                                                 └─ [market_report]  → agenda_map_done → landscape_done → completed
```

- `draft`: 初始状态，有 Brief 但未生成研究计划
- `planned`: AI 已生成研究计划（research_design）
- `probing`: 用户确认计划，探测任务已创建，等待数据
- `collecting`: 探测通过，全量采集进行中
- `ready`: 切片已创建且覆盖度验证通过
- brand_strategy 分支：`insight_done` → `brand_role_done` → `completed`
- market_report 分支：`agenda_map_done` → `landscape_done` → `completed`

> 三阶段在这两条路径下都是**层层递进**（第 N 层消费第 N-1 层的结果），但每条路径用领域术语命名，不再保留 phase 数字后缀。文档中描述"第 1/2/3 层"时指的是此递进顺序，对应字段名见上。

## 4 阶段流程

### ① 研究设计 (draft → planned → probing)

1. `design-research`: research_design_chain 基于 Brief 生成研究问题 + 数据采集方案 + 切片蓝图 + 产出类型
2. 用户可编辑 data_plan（关键词/平台）和 slice_blueprint（切片名/主体）
3. `confirm-research`: 根据 data_plan 的渠道分别创建 SocialMonitor / NewsMonitor + 对应 phase="probe" 任务，状态 → probing
   - 社媒：每个 keyword×platform 一个 SocialTask，max_pages 限制翻页
   - 新闻：每个 keyword 一个 NewsTask，celery `run_news_probe_task` 异步派发（纯搜索）
   - 行业研究：research_design 含 `research_agent` 字段时条件创建 ResearchTask（Celery 立即启动 LangGraph，无探测阶段，与社媒/新闻并行）

### ② 探测验证 (probing → collecting)

1. 前端轮询 `probe-status`
   - 社媒：爬虫采集约 20 条，跳过评论，LLM 打标（NEWS/POST 分析链）
   - 新闻：`run_news_probe_task` 三渠道搜索（baidu + sogou + duckduckgo），每渠道上限 20 条，URL 去重后落库元数据，不抓全文、不打标
2. 所有任务准备就绪后后台自动运行 probe 审查
   - 社媒：规则分流 + `strategy_social_probe_review_chain`（LLM 判定模糊案例）
   - 新闻：`strategy_news_probe_review_chain` 对每个任务并行 LLM 评估（基于卡片 title/source/tier/snippet + 维度→研究问题映射）
   - 社媒创建 `STRATEGY_SOCIAL_PROBE_REVIEW` AnalysisJob、新闻创建 `STRATEGY_NEWS_PROBE_REVIEW` AnalysisJob，独立记录 token/cost；LLM 失败时保守判 pass + 人工核查提示
3. `all_pass` → 自动调用 approve_probe，为每个探测任务创建 phase="collect" 全量任务（社媒 + 新闻），策略 → collecting
4. `partial_pass/fail` → 用户可 `approve-probe`（跳过审查直接全量）或 `refine-probe`（batch 替换/新增/移除关键词，`refinements` 调社媒、`news_refinements` 调新闻，两个列表至少填一个，probe_round++，最多 3 轮）

### ③ 数据就绪 (collecting → ready)

1. 前端轮询 `collection-status`，爬虫采集全量数据（50 条 + 评论）
2. 所有全量任务分析完成后自动按 slice_blueprint 创建切片
   - 社媒：按维度分组任务 → `create_monitor_slice` → SocialSlice（Stage1/2/3 流水线）
   - 新闻：按维度分组任务 → `_create_strategy_news_slice` → NewsSlice（独立 insight 分析）
   - 每个 blueprint 条目可产生 0-1 个 SocialSlice + 0-1 个 NewsSlice
3. 切片就绪后自动运行 coverage_check_chain 验证覆盖度（社媒 + 新闻切片一起验证）
4. `overall_ready=true` → 状态 → ready
5. 用户可 `adjust-slices` 微调切片配置（触发重新验证）

### ④ 产出生成 (ready → completed)

两条独立路径，由 `strategy.output_type` 决定（用户在 confirm-research 时显式选择）。两条路径都基于**两层数据模型**：

- **主数据源（primary）**：直接注入 prompt 的切片数据
  - brand_strategy 路径：`social_media`（SocialSlice，消费者声音主轴）
  - market_report 路径：`news_media`（NewsSlice，媒体视角主轴）
- **行业研究（research）**：Research Agent 自动搜索分析，注入 `{research_findings}` 占位符（无结果时优雅降级为 ""）

#### brand_strategy 路径（Insight → Brand Role → Big Idea）

Insight → Brand Role → Big Idea，层层递进（第 1/2/3 层）。主数据源 = social_media（`load_strategy_inputs`），同时通过 `_format_news_media_section` 将新闻切片作为补充段落注入 `{news_media_section}`（可选上下文，不是主数据）。行业研究通过 `_retrieve_research_findings` 加载 Research Agent 结果，per-stage formatter 注入 `{research_findings}`。

#### market_report 路径（Agenda Map → Landscape → Strategic Brief）

- **Agenda Map（媒体议程图，第 1 层）**：主数据源 = news_media（`load_strategy_news_inputs`）。基于 NewsSlice 的 tagging/insight 产出 narrative_map / agenda_battles / media_voice_patterns / attention_gaps。credibility=high 必须有 tier1+tier2 支撑。禁止引入消费者声音（那是 brand_strategy 路径）。
- **Landscape（竞争格局，第 2 层）**：输入 = Agenda Map 结果 + 原始 news slices。产出 players（role: target/competitor/context，media_sov_pct, media_sentiment）/ positioning_map（LLM 自选 x/y 轴）/ discourse_battles（必须 ref `agenda_map_battle_ref`）/ market_dynamics。
- **Strategic Brief（战略简报，第 3 层）**：输入 = Agenda Map + Landscape（**禁止引入新数据**）。产出 executive_summary / strategic_priorities（每条必须 answer ≥1 research_question + evidence_refs 指向 agenda_map/landscape 字段）/ market_opportunities / risks_and_threats / recommended_positioning（proof_points 通过 `agenda_map_narrative_ref` 回链上游叙事）。

#### data_provenance 记录

每个 stage 生成后，结果 JSONB 的 `data_provenance` 字段记录实际消费来源：

```json
{
  "primary": {
    "channel": "social_media" | "news_media",
    "social_media_slice_count": <int>,
    "news_media_slice_count": <int>
  },
  "research": {
    "research_agent": <bool>
  }
}
```

- `primary` 决定"走哪条产出路径"（brand_strategy vs market_report）
- `research` 是行业研究视角（Research Agent），与 primary 在分析权重上平等，但不驱动路径选择

前端 `DataProvenanceBadge` 组件据此展示数据来源。`AnalysisJob.source_count` 取主数据源对应的切片数（brand_strategy → social 切片数；market_report → news 切片数）。

## LLM Chain

11 条 Chain 位于 `llm/chains/strategy/`（按路径分 `shared/` / `brand_strategy/` / `market_report/` 三个子目录）。

| Chain | 角色 | 触发时机 | 路径 |
|-------|------|---------|------|
| brief_parser_chain | Brief 摄入 + 三渠道分发判断（social_media / news_media / research_agent） | 新建策略时（`parse-brief` 端点） | shared |
| research_design_chain | 研究规划师（产出 data_plan + 可选 research_agent） | ① | shared |
| strategy_social_probe_review_chain | 社媒数据质检员 | ② | shared |
| strategy_news_probe_review_chain | 新闻数据质检员（单任务并行） | ② | shared |
| coverage_check_chain | 覆盖度验证 | ③ | shared |
| insight_chain | 洞察分析师（第 1 层） | ④ | brand_strategy |
| brand_role_chain | 品牌角色策略师（第 2 层） | ④ | brand_strategy |
| big_idea_chain | 创意总监（第 3 层） | ④ | brand_strategy |
| agenda_map_chain | 媒体议程图（第 1 层） | ④ | market_report |
| landscape_chain | 竞争格局（第 2 层） | ④ | market_report |
| strategic_brief_chain | 战略简报（第 3 层，只消费前两层） | ④ | market_report |

所有 stage chain 都注入 `research_design` 中的 research_questions 作为分析上下文。`research_findings.py` 提供 6 个 per-stage formatter 函数，按 token 预算从 ResearchTask.result_data 提取并格式化行业研究数据注入 `{research_findings}`。brand_strategy chain 通过 `_format_news_media_section` 把新闻切片作为补充段落注入；market_report Agenda Map chain 直接消费 `load_strategy_news_inputs` 加载的 NewsSlice 作为主数据源。

## Agent 协议

云端通过 Agent API 向爬虫下发任务，爬虫轮询获取并执行：

```
爬虫轮询 → GET /api/v1/agent/tasks/pending
         → 返回 status="pending" 的任务
         → 接受任务 → 采集 → 上传结果 → status="completed"
```

任务类型：
- **探测任务**（phase="probe"）：max_pages 限制翻页，跳过评论，约 20 条
- **全量任务**（phase="collect"）：采集完整数据（50 条 + 评论）
- **普通任务**：一次性采集到 max_notes_count 指定数量

## Important Notes

- Strategy 通过 `strategy_slices` 关联社媒切片（SocialSlice），新闻切片（NewsSlice）通过 `news_monitor_id` 隐式关联
- `_create_auto_slices` 按 `slice_blueprint` 自动创建：社媒维度 → SocialSlice，新闻维度 → NewsSlice，互不侵入
- `confirm_research` 按渠道分别创建 SocialMonitor / NewsMonitor（同渠道所有任务共��一个 Monitor）+ 条件创建 ResearchTask（research_design 含 `research_agent` 字段时）
- `_task_dimension_map` / `_news_task_dimension_map` 存在 `research_design` 中，分别记录社媒 / 新闻 task_id → dimension_name 映射，供 probe 审查注入研究问题 + 自动建切片使用
- `probe-status` 和 `collection-status` 是轮询端点，全部完成后自动触发下游逻辑（LLM 审查/建切片/覆盖度验证）；两个端点同时返回 `research_agent` 状态（ResearchTask 进度，不阻塞主流程）
- Research Agent 通过 `research_tasks.strategy_id` FK 关联策略，不在 Strategy 表上加冗余字段。`_retrieve_research_findings` 读取最新已完成的 ResearchTask.result_data，per-stage formatter 按 token 预算注入 `{research_findings}`
- 新闻 insight 粒度：独立监测和策略研究都通过 NewsSlice 切片触发 insight（按 blueprint 条目分组新闻任务创建切片），采集阶段仅做 tagging 不做 insight
- 新闻搜索渠道：baidu / sogou / duckduckgo（默认三渠道）+ wechat_mp（可选，通过搜狗微信专用入口）；source_tier 分层：tier1(权威) / tier2(行业) / tier3(其他) / wechat_mp(公众号)
- `output_type` 由用户在 confirm-research 时**显式选择**，前端 `ResearchPlanEditor` 根据 data_plan 的渠道组成阻塞不合法的组合（brand_strategy 需含 social_media 维度；market_report 需含 news_media 维度）。后端 `_validate_market_report_output_type` 在生成时二次校验
- `generate_brand_strategy_stage` 和 `generate_market_report_stage` 都遵循**下游级联清空**语义：重新生成 Insight / Agenda Map 会清空下游结果 + 回退状态到 `ready`；重新生成 Brand Role / Landscape 会清空 Big Idea / Strategic Brief
- `edit_brand_strategy_stage` 和 `edit_market_report_stage` 同样会级联清空下游结果，避免上下游不一致
- Word 导出依赖 `python-docx`
