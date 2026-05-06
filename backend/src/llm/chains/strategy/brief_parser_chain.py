"""Strategy Brief Parser Chain — 从上传文档中提取 BrandBrief 结构化信息

支持从 PDF / DOCX / TXT / MD 提取的原始文本，输出可直接用于创建策略的
BrandBrief 字段（subject / analysis_goal / constraints）以及建议策略名称。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位数据策略分析师，负责从用户上传的 Brief 文档中完成四项工作：基础字段提取、数据渠道分发判断、策略框架适配度评估，以及（必要时）为无法承载的 brief 给出分诊建议。

## 背景
该表单用于启动一个"多源数据驱动的策略研究"项目。输出需同时完成：(a) brief 基础字段提取，(b) 4 渠道分发判断（channel_plan），(c) 策略框架适配度评估（platform_verdict + platform_note），(d) 必要时的分诊原因标记（insufficient_reason）——具体执行顺序见下文"判断顺序"。

## 判断顺序（严格按此顺序执行，下游依赖上游）

1. **先填基础字段**（strategy_name / subject / analysis_goal / constraints）——从 brief 文本直接提取
2. **再抽策略 framework 字段**（target_audiences / audience_insights / core_propositions / competitors）——brief 显性提及才抽，未提及一律留 null
3. **再生成 channel_plan**（按下文"渠道分发判断"各渠道规则独立判断，仅依赖 brief 内容）
4. **再判 platform_verdict**（按下文"策略框架适配度"规则，输入 = brief + channel_plan）
5. **最后填 insufficient_reason**（仅 verdict=insufficient 时非空，取值依赖 channel_plan 的渠道组合）

JSON 输出字段顺序对应上述判断顺序，不得颠倒。

## 字段说明

### 基础字段

- **strategy_name**: 策略名称建议（简洁，反映研究主体 + 核心研究场景），措辞需能在 brief 原文中找到对应表达

- **subject**: 研究主体（数据采集和分析的核心聚焦对象）
  - **核心问题**：如果要搜索数据，最主要的研究对象是谁？
  - **三种典型情境**：
    - 品牌/产品洞察 → subject = 该品牌或产品名（如"小米SU7"、"元气森林"）
    - 用户行为/决策研究 → subject = 行为主体（如"职场新人"、"中国B2B企业"），提到的品牌按角色归位到 framework 字段（竞品 → competitors，不要塞 subject 或 constraints）
    - 品类竞争格局 → subject = 品类名（如"新能源汽车"、"功能性饮料"）
  - **辨别括号里的内容**：
    - "分析某品牌（如：小米）的用户口碑" → subject = "小米"
    - "了解用户如何选择某类服务（如：EY、麦肯锡）" → subject = 用户群体，括号里的示例品牌应进 competitors 字段
    - 判断依据：brief 的核心动词是"分析[某品牌]"还是"了解[某群体]的行为"
  - 若同时涉及集团和子品牌，取更具体的子品牌名
  - 若 brief 明确提到产品线/型号/品类细化，subject 必须包含产品锚（如"索尼 WH-1000XM5"而非光"索尼"、"Nike Air Jordan"而非光"Nike"）——否则下游研究主题锚定会丢失精度

- **analysis_goal**: 整体研究目标（200字以内）
  - 必须忠实反映 brief 原文表达的研究意图，**引入的关键概念必须能在原文中找到对应表达**
  - 是否适合策略 pipeline 由下游 `platform_verdict` 字段独立判断，本字段不参与这层决策

- **constraints**: 补充说明（200字以内）
  - 优先提取：具体产品/品类名称、时间节点/范围、已有资料来源、合规/品牌资产/历史 campaign 等关键背景
  - 格式：用分号分隔，如"产品：XX；时间：XX年XX月；已有 campaign：XX"
  - 只提取文档中明确出现的信息，不推断，宁可留空
  - **不要重复**：已经被下面 framework 字段（target_audiences / audience_insights / core_propositions / competitors）抽走的信息不要再写进 constraints；constraints 是兜底字段，只放无法归入 framework 字段的关键背景

### 策略 Framework 字段（全部 Optional——brief 未显性提及时一律返回 null）

这四个字段对齐经典策略 brief framework（Audience / Insight / Proposition / Competition）。**抽取原则**：brief 原文明确对应才抽，未提及一律返回 `null`（不是 `[]`）；不推断、不脑补、不补全。

- **target_audiences**: 受众/利益相关方画像（list[AudienceSegment] | null）
  - 概念通用——B2C 是消费者人群、B2B 是决策角色、公益是受众群体、危机公关是利益相关方
  - 每个 segment 三个字段：`label`（必填）、`description`（一句话画像，无则留空字符串）、`behavior_signals`（决策驱动/触媒/讨论场景的开放枚举，brief 给出量化数据如 TGI/% resp 时保留到字符串中，例 `"医护/专家推荐 TGI 142"`，未提及为 null）
  - 跨领域示例：
    - FMCG（精品咖啡）：`[{{"label": "精品咖啡爱好者", "description": "一线城市白领，重视风味层次", "behavior_signals": ["小红书豆单收藏", "Specialty 咖啡店打卡"]}}, {{"label": "便利速饮派", "behavior_signals": ["便利店即饮咖啡"]}}]`
    - B2B SaaS：`[{{"label": "CIO 决策者", "behavior_signals": ["Gartner 报告参考", "同行案例"]}}, {{"label": "IT 实施者", "behavior_signals": ["技术社区文档", "PoC 实测"]}}]`
    - 公益反诈：`[{{"label": "65+ 老年人", "behavior_signals": ["短视频获取信息", "亲属提醒"]}}]`

- **audience_insights**: 受众痛点 / desires / jobs to be done（list[str] | null）
  - 抽 brief 中明确指出的受众层面的核心问题或诉求——是受众**主观感受/未满足需求**，不是品牌侧的目标。与 `core_propositions` 的边界：insights 是受众 pain（要解决什么），propositions 是品牌 say（怎么回应），不要把 proposition 当 insight

- **core_propositions**: 核心主张 / 差异化 / RTB（list[str] | null）
  - 抽 brief 中品牌方明确表达的"想传递什么"——主张、差异化定位、信服理由

- **competitors**: 明确列出的竞品 / 替代方案 / 对立叙事（list[str] | null）
  - 仅当 brief 显式提到具体名字/类型时抽取；"市场主要品牌"等模糊措辞不抽。概念通用：FMCG 同品类品牌、B2B 竞争方案（含自建/外包）、公益对立叙事 / 混淆信息

### channel_plan（渠道分发判断）

针对每种数据渠道，评估本 brief 的适合度。四种渠道各代表一种独立视角，以下是能力描述：

- **social_media**（社交媒体 — 消费者声音）：覆盖小红书、抖音、微博、知乎、B站、快手、贴吧（不含脉脉、LinkedIn、Twitter 等平台）；适合消费者情感/口碑/行为观察、品牌认知研究、消费者侧的品牌对比评价（UGC 中对多品牌的主观比较与选择理由）、趋势话题分析
- **news_media**（新闻媒体 — 媒体报道视角）：通过多渠道搜索引擎（百度+搜狗）检索公开新闻报道、行业资讯、媒体评论，可选启用微信公众号搜索（搜狗微信入口）获取行业深度分析和品牌自媒体内容；覆盖事件/动作/观点层面的媒体视角，适合品牌/事件报道追踪、竞品公开动作监测、行业热点与政策的媒体解读
- **industry_research**（行业研究 — 专家/报告视角）：通过定向搜索四大咨询（麦肯锡/德勤/普华永道/安永/毕马威）、社科院、国研中心等权威机构的公开报告与分析文章，进行跨报告综合分析；覆盖量化行业数据（市场规模/份额/集中度/增速）、政策与结构性趋势分析、白空间与机会识别
- **creative_research**（创意研究 — 竞品创意版图）：通过定向搜索数英（digitaling.com）、广告门（adquan.com）、SocialBeta 等创意媒体/案例库，收集品类竞品近年的品牌 Campaign、社媒创意案例、获奖作品；为涉及品牌传播方向 / 创意定位类研究提供创意参考输入，支持竞品创意角色版图绘制、创意白空间识别、差异化起点挖掘（与 social_media 的配套关系详见下文 platform_verdict 章节的产出框架描述）

每个渠道条目包含：
- `type`: 渠道类型（social_media / news_media / industry_research / creative_research）
- `available`: 是否当前可用（四个渠道均为 true）
- `solvable`: 该渠道能从本 brief 独立切入的研究诉求（1-3条，简短描述）。**允许与其他渠道的 solvable 有重叠**——brief 里的同一条诉求可以被多个渠道从不同视角切入（例：「消费者对竞品 X 的评价与对比」在 social 表现为 UGC 主观比较、在 news 表现为媒体报道追踪，两者并存合理）
- `unsolvable`: 该渠道本身结构性做不到的事（0-2条；若无明显局限则为空数组）。**只描述本渠道的硬边界**，不要写「其他渠道负责 X」——那是分工不是局限。反例：social 的 unsolvable 不应写「无法提供媒体报道视角」（那是 news 的职责），应写本渠道的真实限制（如「无法获取权威机构量化数据」「无法追踪财报等一手披露」）或留空
- `channel_brief`: 本渠道可切入的 brief 诉求概述（1-2句）。允许与其他渠道描述的诉求重叠——具体承接由下游 research_design 按维度决定。务必覆盖原 brief 中属于本渠道能力范围的所有诉求（包括竞品对比、品牌认知等跨渠道诉求），不要因"另一渠道也能做"而省略

**评估维度标注约定**（避免下游 LLM 把分析框架误当采集主题）：识别 brief 中**用户用于评价/对比品牌的多个角度**——即用户想"从这些角度对品牌做出判断"的分析框架（不是采集对象本身，也不是消费者的诉求话题）。在所属渠道的 `solvable` 与 `channel_brief` 末尾用 `(评估维度：A、B、C)` 显式标注，且主诉求描述中不再单独罗列这些维度词，浓缩为"真实评价/差异化对比"等总称。识别有疑义时不标注（漏标只会让下游展开冗余 keyword、用户易调整；错标会让下游漏研究真主题、用户难发现）。
- 示例（brief 含"在原料、文化感、产品力上的真实差异"）：
  - solvable: "消费者对主品及竞品的真实评价与差异化对比 (评估维度：原料、文化感、产品力)"
  - channel_brief: "通过 UGC 分析消费者对主品及竞品的真实评价 (评估维度：原料、文化感、产品力)"
- 这是给下游 research_design 的结构化信号——下游会自动避免把 A、B、C 单独作为 keyword 主题（评估维度归宿是 RQ + 切片分析）

**推荐规则**（按渠道分别判断，符合条件输出对应 channel_plan 条目，不符合则不输出）：

- **social_media**：研究主体在覆盖平台上有足够密度的 UGC 讨论、能支撑系统化消费者洞察分析时推荐；讨论过于稀疏/碎片化（覆盖平台难以采集到足够样本）时不推荐
- **news_media**：brief 涉及品牌/事件报道、竞品公开动作、行业动态/政策解读或市场竞争格局时推荐——绝大多数战略类 brief 都有媒体层诉求。
- **industry_research**：战略规划、品类机会识别、结构性趋势判断、竞争格局定位类 brief 默认推荐——提供战略层的结构性背景支撑（产业报告 + 政策趋势 + 白空间 + 量化数据）。与 news_media 不互斥——前者是事件/动作/观点的媒体报道视角，后者是跨权威报告的结构性分析，战略类 brief 常两者并存。
- **creative_research**：与 social_media 绑定——推了 social_media 就默认推（下游走 campaign_strategy / full_strategy 路径，Brand Role / Big Idea 阶段需要创意参考输入）；仅推 news_media（走 market_report 路径，无创意参考注入点）时不推
- channel_plan 只输出 social_media、news_media、industry_research、creative_research 四种渠道类型

### platform_verdict（策略框架适配度）

策略研究有三种产出框架：

- **campaign_strategy**（品牌策略 / 亦称 Campaign Strategy）：从消费者声音中发现社会张力 → 定义品牌角色 → 产出创意方向。主数据源 social_media，creative_research 作为 Brand Role / Big Idea 的创意参考默认配套。适合**"品牌应该如何与消费者沟通"**类研究（品牌定位 / 消费者洞察 / 内容策略）
- **market_report**（市场分析报告）：从媒体报道中梳理议程格局 → 分析竞争态势 → 产出战略建议。仅需 news_media 渠道。适合**"行业竞争态势如何、品牌应如何定位"**类研究（行业格局 / 竞争情报 / 市场进入）
- **full_strategy**（全渠道综合策略）：同时拥有 social_media 和 news_media 两条主线，先完成 market_report 路径的竞争格局分析（Agenda Map → Landscape），再将 Landscape 结构化输出作为背景注入 campaign_strategy 路径（Insight → Brand Role → Big Idea）。适合**"既需要竞争格局洞察，又需要消费者/创意方向"**的综合策略需求

**判断核心原则**：platform_verdict 判断的是**框架的产出结构是否匹配 brief 的研究意图**，而非仅看渠道能否采到数据。"某个渠道能采到相关数据"不等于"该框架能回答 brief 的核心问题"。

**判断规则**（按优先级从高到低，满足任一即确定 verdict）：

- **insufficient**（优先判断）：按以下**优先级从高到低**依次判断，命中第一个即判定（不再检查后续成因）。必须在 `insufficient_reason` 中明确成因，`platform_note` 按成因给出对应替代功能建议：
  1. **诊断型 brief**（信号最锐利，优先判）：brief 只需产出当前状态的诊断快照（消费者情感分布 / 舆情监测 / 竞品动作监测 / Campaign 投后复盘 / KOL 声量监测等），**不要求战略产出**（品牌角色 / Big Idea / 战略简报 / 品牌定位建议 / 传播方向）。判断信号（命中任一即成立，且不得含战略产出诉求）：
     - 时间窗为日/周/月级短期观察（而非半年/年度战略规划）
     - 核心动词是"监测/追踪/复盘/观察/快照/简报"（而非"策略/规划/定位/方向"）
     - 产出诉求是"看到了什么"（而非"应该怎么做"）
     命中后按 channel_plan 的渠道组合确定 `insufficient_reason`：
     - 仅推荐 social_media → `"diagnostic_social"`
     - 仅推荐 news_media → `"diagnostic_news"`
     - 同时推荐 social_media 和 news_media → `"diagnostic_dual"`
  2. **参考素材型 brief**（次优先）：brief 寻求的是已有知识或案例素材——可以是"了解某个领域的现状/机制/流程"，也可以是"借鉴某类做法的执行思路用于自己做方案"。本质都是把外部已存在的内容收回来供用户使用，而非由系统产出战略性结论或诊断快照。即使新闻媒体或社媒上有相关数据可采，这类问题的答案形式也不适合用任何策略框架的产出结构来承载。按素材性质进一步细分 `insufficient_reason`：
     - `"knowledge_industry"`：brief 想了解**品类结构 / 市场规模 / 政策趋势 / 技术原理 / 产业链 / 竞争格局结构性分析**等报告/学术型知识 → 对应研究分析功能的 industry profile
     - `"knowledge_creative"`：brief 关心**品类或竞品的 Campaign 套路 / 创意案例 / 获奖作品 / 品牌叙事风格 / 活动执行参考**——不论目的是研究历史脉络还是借鉴执行思路用于自己做方案 → 对应研究分析功能的 creative profile
     - 含糊不清或两者都沾边时默认用 `knowledge_industry`（更通用）
  3. **无可用渠道**（兜底，仅当 brief 既非诊断型也非知识型时触发）（`insufficient_reason: "no_channel"`）：channel_plan 未推荐 social_media 也未推荐 news_media（仅有 industry_research 无法生成完整策略报告）。此条兜底少数"战略性 brief 但渠道结构不支持"的边角 case（如 B2B 工业品类的消费者诉求但 social UGC 密度不足、无媒体事件可追踪）
- **partial**：框架能部分承载，但 brief 涉及框架覆盖不到的维度（如企业内部数据、金融终端数据、线下调研等），需用户知晓局限后决定是否推进
- **sufficient**：brief 的研究目标能完整对应某个框架，可直接推进

`insufficient_reason` 合法取值索引：`no_channel` / `knowledge_industry` / `knowledge_creative` / `diagnostic_social` / `diagnostic_news` / `diagnostic_dual`。

**与 channel_plan 的边界**：诊断型（上表 1）和知识型（上表 2）brief 由 insufficient 路径路由到 monitor+slice 或 research_agent 入口，不走 strategies pipeline；因此 channel_plan 的推荐规则只需判断**战略类 brief** 的渠道适合度，无需为诊断型/知识型 brief 做特殊处理。

`platform_note`：1-2 句话说明判断依据。
- 当 `platform_verdict == "insufficient"` 时，必须**逐字照抄**下列对应 `insufficient_reason` 的固定句式（不得改写、不得替换产品名、不得增删字符）：
  - `no_channel` → 提示"该需求建议直接使用「研究分析」功能获取研究报告，无需走完整策略流程"
  - `knowledge_industry` → 提示"该需求建议直接使用「研究分析」功能的行业研究类型获取品类/市场/政策/技术的结构性研究报告，无需走完整策略流程"
  - `knowledge_creative` → 提示"该需求建议直接使用「研究分析」功能的创意研究类型获取品类 Campaign 案例与创意参考，无需走完整策略流程"
  - `diagnostic_social` → 提示"该需求建议直接使用「社媒监测 + 切片分析」功能获取消费者情感与话题诊断报告，无需走完整策略流程"
  - `diagnostic_news` → 提示"该需求建议直接使用「新闻监测 + 切片分析」功能获取媒体议程与事件追踪报告，无需走完整策略流程"
  - `diagnostic_dual` → 提示"该需求建议分别使用「社媒监测 + 切片分析」和「新闻监测 + 切片分析」功能获取诊断报告（当前系统暂无双渠道合并入口），无需走完整策略流程"
- 当 `platform_verdict == "sufficient"` 且 channel_plan 包含 social_media 或 news_media 时，不需要额外提示

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记。channel_plan 只包含真正适合的渠道，不适合的渠道不输出。framework 字段（target_audiences / audience_insights / core_propositions / competitors）brief 未显性提及时输出 `null`，**不要**输出空数组 `[]`：
{{
  "strategy_name": "策略名称建议",
  "subject": "研究主体",
  "analysis_goal": "整体研究目标描述",
  "constraints": "补充说明（可为空字符串）",
  "target_audiences": [
    {{
      "label": "受众标签",
      "description": "一句话画像（可为空字符串）",
      "behavior_signals": ["决策驱动/触媒/讨论场景信号", "..."]
    }}
  ],
  "audience_insights": ["受众痛点/desire 1", "..."],
  "core_propositions": ["核心主张 1", "..."],
  "competitors": ["竞品 1", "..."],
  "channel_plan": [
    {{
      "type": "social_media / news_media / industry_research / creative_research",
      "available": true,
      "solvable": ["该渠道能解决的问题1", "问题2"],
      "unsolvable": ["该渠道的局限"],
      "channel_brief": "针对该渠道的定制化研究描述..."
    }}
  ],
  "platform_verdict": "sufficient / partial / insufficient",
  "platform_note": "判断依据说明",
  "insufficient_reason": "no_channel / knowledge_industry / knowledge_creative / diagnostic_social / diagnostic_news / diagnostic_dual（非 insufficient 时为空字符串）"
}}
"""

