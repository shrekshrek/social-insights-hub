# Analysis Module

## Public Interface

- `POST /analysis/screening` — 帖子初筛（spam/value/relevance/sentiment）
- `POST /analysis/deep-posts` — 帖子深度分析（实体/观点/摘要提取）
- `POST /analysis/deep-comments` — 评论深度分析（实体/观点 + 来源追踪）
- `POST /analysis/aggregation` — 任务级聚合（同步执行，返回完整结果）
- `GET /analysis/task/{task_id}/result` — 获取聚合结果
- `POST /analysis/snapshots` — 项目级快照（多任务合并）

## Data Flow

```
初筛 → 深度分析(帖子) → 深度分析(评论) → 聚合
  ↓         ↓                ↓              ↓
spam_score  entities        entities    aggregate_entities()
value_score opinions        opinions    aggregate_opinions()
sentiment   summary                     metrics/charts/insights
```

## Spam 维度体系

### 4D 分布 (SpamDistribution)
实体和观点使用 4 维分布：`high_spam/low_spam × post/comment`
- `post_source_ids` / `comment_source_ids` 分别记录来源
- 通过 `spam_map[post_id]` 映射到 high/low 组

### 2D 分布 (SpamCountBreakdown)
时间分布使用简化的 2 维：`high/low` 计数

### 3 层预计算
关联网络 (ContextGraph) 和竞品雷达 (CompetitorRadar) 按维度预计算：
- `all`: 全部数据
- `organic`: 仅 low_spam 帖子
- `promo`: 仅 high_spam 帖子

默认 spam 阈值: `6.0`（spam_score >= 6.0 为高广告组）

## 聚合流程 (orchestrator.py)

1. 查询所有帖子 + PostAnalysis
2. 计算 CII、NSR、SERP、营销浓度、反差度
3. 并行执行实体聚合 + 观点聚合（含 LLM 归一化）
4. 生成四象限、时间分布
5. 派生洞察：IPA、关联网络、竞品雷达、KOL 声音
6. 附加 spam 分布到所有聚合结果
7. 组装 `TaskAnalysisResultData`

## Important Notes

- **双重情感体系**: 宏观指标（NSR/SERP/四象限）用初筛 -2~+2；微观指标（实体/观点）用深度分析 -1~+1
- **实体角色分类**: target（本品）/ competitor（竞品）/ other，基于 task.keywords 匹配
- **KOL 声音**: 后端返回 top_n=10，前端按 spam_group 筛选（每组约 5 条）
- **IPA 热度去重**: `post_contribution_map` 防止同一帖子对同一词条重复贡献
- **竞品雷达品牌聚合**: 通过 `tags.parent` 将产品归入品牌，展示品牌级对比
