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
| POST | `/strategies/{id}/generate/{insight,brand-role,big-idea}` | campaign_strategy / full_strategy 路径：生成对应阶段 |
| PUT | `/strategies/{id}/{insight,brand-role,big-idea}` | campaign_strategy / full_strategy 路径：编辑阶段结果 |
| POST | `/strategies/{id}/generate/{agenda-map,landscape,strategic-brief}` | market_report / full_strategy 路径：生成对应阶段 |
| PUT | `/strategies/{id}/{agenda-map,landscape,strategic-brief}` | market_report / full_strategy 路径：编辑阶段结果 |
| GET | `/strategies/{id}/export` | 导出 Word 文档 |
| POST | `/strategies/parse-brief` | 上传 Brief 文档 AI 解析 |

### 权限

`strategy` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### 核心表

- `strategies`: 顶级实体，核心 JSONB 字段：
  - 阶段结果：`brand_brief` / `research_design` / `probe_review_result` / `coverage_check_result`
  - campaign_strategy 路径：`insight_result` / `brand_role_result` / `big_idea_result`
  - market_report 路径：`agenda_map_result` / `landscape_result` / `strategic_brief_result`
  - 路由字段：`status` / `output_type`（`campaign_strategy` | `market_report` | `full_strategy`，用户在 confirm-research 时显式选择）
  - 监测关联：`social_monitor_id` / `news_monitor_id`（两条路径分别对应）
- `social_slices` / `news_slices`: 通过 `monitor_id` 隐式关联到策略（社媒走 `social_monitor_id`，新闻走 `news_monitor_id`）；切片由系统自动创建，无显式关联表
- `social_tasks` / `news_tasks`: 通过 `strategy_id` FK 反向关联策略（nullable，策略任务专用）

### 状态流转

三条路径共享前置阶段，在 `ready` 之后按 `output_type` 分叉。`STATUS_ORDER` 中 `agenda_map_done` 与 `insight_done` 共享 order 值，`landscape_done` 与 `brand_role_done` 共享 order 值，确保 `>= ready` 等通用比较仍然有效。

```
draft → planned → probing → collecting → ready ┬─ [campaign_strategy] → insight_done → brand_role_done → completed
                                                 ├─ [market_report]     → agenda_map_done → landscape_done → completed
                                                 └─ [full_strategy]     → agenda_map_done → landscape_done ──────────────→ completed
                                                                                                            (insight/brand_role 阶段
                                                                                                             status 保持 landscape_done)
```

- `draft`: 初始状态，有 Brief 但未生成研究计划
- `planned`: AI 已生成研究计划（research_design）
- `probing`: 用户确认计划，探测任务已创建，等待数据
- `collecting`: 探测通过，全量采集进行中
- `ready`: 切片已创建且覆盖度验证通过
- campaign_strategy 分支：`insight_done` → `brand_role_done` → `completed`
- market_report 分支：`agenda_map_done` → `landscape_done` → `completed`
- full_strategy 分支：`agenda_map_done` → `landscape_done` → （insight/brand_role 不推进 status）→ `completed`（Big Idea 完成时）

> 三阶段在各路径下都是**层层递进**（第 N 层消费第 N-1 层的结果），用领域术语命名。full_strategy 在 landscape_done 后继续执行 campaign_strategy 三阶段，但 status 不回退——用结果字段是否为 None 判断前置依赖，而非 STATUS_ORDER 比较。

## 4 阶段流程

### ① 研究设计 (draft → planned → probing)

1. `design-research`: research_design_chain 基于 Brief 生成研究问题 + 数据采集方案 + 切片蓝图 + 产出类型
2. 用户可编辑 data_plan（关键词/平台）和 slice_blueprint（切片名/主体）
3. `confirm-research`: 根据 data_plan 的渠道分别创建 SocialMonitor / NewsMonitor + 对应 phase="probe" 任务，状态 → probing
   - 社媒：每个 keyword×platform 一个 SocialTask，max_pages 限制翻页
   - 新闻：每个 keyword 一个 NewsTask，celery `run_news_probe_task` 异步派发（纯搜索）
   - 行业研究：brand_brief.channel_plan 含 `industry_research` 渠道时条件创建 ResearchTask（Celery 立即启动 LangGraph，无探测阶段，与社媒/新闻并行）；query=channel_brief，context=analysis_goal，研究问题由 Planner 自行生成
   - 创意研究：brand_brief.channel_plan 含 `creative_research` 渠道且 output_type 为 campaign_strategy / full_strategy 时，自动创建 profile_name="creative" 的 ResearchTask

