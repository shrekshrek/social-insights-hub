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
| POST | `/strategies/{id}/generate/{insight,brand-role,big-idea}` | campaign_strategy / full_strategy 路径：生成对应阶段（brand-role / big-idea body 可选 `tension_ids` 子集；省略=全跑模式重置所有分支，指定=仅跑选定分支保留其他） |
| PUT | `/strategies/{id}/insight` | campaign_strategy / full_strategy 路径：编辑 insight（按新 tensions 重建 pending 分支骨架） |
| PUT | `/strategies/{id}/{brand-role,big-idea}` | 按分支编辑（body 必填 `tension_id`） |
| POST | `/strategies/{id}/branches/select` | 选定 brand_strategy 分支（设 selected=true，影响导出） |
| POST | `/strategies/{id}/branches/regenerate-{brand-role,big-idea}` | 单分支重生成（仅刷新指定 tension 的层） |
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
  - campaign_strategy 路径：`insight_result`（含多 tensions） + `brand_strategy_branches`（多分支：每 tension 一个独立 brand_role + big_idea 路径，结构 `[{tension_id, tension_summary, brand_role, big_idea, selected, status, error_message?}]`）
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
   - 行业/创意研究**不在此处启动**：等到 `approve_probe` 探测通过、进入 collecting 时再起，避免方向被 probe review 否决时浪费 Tavily 调用，并保证研究主题基于稳定后的 brief（详见 ③ 数据就绪）

### ② 探测验证 (probing → collecting)

1. 前端轮询 `probe-status`
   - 社媒：爬虫采集约 20 条，跳过评论，LLM 打标（screening + deep_posts 分析链）；**聚合走 probe_lite 轻量路径**（[`aggregation/probe_lite.py`](../social_media/analysis/celery_tasks/aggregation/probe_lite.py)，纯 SQL/Python，不调 entity/opinion LLM 归一化，~5s），只产出 probe review chain 需要的 4 个字段（posts_count / deep_analyzed / entity_match / top_topics / promotion_ratio）；phase 推进到 collect 后完整 aggregation 覆写 `task.analysis_result`
   - 新闻：`run_news_probe_task` 双渠道搜索（baidu + sogou），每渠道上限 20 条，URL 去重后落库元数据，不抓全文、不打标

   **社媒 vs 新闻 failed 语义不对称**（v2026.04 起）：
   - 社媒 `_PROBE_OK_TERMINAL_STATUSES = {probe_ready, approved, completed}`——**failed 不是终态**，`has_analysis` 恒为 False，`all_analyzed` 永远停留在 false，probe review 不触发。失败任务的两个常用出口：
     1. **等自愈**（默认路径）：agent 启用 `enable_checkpoint=1` 的 auto_retry 拿到数据 → 上传走 [`agent/service.py:_validate_upload_status`](../agent/service.py) 的 failed 白名单 → status 推进到 probe_ready/completed → 进入终态 → 由前端 10s 轮询或 APScheduler `strategy_probe`（2 min）触发审查
     2. **手动删除**：用户去 `/social-media/monitors/{id}` 任务列表，按 `phase=probe` 筛选后删除该任务（永久放弃此关键词×平台组合）
   - 新闻 `_NEWS_PROBE_TERMINAL = {completed, failed}`——**failed 视为终态**，由 `strategy_news_probe_review_chain` 保守判 pass + 标注"人工核查"。理由：新闻走 Celery push 模型，**无 retry 机制**，等待无意义；用户出口与社媒不同，靠审查链路标注降级处理
   - 设计意图：让"等待"对应有 retry 通道的渠道，对没有的渠道走"标注降级"，不强迫用户为单点失败一直等下去
   - **`approve_probe` 端点不算常用出口**：当前 UI 的"忽略问题，继续采集"按钮 gate 在 `probe_review_result` 上，方案 B 下 review 不会触发 → 按钮在 failed 阻塞场景下不显示。端点本身仍可被直接调用（API 层兜底），但**不是用户可达的 UI 出口**——不要在用户文档/帮助里把它列为推荐流程
