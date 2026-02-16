# 模块方案: analysis/spam_dimension_chart (后端+前端)

> 关联网络和竞品雷达增加推广/有机维度筛选，后端预计算 3 版本，前端切换展示。

---

## 背景

当前状态：
- **关联网络**: 基于全量 `post_ids` 计算 Jaccard 共现，无维度筛选
- **竞品雷达**: 基于全量 entity 统计（mentions/heat/sentiment_distribution）计算 5 轴雷达图，tooltip 里有 4D spam 数据但无法按维度筛选

用户需求：
- 关联网络：对比推广内容强调的人群/场景/卖点 vs 有机内容中消费者自发讨论的差异
- 竞品雷达：对比品牌整体数据（可能被推广拉高）vs "仅有机"雷达（真实消费者感知）

分析价值：
- 揭示"营销叙事 vs 真实口碑"错位
- 识别品牌营销策略和真实用户关注点的偏差

---

## 设计原则

1. **后端预计算 3 版本**: 聚合时一次性计算全部/有机/推广 3 份数据，避免前端等待重算
2. **前端即时切换**: TabSwitch 在 3 份预计算结果间切换，无 API 调用
3. **复用现有组件**: 复用 TabSwitch，给子图表组件加 slot（同 IPA 模式）
4. **体积可接受**: 两个图表数据量小（关联网络几十个节点，雷达图最多 5 条线），3 倍开销可接受

---

## 1. 数据模型变更

### 后端返回结构

**关联网络** (`context_graph`):
```python
# 原: { center_node, nodes, edges }
# 改:
{
  "all": { center_node, nodes, edges },
  "organic": { center_node, nodes, edges },
  "promo": { center_node, nodes, edges }
}
```

**竞品雷达** (`competitor_radar`):
```python
# 原: { mode, dimensions?, series }
# 改:
{
  "all": { mode, dimensions?, series },
  "organic": { mode, dimensions?, series },
  "promo": { mode, dimensions?, series }
}
```

### 前端类型

```typescript
export interface ContextGraphWithDimensions {
  all: ContextGraph
  organic: ContextGraph
  promo: ContextGraph
}

export interface CompetitorRadarWithDimensions {
  all: CompetitorRadar
  organic: CompetitorRadar
  promo: CompetitorRadar
}

// TaskAnalysisResultData 中字段类型更新
export interface TaskAnalysisCharts {
  ...
  context_graph?: ContextGraphWithDimensions  // 从 ContextGraph 改为 ContextGraphWithDimensions
  competitor_radar?: CompetitorRadarWithDimensions  // 从 CompetitorRadar 改为 CompetitorRadarWithDimensions
}
```

---

## 2. 实施步骤

### Step 1: 提前构建 spam_map [后端]

**文件**: `backend/src/social_media/analysis/celery_tasks/aggregation/orchestrator.py`

修改内容：
- 在调用 `build_context_graph` 和 `analyze_competitor_radar` 之前，先构建 `spam_map`
- 将 `_build_spam_map` 从 `spam_distribution.py` 导入（或复制逻辑）

```python
from .spam_distribution import _build_spam_map

# 在 §5 派生洞察计算之前
spam_map = _build_spam_map(posts_data, threshold=6.0)

# 然后传给 build_context_graph 和 analyze_competitor_radar
context_graph = build_context_graph(
    top_target_full, aggregated_opinions, competitor_entities_full,
    spam_map=spam_map  # 新增参数
)

competitor_radar = analyze_competitor_radar(
    top_target_full, competitor_entities_full, aggregated_entities,
    spam_map=spam_map, posts_data=posts_data  # 新增参数
)
```

### Step 2: build_context_graph 返回 3 版本 [后端]

**文件**: `backend/src/social_media/analysis/celery_tasks/aggregation/insights.py`

修改内容：

1. 函数签名增加 `spam_map` 参数：
   ```python
   def build_context_graph(
       target_entity: Optional[dict[str, Any]],
       aggregated_opinions: list[dict[str, Any]],
       competitor_entities: Optional[list[dict[str, Any]]] = None,
       top_n_per_type: int = 3,
       spam_map: Optional[dict[int, str]] = None,  # 新增
   ) -> dict[str, Any]:
   ```

2. 如果 `spam_map` 为 None，返回 `{ "all": <原有逻辑结果>, "organic": None, "promo": None }`