### ② 探测验证 (probing → collecting)

1. 前端轮询 `probe-status`
   - 社媒：爬虫采集约 20 条，跳过评论，LLM 打标（NEWS/POST 分析链）
   - 新闻：`run_news_probe_task` 三渠道搜索（baidu + sogou + duckduckgo），每渠道上限 20 条，URL 去重后落库元数据，不抓全文、不打标
2. 所有任务准备就绪后后台自动运行 probe 审查
   - 社媒：规则分流 + `strategy_social_probe_review_chain`（LLM 判定模糊案例）
     - 规则层（`_auto_verdict_probe_task`）：`posts<5` / `promotion_ratio>85%` 直接 fail 并建议移除（`suggested_keyword=null`）；`deep_analyzed<8` 样本不足直接 pass 待全量验证；其余送 LLM
     - LLM 层：单任务并行评估，输入含 `top_topics[:20]`（每个话题带 `mentions + post_source_count`，帮 LLM 识别单帖垄断）
   - 新闻：`strategy_news_probe_review_chain` 对每个任务并行 LLM 评估（基于卡片 title/source/tier/snippet + 维度→研究问题映射）
   - 社媒创建 `STRATEGY_SOCIAL_PROBE_REVIEW` AnalysisJob、新闻创建 `STRATEGY_NEWS_PROBE_REVIEW` AnalysisJob，独立记录 token/cost；LLM 失败时保守判 pass + 人工核查提示
3. `all_pass` → 自动调用 approve_probe，为每个探测任务创建 phase="collect" 全量任务（社媒 + 新闻），策略 → collecting
4. `partial_pass/fail` → 用户可 `approve-probe`（跳过审查直接全量）或 `refine-probe`（batch 替换/新增/移除关键词，`refinements` 调社媒、`news_refinements` 调新闻，两个列表至少填一个，probe_round++，最多 3 轮）
   - `suggested_keyword=null` 的建议条目表示"建议移除"（平台级数据稀疏，换词也无效），refine_probe 识别后仅软删旧任务、不创建新任务
   - 系统级后处理 [`detect_and_replace_symmetry_suggestions`](../llm/chains/strategy/social_probe_review_chain.py)：检测 consumer_voice / competitive 维度的平台互补失败模式，自动合并为"统一迁移至共同平台"建议

**关键词设计原则**（三条链共享，详见各链 prompt 源文件）：

- **研究主题锚定优先于泛属性词**：品牌关键词默认采用"品牌 + 研究主题/事件锚"（如 "3M 车衣"、"索尼 降噪耳机"），不要依赖 LLM 判断品牌"广谱 vs 专精"，统一加锚即可
- **维度词汇隔离**：brand_voice / consumer_voice / competitive / media_narrative / industry 各自有严格的词汇边界
- **同维度结构语义双重一致**：同维度所有品牌关键词共享主题锚，召回数据落在同一研究主题范围，保证横向对比公平
- **情绪中立**：同维度关键词需覆盖正/中/负三类情绪表达
- **保守偏置**：存疑时判 pass，让全量阶段验证；尤其在 `deep_analyzed < 10` 或话题池被单帖垄断时

修改规则应同步三个 chain 的 prompt：[`research_design_chain.py`](../llm/chains/strategy/research_design_chain.py)（源头） → [`social_probe_review_chain.py`](../llm/chains/strategy/social_probe_review_chain.py) / [`news_probe_review_chain.py`](../llm/chains/strategy/news_probe_review_chain.py)（修复建议）。

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

三条路径，由 `strategy.output_type` 决定（用户在 confirm-research 时显式选择）。

- **主数据源（primary）**：直接注入 prompt 的切片数据
  - campaign_strategy / full_strategy 路径：`social_media`（SocialSlice，消费者声音主轴）
  - market_report / full_strategy 路径：`news_media`（NewsSlice，媒体视角主轴）
- **行业研究（research）**：Research Agent 自动搜索分析，注入 `{research_findings}` 占位符（无结果时优雅降级为 ""）
- **创意研究（creative_research）**：campaign_strategy / full_strategy 专属，搜索数英/广告门/SocialBeta，注入 `{creative_references}` 占位符

#### campaign_strategy 路径（Insight → Brand Role → Big Idea）

Insight → Brand Role → Big Idea，层层递进（第 1/2/3 层）。主数据源 = social_media（`load_strategy_inputs`），同时通过 `_format_news_media_section` 将新闻切片作为补充段落注入 `{news_media_section}`（可选上下文）。行业研究注入 `{research_findings}`，创意研究注入 `{creative_references}`（Brand Role ~400 tokens 排除法差异化；Big Idea ~800 tokens 完整版图 + 白空间）。

