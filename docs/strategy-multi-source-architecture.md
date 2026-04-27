# 策略模块多数据源架构方案

> 设计日期：2026-03-26
> 最后更新：2026-04-10
> 状态：阶段一/二/三已完成

---

## 背景

原有数据流强依赖社媒单一管线：

```
社媒 DataTask → AnalysisSlice（Celery 聚合）→ Insight/Brand Role/Big Idea Chain
```

未来需要接入知识库、网络搜索等数据源，这些无法走社媒聚合管线，需要从架构层面解耦。

---

## 设计原则

1. **Brief 摄入时就做渠道分发**：创建策略时判断哪些渠道适合，明确研究边界，用户在提交前就知道系统能解决什么、不能解决什么
2. **各渠道独立处理**：研究设计、数据采集按渠道分路，互不干扰，新增渠道不影响已有逻辑
3. **单一归一化边界**：所有渠道的数据在进入产出 chain 之前统一格式，产出 chain 不感知数据来源

---

## 用户视角流程

```
① 新建策略
   填写 / 上传 Brief → AI 解析

② 查看渠道分发结果（创建前，inline 展示）
   ✅ 社交媒体（当前可用）
      能解决：用户情感与口碑、品牌认知、竞品社媒声量...
      不能解决：市场规模等结构化数据
   ✅ 市场知识库（当前可用）
      能解决：行业背景、政策信息、公共统计数据、内部资料补充
   ✅ 新闻媒体（当前可用）
      能解决：媒体报道态势、行业叙事、竞品媒体定位、权威引述...

③ 确认并创建策略（channel_plan 存入 brand_brief）

④ 进入各渠道研究设计
   → 社媒：关键词 / 平台 / 切片蓝图
   → 其他渠道（未来）

⑤ 各渠道数据采集

⑥ 数据归一化 → 产出生成（campaign_strategy: Insight/Brand Role/Big Idea · market_report: Agenda Map/Landscape/Strategic Brief · full_strategy: Agenda Map/Landscape/Insight/Brand Role/Big Idea）
```

> ✅ 步骤②（创建页展示 channel_plan）已实现，用户可在创建前看到可用/未开通渠道与能力边界。

---

## 技术分层

### Layer 0：Brief 智能摄入 + 渠道分发判断 ✅ 已完成

**职责**：在创建策略时一次性完成，不等到研究设计阶段。

**输入**：用户自然语言 / 上传文档（PDF / DOCX / TXT / MD）

**输出**（存入 `strategy.brand_brief` JSON 列）：

```python
{
    "subject": "研究主体（品牌/产品/品类）",
    "analysis_goal": "整体研究目标",
    "constraints": "补充说明",
    "channel_plan": [
        {
            "type": "social_media",
            "available": True,
            "solvable": ["用户情感态度", "品牌认知", "竞品声量"],
            "unsolvable": ["市场规模等结构化数据"],
            "channel_brief": "聚焦[subject]在社媒的用户讨论，分析消费者情感..."
        },
        {
            "type": "knowledge_base",
            "available": True,
            "solvable": ["行业背景数据", "政策趋势参考", "内部资料补充"],
            "unsolvable": ["实时用户互动数据"],
            "channel_brief": "检索知识库中与[subject]相关的行业报告、政策与内部资料，补充策略研究的市场背景。"
        },
        {
            "type": "news_media",
            "available": True,
            "solvable": ["媒体报道态势", "行业叙事聚类", "竞品媒体定位", "权威引述"],
            "unsolvable": ["实时用户互动数据"],
            "channel_brief": "跟踪[subject]相关新闻与公众号报道，补充媒体视角与行业叙事。"
        }
    ]
}
```

**渠道判断规则**：
- 只输出与本 brief 相关的渠道，完全不适合的不输出
- `social_media` 是默认渠道，除非 brief 完全不涉及用户/消费者讨论
- `available=false` 的渠道仍输出，用于告知用户该数据源能补充哪些问题

