# 切片流水线数据补全方案

## 背景

策略模块（strategies）的 Phase 2/3 Chain 需要时间分布、KOL 声音、IPA 分析等数据，但这些数据目前只存在于任务级 `result_data`，未传播到切片级。

切片流水线的设计初衷是为前端仪表盘提供跨任务归一化后的实体/话题排名和竞品对比。策略模块作为新的消费者，需要更多"故事性"数据来支撑 LLM 生成。

## 目标

在切片 `result_data` 中补全以下 3 类数据，使策略模块和前端都能受益：

| 数据 | 放置位置 | 消费者 |
|------|----------|--------|
| time_distribution | `layers.landscape.time_distribution` | 策略 Phase 2 + 前端时间趋势图 |
| kol_voices | `layers.landscape.kol_voices` | 策略 Phase 2/3 + 前端 KOL 展示 |
| ipa_analysis | `layers.intent.ipa_analysis` | 策略 Phase 3 + 前端 IPA 象限 |

## 现有切片流水线结构

```
Stage 1（同步，service.py + project_slice.py）
  ├─ 查询所有帖子 → post_info_by_key（CII/published_at/spam_score）
  ├─ 跨任务合并实体 → foundation.aligned_entities
  └─ 跨任务合并观点 → foundation.aligned_topics

Stage 2（异步 Celery，orchestrator.py）
  ├─ 并行：实体归一 + 观点归一 → 更新 foundation.aligned_*
  ├─ drivers 计算 → foundation.drivers
  └─ build_slice_layers() → layers.landscape / intent / focus

Stage 3（异步 Celery）
  └─ LLM 报告生成 → reports
```

## 设计方案

### 1. 时间分布 — Stage 1 计算

**原因**：Stage 1 已有 `post_info_by_key`（含 `published_at`），不需要回查数据库。

**改动文件**：`backend/src/social_media/analysis/project_slice.py`

**实现**：在 `build_project_slice_result()` 中，遍历 `post_info_by_key` 构建时间分布。

```python
# 输入：post_info_by_key 中每个 entry 的 published_at
# 输出格式（复用任务级结构）：
{
    "distribution": [
        {"date": "2025-12-01", "count": 15},  # 不含 post_ids（跨任务去重后无意义）
        {"date": "2025-12-02", "count": 23},
    ],
    "skipped_count": 5,
    # freshness 已在 overview 中计算，此处不重复
}
```

**与任务级差异**：
- 不输出 `post_ids`（切片 post_key 无法直接映射到前端可用的 task_id:post_id）
- 不输出 `freshness`（Stage 1 已在 `overview.freshness` 中计算）
- 按 `spam_map_by_key` 分组，额外输出 `organic_distribution` 和 `promo_distribution`

**写入位置**：`layers.landscape.time_distribution`（Stage 1 预写，Stage 2 `build_slice_layers` 透传）

### 2. KOL 声音 — Stage 1 从任务级结果合并

**原因**：KOL 声音需要帖子的 author/title/content/summary 等字段，`post_info_by_key` 中没有这些信息。直接在切片中从头计算 KOL 需要大量数据库查询，不值得。更合理的方式是从各任务的 `result_data.insights.kol_voices` 中合并去重。

**改动文件**：`backend/src/social_media/analysis/project_slice.py`

**实现**：

```python
# 输入：每个任务的 result_data.insights.kol_voices（最多 10 条/任务）
# 合并逻辑：
#   1. 按 (platform, post_id) 去重（同一帖子可能出现在多个任务中）
#   2. 为每条 KOL 补充 spam_group（通过 post_key → spam_map_by_key）
#   3. 重新按 impact_score = CII × quality_factor 排序
#   4. 取 top 10

# 输出格式：
[
    {
        "post_id": 123,           # SocialPost.id（最早出现的任务中的 ID）
        "task_id": 45,            # 来源任务（用于前端跳转）
        "author": "测评达人A",
        "title": "深度评测：...",
        "cii": 8.5,
        "sentiment": 1.2,
        "summary": "...",
        "platform": "xhs",
        "spam_group": "low"       # 新增：organic/promo 标记
    }
]
```

**合并去重策略**：
- 任务级 `kol_voices` 的 `post_id` 是 `SocialPost.id`，同一帖子在不同任务中 ID 不同
- 通过 `post_key_by_id[post_id]` 转为 `platform:post_id_on_platform` 进行去重
- 保留 impact_score 最高的那条记录

**写入位置**：`layers.landscape.kol_voices`

### 3. IPA 分析 — Stage 2 中 build_slice_layers 计算

**原因**：IPA 需要归一化后的 aligned_topics + target entity 的 features/issues，这些在 Stage 2 完成后才可用。

**改动文件**：`backend/src/social_media/analysis/celery_tasks/project_slice/insights.py`

**实现**：在 `build_slice_layers()` 中调用新函数 `_build_ipa()`。