2. 所有任务准备就绪后后台自动运行 probe 审查
   - 社媒：规则分流 + `strategy_social_probe_review_chain`（LLM 判定模糊案例）
     - 规则层（`_auto_verdict_social_probe_task`）：`posts<5` / `promotion_ratio>85%` 直接 fail 并建议移除（`suggested_keyword=null`）；`deep_analyzed<8` 样本不足直接 pass 待全量验证；其余送 LLM
     - LLM 层：单任务并行评估，输入含 `top_topics[:20]`（每个话题带 `mentions + post_source_count`，帮 LLM 识别单帖垄断）
   - 新闻：`strategy_news_probe_review_chain` 对每个任务并行 LLM 评估（基于卡片 title/source/tier/snippet + 维度→研究问题映射）
   - 社媒创建 `STRATEGY_SOCIAL_PROBE_REVIEW` AnalysisJob、新闻创建 `STRATEGY_NEWS_PROBE_REVIEW` AnalysisJob，独立记录 token/cost；LLM 失败时保守判 pass + 人工核查提示
3. `all_pass` → 自动调用 approve_probe，**社媒任务原地推进 phase=probe → collect**（同一 SocialTask 记录承载两个阶段，task_id 不变；爬虫侧通过相同 cloud_task_id 自动续采 probe 阶段的 checkpoint，避免重复抓 probe 已采的笔记）；新闻任务仍创建独立 collect NewsTask（新闻走 Celery push 模型，无 checkpoint 复用需求）；策略 → collecting
4. `partial_pass/fail` → 用户可 `approve-probe`（跳过审查直接全量）或 `refine-probe`（batch 替换/新增/移除关键词，`refinements` 调社媒、`news_refinements` 调新闻，两个列表至少填一个，probe_round++，最多 3 轮）
   - `suggested_keyword=null` 的建议条目表示"建议移除"（平台级数据稀疏，换词也无效），refine_probe 识别后仅软删旧任务、不创建新任务
   - 系统级后处理 [`detect_and_replace_symmetry_suggestions`](../llm/chains/strategy/social_probe_review_chain.py)：检测 consumer_voice / competitive 维度的平台互补失败模式，自动合并为"统一迁移至共同平台"建议

**关键词设计原则**（三条链共享，详见各链 prompt 源文件）：

- **研究主题锚定优先于泛属性词**：品牌关键词默认采用"品牌 + 研究主题/事件锚"（如 "3M 车衣"、"索尼 降噪耳机"），不要依赖 LLM 判断品牌"广谱 vs 专精"，统一加锚即可
- **维度词汇隔离**：brand_voice / consumer_voice / competitive / media_narrative / industry 各自有严格的词汇边界
- **维度归属唯一性**：主品归 consumer_voice、竞品归 competitive，**同一品牌不在两个维度的 keywords 中重复出现**；维度命名应只反映单一 dimension type（dimension_name 与 RQ.dimension 一一对应），避免"主品+竞品塞同一维度"导致重复采集
- **评估维度 ≠ 采集主题**：brief_parser 以 `(评估维度：X、Y、Z)` 标注的词是**分析框架**，归属于 RQ 表述 + 切片分析阶段（从 UGC 提取），**禁止作 keyword 主题或附加词**；keyword 一律使用统一主题锚（品类/事件/场景/趋势）
- **同维度结构语义双重一致**：同维度所有品牌关键词共享主题锚，召回数据落在同一研究主题范围，保证横向对比公平
- **情绪中立**：同维度关键词需覆盖正/中/负三类情绪表达
- **判定核心：实体路径 + 话题路径双信号**——probe 是任务级简易聚合（top_topics 来自 general_opinions、target/competitor entities 来自 entities），下游全量阶段才会跨任务汇总到 slice。判定标准是「该任务对汇总有无贡献」而非「该任务自己能否回答 RQ」。两条独立路径任一有效即 pass：①实体路径 `subject_match` / `competitor_match`（识别实体命中 slice_blueprint 的 expected_subjects/competitors）；②话题路径 `relevant_source_posts ≥ 2`（相关泛话题去重后源帖数）。**双路径均失败才 fail**——top_topics 空但 entities 命中 expected_subjects 是正常 pass（聚焦实体讨论，泛观点本就不该有）。`deep_analyzed < 5` 兜底 pass + 标注。详见 `social_probe_review_chain` SINGLE_TASK_SYSTEM_TEMPLATE「判定规则」

