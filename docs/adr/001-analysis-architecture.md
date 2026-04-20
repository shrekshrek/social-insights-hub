# ADR-001:分析架构选型

> 决策日期:2026-04-20
> 状态:**Closed(v6,4 模块全部结案)**
> 相关实验:[path-b-insight-comparison.md](../experiments/path-b-insight-comparison.md)
> Feature Inventory:[docs/inventory/](../inventory/)(4 模块完整盘点)

## 变更记录

- **2026-04-20 v1**:基于 Strategy #18(乐虎)的 n=1 实验,推出"策略研究必须重构为 LLM-native"
- **2026-04-20 v2**:Strategy #7(大魔王素毛肚)实验结果与 v1 相反,揭示 Path B 在品牌聚焦场景下会被 IP 泛化内容带偏。修订为"场景化混合架构"
- **2026-04-20 v3**:落地 Prompt Caching 修复 + 评估 harness MVP。n=2 自动评分验证手动结论(Strategy 18 Δ +0.47,Strategy 7 Δ +0.38)
- **2026-04-20 v4**:**状态降级为 Investigating**。自我反思发现证据基础不足,新增 Phase 0 Feature Inventory,原"场景化混合"方案降级为初步假设
- **2026-04-20 v5**:**Phase 0 完成**(4 份 inventory 已产出)。新增 Phase 1 架构选项分析(Options A-F + 推荐路径)
- **2026-04-20 v6(当前)**:**4 模块全部结案(Closed),ADR 状态 Closed**。
  - **社媒**:batch post_extraction PoC 验证 batch 改造速度反而慢 4 倍不值得;两层设计合理。落地 `CELERY_AI_POSTS_BATCH_SIZE` 5→15
  - **新闻**:两层 + Probe/Collect 设计精巧。落地 `_TAGGING_BATCH_SIZE` 5→10 + 迁移到根 Settings(`CELERY_AI_NEWS_TAGGING_BATCH_SIZE`)
  - **专题研究**:架构已是 LLM-native/Agentic 典范,**无改动**
  - **策略研究**:4 阶段状态机 + 3 条产出路径 + 10 链 + 级联清空 + evidence_refs 均合理。落地清理测试残留数据(5 条旧 strategy + 5 monitor + 级联 114 tasks / 3,600 posts / 34,779 comments)
  - **工程清理**:移除 3 个 dead config + 并发机制文档化(`backend/CODING_GUIDE.md`)+ 测试去硬编码化(`test_module0.py` 从 6 个 pre-existing 失败 → 18/18 全绿)
  - **总结**:经过从 v1 到 v6 的多轮迭代 + n=2 实验 + 4 份 inventory + 多个 PoC 验证,**当前架构合理,无重构必要**。后续若有新需求(如定期监控、品类扩展),在现有架构上增量叠加即可

## 证据局限性声明(必读)

本 ADR 的当前结论**不能直接支持**任何架构重构决策。已有实验的适用边界:

| 维度 | 已验证 | 未验证 |
|------|-------|-------|
| 链覆盖 | `insight_chain` 单条 | 其他 21 条 chain(screening/post_extraction/comment_extraction/4 条归一化/monitor_entity_merge/monitor_slice_reports/brand_role/big_idea/agenda_map/landscape/strategic_brief/news_tagging/news_insight/coverage_check/research agent 相关链) |
| 场景 | 策略研究的 insight 阶段 | 监测场景(dashboard/SOV/时序)、新闻监测、Research Agent 独立场景、market_report 路径、full_strategy 路径 |
| 输出依赖 | 独立的 insight_result JSON | 跨 stage 的 evidence_refs(strategic_brief 引用 landscape/agenda_map 的结构化字段)、前端 UI 组件对具体字段的绑定 |
| 工程耦合 | 无 | Celery 任务图、APScheduler 依赖、AnalysisJob source_count 语义、auto-slice 触发逻辑 |

**当前只能作为假设**,不作为决策。任何重构动作前必须完成 Feature Inventory。

## 已完成的基础设施改动(与架构决策无关)

这批改动是**纯工程债清偿**,无论后续架构走哪条路都有价值,故不受本次降级影响:

- DeepSeek Prompt Caching 验证 + 修复(命中率 93-97%)
- token_usage 增加 cache_hit_tokens / cache_miss_tokens 字段,成本按命中/未命中分别计价
- 评估 harness MVP (`src/strategies/evaluator.py`),5 维 rule-based 打分
- 诊断工具 (`scripts/experiments/verify_prompt_caching.py` / `evaluate_strategy_output.py`)

