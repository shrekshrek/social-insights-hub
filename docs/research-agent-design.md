# Research Agent 设计方案

> 状态：Phase 1-4 已实现并稳定运行（搜索层 2026-04 收敛为 Tavily-only，详见设计决策 1）
> 日期：2026-04-12（更新：2026-04-14）

## 背景与动机

### 现状问题

策略研究此前通过知识库（KB）单步 RAG 注入市场背景（`_retrieve_strategy_market_context`：query → pgvector → chunks → done），存在以下问题：

- KB 预存模式对四大咨询/麦肯锡等大量专业报告源不可扩展（350-500 篇/年，大部分 chunks 永远不命中）
- 爬取 + 解析 + embedding + 存储成本固定，不管用不用都付
- 无法覆盖所有潜在相关源（源太多、更新太快）
- RAG 返回的 chunks 缺乏上下文，分析深度不足

KB 模块已从策略产出流程中移除（模块本身保留，作为独立的私有文档管理工具）。

### 目标

构建一个 **agentic 搜索分析引擎**，作为策略研究的第三数据渠道（与 social_media / news_media 平级），能够：

1. 根据研究需求自主规划搜索策略
2. 多源搜索，筛选高相关性行业报告
3. 下载全文（PDF/HTML），深度阅读分析
4. 评估覆盖度，发现信息缺口，迭代补充
5. 跨报告综合分析，输出结构化市场背景
6. 既可作为策略渠道自动触发，也可独立创建研究任务

## 模块定位

### 双模式使用

与 social_media / news_media 一致，Research Agent 支持两种使用模式：

| 模式 | 入口 | 触发方式 | 关联 |
|------|------|---------|------|
| **独立研究** | `POST /research/tasks` | 用户手动创建 | 无 strategy 关联 |
| **策略渠道** | `confirm-research` 自动创建 | brief 判断需要 → 研究设计纳入 → confirm 时并行启动 | `strategy_id` FK |

独立模式下无 Monitor 概念——每次是一次性研究任务，不做长期跟踪。

### 三渠道架构

策略产出基于三个数据渠道，各自代表一种独立视角：

```
┌──────────────────────────────────────────────┐
│                策略产出生成                      │
├────────────┬────────────┬────────────────────┤
│  消费者声音   │  媒体报道    │  专业内容 / Agent   │
│  (UGC 层)   │  (事实层)   │  (分析 + 创意层)     │
├────────────┼────────────┼────────────────────┤
│social_media │ news_media │ research_agent     │
│ 爬虫采集     │ 搜索引擎    │ Tavily 定向搜索     │
│ probe→collect│ probe→collect│ 自动循环，无探测    │
│→ SocialSlice│→ NewsSlice │→ 结构化研究报告      │
└────────────┴────────────┴────────────────────┘
  抖音/微博       百度/搜狗     industry: 四大/麦肯锡/政府智库
  小红书等        微信公众号    creative: 数英/TOPYS/广告门/SocialBeta
```

- **social_media**：消费者怎么说（UGC）— probe → collect → SocialSlice
- **news_media**：媒体怎么报（新闻）— probe → collect → NewsSlice
- **research_agent**：两类专业内容，同一张 LangGraph 图、参数化 profile 驱动：
  - **industry**（行业研究）：专家/机构怎么分析 — 四大/麦肯锡/政府智库 → 注入 `{research_findings}`
  - **creative**（创意研究）：同类品牌做过什么 — 数英/TOPYS/广告门/SocialBeta → 注入 `{creative_references}`（campaign_strategy 路径专属）
  - 全自动循环，无探测/审核阶段

### 目录结构

```
src/
├── strategies/          → 策略流水线，research_agent 作为第三渠道
├── social_media/        → 消费者数据（UGC 层），不变
├── news_media/          → 新闻数据（事实层），不变
├── knowledge_base/      → 独立模块：私有文档管理 + 基础统计预存（不参与策略产出）
├── research_agent/      → agentic 搜索分析引擎（LangGraph）
│   ├── graph.py         → LangGraph 状态图定义（sync invoke）
│   ├── nodes/           → 各节点实现
│   │   ├── planner.py       → 搜索策略规划（注入 profile.planner_context）
│   │   ├── searcher.py      → Tavily 定向域名搜索 + 域名限流
│   │   ├── filter.py        → 候选结果批量筛选
│   │   ├── fetcher.py       → 全文获取（内联 httpx PDF + Crawl4AI HTML，含 30s 超时）
│   │   ├── analyzer.py      → 逐篇深度阅读（profile 专属 analyzer_prompt）
│   │   ├── evaluator.py     → 覆盖度评估 + 缺口发现
│   │   └── synthesizer.py   → 跨报告综合分析（profile 专属 synthesizer_prompt）
│   ├── profiles/        → 研究类型参数化（同一张图，两套 prompt/域名/规则）
│   │   ├── base.py          → ResearchProfile dataclass
│   │   ├── industry/        → 行业研究：四大/麦肯锡/智库/政府门户
│   │   └── creative/        → 创意研究：数英/TOPYS/广告门/SocialBeta/梅花网
│   ├── tools/           → 搜索 API 封装（同步）
│   │   └── web_search.py    → Tavily 包装（include_domains 定向搜索，主+备双 key）
│   ├── models.py        → ResearchTask 模型（独立表，含 profile_name 字段）
│   ├── state.py         → TypedDict 状态定义（含 reducer 注解）
│   ├── schemas.py       → Pydantic 模型（继承 CustomBaseModel）
│   ├── service.py       → 对外接口（create_research_task / create_strategy_research）
│   ├── router.py        → API 端点
│   ├── tasks.py         → Celery 任务
│   └── config.py        → 硬编码搜索参数（MAX_ROUNDS / FETCH_TIMEOUT 等）
├── llm/                 → 共享 LLM 实例
└── jobs/                → 共享 AnalysisJob（research_agent 每任务创建一个）
```

依赖方向：`strategies → {social_media, news_media, research_agent} → {jobs, llm}`。research_agent 与 social_media / news_media 同层。knowledge_base 独立运行，不参与策略产出流程。

### API 端点

