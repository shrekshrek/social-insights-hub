# Feature Inventory: 专题研究 Research Agent (`src/research_agent/`)

> ⚠️ **存档（时点快照）**：本文档是 ADR-001 Phase 0 时期（2026-04）的事实盘点，仅供决策溯源，**不随代码更新**。模块现状以代码与各级 CLAUDE.md 为准（已知漂移示例：新闻链已拆 pass1/pass2 并新增 themes 议题层）。

> 盘点日期:2026-04-20
> 目的:为 ADR-001 架构决策提供事实基础。**本文档只做盘点,不下架构结论**。

## TL;DR

Research Agent 是 4 个模块里**架构最独特**的——不是 pipeline 也不是批处理,而是 **LangGraph 循环迭代 Agent**,支持多轮搜索-分析-评估-再搜索。

**关键发现**:
- **6 节点循环图**:plan → search → filter → fetch → analyze → evaluate(→ plan 循环 / → synthesize 收官)
- **2 种 profile**(industry / creative):通过参数化 prompt 和域名白名单实现,**不是两套图**
- **深度依赖外部 API**:Tavily(搜索)+ Crawl4AI(HTML→markdown)+ httpx(PDF)+ DeepSeek(LLM)
- **输出是自然语言为主**(synthesis markdown + findings_by_question),与社媒的结构化矩阵完全不同
- **无 APScheduler,无 pipeline**,纯 Celery 驱动 + 前端轮询
- **独立前端页面**+ 深度嵌入策略研究(通过 formatter 函数按 stage token 预算注入)

---

## 1. LangGraph 图结构

### 1.1 节点与边

图定义:[`src/research_agent/graph.py`](../../backend/src/research_agent/graph.py)(约 70 行)

```
┌──────┐
│plan  │ ← 起点(round=0 时生成 title/research_questions)
└───┬──┘
    ↓
┌───▼──┐
│search│ Tavily 定向搜索（双 key 自动切换）
└───┬──┘
    ↓
┌───▼──┐
│filter│ LLM 批量评分筛选 (≤15/轮)
└───┬──┘
    ↓
┌───▼──┐
│fetch │ Crawl4AI HTML / httpx PDF 抓全文
└───┬──┘
    ↓
┌───▼────┐
│analyze │ per-doc LLM 深度分析(并发 10)
└───┬────┘
    ↓
┌───▼────┐       should_continue == True
│evaluate├──────────────────────────────┐
└───┬────┘                              │
    │ should_continue == False          │
    ↓                                   ↓
┌───▼──────┐                    (回到 plan 循环)
│synthesize│
└───┬──────┘
    ↓
   END
```

### 1.2 每节点详情

| 节点 | 文件 | 输入 state | 输出 state | LLM | 外部 API |
|------|------|---------|---------|-----|--------|
| `plan` | [`nodes/planner.py`](../../backend/src/research_agent/nodes/planner.py) | query, context, research_questions, profile_name | search_plan, title(round=0), round, research_questions(round=0) | ChatDeepSeek(注入 profile.planner_context) | 无 |
| `search` | [`nodes/searcher.py`](../../backend/src/research_agent/nodes/searcher.py) | search_plan, profile_name, findings, selected | candidates(跨轮累积) | 无 | **Tavily**(TAVILY_API_KEY 主 + _2 备用双 key 切换；两个都耗尽抛 `TavilyQuotaExhaustedError`) |
| `filter` | [`nodes/filter.py`](../../backend/src/research_agent/nodes/filter.py) | candidates, profile_name, selected(上轮) | selected(本轮 ≤15) | ChatDeepSeek(批量评分) | 无 |
| `fetch` | [`nodes/fetcher.py`](../../backend/src/research_agent/nodes/fetcher.py) | selected, profile_name | documents(跨轮累积) | 无 | **Crawl4AI**(HTML)/ **httpx**(PDF / 直下) |
| `analyze` | [`nodes/analyzer.py`](../../backend/src/research_agent/nodes/analyzer.py) | documents, research_questions, profile_name | findings(跨轮累积) | ChatDeepSeek(per-doc,**并发 10**) | 无 |
| `evaluate` | [`nodes/evaluator.py`](../../backend/src/research_agent/nodes/evaluator.py) | findings, research_questions, selected, round | evaluation{questions_covered, gap_questions, tier1_source_count, should_continue} | 无(纯规则) | 无 |
| `synthesize` | [`nodes/synthesizer.py`](../../backend/src/research_agent/nodes/synthesizer.py) | findings, research_questions, profile_name | findings_by_question, synthesis, coverage, information_gaps | ChatDeepSeek(一次性综合) | 无 |