**评估维度标注（跨链契约）**：当 brief 包含"用户用于评价/对比品牌的多个角度"（分析框架，非采集对象）时，brief_parser 在所属渠道的 `solvable` 与 `channel_brief` 末尾以 `(评估维度：A、B、C)` 形式显式标注。下游 `research_design_chain` 据此区分"分析框架 vs 采集主题"——A/B/C 不会被单独作为 keyword 主题，归宿是 RQ 表述 + 切片分析阶段（从 UGC 提取各维度内容）。

**`platform_verdict` 分诊**：除渠道分发外，brief_parser 同时输出 `platform_verdict`（`sufficient` / `partial` / `insufficient`）判断 brief 的研究目标是否适合被 strategies pipeline 的产出框架承载。当判定 `insufficient` 时，新增 `insufficient_reason` 字段按**判断优先级**细分分诊方向（诊断型 → 参考素材型 → 无渠道兜底，共 6 种取值：`diagnostic_social` / `diagnostic_news` / `diagnostic_dual` / `knowledge_industry` / `knowledge_creative` / `no_channel`），前端按 reason 引导用户跳转至对应的替代功能入口（研究分析的 industry/creative profile / 社媒监测 + 切片分析 / 新闻监测 + 切片分析）——对应系统的**三层产出架构**。详见 [ADR-002](adr/002-output-tier-routing.md)。

**实现**：`brief_parser_chain.py`

---

### Layer 1：研究设计（按渠道分路）✅ 社媒 + 新闻已完成

各渠道接收各自的 `channel_brief`，由对应的 design chain 生成研究计划：

```
social_media   → research_design_chain（✅ 已实现）
                 输入：channel_brief + subject + constraints（补充上下文）
                 输出：keywords / platforms / slice_blueprint

knowledge_base → 无独立 design chain（✅ 已接入）
                 通过 `_retrieve_strategy_market_context()` 在 stage 生成前注入 RAG 结果

news_media     → 复用 research_design_chain 的 news 分支（✅ 已实现）
                 probe 与 collect 是独立的 NewsTask 记录，由 strategies/service.py 编排
```

**扩展方式**：新增渠道时，只需增加对应的 design chain，channel_plan 路由逻辑不变。

> ⚠️ 注意：`channel_brief` 是 1-2 句话的定向描述，本身信息量有限。research_design_chain 在接收 channel_brief 的同时，应将原始 `subject` 和 `constraints` 作为补充上下文一并传入，避免关键词生成时丢失结构化信息（如竞品名称、时间范围）。当前实现中，旧格式记录（无 channel_plan）已通过 fallback 兜底，新记录需确认上下文传递完整。

---

### Layer 2：数据采集与处理（按渠道分路）✅ 三渠道均已完成

```
social_media（✅ 现有，不变）:
  Monitor → DataTask → probe → 全量采集 → AnalysisSlice

knowledge_base（✅ 已接入）:
  KnowledgeDocument/Chunk（平台公共 + 用户私有）→ 向量检索 → market_context 注入产出 stage

news_media（✅ 已完成）:
  NewsTask(probe) → baidu+sogou 两渠道搜索卡片（可选 +wechat_mp）→ LLM probe review
  → refine/approve → NewsTask(collect) → 全文抓取(Crawl4AI) + tagging + insight
  → 策略建切片时：按 _news_task_dimension_map 分维度 → 跨任务文章 URL 去重 + relevance 筛选
    → 每维度一次 news_insight_chain → 维度级 insight 注入 slice result_data["news_insights"]

  搜索渠道: baidu / sogou（默认） + wechat_mp（opt-in，搜狗微信入口）
  — Bing 已下线（2026-04 反爬升级后返回 0 外部新闻，bing_crawler.py 保留作备用不接入）
  来源分层: tier1(权威央媒) / tier2(行业门户) / tier3(其他) / wechat_mp(微信公众号)
```