#### market_report 路径（Agenda Map → Landscape → Strategic Brief）

- **Agenda Map（媒体议程图，第 1 层）**：主数据源 = news_media（`load_strategy_news_inputs`）。基于 NewsSlice 的 tagging/insight 产出 narrative_map / agenda_battles / media_voice_patterns / attention_gaps。credibility=high 必须有 tier1+tier2 支撑。禁止引入消费者声音（那是 campaign_strategy 路径）。
- **Landscape（竞争格局，第 2 层）**：输入 = Agenda Map 结果 + 原始 news slices。产出 players（role: target/competitor/context，media_sov_pct, media_sentiment）/ positioning_map（LLM 自选 x/y 轴）/ discourse_battles（必须 ref `agenda_map_battle_ref`）/ market_dynamics。
- **Strategic Brief（战略简报，第 3 层）**：输入 = Agenda Map + Landscape（**禁止引入新数据**）。产出 executive_summary / strategic_priorities（每条必须 answer ≥1 research_question + evidence_refs 指向 agenda_map/landscape 字段）/ market_opportunities / risks_and_threats / recommended_positioning（proof_points 通过 `agenda_map_narrative_ref` 回链上游叙事）。**full_strategy 不支持生成 Strategic Brief**（返回 409）。

#### full_strategy 路径（Agenda Map → Landscape → Insight → Brand Role → Big Idea）

