---
name: 策略渠道路线图
description: 多渠道数据采集现状与规划（social_media/knowledge_base/news_media）
type: project
---

策略研究引擎的渠道扩展状态：

- **social_media**（已上线）：4 阶段主采集流程，probe/collect 任务，brand_strategy 路径三层（Insight → Brand Role → Big Idea）
- **knowledge_base**（已上线）：独立模块，文档上传 + 公开数据爬虫（cnnic/nbs/govsite）+ pgvector RAG；通过 `_retrieve_strategy_market_context()` 在策略产出阶段（brand_strategy / market_report 两条路径的三层产出）注入市场背景
- **news_media**（已上线，2026-04-12 完成）：独立监测 + 策略研究场景都已打通；策略下 news probe/collect 两段式，market_report 路径三层（Agenda Map → Landscape → Strategic Brief）

**Why:** 三渠道全部上线，策略重构完成了 phase → 语义命名的全面切换
**How to apply:** 讨论策略多渠道架构时，直接引用 brand_strategy / market_report 两条路径及各自三层名称，不再用 phase1/2/3