独立使用：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/research/tasks` | 创建研究任务（输入：研究主题 + 可选研究问题） |
| GET | `/research/tasks` | 研究任务列表 |
| GET | `/research/tasks/{id}` | 任务详情（状态、进度、引用源列表） |
| GET | `/research/tasks/{id}/result` | 研究结果（synthesis + findings） |
| POST | `/research/tasks/{id}/rerun` | 重新研究 |
| DELETE | `/research/tasks/{id}` | 删除 |

策略内使用（由 strategies 模块内部调用 service，不单独暴露端点）：
- `confirm-research` 时通过 `research_agent.service.create_strategy_research()` 创建
- `collection-status` 轮询时检查 ResearchTask 完成状态

## 策略集成流程

### ① brief 阶段：渠道分发判断

`brief_parser_chain` 的 `channel_plan` 输出**四种**渠道类型：`social_media` / `news_media` / `industry_research` / `creative_research`。后两种都由 Research Agent 承接，通过 `profile_name` 区分（industry / creative），走同一张 LangGraph 图。

```json
{
  "channel_plan": [
    {
      "type": "social_media",
      "available": true,
      "solvable": ["消费者对品牌的情感态度", "用户讨论的核心话题"],
      "unsolvable": ["市场规模等结构化行业数据"],
      "channel_brief": "聚焦小米SU7在社媒平台的用户讨论..."
    },
    {
      "type": "news_media",
      "available": true,
      "solvable": ["行业动态与竞品媒体曝光", "品牌相关新闻报道"],
      "unsolvable": [],
      "channel_brief": "搜索小米汽车及竞品的新闻报道与行业资讯..."
    },
    {
      "type": "industry_research",
      "available": true,
      "solvable": ["行业市场格局与份额数据", "专业机构的竞争分析与趋势预测"],
      "unsolvable": ["实时消费者声音"],
      "channel_brief": "聚焦新能源汽车行业竞争格局、价格带分析与市场趋势..."
    },
    {
      "type": "creative_research",
      "available": true,
      "solvable": ["同品类竞品 Campaign 案例", "获奖创意参考"],
      "unsolvable": ["市场规模数据"],
      "channel_brief": "搜索新能源汽车品类近 2 年的品牌 Campaign 与创意案例..."
    }
  ]
}
```

AI 根据 brief 内容按需分配渠道——简单口碑分析可能只推荐 social_media；品牌策略生成会同时用到全部四种。不强制全开。注意 `creative_research` 只在 `output_type ∈ {campaign_strategy, full_strategy}` 路径下才有意义（注入给 Brand Role / Big Idea 的 `{creative_references}`）。

### ② 研究设计：data_plan（不含 research 两类）

`research_design_chain` 只负责社媒 / 新闻渠道的采集设计（`data_plan`、`slice_blueprint`、`output_type`），**不输出 industry_research / creative_research 字段**。

Research Agent 两类任务由 `brief_parser_chain` 的 `channel_plan` 直接触发（`type == industry_research` 创建 profile="industry" 的 ResearchTask；`type == creative_research` 创建 profile="creative" 的 ResearchTask），`research_design_chain` 无需重复规划。

```json
{
  "research_questions": [
    {"id": "rq1", "question": "小米SU7的消费者认知如何？", "dimension": "brand_voice", "priority": "high"},
    {"id": "rq2", "question": "新能源汽车行业竞争格局？", "dimension": "competitive", "priority": "high"}
  ],
  "data_plan": [
    {"dimension_name": "品牌声量", "channel": "social_media", "keywords": ["小米SU7"], "platforms": ["douyin", "weibo"]},
    {"dimension_name": "行业报道", "channel": "news_media", "keywords": ["小米汽车 行业动态"]}
  ],
  "slice_blueprint": [...],
  "primary_sources": ["social_media", "news_media"],
  "output_type": "campaign_strategy"
}
```

- `primary_sources` 只含 `social_media` / `news_media`（决定产出路径），Research Agent 两类任务都不影响路径选择
- 若 brief_parser 未推荐 industry_research / creative_research，confirm-research 不创建对应 ResearchTask

### ③ confirm-research：按 plan 条件创建

```
confirm-research:
  有 social_media 维度        → 创建 SocialMonitor + probe 任务（等爬虫）
  有 news_media 维度          → 创建 NewsMonitor + probe 任务（Celery 搜索）
  channel_plan 含 industry_research
                              → 创建 ResearchTask(profile="industry")（Celery 启 LangGraph）
  channel_plan 含 creative_research 且 output_type ∈ {campaign_strategy, full_strategy}
                              → 创建 ResearchTask(profile="creative")（Celery 启 LangGraph）
```

Research Agent **按需创建**——两类任务各自独立触发，可能同时存在 industry + creative 两个 ResearchTask。

Research Agent **没有探测/审核阶段**——内部 evaluate 节点自动循环，全自动完成。因此它通常比社媒/新闻更快完成。

### ④ 状态流转

```
                    social_media:    probing → collecting → done
planned → confirm → news_media:      probing → collecting → done    → 全部 done → ready → 产出
                    research(×N):    running → done（无 probe，N=0/1/2 取决于 plan）