修改规则应同步三个 chain 的 prompt：[`research_design_chain.py`](../llm/chains/strategy/research_design_chain.py)（源头） → [`social_probe_review_chain.py`](../llm/chains/strategy/social_probe_review_chain.py) / [`news_probe_review_chain.py`](../llm/chains/strategy/news_probe_review_chain.py)（修复建议）。

### ③ 数据就绪 (collecting → ready)

0. 进入 collecting 时（`approve_probe` 内 `strategy.status = "collecting"` 之后）由后端自动启动 Research Agent 任务，与全量采集并行：
   - 行业研究：`brand_brief.channel_plan` 含 `industry_research` 渠道时创建 profile_name="industry" 的 ResearchTask；query=channel_brief，context=analysis_goal，研究问题由 Planner 自行生成
   - 创意研究：output_type ∈ {campaign_strategy, full_strategy} 且 `brand_brief.channel_plan` 含 `creative_research` 渠道时创建 profile_name="creative" 的 ResearchTask（搜集竞品 Campaign 案例）
   - 失败仅日志告警，不阻塞 collecting 推进；产出阶段 `_retrieve_research_findings` / `_retrieve_creative_research_findings` 找不到已完成 ResearchTask 时优雅降级为空，注入 `{research_findings}=""` / `{creative_references}=""`
   - 幂等：`approve_probe` 入口对 status >= collecting 早返回，避免重复创建
1. 前端轮询 `collection-status`，爬虫采集全量数据（40 条 + 评论）
2. 所有全量任务分析完成后自动按 slice_blueprint 创建切片（`_create_auto_slices`）
   - 社媒：按维度分组任务 → `create_monitor_slice`（同步 Stage1）→ 派发 Celery 跑 Stage2/Stage3
   - 新闻：按维度分组任务 → `_create_strategy_news_slice` 仅创建 NewsSlice 行（status=pending）→ 主事务 commit 后派发 `news_media.run_news_slice_insight` Celery 任务异步跑 insight；这样避免 LLM 长事务持有 INSERT 不 commit、其他事务读不到该行导致重复建切片
   - 每个 blueprint 条目可产生 0-1 个 SocialSlice + 0-1 个 NewsSlice
   - **幂等性**：`_create_auto_slices` 按 `(monitor_id, slice name)` 跳过已存在切片，支持 polling/scheduler 并发触发或上轮部分失败补建；scheduler 额外用 `_slice_creation_in_progress` 进程内 set 与 polling 互斥
3. **"切片完成" = Stage2 完成**（聚合 + 实体/观点归一 + layers 构建）——此时 `SocialSlice.status="completed"`，与 NewsSlice 语义对齐。Stage3 的 3 报告是独立附加产出，不阻塞策略推进、不参与下游 chain
4. 所有社媒切片 Stage2 + 所有新闻切片 insight 到终态（completed/failed/skipped）后，由 `_try_advance_to_ready` 跑 `coverage_check_chain`（只消费 `status=completed` 的切片）
   - 触发来源：①`get_collection_status` 端点（前端 15s 轮询，近实时）；②APScheduler `strategy_collection` job（2min 兜底，前端停轮询时不被卡住）
   - **判定逻辑**：per-RQ 三态判定 `covered / partial / uncovered`，基于切片量化指标（`mentions` + `source_count` + `sentiment`）。`source_count ≥3` 即视为可靠信号（统计上"互相佐证"最低线，避免单帖偏见 / 双帖巧合）；`source=1-2` 判 partial；完全无相关命中判 uncovered。`overall_ready=true` 当且仅当所有 `priority=high` 的 RQ ∈ {covered, partial}。warnings 字段承载跨 RQ 共性诊断（如"slice X 数据稀疏，影响 rq2/rq3"）
