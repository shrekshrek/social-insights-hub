# 实验:Path B(LLM-native 一把梭)vs Path A(Pipeline)Insight 产出对比

> ⚠️ **存档**：实验结论（subject_type 是路径选择的调节变量、n=2 不足以定论）已被 ADR-001 v6 吸收，按场景选型原则落地。本文仅供溯源，不再更新。

> 实验日期:2026-04-20
> 样本:Strategy #18(乐虎功能饮料)+ Strategy #7(大魔王素毛肚世界杯)
> 样本数:n=2(需扩展到 n≥5 方可定论)
> 相关决策:[ADR-001 分析架构选型](../adr/001-analysis-architecture.md)

## ⚠️ 适用范围声明

**本实验仅对比 `insight_chain` 一条链的产出**,不构成对整体架构的最终判断。

明确**不能**从本实验直接推出的结论:
- 其他策略产出链(brand_role / big_idea / agenda_map / landscape / strategic_brief)是否有同样的 Path A vs Path B 差异
- 社媒监测/新闻监测/专题研究场景下 Pipeline 架构是否该改
- 前端 UI 依赖的结构化字段(如 `player.media_sov_pct` / `evidence_refs`)在 Path B 架构下如何维护
- 跨模块工程依赖(Celery 任务图、AnalysisJob source_count、auto-slice 触发逻辑)的影响

