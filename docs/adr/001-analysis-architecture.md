# ADR-001:分析架构的分场景选型

> 决策日期:2026-04-20
> 状态:Proposed(n=2 已揭示场景适配必要,待 n≥5 验证后转 Accepted)
> 相关实验:[path-b-insight-comparison.md](../experiments/path-b-insight-comparison.md)

## 变更记录

- **2026-04-20 v1**:基于 Strategy #18(乐虎)的 n=1 实验,推出"策略研究必须重构为 LLM-native"
- **2026-04-20 v2(当前)**:Strategy #7(大魔王素毛肚)实验结果与 v1 相反,揭示 Path B 在品牌聚焦场景下会被 IP 泛化内容带偏。修订为"**场景化混合架构**",不是简单替换

---

## 背景

系统当前对所有分析场景(社媒监控、新闻监控、策略研究、专题研究)都使用了同一套 pipeline 架构:原始数据 → screening → extraction → normalization → slice_reports → 下游分析链。这套架构继承自 pre-LLM 时代的传统 NLP pipeline 思路(NER → 归一化 → 聚合 → 报告),在 2023-2024 年的模型能力下是合理选择。

但 2026 年的现状:
- DeepSeek-V3.2 输入 ¥2/M tokens,128K 上下文;主流模型上下文普遍 1M+
- LLM 的整体 holistic reasoning 能力远超"拼装小任务"
- Pipeline 的误差会逐级累积(5 阶段 × 5% 误差 = 23% 复合误差)