```

`collection-status` 端点同时检查全部渠道的完成状态。Research Agent 无 probe 阶段；若未完成也不阻塞——产出生成时无结果则优雅降级（`{research_findings}` / `{creative_references}` 注入空字符串）。

### ⑤ 产出生成（已实现）

```
primary:  social_media slices / news_media slices（驱动产出路径选择）
research: ResearchTask(industry) → {research_findings}        （第三视角，所有 stage 都注入）
creative: ResearchTask(creative) → {creative_references}      （仅 campaign_strategy / full_strategy 的 Brand Role / Big Idea 注入）
```

`_retrieve_research_findings` 加载策略关联、最新已完成、`profile_name="industry"` 的 ResearchTask 的 result_data；`_retrieve_creative_research_findings` 同理读 `profile_name="creative"` 的任务。两组 per-stage formatter 各自按 token 预算注入对应占位符：

**industry（`{research_findings}`，所有 stage 都注入）**

| 层级 | Stage | Token 预算 | 注入内容 |
|------|-------|-----------|---------|
| 第 1 层 | Insight / Agenda Map | ~1.5K | 完整 findings_by_question + data_points + information_gaps |
| 第 2 层 | Brand Role / Landscape | ~800 | synthesis + 高置信度 data_points |
| 第 3 层 | Big Idea / Strategic Brief | ~400 | 压缩后的关键要点 |

**creative（`{creative_references}`，仅 campaign_strategy / full_strategy 路径的 Brand Role / Big Idea 注入）**

| 层级 | Stage | Token 预算 | 注入内容 |
|------|-------|-----------|---------|
| 第 2 层 | Brand Role | ~400 | 排除法差异化：竞品做过什么、白空间在哪 |
| 第 3 层 | Big Idea | ~800 | 完整创意版图 + 竞品 Campaign 清单 + 白空间 |

- 无研究结果时所有 formatter 返回空字符串，chain 正常运行
- `data_provenance` 记录实际数据来源：`{primary: {channel, slice_counts}, research: {industry_research: bool, creative_research: bool}}`

## LangGraph 状态图

### Phase 1 线性图（最小可用）

```
START → plan → search → filter → synthesize → END
```

plan 节点即使在 Phase 1 也使用 LLM——用户输入可能是随意的自然语言，需要 LLM 梳理确认研究范围，生成结构化搜索计划。策略模式下 query = channel_brief（research_agent 渠道专属描述），Planner 自行生成 research_questions、关键词和目标域名。

### Phase 2 线性图（全文分析）

```
START → plan → search → filter → fetch → analyze → synthesize → END
```

### Phase 3 完整图（带循环）

```
              ┌─────────┐
              │  START   │
              └────┬─────┘
                   ▼
              ┌─────────┐
              │  plan    │  LLM 梳理输入，生成/调整搜索计划
              └────┬─────┘
                   ▼
              ┌─────────┐
              │ search   │  Tavily 定向搜索（仅权威域名）
              └────┬─────┘
                   ▼
              ┌─────────┐
              │ filter   │  LLM 批量评估相关性，选出 top N（3-8 篇）
              └────┬─────┘
                   ▼
              ┌─────────┐
              │  fetch   │  并行下载全文（PDF→pdfplumber / HTML→Crawl4AI）
              │          │  每个下载 30s 超时
              └────┬─────┘
                   ▼
              ┌─────────┐
              │ analyze  │  逐篇深度阅读，提取 key findings
              └────┬─────┘
                   ▼
              ╔══════════╗
              ║ evaluate ║─── 缺口 + 轮次<max_rounds ──→ plan（补充搜索角度）
              ╚════╤═════╝
                   │ 够了 / 达到上限
                   ▼
              ┌───────────┐
              │ synthesize│  跨报告综合分析，输出结构化 markdown
              └─────┬─────┘
                    ▼
              ┌─────────┐
              │   END    │
              └─────────┘
```

### 执行方式：sync invoke

**关键约束**：现有 Celery worker 使用 gevent pool。LangGraph 必须使用 **sync `invoke()`**，所有 tools 写成同步函数。gevent monkey-patch 自动让 HTTP 调用协作式让出。禁止在 Celery 任务中使用 `ainvoke()` 或 `asyncio.run()` 包装 LangGraph。

### 各节点职责

| 节点 | 输入 | 输出 | 说明 |
|------|------|------|------|
| **plan** | query + research_questions | SearchPlan | LLM 梳理用户输入（可能较随意），确认研究范围，生成结构化搜索计划。首轮：基于研究角度生成初始计划；后续轮（Phase 3）：基于 evaluation 的缺口调整 |
| **search** | SearchPlan | candidates | Tavily `include_domains` 定向搜索（默认域名 + LLM 推荐域名合并） |
| **filter** | candidates + research_questions | selected | **单次 LLM 调用**批量评分所有候选，选 top N，标注 `source_tier`（tier1=四大/权威智库, tier2=行业机构, tier3=其他）。不逐条评分 |
| **fetch** | selected | documents | PDF: httpx 下载 → pdfplumber（30s 超时/个）；HTML: Crawl4AI（30s 超时/个）。失败 `logger.warning()` 记录，不中断 |
| **analyze** | documents + research_questions | findings | 智能截取：目录/摘要优先，LLM 判断关键章节细读。每次 LLM 调用 60s 超时 |
| **evaluate** | findings + research_questions | evaluation | ① 每个问题是否有 findings？confidence 是否够？② tier1 来源数 ≥ 1？③ 定位缺口 → 填入 gap_questions，plan 节点下一轮据此调整搜索方向 |
| **synthesize** | findings（全部累积） | structured result | 输出 `findings_by_question`（按研究问题组织，含 confidence/data_points/source_refs）+ `synthesis`（markdown 报告）+ `sources`（含 source_tier）+ `coverage` 元信息 + `information_gaps` |

## State 定义

```python
from typing import Annotated, TypedDict
import operator


class SearchPlan(TypedDict):
    keywords: list[str]          # 搜索关键词
    target_domains: list[str]    # 优先搜索的域名
    search_angles: list[str]     # 搜索角度（行业趋势/竞争格局/消费者...）


class Candidate(TypedDict):
    title: str
    url: str
    snippet: str
    source: str                  # 来源域名
    content_type: str            # "pdf" | "html"
    source_tier: str             # "tier1" | "tier2" | "tier3"（filter 节点标注）
    relevance_score: float       # filter 节点填入


class Document(TypedDict):
    url: str
    title: str
    content: str                 # 全文或关键章节
    source: str
    content_type: str
    page_count: int | None       # PDF 页数


class DataPoint(TypedDict):
    metric: str                  # 指标名称
    value: str                   # 具体数值
    period: str                  # 时间范围
    source: str                  # 来源名称


class Finding(TypedDict):
    source_url: str
    source_title: str
    source_tier: str             # 继承自 Candidate
    key_points: list[str]        # 关键发现
    data_points: list[DataPoint] # 结构化数据点
    relevance_to_questions: dict[str, str]  # question → 相关发现摘要


class QuestionFinding(TypedDict):
    """按研究问题组织的发现（synthesize 节点产出）"""
    answer_summary: str          # 简要回答
    confidence: str              # "high" | "medium" | "low"
    data_points: list[DataPoint]
    source_refs: list[str]       # 指向 sources[].id


class Evaluation(TypedDict):
    questions_covered: list[str]       # confidence >= medium 的问题
    gap_questions: list[str]           # confidence = low 或无 findings
    tier1_source_count: int            # 四大/权威智库来源数
    should_continue: bool