5. `overall_ready=true` → 状态 → ready
6. 用户可 `adjust-slices` 微调切片配置（触发重新验证）

### ④ 产出生成 (ready → completed)

三条路径，由 `strategy.output_type` 决定（用户在 confirm-research 时显式选择）。

- **主数据源（primary）**：直接注入 prompt 的切片数据
  - campaign_strategy / full_strategy 路径：`social_media`（SocialSlice，消费者声音主轴）
  - market_report / full_strategy 路径：`news_media`（NewsSlice，媒体视角主轴）
- **行业研究（research）**：Research Agent 自动搜索分析，注入 `{research_findings}` 占位符（无结果时优雅降级为 ""）
- **创意研究（creative_research）**：campaign_strategy / full_strategy 专属，搜索数英/广告门/SocialBeta，注入 `{creative_references}` 占位符

#### campaign_strategy 路径（Insight → Brand Role → Big Idea，多分支并行）

Insight → Brand Role → Big Idea，层层递进（第 1/2/3 层）。主数据源 = social_media（`load_strategy_inputs`），同时通过 `_format_news_media_section` 将新闻切片作为补充段落注入 `{news_media_section}`（可选上下文）。行业研究注入 `{research_findings}`，创意研究注入 `{creative_references}`（Brand Role ~400 tokens 排除法差异化；Big Idea ~800 tokens 完整版图 + 白空间）。

**多分支架构（v2026.05）**：Insight 阶段产出多个 social_tensions 后，Brand Role 与 Big Idea 不再产出单一结论，而是**为每个 tension 生成一条独立的 brand_role + big_idea 分支**：

- 数据载体：`strategy.brand_strategy_branches: list[{tension_id, tension_summary, brand_role, big_idea, selected, status, error_message?}]`
- **分支骨架预创建**：Insight 生成或编辑后立刻调 `_ensure_branches_skeleton` 把分支按 tensions 数初始化为 `status="pending"` + brand_role/big_idea = null。前端因此始终能列出分支供用户多选（无需读 `insight_result.social_tensions` 做 fallback）
- 调度：`generate_brand_role` / `generate_big_idea` 用 `asyncio.gather` 并行调用每个分支的 worker（`_run_brand_role_for_one_branch` / `_run_big_idea_for_one_branch`），不共享 DB session；单分支失败不影响其他分支（`status="failed"` + `error_message` 写回该分支，整体仍 commit）
- **生成模式（全跑 vs 子集）**：两个 generate 端点 body 接受可选 `tension_ids: list[int] | None`：
  - `tension_ids=None` / 省略：**全跑模式**——`generate_brand_role` 重置所有分支 brand_role/big_idea/selected/status 后并行跑全部；`generate_big_idea` 对所有 brand_role 已完成的分支跑
  - `tension_ids=[...]`：**子集模式**——仅清空指定分支并跑它们，未指定的分支完全不动（含 selected）。`generate_big_idea` 子集会过滤掉未生成 brand_role 的指定项；空交集时 400
  - 子集模式语义上等价于多次 `regenerate_X_branch` 但合并为一条 AnalysisJob、一次 LLM 批次（成本/审计聚合）