### 1.3 循环机制

**条件边**:`evaluate` → `plan`(循环)或 `synthesize`(收官)

**`should_continue = True` 的触发条件**(`evaluator.py` 的 `_should_continue`):
1. `gap_questions` 非空(至少一个问题"未覆盖")——判定标准:该问题下少于 2 条实质性来源
2. `current_round < max_rounds`(默认 3)
3. 本轮 `selected` 非空(至少筛选到一条候选)

**最大轮数**:`config.py` 定义 `MAX_ROUNDS=4`(实际使用默认 3)

### 1.4 State 设计

跨轮次行为:
- **累积字段**(`operator.add` reducer):`documents`, `findings`, `token_usage_records`
- **每轮替换**:`candidates`, `selected`, `search_plan`, `evaluation`, `round`

---

## 2. 两种 Profile:industry vs creative

### 2.1 通过参数化实现(不是两套图)

所有节点**代码统一**,差异全部通过 `state["profile_name"]` 从 `profiles/` 目录加载对应配置:

```python
profile = get_profile(state["profile_name"])
# profile.planner_context  - planner system prompt 片段
# profile.analyzer_prompt  - analyzer 的完整 prompt
# profile.synthesizer_prompt - synthesizer prompt
# profile.filter.system_prompt / tier1_domains / tier2_domains / min_llm_score
# profile.fetcher.max_content_len / landing_page_max_len
# profile.search_fallback_domains  - Tavily include_domains 兜底
```

### 2.2 Industry Profile

[`profiles/industry/`](../../backend/src/research_agent/profiles/industry/)

- **定位**:行业/市场/政策研究,服务策略研究的 `{research_findings}` 注入
- **Fallback 域名**(tier1 权威源):
  - 政府:`stats.gov.cn`, `ndrc.gov.cn`
  - 国际:`oecd.org`, `ourworldindata.org`, `pewresearch.org`, `datareportal.com`
  - 媒体:`36kr.com`, `latepost.com`
- **Planner prompt**: 强制关键词含"报告/白皮书/report",生成 5-8 个关键词
- **Filter 规则**: `min_llm_score=0.6`(高门槛)
- **Analyzer prompt**: 提取市场规模、增长率、行业玩家、政策影响等定量数据点

### 2.3 Creative Profile

[`profiles/creative/`](../../backend/src/research_agent/profiles/creative/)

- **定位**:创意案例/广告行业动态,服务 Brand Role / Big Idea 的 `{creative_references}` 注入
- **Fallback 域名**:`digitaling.com`, `topys.cn`, `adquan.com`, `socialbeta.com`, `meihua.info`
- **Filter 规则**: `min_llm_score=0.5`(创意内容门槛低)
- **Analyzer**: 聚焦创意角色、品牌定位、视觉风格、故事框架

### 2.4 扩展性

**新增研究类型零代码修改**:只需在 `profiles/` 下新建一个目录,实现 `planner_context / analyzer_prompt / synthesizer_prompt / filter / fetcher` 配置即可。

---

## 3. 外部工具与 API 依赖

### 3.1 Tavily(搜索主力)

位置:[`tools/web_search.py`](../../backend/src/research_agent/tools/web_search.py)

- **SDK**:`TavilyClient.search()`
- **参数**:
  - `query`:planner 生成的关键词
  - `include_domains`:**必填**,不做全网搜索。来源 = `profile.search_fallback_domains` ∪ `planner.target_domains`
  - `max_results`:10 / keyword
  - `search_depth`:`"advanced"`