**⚠️ 待 inventory 时复审的 prompt 改动**:
- `entity_normalization_chain` 的 `{task_keywords}` 从 SYSTEM 移到 USER
- `monitor_entity_merge_chain` 的 `{subject}`/`{competitors}` 从 SYSTEM 移到 USER

这两个改动为启用 cache 而做。行为上理论无影响,但未实测输出质量。做社媒监控 inventory 时一并评估;如果这些链本来就要砍,改动白做但无害;如果要保留,需对比测试验证质量未退化

---

## 背景

系统当前对所有分析场景(社媒监控、新闻监控、策略研究、专题研究)都使用了同一套 pipeline 架构:原始数据 → screening → extraction → normalization → slice_reports → 下游分析链。这套架构继承自 pre-LLM 时代的传统 NLP pipeline 思路(NER → 归一化 → 聚合 → 报告),在 2023-2024 年的模型能力下是合理选择。

但 2026 年的现状:
- DeepSeek-V3.2 输入 ¥2/M tokens,128K 上下文;主流模型上下文普遍 1M+
- LLM 的整体 holistic reasoning 能力远超"拼装小任务"
- Pipeline 的误差会逐级累积(5 阶段 × 5% 误差 = 23% 复合误差)

基于 2026-04-20 进行的 Path B 实验(详见实验文档),pipeline 架构在**策略研究**场景下**系统性劣于 LLM-native 一次性分析**——不仅更贵(20-30x 成本),产出质量也更差(漏掉 3 个主流议题,将 29 帖小众议题捧为 Tension #1)。

但实验不能无限推广:监控类场景(需要时序聚合、SOV 查询、dashboard)**确实需要** pipeline 提供的结构化数据。

因此需要确立"分场景用不同架构"的原则,而不是一刀切推翻重建。

---

## 判断框架

不同使用场景匹配不同架构:

| 架构类型 | 适用场景 | 不适用 |
|---------|---------|------|
| **Pipeline**(结构化逐步提取) | 长期追踪、时序查询、仪表盘、SOV/情感聚合报表 | 一次性叙事洞察 |
| **LLM-native**(一把梭) | 单次分析、叙事输出、样本量可采样进上下文 | 长期聚合、精确时序对比 |
| **Agentic**(迭代智能体) | 外部动作(搜索/抓取/计算)、自适应规划、多轮精炼 | 批量确定性流程 |

核心原则:
- 用户要看**趋势/历史/仪表盘** → Pipeline
- 用户要要**洞察/策略/报告** → LLM-native
- 用户要**搜索+研究+综合** → Agentic

---

## Phase 进度

| Phase | 状态 | 产出 |
|-------|-----|-----|
| 0. Feature Inventory | ✅ 完成 | [docs/inventory/](../inventory/) 4 份 |
| 1. 架构选项评估 | 🟡 进行中(社媒结案,其他 3 模块审阅中) | 本节 |
| 2. 架构决策(Accepted) | ⏳ 待做 | - |
| 3. 执行重构 | ⏳ 待做 | - |

### 模块结案状态

| 模块 | 状态 | 结论 |
|------|-----|-----|
| **社媒监控** | ✅ **Closed** | 两层设计合理,不重构;唯一优化:`CELERY_AI_POSTS_BATCH_SIZE` 5→15 |
| **新闻监控** | ✅ **Closed** | 两层 + Probe/Collect 设计精巧,保留现状;唯一优化:`_TAGGING_BATCH_SIZE` 5→10 + 进 config |
| **专题研究** | ✅ **Closed** | 架构已是 LLM-native/Agentic 典范(LangGraph 循环 + profile 参数化 + per-stage formatter),功能合理,**无改动** |
| **策略研究** | ✅ **Closed** | 4 阶段状态机 + 3 条产出路径 + 10 条链 + 级联清空 + evidence_refs 硬引用,架构合理。唯一操作:清理测试残留数据(5 条旧 strategy + 5 个 monitor) |

### 社媒模块结案摘要(v6)

**决定的改动**:
- ✅ `.env` 改 `CELERY_AI_POSTS_BATCH_SIZE` 5→15(screening 批大小;`config.py` 的 default 保持 5 不变,仅环境变量覆盖)
- ✅ 清理 3 个 dead config(`CELERY_AI_SCREENING_CONCURRENT_STREAMS` / `CELERY_AI_DEEP_ANALYSIS_CONCURRENCY` / `CELERY_AI_COMMENTS_BATCH_SIZE`)
  - 这 3 个原本是为"按 task 类型分 queue 限流"设计,但从未实现
  - 实际并发由 docker-compose 命令 `--concurrency=100` 统一控制(100 greenlet 共享 pool)
  - 同步更新:`config.py` / `.env` / `.env.test` / `.env.example` / `.env.production*` / `tests/test_module0.py` / `backend/CODING_GUIDE.md`

**验证后放弃的改动**:
- ❌ **`post_extraction` 批处理**(5 帖/批)—— [PoC 结果](#poc-task-84--94-batch-post_extraction):质量指标过线(F1 0.68-0.82)但 wall-clock 速度慢 4 倍(60s vs 15s),容错更差(API 单次失败丢 5 帖 vs 1 帖),ROI 负
- ❌ **`comment_extraction` 批处理/全局采样** —— 同上理由,不跑 PoC 直接 skip
- ❌ **`attribute_normalization` 7→2 次合并** —— Prompt Caching 已消化大部分重复 input,真实 token 节省约 ¥0.002/task,不值得 2-3 天开发 + 质量风险
- ❌ **`opinion_normalization` 多类别合并** —— 同上
- ❌ **`entity_normalization` Review 阶段砍** —— Review 专门防"华为手机 + 华为冰箱"跨品类错误合并,砍了可能打坏下游 SOV/SWOT 精度,风险>收益

**核心判定**:
1. 两层架构(Task keyword anchor + Slice subject anchor)是**语义分治,不是冗余**,保留
2. Task 派生(IPA/ContextGraph/竞品雷达/KOL)是纯代码零 LLM 成本,**故意独立于 Slice 分析以防污染**,保留
3. 9 条 LLM 链各司其职,**没有冗余**;Prompt Caching 已自动消化 system prompt 重复开销
4. 前端 10+ 图表重度依赖结构化字段(SOV / organic/promo 分层 / SWOT / 剪刀差 等),LLM-native 一把梭**无法可靠产出精确百分比/统计量**
5. 定期监控需求(未来)通过 APScheduler 周期性创建 Task + 自动 Slice 规则可轻量支持,**现有架构天然适配**

**经过的验证**:
- 2 次 batch PoC(task 84 MFGM + task 94 宠物)见 [docs/experiments/](../experiments/)
- 2 份 feature inventory 对比([social_media.md](../inventory/social_media.md))
- 多轮架构反思和修正(v1→v6)

---

### 新闻监测模块结案摘要(v6)

**架构判定:两层设计 + Probe/Collect 两阶段,合理,保留**。

**核心观察**:
- 只 2 条 LLM 链(`NEWS_TAGGING` 逐文批量标注 + `NEWS_INSIGHT` 切片级聚合),**明显比社媒简洁**
- **Probe/Collect 两阶段设计**是独特优势:probe 阶段只搜索不抓全文不标注,低成本验证关键词;collect 阶段才做全文 + 标注
- 输出结构以 narrative 为主(自然语言),前端硬依赖字段比社媒少(~10 vs 15+)
- 数据流线性,Task 做标注 + Slice 做聚合,**不重复**

**决定的改动**:
- ✅ `_TAGGING_BATCH_SIZE` 5→10 + **从 module 常量迁移到 Settings**(`CELERY_AI_NEWS_TAGGING_BATCH_SIZE`),与社媒 `CELERY_AI_POSTS_BATCH_SIZE` 风格统一,运行时可调
- 配套更新:`config.py` 新增字段、`.env` / `.env.example` / `.env.test` / `.env.production*` 全部同步加配置
- `_PROBE_MAX_RESULTS=20` 保留为模块常量(业务策略级,非性能调优)

**评估过但不做的**:
- ❌ `NEWS_INSIGHT` 批处理/拆分:单切片一次调用已是最优,切片量小(50-100 篇),无需细拆
- ❌ probe review 链并发优化:当前每任务独立调用已用 gevent 100 并发承载
- ❌ source_tier 动态化:硬编码字典比 LLM 更稳定,规模 <500 维持现状
- ❌ 架构性重构:两层 + 两阶段已是最佳实践,无空间

**核心判定**:
1. 两层架构(Task keyword anchor + Slice subject anchor)合理,保留
2. Probe/Collect 两阶段是新闻模块独有的成本控制设计,**必须保留**
3. 2 条 LLM 链分工明确,无冗余
4. `NEWS_INSIGHT` 被"独立新闻监测"和"策略 probe review"两路复用,进一步降低架构复杂度

**与社媒的关键差异**:
- 新闻模块**天然更接近 LLM-native**(输出自由度高)
- 没有社媒的"多层归一化 + 结构化图表硬依赖"问题
- 未来若策略研究重构,新闻通过 formatter 解耦的成本远低于社媒

---

### 专题研究 (Research Agent) 结案摘要(v6)

**架构判定:已是 LLM-native/Agentic 典范,无改动**。

**核心观察**:
- **LangGraph 6 节点循环图**(plan → search → filter → fetch → analyze → evaluate → synthesize),evaluate 可回到 plan 多轮迭代
- **2 个 profile(industry / creative)参数化实现**,不是两套图,扩展性好
- **per-stage token 预算 formatter**(`research_findings.py`)按消费 stage 分层注入策略 chain,是三个上游模块里**唯一"正确姿势"的解耦**
- 无 pre-LLM 遗产,本模块没有"归一化链冗余"问题
- 并发模型与其他模块不同:**节点内并发**(analyzer 10 并发),而非任务级

**无改动理由**:
1. 架构已经是现代 Agent 范式的参考实现,不存在结构性可优化点
2. 模块有独立的 `src/research_agent/config.py` 自管 `MAX_ROUNDS=4` / `MAX_CANDIDATES_PER_ROUND=15` / `MAX_CONCURRENT_TASKS=10` 等,**保持 module-local 配置符合单体模块自洽原则**,不强行进根 Settings
3. 外部依赖(Tavily / Crawl4AI / DeepSeek)属基础设施,与本 ADR 范围无关
4. prompt 中也无破坏 Prompt Caching 前缀的动态模板(社媒 v3 做过的清理不需要在这里再做一遍)

**与社媒/新闻的架构互补**:
- Research Agent 承担**外部搜索/抓取/综合**角色,与本地数据分析(社媒/新闻)互补
- 通过 formatter 与策略研究解耦,策略 chain 不关心 Research Agent 内部实现
- **未来策略研究重构时,Research Agent 作为"已经做对了"的模板参考**

---

### 策略研究模块结案摘要(v6)

**架构判定:下游薄层 + 复杂状态机 + 跨 stage 硬引用 均合理,保留现状**。

**核心观察**:
- **4 阶段状态机**(draft → planned → probing → collecting → ready → 3 路径)有意的渐进式设计,非冗余
- **3 条产出路径**职责清晰:
  - `campaign_strategy`:消费者驱动 → Insight → Brand Role → Big Idea,服务创意 campaign
  - `market_report`:媒体驱动 → Agenda Map → Landscape → Strategic Brief,服务战略决策
  - `full_strategy`:Landscape 结构化作为 Insight 输入,让创意基于完整竞争格局背景
- **10 条 LLM 链**职责明确,无冗余:
  - `brief_parser` / `research_design` 触发时机不同(parse-brief vs design-research),不合并
  - `social_probe_review` / `news_probe_review` 语义不同,不合并
  - `coverage_check` 难以用规则替代,保留
- **Cache 前缀检查**:10 条 SYSTEM_TEMPLATE 全部静态,Prompt Caching 开箱即用
- **`evidence_refs` 硬引用**(`strategic_brief.evidence_refs` → `agenda_map` / `landscape`):不是过度工程,是让策略简报可审计、可跳转的**有价值设计**
- **级联清空语义**:数据一致性硬保证,必要

**决定的操作**:
- ✅ **测试残留数据清理**:删除 5 条旧 strategy(id 6, 7, 11, 12, 13)+ 5 个关联 social_monitor + 级联的 114 tasks / 3,600 posts / 34,779 comments / 3,533 post_analysis
  - strategy 12, 13 使用了废弃值 `output_type='insight_report'`
  - strategy 11 是未完成的 probing,其余是早期测试
  - **保留 strategy 18**(乐虎,`full_strategy` completed,Path B 实验主要 baseline)

**评估过但不做的**:
- ❌ `full_strategy` 是否应包含 `Strategic Brief`——产品决策而非技术问题,当前设计"Landscape 赋能创意"有其合理性
- ❌ 合并任何 chain——触发时机 + 输入语义不同,强行合并破坏工作流
- ❌ 砍 coverage_check_chain——难以用规则替代"研究问题是否被切片覆盖"
- ❌ 改 evidence_refs / 级联清空——二者都是数据一致性保证,改动风险大

**与其他模块的架构协同**:
- 策略研究是**下游消费者**,上游变动(社媒/新闻/专题研究)都通过稳定接口隔离
- Research Agent 的 `research_findings.py` per-stage formatter 是标杆,未来若要进一步解耦社媒/新闻可参考

---

## Phase 0 Inventory 关键结论

基于 4 份 inventory,事实基础与 v3 阶段的假设**显著不同**。核心发现:

### 结论 1:四个模块的架构成熟度差异巨大

| 模块 | 架构成熟度 | 重构门槛 |
|------|---------|------|
| 专题研究 (Research Agent) | **已是 LLM-native/Agentic**(LangGraph 循环,无 pre-LLM 遗产) | 🟢 只需调优 |
| 新闻监控 | 较轻量(2 链 + 卡片式 NewsSlice,输出半自由) | 🟡 中等 |
| 社媒监控 | 最重(9 链 + Stage 1/2/3 pipeline + 前端 10+ 图表硬依赖) | 🔴 高 |
| 策略研究 | 下游薄层(10 链 + 级联清空 + 跨 stage 硬引用) | 🔴 高(耦合约束多) |

**v3 阶段假设"社媒只需瘦身"是错的**——前端有 10+ 图表重度依赖 pipeline 产出的结构化字段(SOV / 四象限 / SWOT / 组织图)。

### 结论 2:策略研究消费上游字段比预期广

- `insight_chain` 消费 SocialSlice **18 个字段路径**(10 个必需)
- `agenda_map_chain` 消费 NewsSlice **11 个字段**
- Research Agent 通过 per-stage formatter 优雅解耦(这是唯一一个"正确姿势"的上游)

### 结论 3:跨 stage 硬引用是重构的关键约束

`strategic_brief.evidence_refs` 硬引用 Agenda Map / Landscape 的结构化字段,前端 UI 用这些 refs 做**点击跳转交互**。任何"一把梭"方案都必须复现这种跨 stage refs,否则前端跳转失效。

### 结论 4:Research Agent 是上游解耦的参考答案

它的 `research_findings.py`(per-stage token 预算 + 无结果时空串降级)是三个上游里唯一的"解耦范例"。社媒/新闻如果要向更好的架构演进,这是可参考的模式。

---

## Phase 1: 架构选项分析

基于 Phase 0 事实,列出**候选架构选项**。每个选项都会:
- 明确具体改什么、不改什么
- 评估预期成本、预期收益、主要风险
- 给出可验证的度量指标

### Option A — 只做工程优化,不改架构

**做什么**:
- 已完成:Prompt Caching 修复 + cache 成本核算 + 评估 harness
- 继续做:`attribute_normalization` 14 次合并为 1-2 次、`comment_extraction` 改采样、APScheduler 轮询间隔优化

**不做什么**:任何架构性改动(chain 拆分/合并、输出结构变更、前端契约变更)

**收益**:
- 成本降 15-25%(基于 inventory 识别的冗余)
- 前端零感知,零破坏风险
- 评估 harness 为未来决策积累真数据

**代价**:
- **不解决** Path B 实验发现的"议题重要性扭曲"问题(Strategy 18 漏掉 880 万赞议题)
- 结构化字段矩阵的"僵化感"依然存在

**风险**: 🟢 极低

**度量**:单次策略总成本从 ¥10 降到 ¥7-8;测试套件全绿。

---

### Option B — 策略 Insight 层改为"混合输入",其他不动

**做什么**:
- 仅改 `insight_chain`(campaign_strategy L1)
- 让它读**两份输入**:
  1. 现有的 SocialSlice 结构化字段(保持前端兼容)
  2. 新增的原始帖子采样(Path B 思路,~120 帖 Top engagement)
- Prompt 融合指引:结构化字段提供宏观数据,采样提供细节证据
- 保留 evidence_refs 到 post_id(前端已验证可行)

**不做什么**:
- 社媒 pipeline 不动
- 其他策略 chain(brand_role/big_idea/agenda_map/landscape/strategic_brief)不动
- 前端契约不动

**收益**:
- 直接解决 Path B 实验的核心发现
- **n=2 量化证据**:Strategy 18 改进 Δ+0.47,Strategy 7 需调 prompt(subject_focus 维度)
- 只改 1 条链,风险可控

**代价**:
- 输入量变大(~80K tokens),单次 insight 调用成本从 ¥0.09 升到 ¥0.15-0.20
- 需要 subject_type 识别 + 相关度加权采样两个前置基建

**风险**: 🟡 中等
- 主要风险:输入混合后 LLM 是否真的会"互相印证"?还是只用其中一份?需实验验证
- 次要风险:Strategy 7 类型(品牌聚焦 + IP 泛化)的 subject_focus 能否回升到 Path A 水平

**度量**:
- 评估 harness 5 维中 Overall ≥ Path A 且 subject_focus 不低于 Path A
- 盲评 5 组至少 3 组新架构胜

---

### Option C — 推广 Research Agent 的"per-stage formatter"解耦模式

**做什么**:
- 为社媒/新闻各自编写 `social_findings.py` / `news_findings.py`
- 提供 per-stage formatter 函数(类似 `research_findings.py`):
  - `format_social_for_insight(social_slice) -> str`
  - `format_social_for_brand_role(social_slice) -> str`
  - 同理新闻
- 策略 chain 改为消费 formatter 输出,不再直接读 `result_data.layers.*`
- 上游 SocialSlice/NewsSlice 结构保持不变(前端图表继续用)

**不做什么**:
- 不改上游 pipeline
- 不改前端

**收益**:
- **解耦上下游**:未来上游结构变化不影响策略 chain
- 统一三个上游的消费模式(研究 agent 已有,推广到其他两个)
- 为后续更大重构(如 Option D)铺路——有 formatter 做兼容层后,可以自由替换底层实现

**代价**:
- 纯工程改造,无质量提升
- 相当于"延迟重构"—— 没解决根本问题,只是让未来重构更容易
- 工作量约 1-2 周

**风险**: 🟢 低(纯增量,不动现有)

**度量**:
- 策略 chain 代码中不再直接引用 `result_data.layers.*` 等深层路径
- 所有策略 chain 测试通过,产出无质量变化(通过 evaluator 验证)

---

### Option D — 社媒 Stage 2 "review 阶段"精简

**做什么**:
- 保留 SocialSlice 对外的 schema
- 内部砍掉 `entity_normalization` / `monitor_entity_merge` 的第二阶段(Review)
- 保留 Merge 阶段 + Attribute/Opinion/Category 归一化(3 条)
- `monitor_slice_reports` 三份报告保留

**依据**:Inventory 显示 DeepSeek V3.2 + 改良 prompt 下,Merge 阶段的 role/parent 判定精度可能已足够,Review 的必要性待验证。

**收益**:
- 成本降 10-15%(每切片 2 次 LLM 调用)
- 对前端零影响

**代价**:
- 需要对比测试:砍 Review 后 `aligned_entities[].role/parent` 字段的准确率下降多少
- 如果精度下降 >5%,需回退

**风险**: 🟡 中(有明确回退路径)

**度量**:
- 抽 20 个已完成 SocialSlice 做对比测试,准确率差异 <5% 则通过
- 下游(insight_chain)的 sov_ranking 结果不变

---

### Option E — 新闻 `news_insight_chain` 改 "全原文 LLM-native"

**做什么**:
- 放弃"基于 tagging 聚合"的两步流程
- 改为:一次性把 N 篇原文(带元数据)塞进 LLM,直接产出 narratives + entities + coverage
- `news_tagging_chain` **保留**供前端过滤(relevance/sentiment)和 probe review 使用

**依据**:Inventory 显示新闻 insight 输出本就接近自然语言(narratives 是叙事文本),重构门槛低。

**收益**:
- 成本降低(从 N 次 tagging + 1 次 insight → 只做 insight)
- 理论上能捕捉到 tagging 阶段遗漏的语境
- 新闻量小(50-100 篇),上下文塞得下

**代价**:
- 失去"先分开标注再聚合"的清晰度
- 需要测试 insight 产出质量是否下降

**风险**: 🟡 中

**度量**:
- 同一批新闻的 narratives/entities 质量对比,新架构胜出 ≥60%
- 策略下游消费无退化

---

### Option F — 激进重构:全部 LLM-native,Pipeline 只做"post-hoc 结构化"

**做什么**:
- 所有分析都走 LLM-native 一把梭
- Pipeline 降级为"从 LLM 自然语言输出中提取结构化字段"的 post-hoc 层
- 前端图表从 post-hoc 提取结果取数

**为什么这是一个 Option**:这是 v1-v3 阶段我多次倾向推的方向,必须列出来对比评估。

**代价**:
- **工作量巨大**(估 3-6 个月)
- 前端 15+ 组件可能需要调整渲染逻辑
- organic/promo 分层依赖 `spam_score`,post-hoc 提取困难
- 级联清空语义需要重新设计
- 跨 stage evidence_refs 需要让 LLM 自己生成符合 schema 的 refs(易幻觉)

**风险**: 🔴 极高

**度量**:
- 需要全套回归测试
- 前端组件测试覆盖度 >90%

**评估**:**不推荐**。Phase 0 inventory 显示 pipeline 承载的功能远比 v1-v3 阶段以为的多,激进重构的 ROI 非常差。

---

## 选项对比矩阵

| Option | 成本降幅 | 质量提升 | 风险 | 工作量 | 前端影响 |
|--------|-------|--------|-----|------|------|
| A 工程优化 | 15-25% | 无 | 🟢 低 | 1-2 周 | 无 |
| B Insight 混合输入 | -10% (反增) | 🟢 直接解决 Path B 问题 | 🟡 中 | 2-3 周 | 轻微(evidence_refs 展示) |
| C Formatter 解耦 | 0% | 无(结构优化) | 🟢 低 | 1-2 周 | 无 |
| D Stage2 Review 砍 | 10-15% | 无 | 🟡 中 | 1 周 | 无 |
| E 新闻 insight 一把梭 | 10% | 可能改善 | 🟡 中 | 1 周 | 无 |
| F 全部 LLM-native | 不确定 | 不确定 | 🔴 高 | 3-6 月 | 大量 |

---

## 推荐路径

**不是单一 Option,而是叠加执行,每步有量化验收**:

### 阶段 1(本周~下周)— Option A 继续

- 跑 `attribute_normalization` 合并的对比测试
- 评估 `comment_extraction` 采样方案可行性
- 扩展评估 harness 到 brand_role / big_idea 产出

**验收**:单次策略成本降到 ¥7-8,所有回归测试绿

### 阶段 2(~1 个月)— Option B Beta

- 实现 subject_type 识别 + 相关度采样(前置基建)
- `insight_chain` Beta 版:双路径混合输入
- 扩展 n=5 实验 + 策略师盲评

**验收**:
- 评估 harness 5 维中 Overall 和 subject_focus 都不退化
- 盲评 5 组 3+ 胜
- 通过则做正式切换,未通过则 Option B 撤回

### 阶段 3(~1 个月)— Option C Formatter 解耦

- 前提:阶段 2 有产出(无论 Beta 是否通过)
- 为社媒/新闻编写 formatter
- 策略 chain 改为消费 formatter(保持行为不变)

**验收**:策略 chain 代码不再引用深层路径,产出质量不变

### 阶段 4(~1 个月,并行)— Option D / E 并行探索

- Option D(社媒 Stage2 精简)和 Option E(新闻 insight 一把梭)可并行
- 各自做 A/B 对比测试

**验收**:各自收益 ≥ 预期,回退路径明确

### 明确不做:Option F

Phase 0 已证明 F 的 ROI 太差。**除非出现颠覆性证据,否则不启动 F**。

---

## Phase 2 准备(何时可以转 Accepted?)

本 ADR 可从 Investigating 升级到 Accepted 的条件:

1. ✅ Phase 0 完成(已达成)
2. 🟡 Phase 1 完成(本文档,待用户复审)
3. ⏳ **阶段 2 Option B Beta 跑完**(含 n=5 + 盲评结果)
4. ⏳ 推荐路径得到用户确认

条件 3 是硬指标——用 Option B 的实验结果反向验证 Phase 1 分析是否靠谱。

---

## 不做什么(边界声明)

为防止过度反应,以下**明确不在本 ADR 范围内**:

1. **不推翻监控场景的 pipeline**。监控有结构化数据的真实需求,pipeline 是对的
2. **不重构 brief_parser / research_design / probe_review 等早期链**。它们本就是单 LLM 调用,不是 pipeline
3. **不废弃 AnalysisJob / slice 等数据模型**。这些是监控场景的基础,且可作为策略 LLM-native 的辅助输入
4. **不更换 LLM 模型**。DeepSeek V3.2 性价比与能力已够用,模型不是瓶颈

---

## 评估标准

重构成功与否的衡量(所有改动都应对标)。已在 `src/strategies/evaluator.py` 中自动化(见 § 评估 harness)。

1. **成本**:单次策略研究的 LLM+API 总成本 ≤ 原来的 30%
2. **质量**:5 组盲评中新架构胜率 ≥ 60%(下调自 80%,因场景差异真实存在)
3. **覆盖度 (thematic_engagement)**:Top tensions 引用的 post 累计 engagement ≥ 总 engagement 的 30%
4. **主体聚焦度 (subject_focus)**(品牌聚焦场景专用):Top 3 tensions 中,直接围绕 subject 本体的 ≥ 2 条(而非 IP/热点泛化分析)
5. **证据可追溯 (citation_validity)**:每条 tension/opportunity 至少 2 条可验证证据(post_id 真实存在 + 内容符合描述)
6. **监控场景不退化**:dashboard / SOV / 时序查询的响应时间与准确性不变

## 评估 harness

`src/strategies/evaluator.py` 提供 5 维 rule-based 打分(0.0-1.0):

| 维度 | 权重 | 含义 |
|------|-----|------|
| `citation_validity` | 0.20 | evidence 引用的 post_id 在 DB 中真实存在的比例 |
| `thematic_engagement` | 0.30 | 引用帖子累计 engagement / monitor 总 engagement(目标 30%) |
| `evidence_density` | 0.15 | 每条结论平均 evidence 数,≥2 条满分 |
| `subject_focus` | 0.20 | 结论 statement/evidence 中提及 subject 的比例(目标 60%) |
| `completeness` | 0.15 | 必要字段(confidence/rationale/conventional_wisdom/data_reality)填充率 |

### CLI 用法

```bash
# 1) 把产出文件复制进容器
docker cp /tmp/path_b_experiment/path_b_insight.json crawler-backend-1:/tmp/path_b_18.json

# 2) 复制评估脚本进容器
docker cp scripts/experiments/evaluate_strategy_output.py crawler-backend-1:/tmp/eval.py

# 3) 评估(对比 Path A 数据库现有 insight_result vs Path B 外部 JSON)
docker-compose exec backend uv run python /tmp/eval.py \
    --strategy-id 18 \
    --path-b-json /tmp/path_b_18.json
```

### n=2 实测结果

| Strategy | Subject | Path A Overall | Path B Overall | Δ | 关键差异维度 |
|---------|--------|---------------|---------------|---|---|
| #18 乐虎(品类级) | 乐虎 | 0.485 | **0.954** | +0.469 | citation_validity +1.0,thematic_engagement +0.85 |
| #7 大魔王素毛肚(品牌聚焦 + IP) | 大魔王素毛肚 | 0.352 | 0.727 | +0.376 | citation_validity +1.0,**subject_focus -0.13**(Path A 胜出维度) |

自动评分成功捕获到 n=2 的关键分化:品牌聚焦场景下 `subject_focus` 维度 Path B 会降分,印证了需要场景化架构的判断。

### 已知限制

1. `subject_focus` 目前只做完整字符串匹配,未做 alias/语义匹配(比如 "大魔王素毛肚" 不会匹配 "大魔王")。后续可扩展为用 LLM 做语义判断或让 brief_parser 产出 aliases
2. 维度权重目前硬编码,应该按场景(category vs brand_focus)动态调整
3. 未评估"反陈词度"(需 LLM-as-judge,不在 MVP 范围)
4. 只评估 `insight_result`,其他产出类型(brand_role/big_idea/agenda_map/landscape/strategic_brief)待扩展

---

## 根本原则

本 ADR 背后的元原则:

> **分析架构的选择应由用户场景决定,而不是由工程传统决定。**

当前系统把四种性质不同的场景(监控/策略/研究/新闻)塞进同一套 pipeline,是 2023 年统一架构的遗产。2026 年的正确姿态是**四种架构并存,按场景匹配**——监控继续 pipeline,策略换 LLM-native,研究保持 agentic,新闻做轻量化。

重构不是"推翻重建",是"对症下药"。

---

## 参考

- 实验数据:[docs/experiments/path-b-insight-comparison.md](../experiments/path-b-insight-comparison.md)
- 实验脚本:[scripts/experiments/run_path_b_insight.py](../../scripts/experiments/run_path_b_insight.py)
- 相关架构文档:[docs/strategy-multi-source-architecture.md](../strategy-multi-source-architecture.md)、[docs/research-agent-design.md](../research-agent-design.md)