本实验的价值是**证明"架构选择值得深入调研"**,不是**给出最终答案**。
完整架构决策必须在 [4 模块 Feature Inventory](../adr/001-analysis-architecture.md#phase-0-feature-inventory当前阶段) 完成后再做。

## 实验结果摘要(n=2)

| Strategy | 主体性质 | 胜方 | 关键原因 |
|---------|--------|-----|--------|
| #18 乐虎 | 品类级(多品牌多平台,饮料赛道) | **Path B 大胜** | 跨源 pattern-matching 抓到 Path A 漏的 3 大议题 |
| #7 大魔王素毛肚 | 品牌聚焦 + 高 IP 泛化(世界杯场景) | **Path A 更 on-topic** | Path B 被 IP 爆款(Faker/姆巴佩)带偏,漏抓品牌核心痛点"麻酱量少" |

**结论**:架构选择依赖研究主体性质,不是二元选择。详见 § 7-8。

---

## 1. 实验目的

验证以下假设:

> 对策略研究场景,LLM-native 一次性分析(直接读原始采样数据)
> 产出的洞察质量 **不低于** 现有 pipeline(screening → extraction → normalization → slice → insight),
> 且总成本 **显著更低**。

---

## 2. 数据背景

- Strategy ID: 18
- 主题:乐虎功能饮料品牌策略研究
- 输出路径:`full_strategy`(同时生成 campaign_strategy 和 market_report)
- 完成状态:`completed`
- Brief 概要:为乐虎功能饮料制定 2026 年品牌策略,分析竞品(红牛、东鹏特饮、Monster、战马)格局,目标人群为 18-30 岁蓝领工人、外卖骑手、长途司机、电竞玩家

**采集数据量**:

| 数据源 | 数量 |
|-------|------|
| 社媒帖(小红书+抖音+知乎,monitor_id=44) | 1,313 |
| 社媒评论(全量) | 9,719 |
| 新闻(monitor_id=4) | 73 |

---

## 3. 方法

### 3.1 Path A(现状 Pipeline)

从数据库直接读取 strategy.insight_result 字段,即系统正常完成后的产出。

产出链路:
```
原始 1313 帖 + 9719 评
→ screening_chain (筛选)
→ post_extraction_chain (每帖提取实体/观点/情感)
→ 4 条归一化链 (实体/属性/类别/观点归一化)
→ monitor_entity_merge (跨项目实体合并)
→ monitor_slice_reports (3 切片 × 3 报告)
→ insight_chain (消费聚合后的切片数据)
```

### 3.2 Path B(LLM-native 一把梭)

绕过所有 pipeline 中间步骤,直接从原始数据采样后一次调用 LLM:

**采样策略**:
- 每平台按 (likes + 2×comments) 排序取 Top 40 帖 → 3 平台共 120 帖
- 每帖按赞数取 Top 8 评论 → 共约 344 条评论
- 全量 73 篇新闻(仅 title + snippet,不读全文)
- 帖正文截断 400 字符,评论截断 80 字符

**Prompt 设计**:
- System prompt 与 Path A 的 insight_chain 相似结构(任务定义 + 洞察质量标准 + 证据要求 + JSON schema)
- User prompt = Brief + 采样原始语料
- model=deepseek-chat,temperature=0.3,max_tokens=8000
- response_format=json_object

**脚本**:[scripts/experiments/run_path_b_insight.py](../../scripts/experiments/run_path_b_insight.py)

---

## 4. 结果

### 4.1 成本对比

| 维度 | Path A | Path B |
|------|--------|--------|
| Insight 链本身 | ~¥0.09 | ¥0.10 |
| 上游必需链成本 | ~¥2-3(extraction + comment_extraction + 归一化 + slice_reports) | ¥0 |
| **总 LLM 成本** | **~¥2-3** | **¥0.10** |
| Token 用量 | 累计 500K+ | 49,605(input 46,470 + output 3,135) |
| 调用次数 | 60+ | 1 |

**Path B 便宜 20-30x**。

注:首次调用 prompt cache 未命中,二次调用后 system prompt 部分(~1,100 字符)会 cache 命中,输入成本可再降 ~5%。

### 4.2 产出结构对比

| 维度 | Path A | Path B |
|------|--------|--------|
| social_tensions 条数 | 3 | 4 |
| brand_opportunities 条数 | 2 | 4 |
| opportunities 含 rationale | ❌ 空 | ✅ 完整 |
| opportunities 含 confidence | ❌ 空 | ✅ 完整 |
| Evidence 来源 | 切片编号("slice 0, unmet_needs[0]") | 真实 post_id("post_id=20945") |

### 4.3 定性对比:Path A 的 3 条 Tension

1. **消费者依赖 vs 怀疑**(心理安慰剂 + 健康风险) — 高置信
2. **媒体叙事 vs 消费者口碑割裂**(乐虎媒体失声) — 高置信
3. **品类同质化 vs 场景精细化需求** — 中置信

特点:**宏观、抽象、方向性**。

### 4.4 定性对比:Path B 的 4 条 Tension

1. **年轻消费者从"提神工具"转向"健康透支负罪感"**(与 A#1 同域但角度更犀利)
2. 🔥 **红牛版本混乱从"假货监管"演变为品类系统性信任侵蚀**(A 完全未提)
3. 🔥 **蓝领工具化 vs 情感价值双重需求矛盾**(A 完全未提)
4. 🔥 **运动/体考场景科学使用认知空白**(A 完全未提)

特点:**具体、有 post_id、可直接转 campaign**。

### 4.5 Path B 的 Brand Opportunities 亮点

- **Opp 4:"真能量,不迷惑"透明化运动** — 针对 Tension 2(红牛版本混乱)的 ready-to-use campaign 概念,含完整 rationale 和竞品对比
- **Opp 1:蓝领奋斗者的情感能量站** — 基于乐虎已有骑手纪录片资产放大,含竞品差异化分析

Path A 的 opps 只有两条抽象 statement,rationale 字段为空。

---

## 5. 定量验证:哪边抓住了更重要的议题?

通过原始数据库查询,验证三个议题的真实讨论规模:

```sql
-- 红牛版本混乱(Path B Tension #2,Path A 漏掉)
SELECT COUNT(*), SUM(likes_count) FROM social_posts sp
JOIN social_tasks st ON sp.task_id=st.id
WHERE st.monitor_id=44 AND sp.is_deleted=false
  AND (sp.content ~ '红牛.*(版本|假|正版|影身|分不清|泰国|天丝)'
    OR sp.title ~ '红牛.*(版本|假|正版|影身|分不清|泰国|天丝)');
-- 结果:161 帖, 3,403,155 赞

-- 蓝领/骑手/打工情感(Path B Tension #3,Path A 漏掉)
SELECT COUNT(*), SUM(likes_count) FROM social_posts sp
JOIN social_tasks st ON sp.task_id=st.id
WHERE st.monitor_id=44 AND sp.is_deleted=false
  AND (sp.content ~ '骑手|外卖|蓝领|工地|打工|司机|加班'
    OR sp.title ~ '骑手|外卖|蓝领|工地|打工|司机|加班');
-- 结果:355 帖, 5,425,944 赞

-- 心理安慰剂/智商税(Path A Tension #1)
SELECT COUNT(*), SUM(likes_count) FROM social_posts sp
JOIN social_tasks st ON sp.task_id=st.id
WHERE st.monitor_id=44 AND sp.is_deleted=false
  AND (sp.content ~ '心理作用|安慰剂|没什么用|没效果|智商税'
    OR sp.title ~ '心理作用|安慰剂|没什么用|没效果|智商税');
-- 结果:29 帖, 115,094 赞
```

| 议题 | 讨论规模(帖) | 累计点赞 | Path A 的处理 |
|------|-----------|--------|------------|
| 红牛版本混乱 | **161 帖** | **340 万** | ❌ 完全未提 |
| 蓝领情感 | **355 帖** | **542 万** | ❌ 完全未提 |
| 心理安慰剂 | 29 帖 | 11 万 | ✅ 捧为 Tension #1 |

**Path A 不仅丢失了语境,还严重扭曲了议题的相对重要性。**

真实规模 30-50 倍的议题被漏掉,被捧上 Tension #1 的反而是小众议题。若乐虎据此投放预算,会压在"破除安慰剂质疑"的宣传上,而真正的市场机会在"透明化打法对标红牛"和"蓝领情感能量站"——这是会让市场费用打水漂的错判。

---

## 6. Path B 证据的真实性核查

抽查 Path B 引用的 8 个 post_id 是否真实存在、与描述是否一致:

| post_id | Path B 描述 | 数据库核查 |
|---------|-----------|---------|
| 20437 | 高赞打假视频 62 万+赞 | ✅ 实际 62.4 万赞 |
| 20945 | 辛吉飞红牛三版本视频 | ✅ 标题"红牛影身之术",10.9 万赞 |
| 21079 | 乐虎骑手纪录片 | ✅ "乐虎携手美团《城市摆渡人》",5.9 万赞 |
| 21487 | 东鹏半佛"打工神水" | ✅ 38 万赞 |
| 21500 | 运动饮料 vs 能量饮料科普 | ✅ 4.8 万赞 |
| 21508 | 东鹏瓶盖量米妙用 | ✅ 7.9 万赞,内容一致 |

**全部真实,无幻觉引用**。

---

## 7. 根因分析:为什么 Pipeline 漏掉主流议题?

Pipeline 的问题链路:

```
原始 1313 帖
  ↓ post_extraction:抽取为 entity/sentiment/topic 结构     ← 丢失原话细节
  ↓ normalization:合并同义实体/观点                        ← 丢失语义差别
  ↓ slice_reports:按维度聚合为 heat × sentiment 排序      ← 丢失帖子语境
  ↓ insight_chain:消费聚合数字
```

到 insight_chain 时,看到的是"未满足需求 top 1: 产品提神效果不佳(heat=1752,sentiment=-0.55)"——**看不到**:
- 辛吉飞视频 20945 是 62 万赞的单点爆款(heat 算法把它稀释在 cluster 里)
- 瓶盖妙用、骑手纪录片这些**跨议题的模式**(pipeline 按"需求/品牌/属性"分类,看不到"工具化+情感化"这种跨切片的主题)

更糟的是排序算法偏差:心理安慰剂讨论 sentiment 极负(-0.93),在 `heat × sentiment` 评分下冲到顶。但真实讨论量(29 帖/11 万赞)远低于被漏掉的议题(161 帖+355 帖,880 万赞合计)。

Path B 直接读原始帖,LLM 在自然语境下做 pattern-matching,红牛版本讨论形成明显 cluster、蓝领情感主题自然浮现。

---

## 8. Path B 的局限

诚实声明:

1. **采样偏差风险**:只读 Top 120 帖,长尾数据未进视野。若长尾藏着重要主题,Path B 会漏
2. **无时序信息**:一次性分析不知道"这个议题是上升还是下降",监控场景的价值被丢失
3. **乐虎骑手情感可能被自家纪录片放大**:官方发布的 21079 被乐虎引流,不是纯自发 UGC
4. **无精确定量**:Path A 能给"SOV=17.5%,sentiment=-0.13",Path B 只有定性
5. **n=1 不够**:单个案例的胜负可能有运气成分,需要 n=5 盲评才能定论

**解决路径**(未来扩展):
- 增加采样量(Top 300 帖)或分层采样
- 混合输入:原始帖 + slice 摘要(保留定量能力)
- Self-consistency:多次运行取稳定结果
- 扩展到 5 个项目并做盲评

---

## 9. Path A 做对的部分

避免完全否定 Path A,客观承认其优势:

1. **Tension 1(依赖 vs 怀疑)本身不是错的**,只是被高估了相对重要性
2. **Tension 2(媒体 vs 社媒割裂)是真洞察**,Path B 也没抓到这个角度——这是 pipeline slice 结构带来的跨源量化对比优势
3. **能给出 SOV/heat/sentiment 定量数字**,对需要"量化支撑"的客户展示场景有用(尽管这些数字本身也是 LLM 抽取,精度存疑)

---

## 10. 结论(Strategy #18 单例)

基于 Strategy #18 实验:

1. Path B 在**品类级研究**场景的产出质量、成本、可追溯性三个维度显著优于 Path A
2. Path A 在这个 case 存在系统性的**议题重要性排序扭曲**
3. Path A 的优势集中在"跨源量化对比"和"定量数字",在品类级分析中价值相对有限

但单例不足以推广——见 § 11 的 Strategy #7 反向案例。

---

## 11. 补充实验:Strategy #7(大魔王素毛肚世界杯营销策略)

### 11.1 数据背景

- Strategy ID: 7,social_monitor_id=29,no news
- 主题:大魔王素毛肚品牌的世界杯营销策略
- 社媒帖:1,379,评论:19,259(小红书 + 抖音)
- 特征:**品牌聚焦 + 世界杯 IP 高泛化场景**

### 11.2 Path B 运行结果

- 采样:80 帖(2 平台 × 40)+ 640 评论 + 0 新闻
- Token:input 29,206(含 **448 cache hit**)+ output 2,640
- 成本:¥0.066
- 首次观察到 DeepSeek prompt cache 命中(system prompt 部分被缓存)

### 11.3 产出对比(摘要)

**Path A 的 3 条 tension**:
1. 看球零食"即时满足 vs 事后懊悔"(油腻胀肚)
2. 零食量贩店"丰富渴望 vs 门店体验不满"
3. 🎯 **"素毛肚/魔芋爽"的"认知健康 vs 酱料不足宣传不符"**(直击大魔王品牌核心痛点)

**Path B 的 4 条 tension**:
1. 魔芋爽社媒 vs 新闻健康认知反差(跨源洞察,有价值)
2. 观赛社交需求 vs 食用不便痛点(有价值)
3. ⚠️ "大魔王"IP 泛化联想(Faker 被羞辱、姆巴佩反派)——**偏离 subject**
4. ⚠️ 品牌赞助舆论风险(比亚迪赞助国足)——**与大魔王关联弱**

### 11.4 定量验证

| 议题 | 讨论规模 | Path A | Path B |
|------|--------|--------|--------|
| 麻酱量少/宣传不符(大魔王核心痛点) | **328 帖,463 万赞** | ✅ Tension #3 | ❌ 样本里有 16 帖但未提升为 tension |
| Faker/姆巴佩(IP 泛化) | 9 帖,218 万赞(集中于少数爆款) | 未提 | ⚠️ Tension #3 |
| 比亚迪赞助国足 | 35 帖,209 万赞 | 未提 | ⚠️ Tension #4 |
| 品牌相关总量 | 605 帖,1550 万赞 | 重点覆盖 | 部分覆盖(42/80 采样 on-topic) |

### 11.5 采样偏差验证

Path B 的 Top 80 采样中:
- **只有 52%(42 帖)真正跟品牌相关**
- 16 帖讨论了"麻酱量少"(Path A T3 的核心证据),**但 LLM 没挑成 tension**——可能是"反直觉"约束把 LLM 引导去找非显而易见的结论,反而绕开了品牌最直接的痛点

### 11.6 根因

1. **采样策略的场景错配**:按 engagement Top N 取帖,在品牌聚焦场景下会把 50% 注意力分配给无关的外部 IP 爆款
2. **Prompt 约束的副作用**:"反直觉"约束鼓励 LLM 避开"显而易见",但在品牌研究中,品牌本体的产品痛点(如麻酱量少)恰恰是最应该抓的"显而易见但高价值"议题
3. **缺少 subject 聚焦约束**:Path B 的 prompt 没有强制"优先分析 subject 本体",因此 LLM 发挥自由度过高,飘向无关 IP

### 11.7 对照:Pipeline 在这个场景的优势

Path A 的 slice 结构天然做了"subject 聚焦切片"(Strategy 18 的分析中也看到过这个机制),会把与品牌 subject 相关的讨论单独聚合。insight_chain 消费 slice 时,就不会被 IP 泛化内容稀释。

这是 **pipeline 架构在品牌聚焦场景的真正价值**——不是准确性,而是**强制聚焦性**。

---

## 12. 修正后的结论(n=2)

1. **Path A(Pipeline)和 Path B(LLM-native)没有绝对胜方**,胜负取决于研究主体性质
2. **品类级研究(多品牌/多源/低 IP 噪声)**:Path B 的跨源 pattern-matching 优势大,显著胜
3. **品牌聚焦研究(高 IP 噪声/强 subject 专注需求)**:Path A 的 slice 结构强制聚焦,反而更好
4. **这不是"Path B 更差"**,是"Path B 在 Strategy #7 的 prompt 和采样策略还不够成熟"
5. **修正方向**:Path B 需要场景化调优(subject 聚焦 prompt + 相关度加权采样),而不是废弃
6. **架构决策更新**:见 ADR-001 v2 的"场景化混合架构"

---

## 13. 下一步

1. 扩展到 n≥5 实验(目标混合 2 个品类级 + 3 个品牌聚焦,获得每种场景 ≥2 样本)
2. 实现 `subject_type` 识别(在 brief_parser 中)
3. 实现相关度加权采样策略
4. 实现品牌聚焦场景的 prompt 增强
5. 策略师盲评 5 组 A/B 结果
6. 根据评分做最终决策

见 [ADR-001 § 重构路线图](../adr/001-analysis-architecture.md#重构路线图)。

---

## 附录 A. 可复现材料

- 实验脚本:[scripts/experiments/run_path_b_insight.py](../../scripts/experiments/run_path_b_insight.py)
- 脚本用法:设置 `DEEPSEEK_API_KEY`,修改 `STRATEGY_ID / SOCIAL_MONITOR_ID / NEWS_MONITOR_ID` 后 `python3 run_path_b_insight.py`
- Path A 产出查询:`SELECT insight_result FROM strategies WHERE id=<ID>`(数据库内可查)
- 本次实验涉及 Strategy ID:18(乐虎)、7(大魔王素毛肚)
