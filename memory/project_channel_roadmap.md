---
name: 策略渠道路线图
description: 多渠道数据采集现状与规划（social_media/knowledge_base/news_media）
type: project
---

策略研究引擎的渠道扩展状态：

- **social_media**（已上线）：4 阶段主采集流程，probe/collect 任务，7 条 LLM Chain
- **knowledge_base**（已上线）：独立模块，文档上传 + 公开数据爬虫（cnnic/nbs/govsite）+ pgvector RAG；通过 `retrieve_market_context()` 在 Phase1/2 生成时注入市场背景
- **news_media**（规划开发中，2026-03-31 确认）：当前在 brief_parser_chain 中标记为 `available=false`，后续需开发

**Why:** 用户明确告知 knowledge_base 已在采集数据，news_media 开始规划
**How to apply:** 讨论策略多渠道架构时，要考虑 news_media 的接入设计