- Chain 输入：`brand_role_chain` / `big_idea_chain` 接受 `selected_tension_id`，prompt 注入 `{insight_focused_section}`（仅当前 tension + 关联 opportunities）和 `{branch_brand_role_section}`（big_idea 阶段：当前分支的 brand_role），系统提示明确"当前分支独立，不要与其他分支综合"
- AnalysisJob：每次 `generate_brand_role` / `generate_big_idea` 创建**单条**跨分支 Job，`analysis_config.{branch_count, subset_mode, target_tension_ids}` 记录调用形态；token_usage / processing_time 通过 `_merge_token_usage_dicts` 聚合多分支总成本；`error_message` 写"K/N 分支生成失败"汇总
- 分支编辑：PUT `/{id}/brand-role` 与 `/{id}/big-idea` body 必填 `tension_id`；编辑 brand_role 同步清空该分支 big_idea
- 单分支重生成：POST `/{id}/branches/regenerate-{brand-role,big-idea}`（仅刷新指定 tension，不影响其他分支）；与子集模式 `generate` 等价但只跑 1 条
- 选定分支：POST `/{id}/branches/select`（设 `selected=true`，仅一条），影响 Word 导出（仅导出 selected 分支；selected 缺失时按 big_idea > brand_role > 第一条回退）
- Insight 重生成或编辑会让 tensions 变化 → `brand_strategy_branches` 整体重建为 pending 骨架（按新 tensions）；旧的所有 brand_role / big_idea / selected 状态作废
- full_strategy 路径：Agenda Map / Landscape 重生成或编辑同步清空 `insight_result + brand_strategy_branches`（用户须重新生成 insight 后骨架自动重建）

#### market_report 路径（Agenda Map → Landscape → Strategic Brief）

- **Agenda Map（媒体议程图，第 1 层）**：主数据源 = news_media（`load_strategy_news_inputs`）。基于 NewsSlice 的 tagging/insight 产出 narrative_map / agenda_battles / media_voice_patterns / attention_gaps。credibility=high 必须有 tier1+tier2 支撑。禁止引入消费者声音（那是 campaign_strategy 路径）。
- **Landscape（竞争格局，第 2 层）**：输入 = Agenda Map 结果 + 原始 news slices。产出 players（role: target/competitor/context，media_sov_pct, media_sentiment）/ positioning_map（LLM 自选 x/y 轴）/ discourse_battles（必须 ref `agenda_map_battle_ref`）/ market_dynamics。
- **Strategic Brief（战略简报，第 3 层 / 双模式终层）**：输出 executive_summary / strategic_priorities（每条必须 answer ≥1 research_question + evidence_refs 指向上游字段）/ market_opportunities / risks_and_threats / recommended_positioning。
  - **media_only 模式（market_report 路径）**：输入 = Agenda Map + Landscape（**禁止引入新市场事实**）。evidence_refs 仅允许指向 `agenda_map.*` / `landscape.*`。聚焦媒体战略 / PR 焦点，服务 PR 团队。**market_report 路径下 SB 是终层**——必须跑才能 status="completed"。
  - **comprehensive 模式（full_strategy 路径）**：输入 = Agenda Map + Landscape **+ Insight + brand_strategy_branches + creative_references**。evidence_refs 额外允许指向 `insight.social_tensions[X]` / `brand_strategy_branches[X].brand_role/big_idea`。recommended_positioning 必须整合 selected 分支的 brand_social_role.statement + big_idea。前置：至少一个分支已生成 big_idea。**full_strategy 路径下 SB 是可选终层**——不自动跑，用户在 Big Idea 完成后主动触发；status 已在 big_idea 完成时置 completed，SB 生成不再改 status。
  - 模式切换：`generation_mode` 字段记录在 result 里供前端展示「媒体视角」vs「综合视角」标签。prompt 通过 `{insight_section}` / `{brand_strategy_branches_section}` 段落是否非空自动判定模式。

#### full_strategy 路径（Agenda Map → Landscape → Insight → Brand Role → Big Idea）

顺序执行两条路径：先完成 market_report 前两层（Agenda Map → Landscape），再执行 campaign_strategy 三层（Insight → Brand Role → Big Idea）。Insight 阶段以 `landscape_result` JSON 作为 `{news_media_section}` 注入，取代原始 news slices，让消费者洞察有完整的竞争格局背景。状态在 landscape_done 后保持不动，直到任意分支 Big Idea 完成跳至 completed。级联清空：重新生成 Agenda Map 或 Landscape 会同时清空 insight_result + brand_strategy_branches。

#### NewsSlice 实体 role 归类机制（Agenda Map / Landscape 依赖）