class ResearchState(TypedDict):
    # 输入
    query: str                    # 研究主题
    research_questions: list[str] # 研究问题列表

    # 过程数据（candidates/selected 每轮替换）
    search_plan: SearchPlan
    candidates: list[Candidate]
    selected: list[Candidate]

    # 过程数据（跨轮次累积，使用 reducer 注解）
    documents: Annotated[list[Document], operator.add]
    findings: Annotated[list[Finding], operator.add]

    # 评估（Phase 3 启用）
    evaluation: Evaluation

    # 控制
    round: int
    max_rounds: int

    # 输出（synthesize 节点填入）
    findings_by_question: dict[str, QuestionFinding]  # 按研究问题组织
    synthesis: str                # markdown 综合报告
    coverage: dict                # {questions_covered, questions_total, high_confidence_count, source_quality}
    information_gaps: list[str]   # 信息缺口描述
```

**关键设计**：
- `documents`、`findings` 使用 `Annotated[list[X], operator.add]` 确保跨轮次追加而非覆盖
- `findings_by_question` 是 synthesize 节点的核心产出，按研究问题组织发现，含 confidence 评估和 data_points
- `source_tier` 贯穿 filter → findings → synthesize 全链路，tier1=四大/权威智库，tier2=行业机构，tier3=其他
- Token 用量通过 AnalysisJob 追踪，不在 State 中冗余存储
- 下载失败直接 `logger.warning()` 记录，不需要专门的 FetchError 类型

## 设计决策

### 1. 搜索工具选型

| 工具 | 角色 | 实现方式 | 依赖 |
|------|------|---------|------|
| **Tavily** | 搜索层**唯一主力**：`include_domains` 定向搜索（仅 profile 规定的权威域名），`TAVILY_API_KEY` 主 + `TAVILY_API_KEY_2` 备用双 key 自动切换 | 同步调用 | `tavily-python`，API key |
| **Crawl4AI** | 全文获取：HTML 抓取（fetcher 节点内联调用） | 同步 HTTP 调用 Crawl4AI REST API | 现有 Docker 服务 |
| **httpx** | 全文获取：PDF 下载（fetcher 节点内联调用） | 同步调用 | 现有依赖 |
| **pdfplumber** | PDF 解析 | 同步 | 现有依赖（KB 模块已用） |

**关于 fallback 的明确立场（2026-04）：**

搜索后端**只用 Tavily**，不做任何 fallback：

- **不做 Exa 切换**——Exa 单价 $7-12/千次比 Tavily $8 略贵，为 1-2× 价差维护双后端代码 + 两份迁移风险不值得。以前文档里的"迁移至 Exa"未来方向已作废
- **不做通用搜索引擎结果页爬取**——曾短期试过 crawl4ai 爬 `baidu.com/s` 和 `bing.com/search`，实测均被反爬降级为"导航噪声"，产出几乎 0 但照样消耗 crawl4ai 配额
- **不做站点独立适配 adapter fallback**——这是成本极高的工程（~10 个站点 DOM + 翻页 + 反爬各自维护，对标 `news_media/tasks/news_search/` 的难度），而且 McKinsey/Deloitte/PwC 等大头根本没列表页，覆盖率远不及 Tavily；价值密度太低，为概率极低的"Tavily 全挂"事件买保险不划算
- **不做 SerpAPI / Bing Search API**——SerpAPI 价差 3-5×；Bing Search API 2026-08-11 停服（Microsoft 付费产品层面停，与新闻模块里 `bing.com/news/search` 的爬虫反爬是两回事）

**两 key 耗尽的处理**：`tavily_search` 抛 `TavilyQuotaExhaustedError`；`research_agent/tasks.py` 的异常分支捕获后把任务标为 `failed`，`error_message` 写入清晰提示"Tavily 搜索配额已耗尽（主 key 与备用 key 均不可用），请联系管理员充值或等待下月配额刷新"，前端任务详情页直接显示该 error_message。日志按 `WARNING` 而非 `ERROR` 打（属于运维事件不是代码 bug，避免告警误报）。

**运维信号**：Tavily 双 key 先后耗尽时任务会明确失败并展示给用户，充值或等下月即可。如果未来真出现"Tavily 周期性不可用但业务不能断"的场景再重新评估兜底方案，在此之前**不做降级兜底**是有意识的决定。

### 2. 定向搜索目标源（Tavily `include_domains`）

两套 profile 各有独立的兜底域名列表，定义在 `research_agent/profiles/<name>/__init__.py` 的 `SEARCH_FALLBACK_DOMAINS` 常量里；运行时与 planner LLM 针对本次主题推荐的域名合并后传给 Tavily `include_domains`。

**industry profile（行业研究）**

| 分类 | 代表域名 | 内容形式 | 说明 |
|------|---------|----------|------|
| 四大 + 综合咨询 | mckinsey.com, deloitte.com, pwccn.com, ey.com, kpmg.com, bcg.com, bain.com, rolandberger.com, accenture.com, oliverwyman.com, kearney.com | HTML + PDF | 免费可爬，年产数十至百篇 |
| 中国政府/智库 | stats.gov.cn, ndrc.gov.cn, miit.gov.cn, mofcom.gov.cn, pbc.gov.cn, csrc.gov.cn, cnnic.net.cn, cssn.cn, drc.gov.cn | PDF + HTML | 完全免费，权威数据 |
| 上市公司披露 ⭐ | cninfo.com.cn, hkexnews.hk, sse.com.cn | PDF（年报/招股书） | 招股书行业概况章节含 Frost & Sullivan 等付费机构数据，免费获取 |
| 国际机构 | worldbank.org, imf.org, oecd.org, unctad.org, wto.org, adb.org | PDF + HTML | 完全免费开放 |
| 中国行业研究 | iresearch.cn, questmobile.com.cn, aliresearch.com, mob.com, research.hktdc.com, caict.ac.cn, cesi.cn | PDF + HTML | 有完整免费报告（艾瑞/QuestMobile 注册可下载） |
| 消费者/买方研究 | edelman.com, datareportal.com, pewresearch.org, ourworldindata.org | PDF | 完全免费，可直接下载 |
| 垂直媒体/深度报道 | 36kr.com, latepost.com, caam.org.cn, ccfa.org.cn | HTML | 深度分析内容，免费 |

**creative profile（创意研究）**

| 分类 | 代表域名 | 内容形式 | 说明 |
|------|---------|----------|------|
| 创意/案例库 | digitaling.com（数英）, topys.cn（TOPYS）, adquan.com（广告门）, socialbeta.com（SocialBeta）, meihua.info（梅花网） | HTML | 竞品 Campaign / 获奖案例 / 品牌叙事素材，免费可爬 |

> ⚠️ 付费墙域名不纳入列表（euromonitor、frost、grandviewresearch、gartner、forrester、analysys、askci 等订阅制平台报告正文无法下载）。如需其数据，优先通过 `cninfo.com.cn` 招股书间接获取。

### 3. 全文分析策略：智能截取

不做临时向量化（太重），不做全文 map-reduce（太贵）：

1. PDF：提取目录 + 摘要（前 2 页）+ 结论（后 2 页）
2. LLM 根据研究问题判断哪些章节值得细读
3. 只取相关章节全文给 LLM 深度分析
4. HTML 文章（通常 2000-5000 字）直接全文喂入

### 4. AnalysisJob 集成

每个 ResearchTask 创建**一个 AnalysisJob**（`job_type = "RESEARCH"`），各节点的 LLM 调用累加 token usage 到该 job。遵循现有跨渠道 AnalysisJob 模式：

- `research_agent/tasks.py` 中创建 job → 各节点执行 → 更新 token_usage → 任务完成时 finalize job
- 前端通过 `/jobs` 统一入口可查看研究任务的 token 消耗和费用

### 5. 超时与并发控制

| 控制项 | 值 | 配置方式 |
|--------|-----|---------|
| `TAVILY_API_KEY` | — | **环境变量**（必需） |
| `TAVILY_API_KEY_2` | — | **环境变量**（可选，主 key 额度耗尽时自动切换） |
| `RESEARCH_AGENT_TARGET_DOMAINS` | 见下方源列表 | **src/config.py**（`Settings` 字段，可通过环境变量覆盖） |
| `max_rounds` | 4 | `research_agent/config.py` 硬编码常量 |
| `fetch_timeout` | 30s | `research_agent/config.py` 硬编码常量 |
| `task_hard_timeout` | 600s | Celery `time_limit` |
| `max_concurrent_tasks` | 10 | `research_agent/config.py` 硬编码常量 |

Token 用量在 LangGraph State 的 `token_usage_records` 字段(扁平 dict 列表,operator.add 跨轮累积)中记录,每个 LLM 节点调用 `src.llm.utils.build_flat_token_record(response)` 产出一条记录(含 `cache_hit_tokens` / `cache_miss_tokens`)。任务完成时 `tasks.py` 调用 `sum_cost_from_flat_records` 按 DeepSeek Context Caching 定价汇总,写入 AnalysisJob 的 `token_usage` 字段。前端通过 `/jobs` 可查看 cache 命中率和成本。

### 6. 与 knowledge_base 的关系

- **KB 已从策略产出流程中完全移除**：原有的 `_retrieve_strategy_market_context`（KB RAG 背景注入）、`market_context` 模板变量、`data_provenance.background` 层级均已删除
- **KB 模块独立保留**：cnnic/nbs/govsite 三个爬虫继续运行，用户上传功能不变，作为独立的私有文档管理工具
- **Research Agent 不检索本地 KB**：Tavily 实时搜索已覆盖公开报告和统计数据
- **不做自动入库**：研究结果存在 ResearchTask.result_data 中，不回写 KB

### 7. 与 news_media 的关系

Research Agent 与 news_media **互不冲突**，搜索不同层次的信息：

| | news_media | research_agent |
|---|---|---|
| 搜什么 | 新闻报道（百度/搜狗，可选微信公众号） | 专业报告（Tavily 定向四大/智库） |
| 内容性质 | **事实层**：正在发生什么（事件、舆论、声量） | **分析层**：深层分析是什么（趋势、框架、数据） |
| 分析方式 | tagging（实体/情感/tier）→ 切片 insight | 逐篇深度阅读 → 跨报告综合 |
| 人工介入 | probe_review → approve/refine | 全自动循环（内部 evaluate） |
| 独立使用 | 有（独立新闻监测项目） | 有（独立研究任务） |
| 策略中角色 | Agenda Map 主数据源（不可替代） | 行业研究第三视角（与 primary 分析权重平等） |

在策略产出各 stage 中的定位：

| Stage | news_media | research_agent |
|-------|-----------|----------------|
| **Agenda Map**（媒体议程图） | **主数据源**：媒体在讨论什么，报告替代不了 | 辅助：行业报告中的媒体分析 |
| **Landscape**（竞争格局） | 有价值但偏表面 | **深度数据**：报告的市场份额/竞争分析更扎实 |
| **Insight**（消费者洞察） | 辅助 | 补充行业趋势 |
| **Brand Role / Big Idea** | 辅助 | 补充竞争格局 |

## 具体场景示例

### 场景 A：策略渠道模式

策略："小米 SU7 品牌策略"，output_type: campaign_strategy

```
① brief_parser_chain → channel_plan:
  [
    {"type": "social_media", "solvable": ["消费者口碑", "购买体验"], "channel_brief": "..."},
    {"type": "news_media", "solvable": ["行业动态", "竞品报道"], "channel_brief": "..."},
    {"type": "research_agent", "solvable": ["市场份额格局", "价格带竞争分析"], "channel_brief": "..."}
  ]

