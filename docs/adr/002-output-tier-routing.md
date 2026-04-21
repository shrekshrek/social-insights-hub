# ADR-002：三层产出架构与 insufficient 分诊

> 决策日期：2026-04-22
> 状态：**Accepted**
> 相关实现：
> - `backend/src/llm/chains/strategy/brief_parser_chain.py`（prompt 规则 + parse 校验）
> - `backend/src/strategies/schemas.py`（`ParseBriefResponse.insufficient_reason`）
> - `frontend/layers/strategies/types/index.ts`（`InsufficientReason` 类型）
> - `frontend/layers/strategies/pages/strategies/create.vue`（按 reason 分支跳转）

---

## 背景

原 brief_parser 对所有非战略型 brief 统一判定 `platform_verdict=insufficient` 并单路推至 research_agent（专题研究）。实际发现两类错配：

1. **诊断型 brief 被硬塞进 strategies pipeline**：类似"最近一周 XX 舆情监测"、"Campaign 投后消费者反馈复盘"这类 brief，只要数据源充足 LLM 就判 `sufficient`，用户被导入 full_strategy / campaign_strategy 路径，触发 creative_research + industry_research 的完整采集，最终跑到 Brand Role / Big Idea / Strategic Brief 阶段——但 brief 根本没要求战略产出，采集和生成都是浪费
2. **insufficient 错分至 research_agent**：诊断型 brief 即便判为 insufficient，被统一推至 research_agent；但 research_agent 只有 `industry` / `creative` 两个 profile，数据源是 Tavily/Exa 开放 Web 搜索，**不访问 social/news 数据库**——结构上无法承接"消费者情感诊断"或"媒体舆情简报"这类需要 4 渠道管道能力的需求

问题根因：系统实际已经具备**三种不同的产出能力**，但 brief_parser 只认识其中一种（strategies pipeline），把其它需求要么强行塞进来、要么单路甩出去。

---

## 决策

明确系统的**三层产出架构**，brief_parser 按产出意图分诊至对应层。

### 三层能力边界

| 层 | 用途 | 入口 | 数据源 | 产出形态 |
|---|---|---|---|---|
| **strategies pipeline** | 战略产出（Brand Role / Big Idea / Strategic Brief / 品牌定位） | `/strategies/*`（brief_parser → research_design → 4 阶段流水线） | 4 渠道全上（social + news + industry + creative） | 端到端策略报告（campaign_strategy / market_report / full_strategy） |
| **monitor + slice** | **诊断产出**（情感快照 / 舆情监测 / 竞品对标 / Campaign 复盘 / KOL 声量监测） | `/social-media/monitors/*` + `/news-media/monitors/*`（独立入口，不经 brief_parser） | 单渠道（social 或 news） | 结构化诊断切片（foundation / layers / reports） |
| **research_agent** | 知识性研究（领域综述 / 机制 / 流程 / 行业报告） | `/research-agent/*` | 开放 Web（Tavily / Exa / Crawl4AI） | 研究综述 + findings_by_question |

三层职责严格区分：
- 只有**策略产出**（需要 Brand Role / Big Idea / Strategic Brief）走 strategies pipeline
- 只要是**诊断产出**（不要求战略建议），归 monitor + slice
- 只有**知识性研究**（了解现状/机制/流程），归 research_agent

### insufficient 分诊机制

`platform_verdict = insufficient` 的成因从 2 种扩展为 **3 种**，并新增 `insufficient_reason` 输出字段精确标记分诊方向。知识性/探索性与诊断型都按下游承接功能的子类型进一步细分，使前端能精准路由至对应入口。下表按**判断优先级从高到低**排列，LLM 命中第一个即判定，不再检查后续成因：

