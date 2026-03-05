# 模块方案: 切片流水线数据补全

> 为切片 result_data 补全 time_distribution、kol_voices、ipa_analysis，使策略模块和前端都能受益。

**设计文档**: `docs/plans/2026-03-05-slice-pipeline-enrichment-design.md`

---

## 1. Data Model

无新表。仅扩展 `ProjectAnalysisSlice.result_data` JSONB 的 3 个字段位置：

| 字段路径 | 计算阶段 | 数据结构 |
|----------|----------|----------|
| `layers.landscape.time_distribution` | Stage 1 | `{distribution: [{date, count}], organic_distribution, promo_distribution, skipped_count}` |
| `layers.landscape.kol_voices` | Stage 1 | `[{post_id, task_id, author, title, cii, sentiment, summary, platform, spam_group}]` (top 10) |
| `layers.intent.ipa_analysis` | Stage 2 | `{quadrants: {strength, improvement, maintain, opportunity}, thresholds: {x, y}}` |

time_distribution 输出格式：

```python
{
    "distribution": [
        {"date": "2025-12-01", "count": 15},
        {"date": "2025-12-02", "count": 23},
    ],
    "organic_distribution": [
        {"date": "2025-12-01", "count": 10},
        {"date": "2025-12-02", "count": 18},
    ],
    "promo_distribution": [
        {"date": "2025-12-01", "count": 5},
        {"date": "2025-12-02", "count": 5},
    ],
    "skipped_count": 3,  # published_at 为 None 的帖子数
}
```

kol_voices 输出格式：

```python
[
    {
        "post_id": 123,        # SocialPost.id（保留最佳条目的 ID）
        "task_id": 45,         # 来源任务（用于前端跳转）
        "author": "测评达人A",
        "title": "深度评测：...",
        "cii": 8.5,
        "sentiment": 1.2,
        "summary": "...",
        "platform": "xhs",
        "spam_group": "low",   # 从 spam_map_by_key 映射
    }
]
```

ipa_analysis 输出格式（复用任务级结构）：

```python
{
    "quadrants": {
        "strength": [
            {"name": "...", "mentions": 20, "sentiment": 0.5, "heat": 100.0, "z": 0.8, "source_type": "topic"}
        ],
        "improvement": [...],
        "maintain": [...],
        "opportunity": [...]
    },
    "thresholds": {"x": 10, "y": 0.0}
}
```

---

## 2. API / Interface Design

无新 API 端点。数据通过现有接口自动返回：
- 切片详情 `GET /analysis/slices/{id}/result` → 含新字段
- 策略 Chain 的 `_load_slice_data()` → 自动读取 `layers.*` 字段

---

## 3. Implementation Steps

### Step 1: 实现 time_distribution 计算

**文件**: `backend/src/social_media/analysis/project_slice.py` (修改)

**接口**:
```python
def _compute_time_distribution(
    post_info_by_key: dict[str, dict[str, Any]],
    spam_map_by_key: dict[str, str],
) -> dict[str, Any]:
    """从去重后的帖子信息计算时间分布。

    Returns:
        {distribution, organic_distribution, promo_distribution, skipped_count}
    """
```

**逻辑**:
1. 遍历 `post_info_by_key`，解析 `published_at` 为日期字符串 (YYYY-MM-DD)
2. 按日期聚合 count（全量 / organic / promo 三组）
3. 无法解析 `published_at` 的条目计入 `skipped_count`
4. 按日期排序返回

**关键断言**:
- 3 条帖子 2 个日期 → distribution 有 2 项，count 之和 = 3
- 含 spam_score >= 6 的帖子 → promo_distribution 有对应条目
- published_at 为 None 的帖子 → skipped_count 递增
- 空 post_info_by_key → 返回 `{distribution: [], organic_distribution: [], promo_distribution: [], skipped_count: 0}`

**验证**: `pnpm be:test -- -k "test_compute_time_distribution"`

**依赖**: 无

---

### Step 2: 实现 kol_voices 合并

**文件**: `backend/src/social_media/analysis/project_slice.py` (修改)

**接口**:
```python
def _merge_kol_voices(
    task_data_list: list[dict[str, Any]],
    post_key_by_id: dict[int, str],
    spam_map_by_key: dict[str, str],
    *,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """从各任务的 kol_voices 合并去重，按 CII 排序取 top_n。"""
```

**逻辑**:
1. 遍历每个任务的 `analysis_result.insights.kol_voices`
2. 通过 `post_key_by_id[post_id]` 转为 post_key，按 post_key 去重
3. 同一 post_key 保留 CII 最高的条目
4. 从 `spam_map_by_key` 映射 spam_group（找不到则为 None）
5. 按 CII 降序排序，取 top_n