② research_design_chain → data_plan（只含社媒/新闻）:
  data_plan:
    [{"dimension_name": "品牌声量", "channel": "social_media", "keywords": ["小米SU7"], "platforms": ["douyin", "weibo"]},
     {"dimension_name": "行业报道", "channel": "news_media", "keywords": ["小米汽车 行业"]}]
  （research_agent 字段已移除，行业研究由 channel_plan 触发，Planner 自主规划）

③ confirm-research → 三渠道条件并行：
  SocialMonitor + probe 任务（social_media 维度存在）
  NewsMonitor + probe 任务（news_media 维度存在）
  ResearchTask（channel_plan 含 research_agent 条目，Celery 立即开始）
    query   = channel_brief（"聚焦新能源汽车行业竞争格局、价格带分析与市场趋势..."）
    context = analysis_goal（整体策略背景）

④ Research Agent 执行：

  plan    → LLM 基于 channel_brief 自行生成研究问题和搜索关键词
            research_questions = ["中国新能源汽车市场份额格局？", "20-30万价格带竞争态势？", ...]
            关键词 = ["新能源汽车行业报告 2025 PDF", "China NEV market share report", ...]
            目标源 = [deloitte.com, mckinsey.com, kpmg.com, ey.com]
  search  → 14 条候选（Tavily 定向搜索）
  filter  → 单次 LLM 调用，选出 5 篇最相关（标注 source_tier）
  synthesize → 结构化产出：

  result_data = {
    "findings_by_question": {
      "中国新能源汽车市场份额格局": {
        "answer_summary": "比亚迪以 33% 份额领先，特斯拉 7.8%...",
        "confidence": "high",
        "data_points": [
          {"metric": "比亚迪市场份额", "value": "33.1%", "period": "2024H2", "source": "KPMG"},
          {"metric": "特斯拉中国份额", "value": "7.8%", "period": "2024H2", "source": "Deloitte"}
        ],
        "source_refs": ["src_0", "src_2"]
      },
      "消费者购买决策变化": {
        "answer_summary": "智能化体验超越续航成为首要因素...",
        "confidence": "medium",
        "data_points": [...],
        "source_refs": ["src_1"]
      },
      "20-30 万价格带竞争态势": {
        "answer_summary": "...",
        "confidence": "low",
        "data_points": [],
        "source_refs": []
      }
    },
    "synthesis": "# 新能源汽车行业研究\n\n## 市场格局\n...",
    "sources": [
      {"id": "src_0", "title": "2025 中国新能源汽车展望", "url": "...",
       "source_tier": "tier1", "relevance_score": 0.92},
      ...
    ],
    "coverage": {
      "questions_covered": 2, "questions_total": 3,
      "high_confidence_count": 1,
      "source_quality": {"tier1": 3, "tier2": 1, "tier3": 0}
    },
    "information_gaps": ["小米 SU7 价格带竞争数据不足——建议参考社媒/新闻渠道"]
  }