- **双 Key 切换**:`TAVILY_API_KEY` + `TAVILY_API_KEY_2`,主 key 触发 `UsageLimitExceededError` 自动切备用
- **响应映射**:`{title, url, snippet, score}` → `candidates[]`

### 3.2 Crawl4AI(HTML 全文抓取)

- **调用形态**:HTTP REST API(独立容器 `crawler-crawl4ai-1`)
- **用途**:URL → markdown 全文
- **timeout**:`FETCH_HTML_TIMEOUT=45s`
- **fallback**:失败则 httpx 直接请求(SPA 页面可能 JS 渲染不出)

### 3.3 httpx(PDF / 兜底抓取)

- **PDF 下载**:大文件 5-20 MB,`FETCH_PDF_TIMEOUT=120s`
- **PDF 文本提取**:使用 pypdf/pdfplumber 类库(具体在 fetcher.py)
- **介绍页 PDF 链接提取**:若 HTML 短且含下载关键词,尝试从 landing page 提取 PDF 直链再下载

### 3.4 "硬编码封堵列表"

`filter.py::_is_fetch_blocked()`:某些域名直接跳过 fetch,仅用 snippet(避免浪费带宽在已知抓不到的源上)。

### 3.5 DeepSeek LLM 调用分布

| 节点 | 模型 | 调用次数/轮 | 并发 |
|------|-----|----------|-----|
| plan | ChatDeepSeek | 1 | - |
| filter | ChatDeepSeek | 1(批量) | - |
| analyze | ChatDeepSeek | N(文档数) | **10 并发** |
| synthesize | ChatDeepSeek | 1 | - |

**Reasoner 未使用**。Token 通过每次 response 的 `usage_metadata` 捕获,累积到 `state["token_usage_records"]`。

---

## 4. 数据模型

### 4.1 `ResearchTask`

[`models.py`](../../backend/src/research_agent/models.py)

| 类别 | 字段 |
|------|-----|
| **输入** | `title`, `analysis_goal`, `research_questions[]`, `search_config{}`, `profile_name`(default "industry") |
| **关联** | `strategy_id`(nullable,可独立), `user_id`, `job_id`(关联 AnalysisJob) |
| **状态** | `status`(pending/running/completed/failed), `error_message` |
| **结果** | `result_data`(JSON), `stats`(JSON), `progress`(逐节点日志列表) |
| **时间** | `created_at`, `updated_at` |

### 4.2 `result_data` 结构(synthesizer 输出)

```
result_data = {
  findings_by_question: {
    "问题文本": {
      answer_summary: "综合答案 (markdown)",
      confidence: "high" | "medium" | "low",
      data_points: [{metric, value, period, source}, ...],
      source_refs: ["url1", "url2", ...]
    },
    ...
  },
  synthesis: "markdown 格式综合报告 (1-3K 字)",
  coverage: {
    questions_covered: 3,
    questions_total: 5,
    ...
  },
  information_gaps: ["缺口1", "缺口2", ...]
}
```

### 4.3 `stats` + `progress`

- `stats`:`{rounds, documents_analyzed, candidates_total, tier1_source_count, ...}`
- `progress`:`[{step, label, round, ts, detail}, ...]` ——**前端用这个做实时进度条**

### 4.4 状态流转

```
pending(刚创建)
  → running(Celery 启动, plan 节点开始)
  → completed(synthesize 完成, result_data 写入)
  或 → failed(任何节点抛异常, error_message 填写)
```

---

## 5. 前端消费 + 策略集成

### 5.1 独立前端页面

目录:[`frontend/layers/research-agent/`](../../frontend/layers/research-agent/)

与新闻/社媒**对等的独立 layer**,不是嵌在策略里。主要页面:

| 页面 | 路由 | 职责 |
|-----|------|-----|
| 任务列表 | `/research-agent/pages/research-agent/index.vue` | 跨用户可见的 task 列表 + 状态过滤 |
| 创建任务 | `.../create.vue` | 上传 brief / 输入 goal / 选择 profile |
| 任务详情 | `.../[id]/index.vue` | **实时进度 + 最终 result_data 展示** |

### 5.2 前端 API 消费