> ADR-003 后，slice 综合分析由 `pass1_chain`（清洗归一抽取）+ `pass2_chain`（解读综述）替代旧 `insight_chain`。任务层只跑 `tagging_chain` 不再产 insight。下游策略层只消费结构化层（`descriptive` / `entities` / `quotes` / `event_clusters` / `media_landscape` / `competitive`），不消费 `page_synthesis`（LLM 散文）。

`landscape_chain` 硬规则「禁止改判 `NewsSlice.entities.role`，以输入为准」，其中「输入」来自下列**三种运行模式之一**（`_enforce_entity_roles` 代码层兜底 + `tagging_chain` / `pass1_chain` prompt 硬绑定共同保证）：

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **独立监测** | `subject == ""` | 所有实体强制 role=context，不做 target/competitor 区分 |
| **显式列表** | `subject` 非空 + `competitors` 非空 | 严格按列表归类：name==subject→target；name∈competitors→competitor；列表外强制 context |
| **自动发现** | `subject` 非空 + `competitors` 空 | LLM 自判同品类/场景级竞品归 competitor；代码仅强制 target 只能是 subject |

- **subject / competitors 的来源**：
  - 策略场景：从 `slice_blueprint[].subject` + `slice_blueprint[].competitors` 取，由 `research_design_chain` 输出时指定。每个品牌聚焦切片独立一对（与社媒 `create_monitor_slice` 对称）；大盘分析切片 subject="" → 退化到独立监测模式
  - Celery `run_news_collect_task` tagging 阶段：从 `brand_brief.subject` + 所有 `slice_blueprint[].competitors` 的 union 传入（per-article 粒度）
  - 独立 NewsMonitor 创建 slice：`subject=""` + `competitors=[]`（无策略上下文）
- **变体合并**：`_enforce_entity_roles` 在 subject + competitors 列表存在时对实体做 case-insensitive exact + substring 匹配（处理 "绿米联创Aqara" → "Aqara" 这类品牌+附加词变体），合并 mention_count / source_count 取 max / sentiment_avg 加权平均；`sentiment_by_tier` / `sentiment_weighted_by_tier` / `top_quote_ids` 由派生层（`_compute_derived` 之后的 `_attach_*` 步骤）基于合并后的 article_ids 重算
- 不再有 `competitive_landscape.entities_mentioned`（旧 schema 字段，已删）。竞争层投影通过 `competitive.players`（基于 `entities[role∈target+competitor]` 派生），含 `tier_weighted_sov` / `sentiment_by_tier` / `top_quote_ids`
- 详见 `backend/src/news_media/analysis/service.py:_enforce_entity_roles`（已从 tasks/service.py 迁移到 analysis/service.py）

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
| brief_parser_chain | Brief 摄入 + 四渠道分发判断（social_media / news_media / industry_research / creative_research）+ `platform_verdict` 分诊（sufficient / partial / insufficient，insufficient 附 `insufficient_reason` 引导至三层产出架构对应入口，详见 `docs/adr/002-output-tier-routing.md`） | 新建策略时（`parse-brief` 端点） | shared |
| research_design_chain | 研究规划师（产出社媒/新闻 data_plan，不含 industry_research） | ① | shared |
| strategy_social_probe_review_chain | 社媒数据质检员 | ② | shared |
| strategy_news_probe_review_chain | 新闻数据质检员（单任务并行） | ② | shared |
| coverage_check_chain | 覆盖度验证 | ③ | shared |
| insight_chain | 洞察分析师（第 1 层） | ④ | campaign_strategy / full_strategy |
| brand_role_chain | 品牌角色策略师（第 2 层） | ④ | campaign_strategy / full_strategy |
| big_idea_chain | 创意总监（第 3 层） | ④ | campaign_strategy / full_strategy |
| agenda_map_chain | 媒体议程图（第 1 层） | ④ | market_report / full_strategy |
| landscape_chain | 竞争格局（第 2 层） | ④ | market_report / full_strategy |
| strategic_brief_chain | 战略简报（双模式终层：media_only / comprehensive） | ④ | market_report（终层必跑）/ full_strategy（可选） |

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
- **全量任务**（phase="collect"）：采集完整数据（40 条 + 评论）
- **普通任务**：一次性采集到 max_notes_count 指定数量