**关键断言**:
- 2 个任务含同一帖子（不同 post_id，相同 post_key）→ 去重后仅 1 条，保留 CII 高的
- 合并 15 条 → 返回 top 10
- KOL 的 spam_group 从 spam_map_by_key 正确映射
- 某任务无 insights 或 kol_voices → 跳过不报错
- post_key_by_id 中找不到 post_id → 跳过该 KOL

**验证**: `pnpm be:test -- -k "test_merge_kol_voices"`

**依赖**: 无

---

### Step 3: 集成到 build_project_slice_result

**文件**: `backend/src/social_media/analysis/project_slice.py` (修改)

**改动**:
在 `build_project_slice_result()` 的返回值中，`layers.landscape` 下新增两个字段：
```python
"layers": {
    "landscape": {
        "freshness": freshness,
        "overview": overview,
        "time_distribution": _compute_time_distribution(post_info_by_key, spam_map_by_key),
        "kol_voices": _merge_kol_voices(task_data_list, post_key_by_id, spam_map_by_key),
    },
    ...
}
```

**关键断言**:
- `build_project_slice_result()` 返回值中 `layers.landscape.time_distribution` 是 dict
- `build_project_slice_result()` 返回值中 `layers.landscape.kol_voices` 是 list

**验证**: `pnpm be:test -- -k "test_build_project_slice"`

**依赖**: Step 1, Step 2

---

### Step 4: Stage 2 透传 + IPA 集成

**文件**: `backend/src/social_media/analysis/celery_tasks/project_slice/orchestrator.py` (修改), `backend/src/social_media/analysis/celery_tasks/project_slice/insights.py` (修改)

**改动 — orchestrator.py**:
从 Stage 1 的 `land0` 中读取 time_distribution 和 kol_voices，传给 `build_slice_layers()`:
```python
layers = build_slice_layers(
    meta=result.get("meta") or {},
    overview=land0.get("overview") ...,
    freshness=land0.get("freshness") ...,
    entities_aligned=entities_aligned,
    topics_aligned=topics_aligned,
    drivers=...,
    # 新增：Stage 1 预计算数据透传
    time_distribution=land0.get("time_distribution"),
    kol_voices=land0.get("kol_voices"),
)
```

**改动 — insights.py `build_slice_layers()`**:
```python
def build_slice_layers(
    *,
    meta: dict[str, Any],
    overview: dict[str, Any],
    freshness: dict[str, Any] | None,
    entities_aligned: list[dict[str, Any]],
    topics_aligned: list[dict[str, Any]],
    drivers: dict[str, Any] | None,
    # 新增
    time_distribution: dict[str, Any] | None = None,
    kol_voices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
```

传给 `_build_landscape()`，并在 intent 中调用 `_build_ipa()`。

**改动 — insights.py `_build_landscape()`**:
新增 `time_distribution` 和 `kol_voices` 参数，写入返回 dict。

**关键断言**:
- Stage 2 输出的 `layers.landscape` 包含 Stage 1 预计算的 time_distribution
- Stage 2 输出的 `layers.landscape` 包含 Stage 1 预计算的 kol_voices
- Stage 2 输出的 `layers.intent` 包含 ipa_analysis（有 subject 时）

**验证**: `pnpm be:test -- -k "test_build_slice_layers"`

**依赖**: Step 3

---

### Step 5: 实现 _build_ipa 函数

**文件**: `backend/src/social_media/analysis/celery_tasks/project_slice/insights.py` (修改)

**接口**:
```python
def _build_ipa(
    *,
    topics_aligned: list[dict[str, Any]],
    entities_aligned: list[dict[str, Any]],
    subject: str,
    min_mentions: int = 3,
) -> dict[str, Any] | None:
    """基于切片级归一化数据计算 IPA 四象限。

    数据来源:
    1. topics_aligned — mentions 作为 importance，sentiment 作为 performance
    2. target entity 的 top_features (sentiment=+0.5) 和 top_issues (sentiment=-0.5)

    Returns:
        {quadrants: {strength, improvement, maintain, opportunity}, thresholds: {x, y}}
        如果无法找到 target entity 或无有效候选项，返回 None。
    """
```

**逻辑**:
1. 在 `entities_aligned` 中找 `role == "Target"` 的实体（可能多个，取第一个）
2. 收集 IPA 候选点:
   - `topics_aligned` 中 `mentions >= min_mentions` 的话题 → `{name, mentions, sentiment, heat, source_type: "topic"}`
   - target entity 的 `top_features` → `{name=text, mentions, sentiment=+0.5, heat=mentions*avg_heat, source_type: "feature"}`
   - target entity 的 `top_issues` → `{name=text, mentions, sentiment=-0.5, heat=mentions*avg_heat, source_type: "issue"}`