[`composables/useResearchAgentApi.ts`](../../frontend/layers/research-agent/composables/useResearchAgentApi.ts)

| 端点 | 方法 | 用途 |
|------|-----|-----|
| `/research/profiles` | GET | 获取可用 profile 列表(industry/creative) |
| `/research/tasks` | GET/POST | 列表 / 创建 |
| `/research/tasks/{id}` | GET/DELETE | 详情 / 删除 |
| `/research/tasks/{id}/result` | GET | 已完成任务的 `result_data` |
| `/research/tasks/{id}/rerun` | POST | 重跑任务 |
| `/research/tasks/preview` | POST | 预览研究计划(不创建任务) |
| `/research/tasks/extract-brief` | POST | 从上传文件提取纯文本 |

### 5.3 前端硬依赖字段

- 列表页:`task.status`, `task.title`, `task.profile_name`, `task.created_at`
- 详情页:
  - `task.status` + `task.progress[]`(实时进度条)
  - `result_data.synthesis`(markdown 渲染)
  - `result_data.findings_by_question`(折叠卡片展示)
  - `result_data.coverage.{questions_covered, questions_total}`(覆盖率进度条)
  - `result_data.information_gaps`(警告提示)
  - `stats.{rounds, documents_analyzed, candidates_total, tier1_source_count}`(侧边栏统计)

**前端结构化字段依赖较少,大量是 markdown 文本**——这与社媒的硬依赖图表矩阵完全不同。

### 5.4 策略研究的集成(关键耦合点)

#### 5.4.1 Research Task 创建时机

策略 `confirm-research` 时自动创建,由 `strategies/service.py` 触发:
- `brand_brief.channel_plan` 含 `industry_research` 渠道 → 创建 `profile_name="industry"` task
- `brand_brief.channel_plan` 含 `creative_research` 渠道且 `output_type` 为 `campaign_strategy`/`full_strategy` → 创建 `profile_name="creative"` task

#### 5.4.2 策略 chain 消费 research findings

`_retrieve_research_findings` 查询:
```python
select(ResearchTask).where(
  strategy_id == strategy.id,
  status == "completed",
  profile_name == "industry",
).order_by(created_at.desc()).limit(1)
```
取**最新已完成**的 industry task 结果。

#### 5.4.3 按 stage 的 token 预算格式化

[`src/llm/chains/strategy/research_findings.py`](../../backend/src/llm/chains/strategy/research_findings.py) 提供 **5 + 2 个格式化器**:

| 格式化器 | Stage | Token 预算 | 注入什么 |
|---------|-------|----------|--------|
| `format_research_for_insight` | Insight (L1 brand_strategy) | ~1.5K | findings_by_question 全量 + information_gaps |
| `format_research_for_agenda_map` | Agenda Map (L1 market_report) | ~1.5K | 同上(校验媒体 vs 行业事实) |
| `format_research_for_brand_role` | Brand Role (L2 brand) | ~800 | synthesis 全文 + high-confidence 数据点 |
| `format_research_for_landscape` | Landscape (L2 market) | ~800 | synthesis + 所有数据点(量化重) |
| `format_research_for_big_idea` | Big Idea (L3 brand) | ~400 | high/medium 答案首句压缩 |
| `format_research_for_strategic_brief` | Strategic Brief (L3 market) | ~400 | high-confidence 要点 |

**创意研究额外 2 个**:
- `format_creative_for_brand_role`:~450 tokens,竞品已占据的创意角色
- `format_creative_for_big_idea`:~800 tokens,完整创意版图 + 白空间

#### 5.4.4 注入机制

策略 chain 的 prompt 模板含 `{research_findings}` 和 `{creative_references}` 占位符,由 service 层调 formatter 填充。**若无关联的已完成 ResearchTask,填充空串,chain 优雅降级**。

---

## 6. 任务图

### 6.1 Celery Task

| Task | 定义 | 触发方式 |
|------|------|--------|
| `research_agent.run_research` | [`tasks.py`](../../backend/src/research_agent/tasks.py) | 创建 ResearchTask 时自动 `.delay(task.id)`(策略或独立) |