```python
def _build_ipa(
    *,
    topics_aligned: list[dict],
    entities_aligned: list[dict],
    subject: str,
) -> dict | None:
    """基于切片级归一化数据计算 IPA 象限。"""
    # 1. 找到 target entity（role=Target 且名称匹配 subject）
    # 2. 收集 IPA 候选点：
    #    - topics_aligned 中 mentions >= 3 的话题 → (importance=mentions, performance=sentiment)
    #    - target entity 的 features → (importance=mentions, performance=+0.5)
    #    - target entity 的 issues → (importance=mentions, performance=-0.5)
    # 3. 按中位数 mentions 计算 X 阈值，Y 阈值固定 0.0
    # 4. 分配到四象限：strength/improvement/maintain/opportunity
```

**与任务级 IPA 差异**：
- 任务级用 `aggregated_opinions`（未归一化），切片用 `topics_aligned`（已归一化）
- 任务级的 features/issues 来自单任务 target entity，切片来自跨任务合并后的 target entity
- 结果更准确（去重归一后的数据）

**输出格式**（复用任务级结构）：
```python
{
    "quadrants": {
        "strength": [...],      # 高重要性 + 高表现
        "improvement": [...],   # 高重要性 + 低表现
        "maintain": [...],      # 低重要性 + 低表现
        "opportunity": [...]    # 低重要性 + 高表现
    },
    "thresholds": {"x": 10, "y": 0.0}
}
```

**写入位置**：`layers.intent.ipa_analysis`

## 数据流总览（改动后）

```
Stage 1（同步）
  ├─ [现有] 查询帖子 → post_info_by_key
  ├─ [现有] 合并实体/观点 → foundation
  ├─ [新增] 从 post_info_by_key 计算 time_distribution → layers.landscape.time_distribution
  └─ [新增] 从各任务 kol_voices 合并去重 → layers.landscape.kol_voices

Stage 2（异步）
  ├─ [现有] 归一化 → aligned_entities / aligned_topics
  ├─ [现有] drivers → foundation.drivers
  ├─ [现有] build_slice_layers() → landscape / intent / focus
  └─ [新增] _build_ipa() → layers.intent.ipa_analysis

Stage 3（异步）
  └─ [现有] LLM 报告
```

## 对 layers 结构的影响

```
layers:
  landscape:
    [现有] sov_ranking, group_share, platform_dna, industry_quadrant, freshness, overview
    [新增] time_distribution      ← 时间分布（含 organic/promo 拆分）
    [新增] kol_voices             ← KOL 声音 Top 10
  intent:
    [现有] topic_radar, unmet_needs, topic_aspects
    [新增] ipa_analysis           ← IPA 四象限
  focus:
    [现有] swot, gap, platform_scissors, product_line_health
    [无变化]
```

## 改动范围

| 文件 | 改动 | 说明 |
|------|------|------|
| `analysis/project_slice.py` | 修改 | `build_project_slice_result()` 新增 time_distribution 计算 + kol_voices 合并 |
| `analysis/service.py` | 修改 | 传递 kol_voices 数据给 `build_project_slice_result()` |
| `analysis/celery_tasks/project_slice/insights.py` | 修改 | `build_slice_layers()` 新增 `_build_ipa()` 调用 |
| `analysis/celery_tasks/project_slice/orchestrator.py` | 修改 | 传递 kol_voices 到 `build_slice_layers()` 或透传 Stage 1 数据 |

## 对现有数据的影响

- **新切片**：自动包含新字段
- **旧切片**：`layers.landscape.time_distribution` / `kol_voices` / `intent.ipa_analysis` 为 null，前端需兼容
- **无需重算**：旧切片仍可正常展示，只是缺少新字段
- **可选重算**：用户可手动重新生成切片以获取新数据

## 与策略模块的关系

此方案完成后，策略模块的 Phase 2/3 Chain 中读取的数据路径将自动生效：
- `layers.landscape.time_distribution` → Phase 2 时间节奏分析
- `layers.landscape.kol_voices` → Phase 2/3 KOL 声音引用
- `layers.intent.ipa_analysis` → Phase 3 IPA 产品力诊断

Phase 2/3 Chain 中的数据读取路径已修正完毕（strategies 模块收尾时完成）。补全后数据将自动被读取。

## 测试策略

| 场景 | 验证点 |
|------|--------|
| time_distribution 计算 | 跨任务去重帖子的时间分布正确、organic/promo 拆分正确 |
| kol_voices 合并 | 跨任务 post_key 去重、impact_score 排序、spam_group 标记 |
| IPA 四象限 | 阈值计算正确、features/issues 正确映射、空数据兜底 |
| 旧切片兼容 | 无新字段时前端不报错、策略 Chain 拿到空值不崩溃 |
| 重新生成切片 | 新字段正确填充 |