顺序执行两条路径：先完成 market_report 前两层（Agenda Map → Landscape），再执行 campaign_strategy 三层（Insight → Brand Role → Big Idea）。Insight 阶段以 `landscape_result` JSON 作为 `{news_media_section}` 注入，取代原始 news slices，让消费者洞察有完整的竞争格局背景。状态在 landscape_done 后保持不动，直到 Big Idea 完成跳至 completed。级联清空：重新生成 Agenda Map 或 Landscape 会同时清空 insight/brand_role/big_idea_result。

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
    "industry_research": <bool>
  }
}
```

- `primary` 决定"走哪条产出路径"（campaign_strategy / full_strategy vs market_report）
- `research` 是行业研究视角（Research Agent），与 primary 在分析权重上平等，但不驱动路径选择

前端 `DataProvenanceBadge` 组件据此展示数据来源。`AnalysisJob.source_count` 取主数据源对应的切片数（campaign_strategy → social 切片数；market_report → news 切片数）。

## LLM Chain

`llm/chains/strategy/` 下按路径分 `shared/` / `brand_strategy/` / `market_report/` 三个子目录（目录名保持不变，仅 output_type 值改为 campaign_strategy）。

| Chain | 角色 | 触发时机 | 路径 |
|-------|------|---------|------|
| brief_parser_chain | Brief 摄入 + 四渠道分发判断（social_media / news_media / industry_research / creative_research） | 新建策略时（`parse-brief` 端点） | shared |
| research_design_chain | 研究规划师（产出社媒/新闻 data_plan，不含 industry_research） | ① | shared |
| strategy_social_probe_review_chain | 社媒数据质检员 | ② | shared |
| strategy_news_probe_review_chain | 新闻数据质检员（单任务并行） | ② | shared |
| coverage_check_chain | 覆盖度验证 | ③ | shared |
| insight_chain | 洞察分析师（第 1 层） | ④ | campaign_strategy / full_strategy |
| brand_role_chain | 品牌角色策略师（第 2 层） | ④ | campaign_strategy / full_strategy |
| big_idea_chain | 创意总监（第 3 层） | ④ | campaign_strategy / full_strategy |
| agenda_map_chain | 媒体议程图（第 1 层） | ④ | market_report / full_strategy |
| landscape_chain | 竞争格局（第 2 层） | ④ | market_report / full_strategy |
| strategic_brief_chain | 战略简报（第 3 层，只消费前两层） | ④ | market_report（full_strategy 不支持） |

所有 stage chain 都注入 `research_design` 中的 research_questions 作为分析上下文。`research_findings.py` 提供 per-stage formatter 函数，按 token 预算从 ResearchTask.result_data 提取并格式化行业研究数据注入 `{research_findings}`，以及 `format_creative_for_brand_role` / `format_creative_for_big_idea` 注入创意研究数据 `{creative_references}`。campaign_strategy chain 通过 `_format_news_media_section` 把新闻切片作为补充段落注入；market_report Agenda Map chain 直接消费 `load_strategy_news_inputs` 加载的 NewsSlice 作为主数据源。

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

## 定时任务（APScheduler）

所有任务定义于 `strategies/tasks.py`，由 `scheduler.py` 注册到 FastAPI asyncio 事件循环。

| Job ID | 函数 | 间隔 | 职责 |
|--------|------|------|------|
| `strategy_probe` | `check_probing_strategies` | 2 分钟 | 扫描 `status=probing` 的策略，所有探测任务（社媒 + 新闻）均达到终态后自动触发 LLM probe review |
| `strategy_collection` | `check_collecting_strategies` | 2 分钟 | 扫描 `status=collecting` 的策略，所有全量任务完成且有分析结果后自动创建切片 + 覆盖度验证 |
| `news_task_watchdog` | `reset_stuck_news_tasks` | 5 分钟 | 将策略新闻任务（probe + collect）中 `running`（Worker 崩溃）或 `pending`（Worker 宕机未消费）超过 20 分钟的记录标记为 `failed`，防止策略永久卡住 |

### 终态定义

- **社媒探测任务**：`has_analysis=True`（LLM 已完成打标）
- **新闻探测任务**：`status in {"completed", "failed"}`（completed=采集成功；failed=失败或被 watchdog 回收）
  - failed 不阻塞流程——probe review chain 会对失败任务保守判 pass 并标注"人工核查"

### 卡死恢复流程

Celery Worker 崩溃/宕机 → 新闻任务停留在 `running` 或 `pending` → watchdog 在任务创建 20 分钟后标记 `failed` → `check_probing_strategies` 在下一个 2 分钟周期检测到所有任务终态 → 自动触发 LLM 审查 → 策略恢复正常流程。全程无需人工干预。

## Important Notes

- Strategy 的社媒切片（SocialSlice）与新闻切片（NewsSlice）均通过 `monitor_id` 隐式关联（`SocialSlice.monitor_id == strategy.social_monitor_id` / `NewsSlice.monitor_id == strategy.news_monitor_id`），无显式关联表；`service._load_strategy_slice_summaries` / `_count_strategy_slices` 统一查询入口
- `_create_auto_slices` 按 `slice_blueprint` 自动创建：社媒维度 → SocialSlice，新闻维度 → NewsSlice，互不侵入
- `confirm_research` 按渠道分别创建 SocialMonitor / NewsMonitor（同渠道所有任务共享一个 Monitor）+ 条件创建 ResearchTask（brand_brief.channel_plan 含 `industry_research` 或 `creative_research` 渠道时）
- `_task_dimension_map` / `_news_task_dimension_map` 存在 `research_design` 中，分别记录社媒 / 新闻 task_id → dimension_name 映射，供 probe 审查注入研究问题 + 自动建切片使用
- `probe-status` 和 `collection-status` 是轮询端点，全部完成后自动触发下游逻辑（LLM 审查/建切片/覆盖度验证）；两个端点同时返回 `industry_research` 和 `creative_research` 状态（ResearchTask 进度，不阻塞主流程）
- Research Agent 通过 `research_tasks.strategy_id` FK 关联策略，不在 Strategy 表上加冗余字段。`_retrieve_research_findings` 读取最新已完成的 profile_name="industry" ResearchTask；`_retrieve_creative_research_findings` 读取 profile_name="creative" ResearchTask
- 新闻 insight 粒度：独立监测和策略研究都通过 NewsSlice 切片触发 insight（按 blueprint 条目分组新闻任务创建切片），采集阶段仅做 tagging 不做 insight
- 新闻搜索渠道：baidu / sogou / duckduckgo（默认三渠道）+ wechat_mp（可选，通过搜狗微信专用入口）；source_tier 分层：tier1(权威) / tier2(行业) / tier3(其他) / wechat_mp(公众号)
- `output_type` 由用户在 confirm-research 时**显式选择**，前端 `ResearchPlanEditor` 根据 data_plan 的渠道组成阻塞不合法的组合（campaign_strategy 需含 social_media 维度；market_report 需含 news_media 维度；full_strategy 需同时含两者）。后端 `_validate_market_report_output_type` 在生成时二次校验
- `generate_brand_strategy_stage` 和 `generate_market_report_stage` 都遵循**下游级联清空**语义：重新生成 Insight / Agenda Map 会清空下游结果 + 回退状态到 `ready`；重新生成 Brand Role / Landscape 会清空 Big Idea / Strategic Brief；full_strategy 重生成 Agenda Map / Landscape 还会同时清空 insight/brand_role/big_idea_result
- `edit_brand_strategy_stage` 和 `edit_market_report_stage` 同样会级联清空下游结果，避免上下游不一致
- Word 导出依赖 `python-docx`
