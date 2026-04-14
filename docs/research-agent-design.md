# Research Agent 设计方案

> 状态：Phase 1-3 已实现，Phase 4（策略集成）进行中
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
│  消费者声音   │  媒体报道    │  专业报告/行业研究   │
│  (UGC 层)   │  (事实层)   │  (分析层)           │
├────────────┼────────────┼────────────────────┤
│social_media │ news_media │ research_agent     │
│ 爬虫采集     │ 搜索引擎    │ Tavily 定向搜索     │
│ probe→collect│ probe→collect│ 自动循环，无探测    │
│→ SocialSlice│→ NewsSlice │→ 结构化研究报告      │
└────────────┴────────────┴────────────────────┘
  抖音/微博       百度/搜狗     四大/麦肯锡
  小红书等        DDG/微信      社科院等
```

- **social_media**：消费者怎么说（UGC）— probe → collect → SocialSlice
- **news_media**：媒体怎么报（新闻）— probe → collect → NewsSlice
- **research_agent**：专家怎么分析（报告）— 全自动循环 → 结构化研究报告（无探测/审核阶段）

### 目录结构

```
src/
├── strategies/          → 策略流水线，research_agent 作为第三渠道
├── social_media/        → 消费者数据（UGC 层），不变
├── news_media/          → 新闻数据（事实层），不变
├── knowledge_base/      → 独立模块：私有文档管理 + 基础统计预存（不参与策略产出）
├── research_agent/      → 新模块：agentic 搜索分析引擎（LangGraph）
│   ├── graph.py         → LangGraph 状态图定义（sync invoke）
│   ├── nodes/           → 各节点实现
│   │   ├── planner.py       → 搜索策略规划
│   │   ├── searcher.py      → 多源搜索执行
│   │   ├── filter.py        → 候选结果批量筛选
│   │   ├── fetcher.py       → 全文获取（PDF/HTML），含超时控制
│   │   ├── analyzer.py      → 逐篇深度阅读（智能截取）
│   │   ├── evaluator.py     → 覆盖度评估 + 缺口发现
│   │   └── synthesizer.py   → 跨报告综合分析
│   ├── tools/           → 搜索工具集（全部同步实现）
│   │   ├── web_search.py    → Tavily 包装（include_domains 定向搜索）
│   │   ├── web_fetch.py     → Crawl4AI HTML 抓取
│   │   └── pdf_fetch.py     → httpx PDF 下载 + pdfplumber 解析
│   ├── models.py        → ResearchTask 模型（独立表）
│   ├── state.py         → TypedDict 状态定义（含 reducer 注解）
│   ├── schemas.py       → Pydantic 模型（继承 CustomBaseModel）
│   ├── service.py       → 对外接口
│   ├── router.py        → API 端点
│   ├── tasks.py         → Celery 任务
│   └── config.py        → 源配置、搜索参数
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

`brief_parser_chain` 的 `channel_plan` 输出三种渠道类型：`social_media` / `news_media` / `research_agent`。

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
      "type": "research_agent",
      "available": true,
      "solvable": ["行业市场格局与份额数据", "专业机构的竞争分析与趋势预测"],
      "unsolvable": ["实时消费者声音"],
      "channel_brief": "聚焦新能源汽车行业竞争格局、价格带分析与市场趋势..."
    }
  ]
}
```

AI 根据 brief 内容按需分配渠道——简单口碑分析可能只推荐 social_media；行业格局分析推荐全部三个。不强制全开。

### ② 研究设计：data_plan（不含 research_agent）

`research_design_chain` 只负责社媒 / 新闻渠道的采集设计（`data_plan`、`slice_blueprint`、`output_type`），**不再输出 `research_agent` 字段**。

行业研究渠道由 `brief_parser_chain` 的 `channel_plan` 决定（存在 `type: "research_agent"` 条目即触发），`research_design_chain` 无需重复规划。

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
  "output_type": "brand_strategy"
}
```

- `primary_sources` 只含 `social_media` / `news_media`（决定产出路径），research_agent 不影响路径选择
- 若 brief_parser 未推荐 research_agent，confirm-research 不创建 ResearchTask

### ③ confirm-research：按 plan 条件创建

```
confirm-research:
  有 social_media 维度 → 创建 SocialMonitor + probe 任务（等爬虫）
  有 news_media 维度   → 创建 NewsMonitor + probe 任务（Celery 搜索）
  channel_plan 含 research_agent → 创建 ResearchTask（Celery 立即启动 LangGraph）
```