3. 如果 `spam_map` 非 None，计算 3 个版本：
   - 抽取当前逻辑为内部函数 `_build_single_graph(center_pids, candidates_by_type, dimension_filter)`
   - `dimension_filter` 用于过滤 `post_ids`：
     ```python
     def _filter_pids_by_dimension(pids: set[int], spam_map: dict, dimension: str) -> set[int]:
         if dimension == "all": return pids
         if dimension == "organic": return {pid for pid in pids if spam_map.get(pid) == "low"}
         if dimension == "promo": return {pid for pid in pids if spam_map.get(pid) == "high"}
         return pids
     ```
   - 对每个维度调用 `_build_single_graph`，返回：
     ```python
     {
       "all": _build_single_graph(..., "all"),
       "organic": _build_single_graph(..., "organic"),
       "promo": _build_single_graph(..., "promo"),
     }
     ```

### Step 3: analyze_competitor_radar 返回 3 版本 [后端]

**文件**: `backend/src/social_media/analysis/celery_tasks/aggregation/insights.py`

修改内容：

1. 函数签名增加 `spam_map` 和 `posts_data` 参数：
   ```python
   def analyze_competitor_radar(
       target_entity: Optional[dict[str, Any]],
       competitor_entities: list[dict[str, Any]],
       aggregated_entities: list[dict[str, Any]],
       max_competitors: int = 4,
       spam_map: Optional[dict[int, str]] = None,  # 新增
       posts_data: Optional[list[dict]] = None,  # 新增
   ) -> dict[str, Any]:
   ```

2. 如果 `spam_map` 为 None，返回 `{ "all": <原有逻辑结果>, "organic": None, "promo": None }`

3. 如果 `spam_map` 非 None，计算 3 个版本：
   - 写辅助函数 `_aggregate_entity_stats_by_dimension(entity, spam_map, posts_data, dimension)`，从 entity 的 `post_source_ids` + `comment_source_ids` 按维度重新聚合统计：
     ```python
     def _aggregate_entity_stats_by_dimension(
         entity: dict, spam_map: dict, posts_data: list[dict], dimension: str
     ) -> dict:
         """按 spam 维度重新聚合实体的统计字段"""
         # 1. 过滤 post_source_ids 和 comment_source_ids
         post_src = [pid for pid in entity.get("post_source_ids", [])
                     if _match_dimension(pid, spam_map, dimension)]
         comment_src = [pid for pid in entity.get("comment_source_ids", [])
                        if _match_dimension(pid, spam_map, dimension)]

         # 2. 从 posts_data 中提取对应帖子的统计数据
         mentions = len(post_src) + len(comment_src)

         # 3. 计算 heat (从 posts_data 中取 cii 求和)
         heat = 0.0
         for post in posts_data:
             pid = post.get("post_id")
             if pid in post_src or pid in comment_src:
                 heat += post.get("cii", 0)

         # 4. 计算加权 sentiment 和 sentiment_distribution
         sentiment_weighted_sum = 0.0
         sentiment_weight = 0
         pos_count = neg_count = neu_count = 0
         for post in posts_data:
             pid = post.get("post_id")
             if pid in post_src or pid in comment_src:
                 post_sentiment = post.get("sentiment", 0)
                 post_cii = post.get("cii", 1)
                 sentiment_weighted_sum += post_sentiment * post_cii
                 sentiment_weight += post_cii
                 if post_sentiment > 0: pos_count += 1
                 elif post_sentiment < 0: neg_count += 1
                 else: neu_count += 1

         sentiment = sentiment_weighted_sum / sentiment_weight if sentiment_weight > 0 else 0

         return {
             "mentions": mentions,
             "heat": heat,
             "sentiment": sentiment,
             "sentiment_distribution": {
                 "positive": pos_count,
                 "negative": neg_count,
                 "neutral": neu_count,
             },
         }
     ```
   - 抽取当前逻辑为内部函数 `_build_single_radar(target_data, competitor_data_list, dimension_stats)`
   - 对每个维度：
     - 对所有 entity（target + competitors）调用 `_aggregate_entity_stats_by_dimension`
     - 调用 `_build_single_radar`
   - 返回：
     ```python
     {
       "all": _build_single_radar(..., all_stats),
       "organic": _build_single_radar(..., organic_stats),
       "promo": _build_single_radar(..., promo_stats),
     }
     ```