⑤ 产出生成时 per-stage formatter 按 token 预算注入：
  Insight 层 → format_research_for_insight(result_data) → 完整 findings + data_points（~1.5K tokens）
  Brand Role 层 → format_research_for_brand_role(result_data) → synthesis + 高置信度 data_points（~800 tokens）
  Big Idea 层 → format_research_for_big_idea(result_data) → 压缩关键要点（~400 tokens）
```

### 场景 B：独立研究模式（industry）

```
用户创建：
  POST /research/tasks
  {
    "title": "2025 中国新能源汽车行业格局",
    "analysis_goal": "摸清头部玩家份额 + 价格带竞争 + 技术路线分化趋势",
    "research_questions": ["头部玩家市场份额？", "技术路线分化趋势？"],
    "profile_name": "industry"   // 可省略，默认 industry
  }

Agent 自主执行（同上流程）→ 用户查看研究报告 + 引用源列表 + findings
```

### 场景 C：独立研究模式（creative）

```
用户创建：
  POST /research/tasks
  {
    "title": "新能源汽车品牌 Campaign 扫描 2024",
    "analysis_goal": "梳理同品类竞品近两年的主要 Campaign、创意切入点、获奖作品",
    "research_questions": ["头部品牌的情感锚点？", "哪些创意手法获奖？"],
    "profile_name": "creative"
  }

Agent 走 creative profile 的 planner/analyzer/synthesizer，在数英 / TOPYS / 广告门 /
SocialBeta / 梅花网等源里搜案例 → 产出创意版图（而非行业数据结构），作为
Brand Role / Big Idea 的 {creative_references} 输入
```

## 数据模型

### research_tasks 表

以代码为准，见 [`backend/src/research_agent/models.py`](../backend/src/research_agent/models.py)。关键字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| title | String(200) | 研究标题，可选，planner 自动生成 |
| analysis_goal | Text | 核心研究意图（原 query） |
| research_questions | JSON | 研究问题列表 |
| search_config | JSON | research_angles / focus_domains / context 等 |
| profile_name | String(32) | **`industry` / `creative`**，决定用哪套 planner_context / analyzer_prompt / 兜底域名 |
| strategy_id | Integer, FK nullable | 关联策略（策略模式下非空；ondelete CASCADE） |
| user_id | Integer, FK | 创建者 |
| job_id | Integer, FK nullable | 关联 AnalysisJob（token/cost 追踪） |
| status | String(20) | pending / running / completed / failed |
| error_message | Text nullable | 失败原因 |
| result_data | JSON | synthesis + findings + sources |
| stats | JSON | rounds / documents_analyzed / candidates_total 等 |
| progress | JSON | 执行进度日志，每个节点完成后追加一条 |
| created_at / updated_at | DateTime | — |

语义字段遵循项目规范：`user_id`、`status`、`error_message`、`result_data`、`stats`。

### 与 Strategy 的关联

通过 `research_tasks.strategy_id` FK 关联，**不在 Strategy 表上加冗余字段**。查询策略的研究状态直接查 ResearchTask：

```python
# 查策略关联的研究结果
task = await db.scalar(
    select(ResearchTask)
    .where(ResearchTask.strategy_id == strategy_id)
    .order_by(ResearchTask.created_at.desc())
)
```

## 新增依赖

| 包 | 用途 | 说明 |
|----|------|------|
| `langgraph` | 状态图编排 | 与现有 langchain 同生态，sync invoke |
| `tavily-python` | Web 搜索 API | 轻量，按调用付费（~$0.01/次） |

现有依赖复用：`langchain`、`httpx`、`pdfplumber`、`crawl4ai`（Docker 服务）。

## 配置项

```python
# src/config.py（环境变量 / Settings）
TAVILY_API_KEY: str                          # Tavily 搜索 API key（必需）
TAVILY_API_KEY_2: str | None = None          # 备用 key，主 key 额度耗尽自动切换；
                                             # 两 key 都耗尽 → 任务 failed + error_message 给前端

# research_agent/config.py 硬编码常量（不暴露到 Settings）
MAX_ROUNDS = 4
MAX_CANDIDATES_PER_ROUND = 15
FETCH_HTML_TIMEOUT = 45     # 秒，HTML 抓取（Crawl4AI + httpx 渲染）
FETCH_PDF_TIMEOUT = 120     # 秒，PDF 下载（5-20MB 常见）
MAX_CONCURRENT_TASKS = 10   # analyze 节点并发度