Research Agent **不是每次都创建**——只有 research_design 中包含 `research_agent` 字段时才创建。

Research Agent **没有探测/审核阶段**——内部 evaluate 节点自动循环，全自动完成。因此它通常比社媒/新闻更快完成。

### ④ 状态流转

```
                    social_media:   probing → collecting → done
planned → confirm → news_media:     probing → collecting → done    → 全部 done → ready → 产出
                    research_agent: running → done（无 probe）
```

`collection-status` 端点同时检查三个渠道的完成状态。Research Agent 无 probe 阶段，但若未完成也不阻塞——产出生成时无结果则优雅降级。

### ⑤ 产出生成（已实现）

```
primary: social_media slices / news_media slices（驱动产出路径选择）
research: research_agent → {research_findings}（第三视角，与 primary 分析权重平等）
```

`_retrieve_research_findings` 加载策略关联的最新已完成 ResearchTask 的 result_data，per-stage formatter 按 token 预算注入 `{research_findings}`：

| 层级 | Stage | Token 预算 | 注入内容 |
|------|-------|-----------|---------|
| 第 1 层 | Insight / Agenda Map | ~1.5K | 完整 findings_by_question + data_points + information_gaps |
| 第 2 层 | Brand Role / Landscape | ~800 | synthesis + 高置信度 data_points |
| 第 3 层 | Big Idea / Strategic Brief | ~400 | 压缩后的关键要点 |

- 无研究结果时所有 formatter 返回空字符串，chain 正常运行
- `data_provenance` 记录实际数据来源：`{primary: {channel, slice_counts}, research: {research_agent: bool}}`

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
| **Tavily** | 搜索层：`include_domains` 定向搜索（仅权威域名） | 同步调用 | `tavily-python`，API key |
| **Crawl4AI** | 全文获取：HTML 文章抓取 | 同步 HTTP 调用 Crawl4AI REST API | 现有 Docker 服务 |
| **httpx** | 全文获取：PDF 下载 | 同步调用 | 现有依赖 |
| **pdfplumber** | PDF 解析 | 同步 | 现有依赖（KB 模块已用） |

不加 SerpAPI 百度引擎——Tavily 中文覆盖对专业报告场景够用，四大/麦肯锡官网中英双语。

#### 未来方向：迁移至 Exa

> **当前不实施**，在此记录决策依据。

调研结论：**Exa 在研究报告发现场景下优于 Tavily**。

| 维度 | Tavily（当前） | Exa |
|------|--------------|-----|
| 域名限制 | 最多 300 个 | 最多 1,200 个 |
| 研究报告发现 | 通用语义搜索 | 专用 `research_paper` 分类，索引 1 亿+ 研究文档 |
| 响应包含全文 | ✓ | ✓（最高 10K+ 字符，可省略 fetch 节点） |
| 检索准确率（复杂查询） | 71% | 81% |
| 速度 | 基准 | 2–3× 更快 |
| 价格 / 千次查询 | $8 | $7–12 |

**Exa 的核心价值**：响应直接携带页面全文，HTML 来源可跳过 fetcher 节点，每轮减少 30–60s；`research_paper` 分类更适合定向报告检索；域名白名单上限 4 倍于 Tavily。

**触发迁移的条件**：
- Tavily 中文报告检索质量明显下降，或
- 需要研究报告的专项分类（`research_paper`），或
- 每月 Tavily 费用超出预算

**迁移工作量**：低——Exa Python SDK 接口结构与 Tavily 相近，主要改动在 `searcher.py`；fetcher 节点可为 Exa 已含全文的结果增加快速路径（跳过 HTTP 抓取）。

⚠️ **Bing Search API 将于 2026-08-11 停服**，SerpAPI 价格 3–5 倍于 Exa，均不作考虑。

#### 未来方向：双轨搜索（Tavily/Exa + 列表页直抓）

> **当前不实施**，记录在此供后续参考。

**问题背景**：Tavily 是语义搜索引擎，只返回关键词匹配的结果，可能漏掉"已知某域名存在但与关键词表述不符"的报告。对于有固定报告列表页的域名，直接爬取列表能获得完整覆盖。