| 优先级 | 成因 | `insufficient_reason` | 触发条件 | 前端跳转 |
|--------|------|----------------------|---------|---------|
| ① 最优先 | **诊断型 brief（新增）** | `diagnostic_social` / `diagnostic_news` / `diagnostic_dual` | brief 只需诊断快照，不要求战略产出。按 channel_plan 推荐的渠道分三个子类 | 对应跳转社媒监测 / 新闻监测 / 两者并列 |
| ② 次优先 | 知识性/探索性 brief · 行业知识型 | `knowledge_industry` | brief 想了解品类结构 / 市场规模 / 政策趋势 / 技术原理 / 产业链 / 竞争格局结构性分析 | 前往专题研究 · 行业研究（`?profile=industry`） |
| ② 次优先 | 知识性/探索性 brief · 创意知识型 | `knowledge_creative` | brief 想了解品类 / 竞品的 Campaign 套路 / 创意案例 / 获奖作品 / 品牌叙事风格 / 传播创意历史 | 前往专题研究 · 创意研究（`?profile=creative`） |
| ③ 兜底 | 无可用渠道 | `no_channel` | channel_plan 未推荐 social_media 也未推荐 news_media（仅有 industry_research）。仅当 brief 既非诊断型也非知识型时触发——覆盖"战略性 brief 但渠道结构不支持"的罕见边角 case（如 B2B 工业品类的消费者诉求，但 social UGC 密度不足、无媒体事件可追踪） | 前往专题研究（默认 profile） |

**为何要定优先级**：诊断型信号最锐利（时间窗 + 动词 + 产出诉求三条硬信号），必须最先判才不会被知识性或"无渠道"误吸收；知识性次之，其枚举值明确 research_agent 的 profile，比 no_channel 更精准；`no_channel` 纯作结构性兜底，避免战略型 brief 在渠道不支持时无处可去。

**为何细分**：research_agent（专题研究）实际有 `industry` 和 `creative` 两个 profile，各自面向不同的数据源和产出形态（industry → 权威报告/政策/量化数据；creative → 数英/广告门/SocialBeta 创意案例库）。若 `knowledge_research` 不细分、一律默认落 `industry` profile，创意知识型 brief 会被错误导向行业报告搜索。与诊断型按 monitor 渠道细分的逻辑对称。

**诊断型 brief 的判断信号**（命中任一且无战略产出诉求即成立）：
- 时间窗为日/周/月级短期观察（而非半年/年度战略规划）
- 核心动词是"监测/追踪/复盘/观察/快照/简报"（而非"策略/规划/定位/方向"）
- 产出诉求是"看到了什么"（而非"应该怎么做"）

**硬约束**：`insufficient_reason` 仅当 `platform_verdict == "insufficient"` 时非空；`sufficient` / `partial` 时强制为空字符串。`parse_brief_parser_response` 在后端做 defensive normalize，即使 LLM 违规也强制修正（不信任 LLM 自报）。

### 前端路由策略

brief_parser 给出 `insufficient_reason` 后，`create.vue` 按 reason 决定显示哪个跳转按钮：

```
no_channel / ""      → 前往专题研究（/research-agent/create，默认 profile=industry）
knowledge_industry   → 前往专题研究 · 行业研究（/research-agent/create?profile=industry）
knowledge_creative   → 前往专题研究 · 创意研究（/research-agent/create?profile=creative）
diagnostic_social    → 前往社媒监测 + 切片分析（/social-media/monitors/create）
diagnostic_news      → 前往新闻监测 + 切片分析（/news-media/monitors/create）
diagnostic_dual      → 同时显示社媒 + 新闻两个按钮
```

研究创建页（[research-agent/create.vue](../../frontend/layers/research-agent/pages/research-agent/create.vue)）读取 `route.query.profile` 初始化 `formState.profile_name`，合法值为 `industry` / `creative`，否则回退至默认 `industry`。

---

## 结果

### Positive

- **诊断型 brief 找到正确归属**：不再被浪费性地跑完整 strategies 流水线，也不会被错分至能力不匹配的 research_agent
- **三层职责清晰**：每种产出需求都有明确入口，新需求落位有据
- **不增加架构复杂度**：monitor + slice 能力一直存在，本次只是让 brief_parser 识别并正确分诊
- **`insufficient_reason` 精确建模**：前端可以做有意义的路由而不是给用户一个错误按钮