3. 计算 avg_heat_per_mention = topics 总 heat / 总 mentions（给 features/issues 估算 heat 用）
4. X 阈值 = 候选点 mentions 中位数，Y 阈值 = 0.0
5. 按 (mentions vs X, sentiment vs Y) 分配到四象限
6. 归一化 z 值（heat → 0~1 范围，用于前端气泡大小）

**关键断言**:
- 有 target entity + 话题 mentions >= 3 → 返回四象限结构
- target features (sentiment=+0.5, mentions=高) → 进入 strength 象限
- target issues (sentiment=-0.5, mentions=高) → 进入 improvement 象限
- 无 target entity → 返回 None
- 所有候选 mentions < min_mentions → 返回 None
- X 阈值 = 中位数 mentions，Y 阈值 = 0.0

**验证**: `pnpm be:test -- -k "test_build_ipa"`

**依赖**: 无

---

### Step 6: 将 _build_ipa 集成到 build_slice_layers

**文件**: `backend/src/social_media/analysis/celery_tasks/project_slice/insights.py` (修改)

**改动**:
在 `build_slice_layers()` 中，`_build_intent()` 之后调用 `_build_ipa()`：
```python
intent = _build_intent(topics_aligned=topics_aligned)

# IPA（仅在有 subject 时计算）
if subject:
    ipa = _build_ipa(
        topics_aligned=topics_aligned,
        entities_aligned=entities_aligned,
        subject=subject,
    )
    if ipa is not None:
        intent["ipa_analysis"] = ipa
```

**关键断言**:
- 有 subject → intent 含 ipa_analysis 键
- 无 subject → intent 无 ipa_analysis 键

**验证**: `pnpm be:test -- -k "test_build_slice_layers"`

**依赖**: Step 4, Step 5

---

## 4. Edge Cases & Error Handling

| 场景 | 处理方式 |
|------|----------|
| `published_at` 为 None 或格式异常 | 计入 `skipped_count`，不中断 |
| 全部帖子无 `published_at` | `distribution` 为空列表 |
| 某任务 `analysis_result` 无 `insights` 或 `kol_voices` | 跳过该任务 |
| `post_key_by_id` 中找不到某 KOL 的 `post_id` | 跳过该条 KOL |
| 无 target entity（subject 为空或 role 不匹配） | `_build_ipa()` 返回 None，intent 不含 ipa_analysis |
| `topics_aligned` 全部 mentions < 3 且 target 无 features/issues | `_build_ipa()` 返回 None |
| 旧切片无新字段 | 前端兼容 null；策略 Chain 的 format 函数对空值跳过 |
| `published_at` 为 ISO 格式字符串（含时区） | 正确解析为日期 |
| task_data_list 为空 | kol_voices 返回空列表 |

---

## 5. Test Strategy

### 需要测试

| 函数 | 测试文件 | 场景数 |
|------|----------|--------|
| `_compute_time_distribution` | `tests/social_media/analysis/test_project_slice.py` | 4: 正常多日期、无 published_at、organic/promo 拆分、空输入 |
| `_merge_kol_voices` | `tests/social_media/analysis/test_project_slice.py` | 4: 跨任务去重、CII 排序取 top_n、spam_group 映射、空/异常数据 |
| `_build_ipa` | `tests/social_media/analysis/test_slice_insights.py` | 5: 四象限分配、features/issues 映射、无 target、空数据、阈值计算 |

### 不需要单独测试

- orchestrator 透传（简单赋值，集成覆盖）
- `_build_landscape` 新增参数（简单透传）
- `build_slice_layers` 的签名变更（由 `_build_ipa` 和透传的测试组合覆盖）

---

## 6. Key Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| time_distribution 在 Stage 1 计算 | ✅ | Stage 1 已有 `post_info_by_key`（含 published_at），不需额外数据 |
| kol_voices 在 Stage 1 合并 | ✅ | Stage 1 已有 `task_data_list`（含 analysis_result.insights.kol_voices），不需回查数据库 |
| IPA 在 Stage 2 计算 | ✅ | IPA 需要归一化后的 topics_aligned 和 entities_aligned，这些在 Stage 2 完成 |
| KOL 去重用 post_key | ✅ | `platform:post_id_on_platform` 是跨任务唯一标识；`SocialPost.id` 在不同任务中不同 |
| IPA 不用任务级 `aggregated_opinions` | ✅ | 切片有归一化后的 `topics_aligned`，数据质量更高且已去重 |
| time_distribution 不含 post_ids | ✅ | 切片 post_key 无法直接映射到前端可用的 task_id:post_id |
| Stage 2 透传而非重算 | ✅ | 简单透明，避免重复计算；orchestrator 已有读 Stage 1 layers 的模式 |