### Step 4: 前端类型升级 [前端]

**文件**: `frontend/layers/social-media/analysis/types/index.ts`

修改内容：
- 新增 `ContextGraphWithDimensions` 和 `CompetitorRadarWithDimensions` 类型
- `TaskAnalysisCharts` 中更新字段类型

### Step 5: TaskAnalysisReport 增加筛选逻辑 [前端]

**文件**: `frontend/layers/social-media/analysis/components/task/TaskAnalysisReport.vue`

修改内容：

1. 新增状态和选项：
   ```typescript
   const contextGraphFilterMode = ref('all')
   const competitorRadarFilterMode = ref('all')
   const dimensionFilterOptions = [
     { value: 'all', label: '全部' },
     { value: 'organic', label: '仅有机' },
     { value: 'promo', label: '仅推广' },
   ]
   ```

2. 新增 `hasXxxSpamData` computed（检查 organic/promo 是否为 null）：
   ```typescript
   const hasContextGraphSpamData = computed(() => {
     const cg = props.data.charts.context_graph
     return cg?.organic != null && cg?.promo != null
   })

   const hasCompetitorRadarSpamData = computed(() => {
     const cr = props.data.charts.competitor_radar
     return cr?.organic != null && cr?.promo != null
   })
   ```

3. 新增 `filteredXxx` computed：
   ```typescript
   const filteredContextGraph = computed(() => {
     const cg = props.data.charts.context_graph
     if (!cg) return undefined
     const mode = contextGraphFilterMode.value as 'all' | 'organic' | 'promo'
     return cg[mode] || cg.all
   })

   const filteredCompetitorRadar = computed(() => {
     const cr = props.data.charts.competitor_radar
     if (!cr) return undefined
     const mode = competitorRadarFilterMode.value as 'all' | 'organic' | 'promo'
     return cr[mode] || cr.all
   })
   ```

4. 模板中传 `filteredXxx` 给子组件，并添加 TabSwitch 到 slot

### Step 6: ContextGraphChart 增加 slot [前端]

**文件**: `frontend/layers/social-media/analysis/components/task/ContextGraphChart.vue`

修改内容：
- 模板标题行增加 `<slot />` （同 IpaChart 模式）

### Step 7: CompetitorRadarChart 增加 slot [前端]

**文件**: `frontend/layers/social-media/analysis/components/task/CompetitorRadarChart.vue`

修改内容：
- 模板标题行增加 `<slot />` （同 IpaChart 模式）

---

## 3. 边界情况与错误处理

| 场景 | 处理方式 |
|------|---------|
| 无 spam_score 数据（旧任务） | spam_map 为空 dict，返回 `{ all: <原逻辑>, organic: None, promo: None }` |
| 维度过滤后节点/品牌为空 | 返回空图表（nodes: [], series: []），前端正常渲染空状态 |
| 某维度数据不足（如全是推广） | 该维度返回有效数据，其他维度为空，前端切换时展示对应结果 |
| 前端旧报告（单层结构） | 类型兼容：`context_graph: ContextGraph | ContextGraphWithDimensions`，前端判断是否有 all 字段 |

---

## 4. 测试策略

### 后端
- `pnpm be:lint` 通过
- `pnpm be:test` 通过
- 手动验证：重新执行聚合分析，检查 `context_graph` 和 `competitor_radar` 输出为 3 层结构

### 前端
- `pnpm fe:typecheck` 通过
- `pnpm fe:lint` 通过
- 手动验证：切换筛选标签，关联网络节点变化，雷达图形状变化

---

## 5. 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 预计算 vs 重算 | 预计算 3 版本 | 用户交互无等待，数据量小体积增加可接受 |
| 关联网络过滤策略 | 中心节点和候选节点的 post_ids 都按维度过滤 | Jaccard 计算"维度内共现关系" |
| 竞品雷达统计来源 | 从 posts_data 按维度重新聚合 | 保证统计准确性，避免从 aggregated_entities 推断 |
| 前端兼容旧报告 | 类型联合 + 判断 all 字段 | 优雅降级，旧报告显示全部维度 |
| spam_map 阈值 | 固定 6.0 | 与 spam_distribution 模块保持一致 |