基于 2026-04-20 进行的 Path B 实验(详见实验文档),pipeline 架构在**策略研究**场景下**系统性劣于 LLM-native 一次性分析**——不仅更贵(20-30x 成本),产出质量也更差(漏掉 3 个主流议题,将 29 帖小众议题捧为 Tension #1)。

但实验不能无限推广:监控类场景(需要时序聚合、SOV 查询、dashboard)**确实需要** pipeline 提供的结构化数据。

因此需要确立"分场景用不同架构"的原则,而不是一刀切推翻重建。

---

## 判断框架

不同使用场景匹配不同架构:

| 架构类型 | 适用场景 | 不适用 |
|---------|---------|------|
| **Pipeline**(结构化逐步提取) | 长期追踪、时序查询、仪表盘、SOV/情感聚合报表 | 一次性叙事洞察 |
| **LLM-native**(一把梭) | 单次分析、叙事输出、样本量可采样进上下文 | 长期聚合、精确时序对比 |
| **Agentic**(迭代智能体) | 外部动作(搜索/抓取/计算)、自适应规划、多轮精炼 | 批量确定性流程 |

核心原则:
- 用户要看**趋势/历史/仪表盘** → Pipeline
- 用户要要**洞察/策略/报告** → LLM-native
- 用户要**搜索+研究+综合** → Agentic

---

## 决策:各模块架构选型

### 1. 社媒监控:保留 Pipeline,但大幅瘦身

**保留理由**:监控场景需要时序聚合、SOV 查询、dashboard、异常告警,这些离不开预先结构化的数据。

**链级判决**:

| 链 | 决策 | 理由 |
|----|----|------|
| `screening_chain` | 保留 | 降噪,降下游成本,监控必需 |
| `post_extraction` | 改批量(10 帖/批) | 监控精度够用,省 ~80% 成本 |
| `comment_extraction` | 砍掉大部分 | 9K+ 评论逐条分析是重度浪费。改为只对 high-signal 帖做或全局抽样 Top N 批处理 |
| `entity_normalization` | 保留 | SOV 查询必需 |
| `attribute/category/opinion_normalization` | 砍掉 | 下游 LLM 在查询时做同义识别即可 |
| `monitor_entity_merge` | 保留 | 跨项目实体合并,真有价值 |
| `monitor_slice_reports`(3×) | 保留 | 仪表盘和 Review 会消费 |

**预期效果**:监控路径成本降 60-70%,dashboard 功能不变。

### 2. 新闻监控:轻改即可

**判决**:架构基本不动,只优化 `news_insight_chain` 改为一次性读全部文章而非基于 tagging 聚合。`news_tagging_chain` 保留用于 dashboard 过滤/检索。

新闻量本就小(单次 50-100 条量级),现有结构轻量,不是重构重点。

### 3. 专题研究 (Research Agent):保留,调优

**判决**:架构已是 agentic(LangGraph 迭代),方向正确,不需重构。

**需要的是运维级调优**:
- 循环上限从 3-4 轮降到 2 轮(大多数场景 2 轮够)
- Tavily query 质量优化(一次搜好 vs 多次试探)
- Synthesize 阶段的 grounding 强化(引用真实抓取内容,避免凭"记忆"拼凑)

### 4. 策略研究:场景化混合架构(最高优先级)

**判决**:策略研究的输出链不能简单从 pipeline 替换为 LLM-native。**n=2 实验揭示架构选择依赖研究主体的性质**:

| 研究主体类型 | 典型特征 | 推荐架构 | 证据 |
|-----------|---------|--------|-----|
| **品类级研究** | 多品牌对比、多数据源、讨论围绕品类/赛道 | **LLM-native 主** + pipeline 辅助 | Strategy #18 乐虎(品类级)Path B 大胜 |
| **品牌聚焦研究** | 单一主体、IP/热点自带噪声、需严格聚焦 subject | **Pipeline slice 主** + LLM-native 辅助 | Strategy #7 大魔王素毛肚 Path A 更 on-topic |

**为什么有差异**:
- 品类级研究:讨论自然聚焦在产品/场景本身,LLM 读原始数据能 pattern-match 跨源议题(如 Strategy 18 的"红牛版本混乱")
- 品牌聚焦研究:外部 IP(世界杯/明星事件等)会产生大量爆款帖,Path B 的"按 engagement Top N"采样会把 50%+ 的注意力分配给 IP 泛化内容。LLM 在"反直觉"约束下容易绕开显而易见的品牌痛点(如大魔王的"麻酱量少"),反而去分析无关的 IP 现象(Faker/姆巴佩)

**目标架构(v2)**:

```
Brief 解析阶段 → 识别研究主体类型 (category | brand_focus | mixed)
   ↓
根据主体类型路由:
   ├─ category 路径:
   │    原始数据采样(按 engagement Top N)
   │    + 切片摘要辅助
   │    → LLM-native insight 链
   │
   ├─ brand_focus 路径:
   │    原始数据采样(按 subject 相关度加权,而非纯 engagement)
   │    + slice_reports(含 subject 聚焦维度)为主数据源
   │    → LLM-native 链但 prompt 强化"主体聚焦"约束
   │
   └─ mixed 路径:
        两种路径并行产出 → 合并 tensions 去重
```

**关键设计**:
1. **Brief 解析时识别主体类型**(brief_parser 新增 `subject_type` 字段)
2. **采样策略场景化**:品类级按 engagement Top N;品牌聚焦按相关度加权 + subject 关键词过滤后再取 Top N
3. **Prompt 约束场景化**:品牌聚焦场景必须在 prompt 加入"优先分析 subject 本体痛点,再看周边现象"的强约束,抵消"反直觉"约束被 IP 内容劫持
4. **保留 slice 结构作为品牌聚焦的主数据源**:slice_reports 的 subject 聚焦视角在品牌研究中是刚需
5. **Self-consistency**:两种场景都跑 2-3 次取稳定输出
6. **保留 evidence 结构化**:每条 tension/opportunity 带 post_id

market_report 路径同理分场景处理。

---

## 重构路线图

不要立即全面推翻重建。按下列优先级推进:

| 优先级 | 事项 | 数据证据 | 工作量 | 前置依赖 |
|-------|------|---------|------|---------|
| P0 | 扩展 Path B 实验到 5 个项目(含品类级 + 品牌聚焦各半)+ 策略师盲评 | n=2 已揭示分歧,需更多数据判断边界 | 1-2 周 | - |
| P0 | brief_parser 识别 `subject_type`(category/brand_focus/mixed) | ⭐⭐ n=2 验证必要 | 2-3 天 | - |
| P0 | 实现场景化采样策略(相关度加权 vs 纯 engagement) | ⭐⭐ n=2 验证必要 | 3-5 天 | - |
| P0 | 策略研究 `insight_v2` 双路径 Beta 并行上线 | ⭐⭐ | 2 周 | 场景路由就绪 |
| P0 | 建立评估 harness(引用准确性/议题重要性/主体聚焦度/数据源多样性) | - | 1 周 | - |
| P1 | 品牌聚焦场景的 prompt 强化"主体聚焦"约束 | ⭐⭐ Strategy 7 验证 | 3 天 | - |
| P1 | 社媒 `comment_extraction` 改为全局抽样批处理 | ⭐⭐ 高置信度推理 | 3 天 | - |
| P1 | 确认 DeepSeek prompt caching 生效,修复破坏前缀的 prompt | ⭐⭐ Strategy 7 实验中已观察到 cache 命中 | 1 天 | - |
| P2 | 策略研究输出链完整重构(场景化混合) | 依赖 P0 验证 | 1 月 | P0 通过 |
| P2 | 归一化链瘦身(砍 3 保 1) | ⭐ 推理 | 1 周 | - |
| P3 | Research Agent 循环上限优化 + Tavily 调优 | ⭐ | 3 天 | - |
| P3 | 新闻 `insight_chain` 改 LLM-native | ⭐ | 1 周 | - |

**关键节点**:
- **不要在 n=2 基础上推倒主干**。Strategy 18 和 Strategy 7 的结果相反,说明单点结论不可推广
- **优先做场景识别 + 采样策略**,这是低成本高回报的前置基础设施,即便最终不大改架构也有价值
- P0 全部完成后才能解锁 P2 的完整重构

---

## 不做什么(边界声明)

为防止过度反应,以下**明确不在本 ADR 范围内**:

1. **不推翻监控场景的 pipeline**。监控有结构化数据的真实需求,pipeline 是对的
2. **不重构 brief_parser / research_design / probe_review 等早期链**。它们本就是单 LLM 调用,不是 pipeline
3. **不废弃 AnalysisJob / slice 等数据模型**。这些是监控场景的基础,且可作为策略 LLM-native 的辅助输入
4. **不更换 LLM 模型**。DeepSeek V3.2 性价比与能力已够用,模型不是瓶颈

---

## 评估标准

重构成功与否的衡量(所有改动都应对标):

1. **成本**:单次策略研究的 LLM+API 总成本 ≤ 原来的 30%
2. **质量**:5 组盲评中新架构胜率 ≥ 60%(下调自 80%,因场景差异真实存在)
3. **覆盖度**:Top tensions 引用的 post 累计 engagement ≥ 总 engagement 的 30%
4. **主体聚焦度(品牌聚焦场景专用)**:Top 3 tensions 中,直接围绕 subject 本体的 ≥ 2 条(而非 IP/热点泛化分析)
5. **证据可追溯**:每条 tension/opportunity 至少 2 条可验证证据(post_id 真实存在 + 内容符合描述)
6. **监控场景不退化**:dashboard / SOV / 时序查询的响应时间与准确性不变

---

## 根本原则

本 ADR 背后的元原则:

> **分析架构的选择应由用户场景决定,而不是由工程传统决定。**

当前系统把四种性质不同的场景(监控/策略/研究/新闻)塞进同一套 pipeline,是 2023 年统一架构的遗产。2026 年的正确姿态是**四种架构并存,按场景匹配**——监控继续 pipeline,策略换 LLM-native,研究保持 agentic,新闻做轻量化。

重构不是"推翻重建",是"对症下药"。

---

## 参考

- 实验数据:[docs/experiments/path-b-insight-comparison.md](../experiments/path-b-insight-comparison.md)
- 实验脚本:[scripts/experiments/run_path_b_insight.py](../../scripts/experiments/run_path_b_insight.py)
- 相关架构文档:[docs/strategy-multi-source-architecture.md](../strategy-multi-source-architecture.md)、[docs/research-agent-design.md](../research-agent-design.md)