**执行流程**:
1. 加载 ResearchTask 记录
2. 初始化 `ResearchState`
3. **同步** `research_graph.invoke()`(gevent worker 里必须同步调用避免事件循环冲突)
4. 每节点完成后追加 `progress` 记录
5. synthesize 完成后写 `result_data` + 更新 status

### 6.2 APScheduler

**Research Agent 本身无定时任务**。与 news_media 的 watchdog 模式不同。

### 6.3 触发时机

- **独立触发**:前端创建任务 → router → `.delay()` 派发,后续轮询进度
- **策略集成**:策略 confirm-research 时自动创建 + 派发
- **无手动执行端点**:不存在 `/research/tasks/{id}/execute`(与 news_media 的 two-phase 模式不同)

---

## 7. 与其他模块的对比

### 7.1 架构形态对比

| 维度 | 社媒监控 | 新闻监控 | **Research Agent** |
|------|---------|---------|------------------|
| 架构 | Stage 1/2/3 pipeline | Two-phase(probe + collect) | **LangGraph 循环图** |
| 链数量 | 9 | 2 | **4 个节点调 LLM** |
| 并发模型 | Celery 任务链(gevent pool) | Celery 任务 | **节点内并发(analyzer 10 并发)** |
| 迭代机制 | 无 | 无 | **evaluate → plan 多轮循环(≤3 轮)** |
| 输出结构 | 高度结构化(layers/图表字段) | 半结构化(narratives 为主) | **自然语言(synthesis markdown)** |
| 前端硬依赖 | 15+ 字段 | ~10 字段 | **<5 字段** |

### 7.2 为什么 Research Agent 已经是 "LLM-native"

从本次盘点看,Research Agent **本身已经是 LLM-native 架构**:
- 没有传统 pipeline 的 pre-LLM 规则层(归一化、SOV 聚合等)
- 输出直接给 LLM 消费(策略 chain 注入)
- 前端也直接渲染 markdown

**它不是 Path A pipeline 的受害者,也不是 Path B 一把梭的候选——它是另一类。**

### 7.3 潜在优化空间(未验证)

- **analyzer 节点 per-doc 调用** 10 并发,是不是该批处理?(5-10 文档/批 vs 单文档)
- **evaluate 纯规则判断"覆盖度"**:每个问题要 ≥2 条实质性来源。这个阈值在不同 profile 下是否合理?
- **循环上限 3 轮**:实际有多少 task 跑满 3 轮?多数 1-2 轮就够了的话,可考虑早停
- **Tavily 双 key**:会不会经常耗尽?是否该用更激进的 rate limit?

这些是调优题,不涉及架构重构。

---

## 8. 关键发现摘要(事实,非结论)

1. **架构上最"干净"**:LangGraph 循环结构 + profile 参数化,没有 pre-LLM 遗产
2. **输出自由度最高**:synthesis 是纯 markdown,findings_by_question 是半结构化,前端硬依赖字段最少
3. **深度依赖外部 API**:Tavily(搜索)/ Crawl4AI(HTML)/ httpx(PDF)—— 这些是基础设施,与 LLM 架构无关
4. **策略集成通过 formatter 解耦**:`research_findings.py` 按 stage token 预算分层注入,可优雅降级(无 task 时空串)
5. **有独立前端**,不只是策略的附属
6. **无定时任务**,事件驱动
7. **并发模型与其他模块不同**:节点内并发(analyzer 10 并发),不是任务级

## 9. 先前改动的复盘

到目前为止的所有改动(Prompt Caching、evaluator.py 等)都**没有碰 Research Agent 的代码**。本模块的 prompt 中也没有发现破坏 cache 前缀的动态模板。

---

## 后续

1. ✅ 社媒监控 inventory 完成
2. ✅ 新闻监控 inventory 完成
3. ✅ 专题研究(Research Agent)inventory 完成
4. ⏭️ **下一步**:策略研究 inventory ——**下游消费者,关键在于理清"策略如何消费前 3 个模块的产出"**
5. 4 份全部完成后,在 ADR-001 Phase 1 重新评估架构选项