`AnalysisSlice` 的现有逻辑完全保留，不做任何修改。

---

### Layer 3：策略输入归一化 ✅ 已实现

这是唯一的抽象边界，产出 chain 不感知数据来源。

```python
async def load_strategy_inputs(
    db: AsyncSession,
    strategy: Strategy,
) -> list[dict]:
    """统一加载策略输入，屏蔽数据来源差异"""
    inputs = []

    # 路径 A：社媒切片（按 monitor_id 隐式关联）
    if strategy.social_monitor_id:
        result = await db.execute(
            select(SocialSlice).where(
                SocialSlice.monitor_id == strategy.social_monitor_id
            )
        )
        for s in result.scalars().all():
            if s.result_data:
                inputs.append(s.result_data)

    # 路径 B：新闻切片（按 monitor_id 隐式关联）
    if strategy.news_monitor_id:
        result = await db.execute(
            select(NewsSlice).where(
                NewsSlice.monitor_id == strategy.news_monitor_id,
                NewsSlice.status == "completed",
            )
        )
        for s in result.scalars().all():
            if s.result_data:
                inputs.append(s.result_data)

    # 路径 C（可选）：知识库摘要
    # for kb in strategy.knowledge_summaries:
    #     inputs.append(adapt_knowledge_summary(kb))

    return inputs
```

实现时替换 `service.py` 中的 `load_slice_data()` 调用，当前行为完全等价。

---

### Layer 4：产出生成 ✅ 已完成

campaign_strategy 路径的 Insight / Brand Role / Big Idea chain 消费社媒切片数据（`meta/foundation/layers`）+ 新闻媒体视角（`news_insights`），通过 `_format_news_media_section` 格式化后作为 `{news_media_section}` 注入 USER_TEMPLATE。

SYSTEM_TEMPLATE 中包含"新闻媒体数据使用指南"，指导 LLM 交叉验证消费者声音与媒体报道：
- Insight（第 1 层）：消费者-媒体矛盾→Tension 线索；新闻仅作补充证据
- Brand Role（第 2 层）：媒体叙事作为品牌角色外部锚点；竞品格局互为补充
- Big Idea（第 3 层）：借势/颠覆媒体叙事；引述作为话题锚点

market_report 路径的 Agenda Map / Landscape / Strategic Brief chain 以 news_media 为主数据源（`load_strategy_news_inputs`），同样层层递进：Agenda Map 负责议程聚类，Landscape 在其上叠加竞品/定位分析，Strategic Brief 只消费前两层的结构化结论不得引入新数据。

---

## 数据模型

### brand_brief JSON 结构

```python
class BrandBrief:
    subject: str                          # 研究主体
    analysis_goal: str                    # 整体研究目标
    constraints: str | None              # 补充说明
    channel_plan: list[ChannelPlanItem] | None  # 渠道分发结果

class ChannelPlanItem:
    type: str          # social_media / knowledge_base / news_media / vertical_platform
    available: bool    # 当前是否可用
    solvable: list[str]    # 该渠道能解决的问题
    unsolvable: list[str]  # 该渠道的局限
    channel_brief: str     # 该渠道专属研究描述，作为该渠道 research_design 的主输入
```

### 状态流

当前状态流按单渠道设计，满足现阶段需求（按 `output_type` 在 `ready` 之后分叉为两条三阶段路径）：

```
draft → planned → probing → collecting → ready ┬─ [campaign_strategy] insight_done → brand_role_done → completed
                                                 ├─ [market_report]     agenda_map_done → landscape_done → completed
                                                 └─ [full_strategy]     agenda_map_done → landscape_done ──→ completed
```

Brief 摄入作为 `draft` 阶段内的步骤，不新增状态。

---

## 实施路线图

### 阶段一：Brief 智能摄入 + 渠道分发 ✅ 已完成