**触发条件（满足其一时值得实施）**：
1. Tavily 按查询计费积累后成本显著
2. 多轮搜索后信息缺口依然大量存在，且明确是"已知域名有相关报告但 Tavily 未检索到"——即卡点是搜索工具，而非报告本身稀缺

**设计方案**：

```
searcher_node（双轨并行）
  ├── track_a: Tavily 语义搜索（处理抽象主题、跨域发现）
  └── track_b: 列表页直抓（Crawl4AI 抓固定入口，覆盖已知优质来源）
       ↓ 合并去重 → filter（现有逻辑不变）
```

**已确认有独立报告列表页/子域名的来源**（track_b 候选）：

| 来源 | 列表页入口 | 说明 |
|------|-----------|------|
| KPMG | `assets.kpmg.com` | PDF 资产库（已加入搜索域名列表） |
| BCG | `media-publications.bcg.com` | BCG 报告 PDF 库 |
| Bain | `media.bain.com` | Bain 报告 PDF 库 |
| 艾瑞咨询 | `report.iresearch.cn` | 报告专页（已加入搜索域名列表） |
| 信通院 | `caict.ac.cn/kxyj/qwfb/` | 研究报告发布页 |
| CNNIC | `cnnic.net.cn/IDR/ReportDownloads/` | 报告下载页 |

其余域名（McKinsey、Deloitte、PwC、EY、Roland Berger 等）报告分散在路径下，无独立列表页，不适合 track_b。

**为何现在不做**：当前搜索噪音问题（服务页混入、单域名垄断）已通过 filter 代码层修复；主要信息缺口（如买方视角研究）属于报告本身稀缺，多搜一轮也找不到，不是搜索工具的问题。

### 2. 定向搜索目标源（Tavily `include_domains`）

完整列表配置在 `src/config.py` 的 `RESEARCH_AGENT_TARGET_DOMAINS`，运行时与 planner LLM 推荐域名合并后传给 Tavily `include_domains`。

| 分类 | 代表域名 | 内容形式 | 说明 |
|------|---------|----------|------|
| 四大 + 综合咨询 | mckinsey.com, deloitte.com, pwccn.com, ey.com, kpmg.com, bcg.com, bain.com, rolandberger.com, accenture.com, oliverwyman.com, kearney.com | HTML + PDF | 免费可爬，年产数十至百篇 |
| 中国政府/智库 | stats.gov.cn, ndrc.gov.cn, miit.gov.cn, mofcom.gov.cn, pbc.gov.cn, csrc.gov.cn, cnnic.net.cn, cssn.cn, drc.gov.cn | PDF + HTML | 完全免费，权威数据 |
| 上市公司披露 ⭐ | cninfo.com.cn, hkexnews.hk, sse.com.cn | PDF（年报/招股书） | 招股书行业概况章节含 Frost & Sullivan 等付费机构数据，免费获取 |
| 国际机构 | worldbank.org, imf.org, oecd.org, unctad.org, wto.org, adb.org | PDF + HTML | 完全免费开放 |
| 中国行业研究 | iresearch.cn, questmobile.com.cn, aliresearch.com, mob.com, research.hktdc.com, caict.ac.cn, cesi.cn | PDF + HTML | 有完整免费报告（艾瑞/QuestMobile 注册可下载） |
| 消费者/买方研究 | edelman.com, datareportal.com, pewresearch.org, ourworldindata.org | PDF | 完全免费，可直接下载 |
| 垂直媒体/深度报道 | 36kr.com, latepost.com, caam.org.cn, ccfa.org.cn | HTML | 深度分析内容，免费 |

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
| `RESEARCH_AGENT_TARGET_DOMAINS` | 见下方源列表 | **src/config.py**（`Settings` 字段，可通过环境变量覆盖） |
| `max_rounds` | 4 | `research_agent/config.py` 硬编码常量 |
| `fetch_timeout` | 30s | `research_agent/config.py` 硬编码常量 |
| `task_hard_timeout` | 600s | Celery `time_limit` |
| `max_concurrent_tasks` | 10 | `research_agent/config.py` 硬编码常量 |

Token 用量通过 AnalysisJob 记录和追踪，不在 LangGraph State 中管理。Phase 3 的 evaluate 节点可通过查询 AnalysisJob 累积 token 判断是否终止循环。

### 6. 与 knowledge_base 的关系