**社媒单任务多阶段模型**（v2026.04 起）：
- 一条 `SocialTask` 记录承载 probe → collect 全生命周期，phase 字段标识当前阶段
- `approve_probe` 不再创建新 collect 记录，而是将 probe 任务原地推进：phase 改 collect、status 重置为 pending、task_params 覆写为全量参数；agent 重新认领同 cloud_task_id 时，通过本地 SQLite 历史 checkpoint 自动续采
- agent 端会按 cloud_task_id 聚合多次本地执行的 JSON 后整包上传，云端用 dedup 模型保证幂等：相同 post_id_on_platform / comment_id_on_platform 跳过创建，仅有真实新增数据时才触发 auto_analysis
- "清空数据" (`POST /tasks/{id}/clear-data`) 是硬删除 + 完整分析状态重置（Redis 锁 / Celery 撤销 / PostAnalysis / AnalysisJob 全清），重置后任务回 pending，agent 自动重接

## 定时任务（APScheduler）

所有任务定义于 `strategies/tasks.py`，由 `scheduler.py` 注册到 FastAPI asyncio 事件循环。

| Job ID | 函数 | 间隔 | 职责 |
|--------|------|------|------|
| `strategy_probe` | `check_probing_strategies` | 2 分钟 | 扫描 `status=probing` 的策略，所有探测任务（社媒 + 新闻）均达到终态后自动触发 LLM probe review |
| `strategy_collection` | `check_collecting_strategies` | 2 分钟 | 扫描 `status=collecting` 的策略，两阶段推进：① 任务全分析完成且切片未建 → 自动建切片；② 切片已建 + 所有切片 Stage2/新闻 insight 到终态 + coverage 未跑 → `_try_advance_to_ready` 推进到 ready |
| `news_task_watchdog` | `reset_stuck_news_tasks` | 5 分钟 | 将策略新闻任务（probe + collect）中 `running`（Worker 崩溃）或 `pending`（Worker 宕机未消费）超过 20 分钟的记录标记为 `failed`，防止策略永久卡住 |

### 终态定义

- **社媒探测任务**：`has_analysis=True` —— 即 `analysis_result is not None and status != "failed"`，或者"成功终态 + 0 帖兜底"（`status in {probe_ready, approved, completed}` AND `posts_count == 0`）。**failed 恒判 False**，强制等待 retry 或人工删除（详见 ② 探测验证 章节的"社媒 vs 新闻 failed 语义不对称"）
- **新闻探测任务**：`status in {"completed", "failed"}`（completed=采集成功；failed=失败或被 watchdog 回收）
  - failed 不阻塞流程——probe review chain 会对失败任务保守判 pass 并标注"人工核查"（与社媒不对称，因新闻无 retry 机制）

### 卡死恢复流程

**新闻任务卡死**：Celery Worker 崩溃/宕机 → 新闻任务停留在 `running` 或 `pending` → watchdog 在任务创建 20 分钟后标记 `failed` → `check_probing_strategies` 在下一个 2 分钟周期检测到所有任务终态 → 自动触发 LLM 审查 → 策略恢复正常流程。全程无需人工干预。

**社媒任务失败**：账号风控/采集异常 → task.status=failed → `has_analysis=False` 阻塞 `all_analyzed` → 等 agent `enable_checkpoint=1` 的 auto_retry 拿到数据 → 上传被 failed 白名单接受 → status 推进到 probe_ready → 进入终态 → 前端轮询或 `check_probing_strategies` 触发审查。永久失败（如账号永封）需人工去 monitor 页删除，否则策略一直卡在 probing。

## Important Notes

