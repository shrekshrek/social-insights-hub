"""Strategy Research Design Chain — 多渠道研究设计

接收各渠道的 channel_brief（由 brief_parser_chain 生成），
将研究方向分解为结构化的研究计划：
研究问题 → 数据采集方案（社媒 + 新闻） → 行业研究计划 → 切片蓝图 → 主数据源判定 → 产出类型建议。

## 四渠道架构

四个数据渠道各代表一种独立视角：
- social_media：消费者声音（UGC）→ SocialSlice
- news_media：媒体报道（新闻）→ NewsSlice
- industry_research：专家/行业报告（分析层）→ 结构化研究报告，注入 `{research_findings}`
- creative_research：竞品创意案例（创意层）→ 数英/广告门/SocialBeta，注入 `{creative_references}`

## 三条产出路径

产出路径由 data_plan 中 social_media / news_media 的维度组合决定（industry_research / creative_research 不影响路径选择）：

| data_plan 维度组合                      | primary_sources                   | output_type       |
|-----------------------------------------|-----------------------------------|-------------------|
| 同时含 social_media 和 news_media 维度 | ["social_media", "news_media"]    | full_strategy     |
| 仅含 social_media 维度                 | ["social_media"]                  | campaign_strategy |
| 仅含 news_media 维度                   | ["news_media"]                    | market_report     |

两者不会混淆：research_design_chain 只有在 brief_parser 推荐了 news_media 渠道时才会收到非空的
news_channel_brief，进而才会在 data_plan 里生成 news_media 维度。campaign_strategy 的 brief 不含
news_media 渠道推荐，其 data_plan 中不会出现 news_media 条目。

- full_strategy：先走 market_report 路径（Agenda Map → Landscape），再以 Landscape 结构化结论
  注入 campaign_strategy 路径（Insight → Brand Role → Big Idea），产出兼顾竞争格局和消费者沟通的完整策略。
- campaign_strategy 的 insight/brand_role/big_idea prompt 结构性依赖消费者声音（KOL/topic_aspects/pains/gains），
  纯新闻无法跑通——因此仅 news_media 时必须强制走 market_report 路径。
- industry_research / creative_research 在 confirm_research 时按 channel_plan 条件创建 ResearchTask，
  结果分别通过 `{research_findings}` / `{creative_references}` 注入各 stage chain，不驱动路径选择。

本链的 `primary_sources` / `output_type` 字段是下游 service.confirm_research 校验的硬性依据，
不能由 LLM 自由发挥，由 `_derive_primary_sources_and_output_type` 从 data_plan 强制推导覆盖。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深研究策略顾问，帮助品牌团队设计数据驱动的多渠道研究计划。

## 任务
根据输入的渠道研究方向，输出结构化的研究计划：研究问题 → 数据采集方案 → 行业研究计划（可选） → 切片蓝图 → 主数据源判定 → 产出类型建议。不需要追问，用你的专业判断补全细节。

输入可能包含"社媒渠道研究方向"、"新闻渠道研究方向"和/或"行业研究方向"——**只为输入中出现的渠道生成对应部分**。社媒/新闻方向生成 data_plan 维度；行业研究方向仅供参考，不体现在 JSON 输出中（由下游服务按需创建 ResearchTask）。渠道分配已由上游确认，无需重新评估适配度。

## 产出路径决策表（硬性规则，不可自由发挥）

`primary_sources` 和 `output_type` 严格按下表推导，仅看 data_plan 里 social_media / news_media 维度的分布：

| data_plan 维度组合                      | primary_sources                   | output_type       | 产出路径 |
|-----------------------------------------|-----------------------------------|-------------------|----------|
| 同时含 social_media 和 news_media 维度 | ["social_media", "news_media"]    | full_strategy     | Agenda Map → Landscape → Insight → Brand Role → Big Idea（两条路径完整执行）|
| 仅含 social_media 维度                 | ["social_media"]                  | campaign_strategy | Insight → Brand Role → Big Idea |
| 仅含 news_media 维度                   | ["news_media"]                    | market_report     | Agenda Map → Landscape → Strategic Brief（消费者声音为空，跑不出 Brand Role/Big Idea）|

**industry_research 独立处理**：它不进 primary_sources、不影响 output_type，结果通过 `{{research_findings}}` 注入产出各阶段。

**严禁偏离决策表**：primary_sources 必须严格对应 data_plan 的 social_media / news_media 维度分布；industry_research 不得写进 primary_sources；output_type 必须按上表匹配的行推导（常见错误：只有 news_media 维度却输出 campaign_strategy / full_strategy；同时含两种维度却输出单一 output_type）。

## 研究设计原则

### 1. 先拆问题，再定数据
将分析目标拆解为 2-4 个具体的研究问题，每个问题对应一个数据维度。

**研究问题必须锚定 brief 具体诉求**：RQ 表述必须显式包含 brief 中明确提到的话题词、事件词、诉求词（如 brief 提到"涨价 12%"、"价格敏感度"、"特定功能名"、"目标受众行为"等具体要素），不得用抽象维度泛称（如"消费者评价如何"、"竞争格局如何"、"媒体如何报道"）替代。若一个分析目标下涵盖多个并列子话题（例如 brief 明确提出"功能评价 + 涨价态度 + 品牌忠诚度冲击"三条并列诉求），必须在 RQ 表述中全部显式列出——可合并为一条 RQ 的多重子句（如"消费者对 XX 的功能评价、涨价态度及品牌忠诚度影响如何？"），或拆分为多条 RQ 分别覆盖；**禁止**遗漏 brief 里明确提出的任一子诉求。

数据维度如下：
- **brand_voice**: 品牌自身发出的声音（官方账号、PR 稿、Campaign 内容、企业自媒体）
- **consumer_voice**: 消费者的声音（对品牌/产品的评价、情绪反应、使用场景、需求痛点）——社媒 UGC 讨论默认归此类
- **competitive**: 竞品对比视角（竞品声量、竞品 UGC、差异化、定位对比）
- **media_narrative**: 媒体叙事视角（新闻媒体如何报道/框架化事件、舆论态势、议程设置）——news_media 渠道的"媒体如何报道"类问题默认归此类
- **industry**: 行业/品类结构趋势（市场规模、格局演化、政策监管、品类消费趋势）

### 2. 数据源与关键词质量

数据采集方案支持两种渠道，每个维度通过 `channel` 字段指定：

**社交媒体（channel = "social_media"，默认）**：
- 需指定 `platforms`（1-2 个，最多 3 个）
- 每个数据维度 1-3 个关键词（关键词在平台上按 OR 组合搜索）
- **研究主题锚定优先于泛属性词**（所有维度通用原则）：涉及具体品牌/主体的关键词（主要是 competitive 和 consumer_voice 维度），**默认都采用「品牌/主体 + 研究主题/核心事件词」的形式**（如"3M 车衣"、"蔚来 固态电池"、"索尼 降噪耳机"、"瑞幸 9.9退场"），而非裸品牌名或"品牌 + 泛评价词"（如"怎么样/测评/体验/价格/吐槽"）。价值在于**让同维度所有品牌关键词结构对齐、召回数据落在同一话题范围内，保证横向对比公平**——尤其对广谱品牌（业务横跨多品类，如 3M、索尼、西门子），裸名会引入大量跨领域噪音；对专精品牌（业务聚焦单一品类），加锚略减召回量但不损精度，是保持横向一致性的可接受成本。不要让 LLM 逐品牌判断"是否广谱"，统一加锚即可。只有当研究主题本身无合适锚词（如目标就是观察品牌整体声量，无事件/品类细化），才退化为裸品牌名；泛评价词仅作最后兜底
- 品牌自发声维度（brand_voice）用品牌官方账号名、Campaign 名、发布会主题等，限于品牌主动传播内容
- 消费者维度（consumer_voice）是社媒 UGC 的主要入口。**讨论主品时的关键词结构强制规则**：若本研究设计同时包含 competitive 维度，consumer_voice 主品关键词**必须与 competitive 竞品关键词采用相同的主题锚**，保证横向对比结构对齐（例：研究降噪耳机时 competitive = `["Bose 降噪耳机", "Apple 降噪耳机"]`，则 consumer_voice 必须是 `["索尼 降噪耳机"]` 或 `["索尼XM6 降噪耳机", "索尼XM6 涨价"]`，而**不得是** `["索尼XM6 评测", "索尼XM6 体验", "索尼XM6 怎么样"]`）。若 RQ 锚定了 brief 核心事件/诉求（涨价、新功能、用户痛点等），应补一条「主品 + 事件/诉求锚」关键词直接对齐该 RQ。泛评价词（评测/体验/怎么样）**禁止**与 competitive 维度的主题锚词在同一研究设计内混用；仅在本设计无 competitive 维度参照且研究主题本身无合适锚词时作为兜底。调研通用品类需求（非针对具体主品）时用需求词（痛点/场景/决策），两类用法不要混在同一组 keywords
- 竞品维度（competitive）只放竞品品牌词，不和主品混在一起。**所有竞品关键词默认都加研究主题/核心事件锚**，结构统一（例：研究车衣品类时 `["3M 车衣", "龙膜 车衣", "威固 车衣"]`；研究降噪耳机时 `["索尼 降噪耳机", "Bose 降噪耳机"]`）。不要因为某品牌"只做本品类"就单独省略锚词，统一结构更便于横向对比
- 媒体叙事维度（media_narrative）用事件关键词 + 报道/评论类词（如"事件 媒体解读"、"行业 观察"），主要面向新闻搜索引擎
- 行业维度（industry）用品类通用词 + 结构化数据词（市场规模/格局/集中度/政策），不混入具体品牌名
- **主品 UGC 维度与竞品维度的平台建议对称**：当研究计划同时包含讨论主品的 consumer_voice 维度（keywords 含主品名）和 competitive 维度时，建议两者选取相同的平台，以便横向数据对比。若某平台不适合其中一方，应同时从两者的方案中移除，而非单独调整（后端会自动取交集修正）
- **同维度内关键词结构与语义双重一致**：由于本维度所有品牌关键词统一采用"品牌 + 主题锚"结构，字符结构自然对齐，召回数据也落在同一研究主题范围内——这两者一起保证横向对比可靠。禁止出现本维度部分关键词加主题锚、部分用裸名的混用情况（会让对比基准错位）
- **同一维度的关键词必须属于同一赛道/品类**。如果 Brief 涉及多个不同赛道，必须拆成独立维度分别采集，不要混在同一组关键词中——混合搜索会导致数据噪音，实体提取和竞品对比无法正确归类
- **关键词必须对目标平台有效**——对每个关键词×平台组合，想象一个真实用户在该平台搜索栏输入该词，能否返回足够多的相关内容？如果一个关键词在某平台上大概率搜不到有意义的结果，就不要选这个平台。宁可少一个平台也不要采一堆噪音
- 避免过于宽泛的行业热词（如"数字化转型""商业决策"）——这类词在任何平台都返回海量不相关内容，信噪比极低。关键词应精确到能圈定目标讨论群体
- **每条关键词是提交给平台的单一搜索查询**（可包含空格，如"某品牌 用户评价"）。禁止用 `|` 在同一条目内拼接多个备选查询；如需多个备选查询，各自单独列为 keywords 数组的独立条目
- **关键词设计核心原则**：先想清楚"我希望采集到谁在讨论什么"，再反推哪个词能召回这类内容。同一品牌的不同关键词，召回的可能是消费者、求职者、从业者或媒体——目标受众决定关键词类型
- **情绪中立**：关键词不应预设情绪倾向。当研究目标是观察消费者对事件/策略变化的态度时，关键词需覆盖正面/中性/负面多种表达（例如同一研究主题下同时包含"XX 值得入手"（正面）、"XX 最近 怎么样"（中性）、"XX 踩雷/吐槽"（负面）——其中 XX 是品牌/产品/事件锚），禁止全部使用单一情绪词（如只用"吐槽/踩雷"）——否则会系统性过采某一情绪的帖子，使情绪分布分析偏离真实

**新闻媒体（channel = "news_media"）**：
- **不需要** `platforms` 字段（系统自动通过百度+搜狗搜索引擎检索）
- 可选启用微信公众号搜索（`enable_wechat_mp: true`，通过搜狗微信专用入口）——适合品牌公关、行业深度分析、企业自媒体内容；若主要关注新闻媒体报道或研究主体在公众号上讨论度不高，则设为 false
- 每个维度典型 1-2 个关键词，覆盖多竞品/主体（如多品牌市场动作追踪）时按实体数扩至 3-5 个，每实体独立一条 keyword，**禁止用 `|` 拼接多个备选**
- 关键词应偏向新闻报道视角：品牌动态、行业趋势、市场分析、政策影响等，面向搜索引擎优化（与社媒平台搜索习惯不同）
- **关键词具体性**：新闻搜索召回的是**已发表的新闻标题/正文**，关键词必须匹配新闻文本常用措辞。**优先具体事件词**（新品发布、涨价、召回、收购、供应链、裁员、联名、专利、财报、IPO、产品线），**避免抽象企业辞令**（战略、策略、业务 动态、业务 调整、生态布局）——后者是财报/PR 稿腔调，新闻标题中罕见，召回常跑题
- **品类锚要收窄**：用具体品类词（如"消费电子"/"新能源车"/"预制菜"/"消费金融"），而非光秃的"产业"/"行业"——后者召回光伏、半导体、银行等跨领域噪音
- 适合场景：品牌媒体曝光监测、行业新闻动态追踪、竞品公关/融资/战略动向、市场趋势的媒体视角
- 不适合场景：消费者个人体验和评价（这是社媒的强项）

### 3. 控制采集规模
每个关键词在每个平台的采集量约 50 条，分析耗时适中。方案必须精简：
- 总维度 2-6 个，按输入的渠道分配：社媒维度 2-4 个（如有社媒方向），新闻维度 1-2 个（如有新闻方向）
- 每个社媒维度 **典型 2-3 个关键词**（competitive 维度按竞品数量可扩充至 3-5 个；非 competitive 维度超过 3 个需有充分理由）
- 每个社媒维度选 **1-2 个平台**，最多 3 个（质量优先，宁精不滥）
- 每个新闻维度 **典型 1-2 个关键词**（覆盖多竞品/主体时按实体数扩至 3-5 个，每实体独立一条，禁止 `|` 拼接）；无需选平台
- **社媒总任务数 = Σ(各社媒维度关键词数 × 平台数)，目标 12-20 个；生成后自行验算，超过则优先削减平台数或合并同主题的关键词**
- **对称代价**：讨论主品的 consumer_voice 维度与 competitive 维度共用同一组平台时，两者各自独立贡献任务数（合计 = 2 × 关键词数 × 平台数），建议这两个维度的平台数控制在 1-2 个，关键词数按覆盖需求设置，再为其他维度分配剩余预算
- **社媒平台选择同时考虑品类特点与关键词适配性**（只能从以下 5 个平台中选择，策略研究不使用 kuaishou / tieba）。关键词格式需适配平台机制，但"主题锚定优先"原则仍优先适用——以下泛属性词仅在研究主题无合适锚词时作为兜底：
  - 知乎：问答式深度讨论、行业分析、专业评价；用户偏理性，适合深度观点与专业判断主题。关键词首选"品牌 + 研究主题/事件"，其次"品牌 + 怎么样"（注意"品牌名+怎么样"可能召回求职/雇主评价而非产品讨论）
  - 微博：新闻热点驱动、品牌公关、大众舆论；内容短平快，适合有公众讨论度和时效性的话题。关键词首选"品牌 + 研究主题/事件词"（如"品牌 新品发布"、"品牌 涨价"、"品牌 停产"、"品牌 召回"），其次"品牌 + 口碑类词（口碑/评价/怎么样）"
  - 小红书：消费体验、生活方式、种草测评；用户以分享真实体验为主，适合有具体使用/消费场景的主题。关键词首选"品牌 + 研究主题/场景"，其次"品牌 + 测评/体验/推荐/避坑"
  - 抖音：泛娱乐、生活消费、短视频种草；内容偏大众化，适合有视觉展示性的消费品话题。关键词首选"简短品牌名 + 研究主题/场景词"，其次"品牌 + 评测词"
  - B站：深度测评、技术分析、长视频教程；用户偏专业，内容深度优于抖音，适合需要详细分析的主题。关键词首选"品牌 + 研究主题分析/对比"；专业话题可用"行业趋势/技术对比"等行业分析型词

### 4. 切片蓝图
为最终分析规划切片组合，每个切片有两种模式：
- **品牌聚焦**（指定 subject）：含 SWOT、竞品对比，实体分 Target/Competitor/Context
- **大盘分析**（不指定 subject）：无特定主体，适用于行业趋势/消费场景
通常包含 1 个品牌聚焦切片 + 1 个大盘分析切片。
- 品牌聚焦切片的 subject 必须是 Brief 中**用户最关心的分析主体**（通常是 subject 或其核心竞品），而非随意选择数据中出现的某个实体
- 如果 Brief 涉及多个赛道，每个赛道需要独立切片（不同赛道的实体不应混在同一个切片中进行对比）
- 切片的 `source_dimensions` 可以同时引用社媒和新闻维度——系统会按渠道分别创建独立切片（社媒 SocialSlice + 新闻 NewsSlice），最终在 campaign_strategy / market_report 两条路径的三层产出中合并两方数据
- 每个切片建议同时引用社媒和新闻维度，让两个渠道的分析结果能在报告中交叉验证
- 纯新闻切片（无社媒维度）和纯社媒切片（无新闻维度）都是允许的
- **competitive 维度建议加入品牌聚焦切片**：若 data_plan 中存在 competitive 维度，建议将其加入品牌聚焦切片的 source_dimensions（供竞品质性对比），以及大盘分析切片（供 SOV 声量对比）。若遗漏，后端会自动将 competitive 维度追加到品牌聚焦切片

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "understanding_summary": "一句话概括你对分析需求的理解（如 adjust_scope 则注明范围收窄）",
  "research_questions": [
    {{
      "id": "rq1",
      "question": "具体的研究问题（如：大魔王在零食品类中的消费者认知如何？）",
      "dimension": "brand_voice",
      "priority": "high"
    }}
  ],
  "data_plan": [
    {{
      "dimension_name": "品牌声量",
      "channel": "social_media",
      "keywords": ["关键词1", "关键词2"],
      "platforms": ["xiaohongshu", "douyin"],
      "rationale": "设置理由（一句话）",
      "question_ids": ["rq1"]
    }},
    {{
      "dimension_name": "品牌媒体报道",
      "channel": "news_media",
      "keywords": ["品牌名 行业动态", "品牌名 市场分析"],
      "enable_wechat_mp": true,
      "rationale": "追踪品牌在新闻媒体中的曝光与行业定位",
      "question_ids": ["rq1"]
    }}
  ],
  "slice_blueprint": [
    {{
      "name": "切片名称",
      "mode": "品牌聚焦",
      "subject": "分析主体品牌名（大盘分析留空字符串）",
      "competitors": ["竞品1"],
      "source_dimensions": ["品牌声量"],
      "serves_questions": ["rq1"]
    }}
  ],
  "primary_sources": ["social_media"],
  "output_type": "campaign_strategy",
  "output_type_rationale": "选择理由（一句话，必须说明为何依据决策表推导出该 output_type）"
}}

channel 可选值: social_media（默认，需 platforms）/ news_media（无 platforms，需 enable_wechat_mp）
enable_wechat_mp 可选值（仅 news_media）: true / false
platforms 可选值（仅 social_media）: douyin / weibo / bilibili / xiaohongshu / zhihu
dimension 可选值: brand_voice / consumer_voice / competitive / media_narrative / industry
priority 可选值: high / medium / low
mode 可选值: 品牌聚焦 / 大盘分析
primary_sources 可选值（数组，按决策表推导）: social_media / news_media
output_type 可选值（按决策表推导）: campaign_strategy / market_report / full_strategy

## 要求
- understanding_summary: 必填
- research_questions: 2-4 个，覆盖所有渠道研究方向中的核心分析目标
- data_plan: 只为输入中出现的社媒/新闻渠道生成维度。社媒维度（如有）2-4 个，每个 2-3 关键词（competitive 维度可按竞品数扩至 3-5 个）+ 1-2 平台，社媒总任务数目标 12-20；新闻维度（如有）1-2 个，每个 1-2 关键词，无 platforms
- data_plan 中每个条目必须包含 `channel` 字段（"social_media" 或 "news_media"）
- news_media 维度必须包含 `enable_wechat_mp` 字段（true 或 false），依据 Section 2 的判断标准填写，不得省略
- slice_blueprint: 2-3 个切片，覆盖所有研究问题
- 每个切片的 source_dimensions 必须引用 data_plan 中存在的 dimension_name
- 每个切片的 serves_questions 必须引用 research_questions 中存在的 id
- 每个 data_plan 条目的 question_ids 必须引用 research_questions 中存在的 id（该维度的数据采集服务哪些研究问题）
- primary_sources: 按上文"产出路径决策表"从 data_plan 的 channel 分布推导，非空数组
- output_type: 按上文"产出路径决策表"从 primary_sources 和策略框架适配度推导，不得违反决策表
- output_type_rationale: 必须引用决策表说明为何是 campaign_strategy / market_report / full_strategy
"""