- **KB 已从策略产出流程中完全移除**：原有的 `_retrieve_strategy_market_context`（KB RAG 背景注入）、`market_context` 模板变量、`data_provenance.background` 层级均已删除
- **KB 模块独立保留**：cnnic/nbs/govsite 三个爬虫继续运行，用户上传功能不变，作为独立的私有文档管理工具
- **Research Agent 不检索本地 KB**：Tavily 实时搜索已覆盖公开报告和统计数据
- **不做自动入库**：研究结果存在 ResearchTask.result_data 中，不回写 KB

### 7. 与 news_media 的关系

Research Agent 与 news_media **互不冲突**，搜索不同层次的信息：

| | news_media | research_agent |
|---|---|---|
| 搜什么 | 新闻报道（百度/搜狗/DDG/微信） | 专业报告（Tavily 定向四大/智库） |
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

策略："小米 SU7 品牌策略"，output_type: brand_strategy

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

### 场景 B：独立研究模式

```
用户创建：
  POST /research/tasks
  {
    "query": "2025 中国新能源汽车行业格局",
    "research_questions": ["头部玩家市场份额？", "技术路线分化趋势？"]
  }

Agent 自主执行（同上流程）→ 用户查看研究报告 + 引用源列表 + findings
```

## 数据模型

### research_tasks 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | PK |
| query | Text | 研究主题 |
| research_questions | JSONB | 研究问题列表 |
| strategy_id | UUID, FK, nullable | 关联策略（策略模式下非空） |
| user_id | UUID, FK | 创建者 |
| status | String(20) | pending / running / completed / failed |
| error_message | Text, nullable | 失败原因 |
| search_config | JSONB | research_angles, focus_domains 等 |
| result_data | JSONB | synthesis + findings + sources + evaluation |
| stats | JSONB | token_usage, rounds, documents_analyzed 等统计 |
| job_id | UUID, FK, nullable | 关联 AnalysisJob（token/cost 追踪） |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

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

## 配置项（新增）

```python
# config.py 新增（仅 2 个环境变量，其余硬编码在 research_agent/config.py）
TAVILY_API_KEY: str                          # Tavily 搜索 API key
RESEARCH_AGENT_TARGET_DOMAINS: list[str] = [  # 定向搜索域名
    "mckinsey.com.cn", "mckinsey.com",
    "deloitte.com",
    "pwccn.com",
    "ey.com",
    "kpmg.com",
    "cssn.cn",
    "drc.gov.cn",
]

# research_agent/config.py 硬编码常量（不暴露到 Settings）
MAX_ROUNDS = 3
MAX_CANDIDATES_PER_ROUND = 8
FETCH_TIMEOUT = 30   # 秒
LLM_TIMEOUT = 60     # 秒
MAX_CONCURRENT_TASKS = 3
```

## 对现有模块的改动

### 已完成

| 文件 | 改动 | 状态 |
|------|------|------|
| `llm/chains/strategy/research_findings.py` | 新建 per-stage formatter 模块（6 个函数，按 token 预算格式化研究数据） | ✅ |
| `llm/chains/strategy/brand_strategy/*.py` | `{market_context}` → `{research_findings}`，SYSTEM_TEMPLATE 更新研究数据使用指南 | ✅ |
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
| `strategies/service.py collection-status` | 加入 ResearchTask 完成状态检查 |
| `strategies/schemas.py` | ChannelPlanItem.type 描述更新、ConfirmResearchRequest/Response 适配 |
| `strategies/CLAUDE.md` | 更新流程文档 |

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

### Phase 4: 策略集成（进行中）

**已完成**：
- KB RAG 从策略产出流程中完全移除（`market_context` → `research_findings`）
- `_retrieve_research_findings` 读取 ResearchTask 结构化结果
- per-stage formatter 模块（`research_findings.py`，6 个函数，分层 token 预算）
- 6 条 stage chain 的 prompt 更新（research_findings 使用指南 + 三位一体交叉验证）
- `data_provenance` 重构为 `{primary, research}` 两层

**待实施**：
- brief_parser_chain：channel_plan 新增 research_agent 渠道
- research_design_chain：新增 research_agent 顶层字段
- confirm-research：条件创建 ResearchTask（plan 里有才创建）
- collection-status：加入 ResearchTask 完成状态检查
- 前端：ResearchPlanEditor 适配、采集状态页三渠道并列
