# 策略模块多数据源架构方案

> 设计日期：2026-03-26
> 最后更新：2026-04-09
> 状态：阶段一/二/三已完成

---

## 背景

原有数据流强依赖社媒单一管线：

```
社媒 DataTask → AnalysisSlice（Celery 聚合）→ Phase 1/2/3 Chain
```

未来需要接入知识库、网络搜索等数据源，这些无法走社媒聚合管线，需要从架构层面解耦。

---

## 设计原则

1. **Brief 摄入时就做渠道分发**：创建策略时判断哪些渠道适合，明确研究边界，用户在提交前就知道系统能解决什么、不能解决什么
2. **各渠道独立处理**：研究设计、数据采集按渠道分路，互不干扰，新增渠道不影响已有逻辑
3. **单一归一化边界**：所有渠道的数据在进入 Phase 链之前统一格式，Phase 链不感知数据来源

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
   🔒 新闻媒体（未开通）
      若开通可补充：近期舆情事件、PR 传播动态...

③ 确认并创建策略（channel_plan 存入 brand_brief）

④ 进入各渠道研究设计
   → 社媒：关键词 / 平台 / 切片蓝图
   → 其他渠道（未来）

⑤ 各渠道数据采集

⑥ 数据归一化 → Phase 1/2/3 最终分析
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
            "available": False,          # 未来接入
            "solvable": ["近期舆情事件", "媒体传播动态"],
            "unsolvable": [],
            "channel_brief": "跟踪[subject]相关新闻与报道，补充事件脉络与舆情语境。"
        }
    ]
}
```

**渠道判断规则**：
- 只输出与本 brief 相关的渠道，完全不适合的不输出
- `social_media` 是默认渠道，除非 brief 完全不涉及用户/消费者讨论
- `available=false` 的渠道仍输出，用于告知用户该数据源能补充哪些问题

**实现**：`strategy_brief_parser_chain.py`

---

### Layer 1：研究设计（按渠道分路）✅ 社媒已完成 / 其他渠道待实现

各渠道接收各自的 `channel_brief`，由对应的 design chain 生成研究计划：

```
social_media   → research_design_chain（✅ 已实现）
                 输入：channel_brief + subject + constraints（补充上下文）
                 输出：keywords / platforms / slice_blueprint

knowledge_base → 无独立 design chain（✅ 已接入）
                 通过 `retrieve_market_context()` 在 Phase1/2 生成前注入 RAG 结果

news_media     → 复用 research_design_chain 的 news 分支（✅ 已实现）
                 probe 与 collect 是独立的 NewsTask 记录，由 strategies/service.py 编排
```

**扩展方式**：新增渠道时，只需增加对应的 design chain，channel_plan 路由逻辑不变。

> ⚠️ 注意：`channel_brief` 是 1-2 句话的定向描述，本身信息量有限。research_design_chain 在接收 channel_brief 的同时，应将原始 `subject` 和 `constraints` 作为补充上下文一并传入，避免关键词生成时丢失结构化信息（如竞品名称、时间范围）。当前实现中，旧格式记录（无 channel_plan）已通过 fallback 兜底，新记录需确认上下文传递完整。

---

### Layer 2：数据采集与处理（按渠道分路）✅ 社媒已完成 / 其他渠道待实现

```
social_media（✅ 现有，不变）:
  Monitor → DataTask → probe → 全量采集 → AnalysisSlice

knowledge_base（✅ 已接入）:
  KnowledgeDocument/Chunk（平台公共 + 用户私有）→ 向量检索 → market_context 注入 Phase1/2

news_media（✅ 已接入）:
  NewsTask(probe) → 百度+DDG 双渠道搜索卡片 → LLM probe review
  → refine/approve → NewsTask(collect) → 全文抓取 + tagging/insight
```

`AnalysisSlice` 的现有逻辑完全保留，不做任何修改。

---

### Layer 3：策略输入归一化 ✅ 已实现

这是唯一的抽象边界，Phase chain 不感知数据来源。

```python
async def load_strategy_inputs(
    db: AsyncSession,
    strategy: Strategy,
) -> list[dict]:
    """统一加载策略输入，屏蔽数据来源差异"""
    inputs = []

    # 路径 A：社媒切片（现有）
    for ss in strategy.slices:
        if ss.slice and ss.slice.result_data:
            inputs.append(ss.slice.result_data)

    # 路径 B（未来）：知识库摘要
    # for kb in strategy.knowledge_summaries:
    #     inputs.append(adapt_knowledge_summary(kb))

    # 路径 C（未来）：新闻媒体摘要
    # for nm in strategy.news_media_summaries:
    #     inputs.append(adapt_news_media_summary(nm))

    return inputs
```

实现时替换 `service.py` 中的 `load_slice_data()` 调用，当前行为完全等价。

---

### Layer 4：Phase 生成 ✅ 已完成

Phase 1/2/3 chain 消费 `list[dict]`，与数据来源完全解耦，无需改动。

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

当前状态流按单渠道设计，满足现阶段需求：

```
draft → planned → probing → collecting → ready → phase1_done → phase2_done → completed
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
7. ✅ Knowledge Base：RAG 检索接入，Phase1/2 注入 `market_context`

### 阶段三：News Media 数据源 ✅ 已完成

8. ✅ News Media 模块：`news_media/monitors` + `news_media/tasks`，百度+DuckDuckGo 双渠道
9. ✅ 两段式 probe→collect：各自为独立 NewsTask 记录（硬删除，ondelete CASCADE 到 NewsArticle）
10. ✅ `news_probe_review_chain` + 并行 LLM 评估，包裹在 STRATEGY_PROBE_REVIEW AnalysisJob 内统一追踪成本
11. ✅ `refine_probe` 批量端点同时处理 social/news 两路 refinements

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
| Phase 1/2/3 chain | ✅ 不变 | |
| `strategy_brief_parser_chain` | ✅ 已改 | 升级为渠道分发判断，输出 `channel_plan` |
| `strategy_research_design_chain` | ✅ 已改 | 接收 `channel_brief`，移除课题适配度评估 |
| `service.py` Phase 生成函数 | ✅ 已改 | `load_slice_data()` → `load_strategy_inputs()` |
| `service.py` 市场背景注入 | ✅ 已改 | Phase1/2 前调用 `retrieve_market_context()` 注入 `market_context` |
| `Strategy` 模型 | ✅ 已改 | `channel_plan` 存于 `brand_brief` JSON |
| 新建策略前端 | ✅ 已改 | AI 解析后展示 channel_plan，策略详情页 brief 区也展示 |

**已完成迁移**：`strategies.source_plan` 独立列已删除（迁移：`20260326_brief_subject`）