### Trade-offs

- **诊断型判断信号依赖 LLM 语义识别**：若 brief 表述模糊（战略诉求 + 监测诉求混在一起），LLM 可能误分类。通过锐利的信号清单（时间窗 + 动词 + 产出诉求）缓解，但不能完全消除
- **诊断型 brief 保守偏置**：当 brief 同时包含诊断和战略诉求时，按 prompt 当前定义，只要有任何战略产出诉求就不判诊断——保证 strategies pipeline 不漏接，代价是纯诊断场景识别得稍保守

### 已知 Gap

**跨渠道诊断快照无统一入口**：用户想要"social + news 合并的市场诊断快照"时，当前 `diagnostic_dual` 会让用户分别建立 social monitor 和 news monitor，手动整合两边切片。

**未来补位方向**：如果需求足够，应在 **monitor 层**扩展"跨渠道聚合切片"能力（统一入口 + 合并输出），**不**在 strategies pipeline 新增 output_type。理由见下文 Alternative A。

---

## 备选方案（未采纳）

### A. 新增 `insight_brief` 作为 strategies pipeline 的第 4 种 output_type

**核心问题**：`output_depth` 和 `source_combo` 是正交维度。

现有 3 种 output_type 本质是按**主数据源组合**划分的：
- `campaign_strategy` = social
- `market_report` = news
- `full_strategy` = social + news

而 insight_brief 的差异是**产出深度**（浅 vs 深），不是数据源组合。把它塞进同一枚举会出现：
- 固定单一数据源定义 → 丢失"仅社媒诊断 / 仅新闻诊断 / 社媒+新闻联合诊断"的覆盖面
- 完整矩阵 → 3 × 2 = 6 种组合，产出路径爆炸，下游 chain 路由复杂度翻倍

不如让诊断产出归属 monitor + slice（它本来就是按单渠道独立设计的），strategies pipeline 继续专注战略产出。

### B. 复用 research_agent 承接诊断

**结构不匹配**：research_agent 的：
- Profile 只有 `industry` / `creative`，无通用诊断 profile
- 数据源是 Tavily / Exa / Crawl4AI 开放 Web 搜索，**不访问 social/news 数据库**
- 产出是"研究综述 + findings_by_question"形态，不是"情感分布 + KOL + Entity + Landscape"等诊断切片结构

扩展出第三个 profile 的代价（新 domain tiers + planner prompt + analyzer/synthesizer prompt）远超在 brief_parser 做分诊的代价。

### C. 不改，维持单路 insufficient 推至 research_agent

接受"诊断型 brief 要么被错分至 strategies pipeline 浪费采集，要么被单路甩给功能不匹配的 research_agent"的现状。对于主要用例（战略 brief）无影响，但对偶发的诊断型 brief 无解。

否决理由：诊断型 brief 不是偶发需求，而且 monitor + slice 能力一直存在，不承接是明显浪费。

---

## 实施记录

- `brief_parser_chain.py` 的 prompt 从 2 成因扩展为 3 成因，新增 `insufficient_reason` 字段规则；`parse_brief_parser_response` 增加 defensive normalize
- `ParseBriefResponse` schema 增加 `insufficient_reason: str = Field("", ...)`
- 前端 `ParseBriefResponse` 类型同步；`InsufficientReason` 联合类型新增
- 前端 `create.vue` 按 reason 分支渲染 1-2 个跳转按钮（原先硬编码单一按钮）

变更不涉及数据库迁移（`brand_brief` JSON 字段不存 insufficient_reason，它仅是 `parse-brief` 端点的响应字段，未进入持久化）。

---

## 引用

- 相关 ADR：ADR-001（分析架构选型，已 Closed；本 ADR 不依赖其决策）
- 相关文档：`docs/strategy-multi-source-architecture.md` Layer 0（brief 摄入与渠道分发）
- 触发讨论：Sony WH-1000XM6 H2 策略 brief 的解析评估（2026-04-21）
