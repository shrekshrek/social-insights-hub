# 分析模式与成本优化策略 (Analysis Modes Draft)

本文档记录了关于任务级分析中不同深度模式的规划，以及针对 LLM Token 的成本优化策略。这些策略在需要精细化控制 API 成本时可重新启用。

## 1. 分析模式 (Analysis Modes)

为平衡成本与效果，引入 **Analysis Depth (分析深度)** 配置参数。

| 模式 | 适用场景 | Screening | Post Extraction | Comment Extraction | 预估成本 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Light (日常)** | 日常巡检、高频监控 | 全量 | 仅 Top 5 高互动贴 | 关闭 | Low (~0.01元) |
| **Standard (默认)** | 舆情事件追踪 | 全量 | Top 20 高互动贴 | Top 20 贴的 Top 5 评论 | Medium (~0.1元) |
| **Deep (调研)** | 深度报告、竞品分析 | 全量 | 全量 (Top 100) | 全量 (Top 100 贴 * 20 评) | High (~0.5元) |

## 2. Token 节省策略 (Cost Optimization)

针对最耗费 Token 的评论分析环节，实施以下优化：

1.  **Context 瘦身**：
    *   **原逻辑**：传入帖子完整正文作为背景。
    *   **优化后**：只传入 `Post Extraction` 生成的 **Summary (摘要)**。大幅减少 Input Token。
2.  **评论截断**：
    *   对于 *Standard* 模式，只分析点赞最高的 **Top 5 评论**。因为前排评论通常已覆盖 80% 的主要观点。

## 3. 开发实现建议 (已移除部分)

*   **参数透传**：确保 `analysis_mode` 参数能从 API 传到 Celery Coordinator。
*   **动态截断**：在 `Coordinator` 分发子任务时，根据模式对 `post_ids` 进行切片。