# 各 profile 的兜底域名：research_agent/profiles/<name>/__init__.py 的 SEARCH_FALLBACK_DOMAINS
# industry → 四大 / 麦肯锡 / 政府智库 / 国际机构 等
# creative → 数英 / TOPYS / 广告门 / SocialBeta / 梅花网
```

## 对现有模块的改动

### 已完成

| 文件 | 改动 | 状态 |
|------|------|------|
| `llm/chains/strategy/research_findings.py` | 新建 per-stage formatter 模块（6 个函数，按 token 预算格式化研究数据） | ✅ |
| `llm/chains/strategy/brand_strategy/*.py` | `{market_context}` → `{research_findings}`，SYSTEM_TEMPLATE 更新研究数据使用指南（目录名保持 brand_strategy/，output_type 值为 campaign_strategy） | ✅ |
| `llm/chains/strategy/market_report/*.py` | 同上 | ✅ |
| `strategies/service.py` | `_retrieve_strategy_market_context` → `_retrieve_research_findings`；6 个 generate 函数注入 research_findings；`_build_data_provenance` 改为 `{primary, research}` 两层 | ✅ |
| `strategies/schemas.py` | 移除 KB 相关描述 | ✅ |
| `celery_app.py` | `include` 列表新增 `src.research_agent.tasks` | ✅ |
| `main.py` | 注册 research_agent router | ✅ |
| `config.py` | 新增 Tavily / research agent 配置项 | ✅ |
| `jobs/` | 新增 `RESEARCH` job_type | ✅ |

### 待实施

| 文件 | 改动 |
|------|------|
| `llm/chains/strategy/brief_parser_chain.py` | channel_plan 新增 `research_agent` 渠道类型 + prompt 描述 | ✅ |
| `llm/chains/strategy/research_design_chain.py` | 只产出社媒/新闻 data_plan，移除 research_agent 字段 | ✅ |
| `strategies/service.py confirm_research` | 触发条件改为 channel_plan 含 research_agent，query=channel_brief，context=analysis_goal | ✅ |
| `strategies/service.py collection-status` | 加入 ResearchTask 完成状态检查（`_get_research_agent_status` 分别统计 industry + creative） | ✅ |
| `strategies/schemas.py` | ChannelPlanItem.type 覆盖 4 种渠道类型 + `CollectionStatusResponse.industry_research/creative_research` 字段 | ✅ |
| `strategies/CLAUDE.md` | 模块流程文档已写入 Research Agent 两类任务的触发条件、编排与占位符注入规则 | ✅ |

## 前端改动

- 策略研究计划编辑器（ResearchPlanEditor）：展示/编辑 research_agent 的 research_questions、scope 和 focus_domains，支持整体开关
- 策略数据采集状态页：显示研究任务进度（与社媒/新闻探测进度并列）
- 策略产出页：DataProvenanceBadge 展示 research_agent 数据来源
- 独立研究页面：创建研究任务、查看结果（已有 layer: `research/`）

## 实施顺序

### Phase 1: 最小可用（snippet 综合，线性图） ✅ 已完成

- **线性 LangGraph 图**：plan → search → filter → synthesize（4 节点，无循环）
- plan 节点用 LLM 梳理用户输入、确认研究范围、生成搜索计划
- Tavily 搜索，**不下载全文**，用 snippet 做综合
- 独立 API 端点（`/research/tasks`）
- Celery 任务 + AnalysisJob 集成
- 前端独立研究页面（列表/创建/详情结果页）
- RBAC 权限 + 路由配置

### Phase 2: 全文分析（线性图扩展） ✅ 已完成

- **线性图扩展**：plan → search → filter → fetch → analyze → synthesize（6 节点，无循环）
- 增加 fetch + analyze 节点
- PDF 下载解析（httpx + pdfplumber）+ HTML 全文获取（Crawl4AI REST API）
- 每节点独立 LLM 实例（短超时 60-120s，max_retries=1，防止单文档阻塞整个任务）

### Phase 3: 闭环优化（引入循环） ✅ 已完成

- **图变为有循环**：analyze → evaluate → plan（回到起点补充搜索）
- evaluate 节点：覆盖度评估（每问题 ≥2 来源）+ 缺口发现 + 补充关键词建议
- max_rounds=3 控制最大循环次数
- E2E 验证：78 data points，5 tier1 sources，1574 字综合报告，288s 完成

### Phase 4: 策略集成 ✅ 已完成

- KB RAG 从策略产出流程中完全移除（`market_context` → `research_findings`）
- `_retrieve_research_findings` / `_retrieve_creative_research_findings` 分别读取
  `profile_name=industry` / `profile_name=creative` 的 ResearchTask 结构化结果
- per-stage formatter 模块（`research_findings.py`，6 个函数分层 token 预算 +
  creative 专属 `format_creative_for_brand_role` / `format_creative_for_big_idea`）
- 6 条 stage chain 的 prompt 更新（research_findings 使用指南 + 三位一体交叉验证）
- `data_provenance` 重构为 `{primary, research}` 两层，research 内含 industry_research /
  creative_research 两个布尔标志
- `brief_parser_chain` channel_plan 输出 4 渠道类型（social_media / news_media /
  industry_research / creative_research）
- `research_design_chain` 只产出社媒/新闻 data_plan（research 两类由 brief_parser 直接触发）
- `confirm-research` 按 channel_plan 条件创建 ResearchTask（industry 无条件，
  creative 限 campaign_strategy / full_strategy 路径）
- `collection-status` 返回 industry_research + creative_research 两个独立进度
- 前端 ResearchPlanEditor 适配 + 采集状态页四渠道并列展示

---

## 决策历史 & 明确不做的事

> 本节记录每次对 Research Agent 的调整及其**理由**,以及**讨论过但决定不做**的
> 优化项。目的是避免后人(或未来的自己)重复同样的讨论,或在不了解背景的
> 情况下"改出新 bug"。时间倒序。

### 2026-04-20 · 修复 synthesizer 末轮 selected 清零时丢弃跨轮 findings

**Commit**: `fec365c`

**背景**:Strategy 18 关联的 Task 38 出现异常 — progress 日志显示 round 1 成功
分析了 10 篇文档,但 `result_data.findings_by_question` 的 5 个研究问题全部
`confidence: low`、`answer_summary: "未找到相关数据"`。10 篇 findings "凭空消失"。

**根因**:
- `state.py` 中 `findings` 字段是 `Annotated[list, operator.add]` — 跨轮累积
- `selected` 字段**不是** operator.add — 每轮替换
- round 1:fetch+analyze 成功 10 篇 → findings += 10,selected=10
- round 2:filter 跨轮去重(`already_processed` 剔除已 fetch URL)后 selected=[] → fetch 0 → analyze 0
- evaluator 看到 selected=[] → `should_continue=False` → 转 synthesize
- synthesizer 早返回分支 `if not selected:` 只看 selected,**忽略累积的 findings**,直接把所有问题标为 low

**修复**:条件改为 `if not selected and not findings`,两者都空才真的走空返回。
后续代码(`if findings:` 分支)已能正确消费 findings-only 的情况,不需要额外改动。

**为何过去没发现**:B2B 类研究每轮都能找到足够多新候选,filter 跨轮去重后
selected 仍非空,该分支从未被触发。乐虎这种**小品牌窄主题**在 round 1 几乎穷尽
可用源,round 2 才会踩坑。

**防回归**:`tests/test_research_synthesizer.py` 三个用例覆盖了
(selected=[], findings 非空)/ 两者都空 / selected 非空 findings 为空 三个边界。

---

### 2026-04-20 · 4 节点 `_token_record` 合并为共享函数 + tasks.py 成本计算对齐

**Commit**: `72895c2`

**背景**:四个节点(plan / filter / analyzer / synthesizer)各自定义了
**一模一样**的 `_token_record(response) -> dict`,返回
`{input_tokens, output_tokens, total_tokens}` 三字段。同时 `tasks.py` 汇总
成本时硬编码"全部按 miss 价"(`DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION × total_input + output_price × total_output`),没有享受 DeepSeek Context Caching 的分层计价。

**具体现状**:
- 4 份完全相同的私有函数(经典 duplicate)
- `cache_hit_tokens` / `cache_miss_tokens` 既没采集也没记录
- `AnalysisJob.token_usage` 的 Research Agent 记录里看不到 cache 命中率

**改动**:
- `src/llm/utils.py` 新增两个共享 helper:
  - `build_flat_token_record(response)` — 返回扁平 dict,含 cache 字段
  - `sum_cost_from_flat_records(records, llm_type)` — 按 Context Caching 分层计价
- 4 个节点 `import build_flat_token_record` 替换各自的私有 `_token_record`
- `tasks.py` 汇总改用 `sum_cost_from_flat_records`,`token_usage.summary`
  新增 `total_cache_hit_tokens` / `total_cache_miss_tokens` / `cache_hit_ratio`

**向前兼容**:若响应未返回 cache 字段(理论上不会,但防御式编程),helper 退化为"全部按 miss 价"——和旧行为一致。

**收益**:
- 未来改 DeepSeek 定价公式只需动 `llm/utils.py` 一处
- Research Agent 开始正确观测 cache 命中(跟社媒/策略对齐)
- 删除 60+ 行 duplicate 代码

---

### 明确不做的优化(及理由)

以下优化项**讨论过、评估过,暂不实施**。未来若需要重新评估,先读这里再开工,避免重复讨论。

#### 1. Tavily `search_depth` basic/advanced 混合策略

**讨论背景**:代码里硬编码 `search_depth="advanced"`,比 `basic` 贵 2x。

**A/B 实测结论**(3 个真实 query 各 10 条结果):
- avg snippet 长度:basic 2171-3443 字,advanced 2036-2177 字——**advanced 不是更长**
- snippet 长度范围:basic 77-12890 字(方差极大),advanced 1530-2397 字(稳定)
- URL 重合率:0% / 25% / 54% — 两种 depth 返回的**结果集本质不同**

**真实价值**:advanced 的价值是**稳定的 snippet 长度**——filter 节点用 snippet 给 LLM 评分,basic 的 77 字残片会让评分失效。不是"更长"。

**为何不做**:
- Tavily 成本占 Research Agent 总成本约 30-50%,Research Agent 又占总成本约 30%,算下来 Tavily 占总 10-15%
- 基于 10-15% 的成本项做复杂混合策略,优化收益不足以支付实施复杂度 + 新 bug 风险

**触发重新评估的条件**:Tavily 月费超预算,或 basic/advanced 价差拉大到 3x+。

#### 2. `min_sources=2` 最后一轮放宽

**讨论背景**:observer 观察到"大部分 task 跑满 3 轮,少数 4 轮,极少 2 轮",
有人提议"最后一轮把 min_sources 降到 1,减少 gap_questions"。

**为何不做**:
- 跑满 3 轮是 evaluator 的**设计意图**,见 [`nodes/evaluator.py`](../../backend/src/research_agent/nodes/evaluator.py#L74-L76) 注释:"不对 round 1 放宽——若 round 1 只找到 1 条就停止,质量往往不够,应继续搜索"
- 研究问题必须有 ≥2 条实质性来源互相印证是质量控制,单条来源无法排除偶然
- 若确实某问题只有 1 条权威资料,它会作为 `information_gaps` 优雅降级,**不会丢失**
- 放宽阈值 = 降低产出质量,解决的是"感觉循环太多"的伪问题

**触发重新评估的条件**:出现大量"明知有权威数据但被判为 gap"的误杀案例。

#### 3. Grounding 验证(synthesize 引用真实性检查)

**讨论背景**:synthesize 节点输出的 `source_refs` 是 LLM 基于 documents 生成的,理论上 LLM 可能"凭记忆"编造引用而非真正来自 fetched content。

**为何不做**:
- 这是所有 RAG 系统的通病,当前没有观察到具体的误引用案例
- Tavily 的 include_domains 已经保证来源权威性,LLM 幻觉空间小
- 实施成本(需要在 synthesize 后加一层 URL→正文检索 + 字符串核验)中等
- 属于 nice-to-have 的质量增强,而非 bug 修复

**触发重新评估的条件**:用户/业务方反馈"引用的数据在原报告找不到"的真实案例出现 ≥3 次。

#### 4. Observability 埋点(round 完成率、fetch 成功率、tavily 调用数等)

**讨论背景**:当前没有聚合的"跑满 X 轮的比例"、"fetch 失败率"、"平均 candidates 衰减率"等指标,所有判断基于 ad-hoc SQL 查询 `stats` 字段。

**为何不做**:
- Research Agent 总量不大(7 天 9 次任务),样本不足以支撑指标的统计意义
- 现有 `progress`/`stats` 字段已能满足单任务的 debug 需求
- 加埋点 = 增加系统复杂度 + 需要维护 Grafana/看板,ROI 低

**触发重新评估的条件**:任务量增长 10 倍以上,或运营方需要定期健康检查报表。