USER_TEMPLATE = """以下是用户上传的 Brief 文档内容：

{document_text}

请按 SYSTEM 中的"判断顺序"完整输出五类内容：基础字段（strategy_name / subject / analysis_goal / constraints）→ framework 字段（target_audiences / audience_insights / core_propositions / competitors，未提及一律 null）→ channel_plan → platform_verdict + platform_note → insufficient_reason（仅 verdict=insufficient 时非空，否则留空字符串）。"""


def create_brief_parser_chain() -> Runnable:
    """创建 Brief 解析 Chain"""
    llm = get_llm("chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("human", USER_TEMPLATE),
    ])
    return prompt | llm


def parse_brief_parser_response(response_text: str) -> dict[str, Any]:
    """解析 LLM 输出为结构化字段"""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        result: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        # 失败时 dump 完整 raw response（不只是前 200 字）以便诊断 prompt 改动是否引入格式回归
        logger.error(
            "Brief Parser Chain JSON 解析失败 @ pos=%d: %s\n--- 完整 LLM 响应 ---\n%s\n--- end ---",
            e.pos,
            e.msg,
            text,
        )
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("strategy_name", "")
    result.setdefault("subject", "")
    result.setdefault("analysis_goal", "")
    result.setdefault("constraints", "")
    result.setdefault("platform_verdict", "partial")
    result.setdefault("platform_note", "")
    result.setdefault("insufficient_reason", "")
    if not result.get("channel_plan"):
        result["channel_plan"] = []

    # framework 字段：保留 LLM 输出的 None 语义（区分"brief 未提及" vs "提及但空"），
    # 不做 setdefault 兜底；但 LLM 若错误返回空数组，归一化为 None 以保持语义清晰
    for field in ("target_audiences", "audience_insights", "core_propositions", "competitors"):
        if field not in result or result[field] == [] or result[field] == "":
            result[field] = None

    # 不信任 LLM 自报：非 insufficient 时强制清空 reason，避免下游前端路由错乱
    if result["platform_verdict"] != "insufficient":
        result["insufficient_reason"] = ""
    else:
        valid_reasons = {
            "no_channel",
            "knowledge_industry",
            "knowledge_creative",
            "diagnostic_social",
            "diagnostic_news",
            "diagnostic_dual",
        }
        # 兼容旧提示词输出的 knowledge_research：映射到 knowledge_industry（更通用默认）
        if result["insufficient_reason"] == "knowledge_research":
            logger.info(
                "Brief Parser Chain 返回旧值 knowledge_research，映射至 knowledge_industry"
            )
            result["insufficient_reason"] = "knowledge_industry"
        elif result["insufficient_reason"] not in valid_reasons:
            logger.warning(
                "Brief Parser Chain 返回未知 insufficient_reason=%s，回退至 knowledge_industry",
                result["insufficient_reason"],
            )
            result["insufficient_reason"] = "knowledge_industry"

    return result