- Strategy 的社媒切片（SocialSlice）与新闻切片（NewsSlice）均通过 `monitor_id` 隐式关联（`SocialSlice.monitor_id == strategy.social_monitor_id` / `NewsSlice.monitor_id == strategy.news_monitor_id`），无显式关联表；`service._load_strategy_slice_summaries` / `_count_strategy_slices` 统一查询入口，**两边都查并合并**（社媒在前、新闻在后），返回的 `SliceSummary` 携带 `channel: "social" | "news"` 字段供前端按渠道分组路由（`/social-media/monitors/{m}/analysis?slice_id=...` vs `/news-media/slices/{id}`）。`StrategyListItem.slice_count` 也是两渠道之和
- `adjust_slices` 当前**仅支持调整社媒切片**——传入新闻切片 ID 会返回 409；新闻切片的 subject/competitors 影响 insight chain 的实体 role 归类，调整后需要重跑 insight，待后续支持
- `_create_auto_slices` 按 `slice_blueprint` 自动创建：社媒维度 → SocialSlice，新闻维度 → NewsSlice，互不侵入。**建完切片不直接跑 coverage_check，也不置 ready**——策略保持 `collecting`，由 `_try_advance_to_ready` 在切片 Stage2 全完成后异步推进
- `SocialSlice.status="completed"` 语义 = Stage2 完成（下游可用）；Stage3 的 3 报告失败不回退该状态，只记在 `result_data.pipeline.stage3`。`load_strategy_inputs` / `load_strategy_news_inputs` 均按 `status=completed` 过滤，Stage2 未就绪或失败的切片不会喂给策略 chain
- `confirm_research` 按渠道分别创建 SocialMonitor / NewsMonitor（同渠道所有任务共享一个 Monitor）+ 探测任务；ResearchTask 不在此处创建，移到 `approve_probe` 探测通过、进入 collecting 时启动（详见 ③ 数据就绪 第 0 步）
- `_task_dimension_map` / `_news_task_dimension_map` 存在 `research_design` 中，分别记录社媒 / 新闻 task_id → dimension_name 映射，供 probe 审查注入研究问题 + 自动建切片使用
- `probe-status` 是轮询端点，全部分析完成后触发 LLM 审查；不返回研究状态（探测阶段研究还未启动）。`collection-status` 同样是轮询端点，全部完成后触发建切片/覆盖度验证，并返回 `industry_research` / `creative_research` 状态（ResearchTask 进度，不阻塞主流程）
- Research Agent 通过 `research_tasks.strategy_id` FK 关联策略，不在 Strategy 表上加冗余字段。`_retrieve_research_findings` 读取最新已完成的 profile_name="industry" ResearchTask；`_retrieve_creative_research_findings` 读取 profile_name="creative" ResearchTask
- 新闻 insight 粒度：独立监测和策略研究都通过 NewsSlice 切片触发 insight（按 blueprint 条目分组新闻任务创建切片），采集阶段仅做 tagging 不做 insight
- 新闻搜索渠道：baidu / sogou（默认两渠道，均通过 Crawl4AI）+ wechat_mp（可选，通过搜狗微信专用入口）；source_tier 分层：tier1(权威) / tier2(行业) / tier3(其他) / wechat_mp(公众号)
- `output_type` 由用户在 confirm-research 时**显式选择**，前端 `ResearchPlanEditor` 根据 data_plan 的渠道组成阻塞不合法的组合（campaign_strategy 需含 social_media 维度；market_report 需含 news_media 维度；full_strategy 需同时含两者）。后端 `_validate_market_report_output_type` 在生成时二次校验
- `generate_*` 与 `edit_*` 都遵循**下游级联清空**语义：重新生成或编辑 Insight 会清空整张 `brand_strategy_branches`（tensions 可能变化）；重新生成 Agenda Map 会清空 landscape_result/strategic_brief_result，full_strategy 还同步清空 insight_result + brand_strategy_branches；重新生成 Landscape 会清空 strategic_brief_result，full_strategy 还同步清空 insight_result + brand_strategy_branches；分支级编辑 brand_role 仅清空**该分支** big_idea，不影响其他分支
- Word 导出依赖 `python-docx`