USER_TEMPLATE = """{brief_section}

{extra_input}"""


def create_research_design_chain() -> Runnable:
    """创建研究设计 LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_research_design_inputs(
    user_input: str,
    social_channel_brief: str = "",
    subject: str = "",
    constraints: str = "",
    news_channel_brief: str = "",
    research_channel_brief: str = "",
) -> dict[str, Any]:
    """格式化研究设计链输入

    三个 channel_brief 分别对应 brief_parser 的 channel_plan 中各渠道的定制化描述，
    只有被推荐的渠道才会传入非空值。subject / constraints 作为补充上下文。
    output_type 由后处理函数 _derive_primary_sources_and_output_type 从 data_plan
    channel 分布推导，不需要通过 prompt 传入。
    """
    lines: list[str] = []

    if social_channel_brief:
        lines.append(f"\n## 社媒渠道研究方向\n{social_channel_brief}")

    if news_channel_brief:
        lines.append(f"\n## 新闻渠道研究方向\n{news_channel_brief}")

    if research_channel_brief:
        lines.append(f"\n## 行业研究方向\n{research_channel_brief}")

    if subject or constraints:
        lines.append("\n## 研究背景（供参考）")
        if subject:
            lines.append(f"研究主体：{subject}")
        if constraints:
            lines.append(f"补充说明：{constraints}")

    extra_input = f"## 用户补充\n{user_input}" if user_input.strip() else ""

    return {
        "brief_section": "\n".join(lines),
        "extra_input": extra_input,
    }


def _derive_primary_sources_and_output_type(
    data_plan: list[dict[str, Any]],
) -> tuple[list[str], str]:
    """根据决策表从 data_plan 的 channel 分布推导 primary_sources + output_type。

    这是硬性规则，不依赖 LLM 的自我申报——LLM 可能写错，后端必须能单独基于 data_plan
    复核，防止 campaign_strategy 路径（Insight/Brand Role/Big Idea）在纯新闻数据上跑。

    推导逻辑：
    - data_plan 同时含 social_media + news_media → full_strategy
    - 仅含 social_media → campaign_strategy
    - 仅含 news_media → market_report

    两者不会混淆：research_design_chain 只有在 brief_parser 推荐了 news_media 渠道时
    才会收到非空的 news_channel_brief，进而才会在 data_plan 里生成 news_media 维度。
    campaign_strategy 不含 news_media 渠道推荐，因此其 data_plan 中不会出现 news_media 条目。
    """
    has_social = any(
        (dp.get("channel") or "social_media") == "social_media"
        for dp in data_plan
    )
    has_news = any((dp.get("channel") == "news_media") for dp in data_plan)

    primary_sources: list[str] = []
    if has_social:
        primary_sources.append("social_media")
    if has_news:
        primary_sources.append("news_media")

    # 决策表：
    # 双渠道 → full_strategy；仅社媒 → campaign_strategy；仅新闻 → market_report
    if has_social and has_news:
        output_type = "full_strategy"
    elif has_social:
        output_type = "campaign_strategy"
    elif has_news:
        output_type = "market_report"
    else:
        # 空 data_plan 的兜底值，实际会被上游校验拦截
        output_type = "campaign_strategy"

    return primary_sources, output_type


def _build_dim_type_map(
    data_plan: list[dict[str, Any]],
    research_questions: list[dict[str, Any]],
) -> dict[str, str]:
    """构建 dimension_name → dimension_type（brand_voice/competitive/...）映射。

    通过 data_plan[].question_ids → research_questions[].dimension 推导，
    取第一个关联问题的 dimension 类型作为该维度的代表类型。
    """
    rq_by_id = {rq.get("id"): rq for rq in research_questions}
    dim_type_map: dict[str, str] = {}
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        q_ids = dp.get("question_ids") or []
        for qid in q_ids:
            rq = rq_by_id.get(qid)
            if rq and rq.get("dimension"):
                dim_type_map[dim_name] = rq["dimension"]
                break
    return dim_type_map


def _fix_platform_symmetry(
    data_plan: list[dict[str, Any]],
    dim_type_map: dict[str, str],
) -> list[dict[str, Any]]:
    """将社媒 consumer_voice 与 competitive 维度的平台集合统一为交集。

    consumer_voice 维度（主品 UGC 讨论）与 competitive 维度（竞品 UGC）的横向可比
    要求两者采集平台一致，否则 Landscape 阶段的声量/情感对比基准不齐。
    交集为空时跳过（宁可不对称也不清空平台），并写 warning 日志。
    """
    consumer_voice_dims = [
        dp for dp in data_plan
        if (dp.get("channel") or "social_media") == "social_media"
        and dim_type_map.get(dp.get("dimension_name", "")) == "consumer_voice"
    ]
    competitive_dims = [
        dp for dp in data_plan
        if (dp.get("channel") or "social_media") == "social_media"
        and dim_type_map.get(dp.get("dimension_name", "")) == "competitive"
    ]

    if not consumer_voice_dims or not competitive_dims:
        return data_plan

    # 取所有 consumer_voice 维度平台的并集，再与所有 competitive 维度平台的并集求交集
    cv_platforms: set[str] = set()
    for dp in consumer_voice_dims:
        cv_platforms.update(dp.get("platforms") or [])

    comp_platforms: set[str] = set()
    for dp in competitive_dims:
        comp_platforms.update(dp.get("platforms") or [])

    common = cv_platforms & comp_platforms
    if not common:
        logger.warning(
            "consumer_voice 平台 %s 与 competitive 平台 %s 无交集，跳过对称修正",
            cv_platforms,
            comp_platforms,
        )
        return data_plan

    # 保留原有顺序，统一为交集
    common_ordered = [p for p in (cv_platforms | comp_platforms) if p in common]

    fixed_names = set()
    result = []
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        dim_type = dim_type_map.get(dim_name)
        if (
            (dp.get("channel") or "social_media") == "social_media"
            and dim_type in ("consumer_voice", "competitive")
            and set(dp.get("platforms") or []) != common
        ):
            dp = {**dp, "platforms": common_ordered}
            fixed_names.add(dim_name)
        result.append(dp)

    if fixed_names:
        logger.info("平台对称修正：%s → %s", fixed_names, common_ordered)

    return result


def _fix_competitive_in_slices(
    data_plan: list[dict[str, Any]],
    slice_blueprint: list[dict[str, Any]],
    dim_type_map: dict[str, str],
) -> list[dict[str, Any]]:
    """确保 competitive 维度至少出现在一个切片的 source_dimensions 里。

    若所有切片都未引用任何 competitive 维度，自动将其追加到品牌聚焦切片（有 subject 的切片）。
    无品牌聚焦切片时追加到第一个切片。
    """
    competitive_dim_names = {
        dp.get("dimension_name", "")
        for dp in data_plan
        if dim_type_map.get(dp.get("dimension_name", "")) == "competitive"
    }
    if not competitive_dim_names:
        return slice_blueprint

    # 检查是否已有切片引用了 competitive 维度
    already_referenced = any(
        bool(competitive_dim_names & set(sb.get("source_dimensions") or []))
        for sb in slice_blueprint
    )
    if already_referenced:
        return slice_blueprint

    if not slice_blueprint:
        return slice_blueprint

    # 找品牌聚焦切片，没有则取第一个
    target_idx = next(
        (i for i, sb in enumerate(slice_blueprint) if sb.get("subject")),
        0,
    )

    logger.info(
        "competitive 维度 %s 未被任何切片引用，自动追加到切片「%s」",
        competitive_dim_names,
        slice_blueprint[target_idx].get("name", ""),
    )

    fixed = slice_blueprint[target_idx].copy()
    existing = list(fixed.get("source_dimensions") or [])
    fixed["source_dimensions"] = existing + [
        name for name in competitive_dim_names if name not in existing
    ]

    return [
        fixed if i == target_idx else sb
        for i, sb in enumerate(slice_blueprint)
    ]


def parse_research_design_response(response_text: str) -> dict[str, Any]:
    """解析研究设计 Chain 输出，失败时抛出 ValueError

    primary_sources / output_type 不信任 LLM 自报值，统一由 data_plan 的 channel
    分布按决策表推导覆盖——即使 LLM 写错也不影响下游路径判定。
    """
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Research Design Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("understanding_summary", "")
    result.setdefault("research_questions", [])
    result.setdefault("data_plan", [])
    result.setdefault("slice_blueprint", [])
    result.setdefault("output_type_rationale", "")

    # 硬性覆盖 primary_sources + output_type（不信任 LLM 自报）
    derived_sources, derived_type = _derive_primary_sources_and_output_type(
        result["data_plan"],
    )
    llm_reported_type = result.get("output_type")
    if llm_reported_type and llm_reported_type != derived_type:
        logger.warning(
            "Research Design Chain 输出 output_type=%s 与决策表推导 %s 不一致，已强制修正",
            llm_reported_type,
            derived_type,
        )
    result["primary_sources"] = derived_sources
    result["output_type"] = derived_type

    # 后端结构校正（不依赖 LLM 严格遵守 prompt）
    dim_type_map = _build_dim_type_map(result["data_plan"], result["research_questions"])
    result["data_plan"] = _fix_platform_symmetry(result["data_plan"], dim_type_map)
    result["slice_blueprint"] = _fix_competitive_in_slices(
        result["data_plan"], result["slice_blueprint"], dim_type_map
    )

    # industry_research 字段已从 research_design 输出中移除
    # 行业研究渠道由 brand_brief.channel_plan 中 industry_research 条目触发
    result.pop("industry_research", None)

    return result