1. ✅ `strategy_brief_parser_chain` 升级为渠道分发判断，输出 `channel_plan`
2. ✅ `BrandBrief` schema 扩展：含 `channel_plan`（`available / solvable / unsolvable / channel_brief`）
3. ✅ `research_design_chain` 接收社媒 `channel_brief` 替代原始完整 brief
4. ✅ 新建策略页展示 `channel_plan` 结果，让用户在创建前了解研究边界

### 阶段二：UX 补全 + 归一化层（已完成）

5. ✅ 新建策略页：AI 解析后展示 channel_plan，标注可用/未开通渠道及能力边界
6. ✅ `load_strategy_inputs()` 替换 `load_slice_data()`：当前行为不变，接口已为多数据源就绪
7. ✅ Knowledge Base：RAG 检索接入，产出 stage 注入 `market_context`

### 阶段三：News Media 数据源 ✅ 已完成

8. ✅ News Media 模块：`news_media/monitors` + `news_media/tasks`，baidu+sogou 默认双渠道 + wechat_mp opt-in（Bing 2026-04 下线）
9. ✅ 两段式 probe→collect：各自为独立 NewsTask 记录（硬删除，ondelete CASCADE 到 NewsArticle）
10. ✅ `strategy_news_probe_review_chain` + 并行 LLM 评估，包裹在 STRATEGY_NEWS_PROBE_REVIEW AnalysisJob 内统一追踪成本（社媒对应 STRATEGY_SOCIAL_PROBE_REVIEW / `strategy_social_probe_review_chain`）
11. ✅ `refine_probe` 批量端点同时处理 social/news 两路 refinements
12. ✅ 维度级 news insight：`_run_dimension_news_insights` 按维度合并文章（去重+筛选）→ 每维度一次 insight chain
13. ✅ campaign_strategy 三阶段 chain（Insight/Brand Role/Big Idea）新增 `_format_news_media_section` 注入新闻媒体视角，SYSTEM_TEMPLATE 新增交叉分析指南
14. ✅ 微信公众号搜索（wechat_mp）：通过搜狗微信入口 + Crawl4AI 抓取，source_tier 独立为 "wechat_mp"

---

## 已知待解决问题

### 多渠道并行时的状态管理

当前状态机（`probing → collecting → ready`）假设单渠道串行。接入第二个渠道时，不同渠道可能处于不同进度（如社媒已 `collecting`，news_media 还在 `planned`）——现有状态流无法表达这种并行状态。

**当前结论**：单渠道阶段不受影响，接入第二个渠道前需专项设计状态追踪方式，届时再决策。

---

## 对现有代码的影响

| 组件 | 状态 | 说明 |
|------|------|------|
| `AnalysisSlice` 及聚合管线 | ✅ 不变 | |
| campaign_strategy 三阶段 chain（Insight/Brand Role/Big Idea） | ✅ 已改 | USER_TEMPLATE 新增 `{news_media_section}`；SYSTEM_TEMPLATE 新增新闻媒体数据使用指南 |
| `strategy_brief_parser_chain` | ✅ 已改 | 升级为渠道分发判断，输出 `channel_plan` |
| `strategy_research_design_chain` | ✅ 已改 | 接收 `channel_brief`，移除课题适配度评估 |
| `service.py` stage 生成函数 | ✅ 已改 | `load_slice_data()` → `load_strategy_inputs()` |
| `service.py` 市场背景注入 | ✅ 已改 | stage 生成前调用 `_retrieve_strategy_market_context()` 注入 `market_context` |
| `Strategy` 模型 | ✅ 已改 | `channel_plan` 存于 `brand_brief` JSON |
| 新建策略前端 | ✅ 已改 | AI 解析后展示 channel_plan，策略详情页 brief 区也展示 |

**已完成迁移**：`strategies.source_plan` 独立列已删除（迁移：`20260326_brief_subject`）
