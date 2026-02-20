# 模块方案: analysis/project_slice_spam (后端+前端)

> 项目级切片实体/话题增加 4D spam 分布数据，前端展示 SpamRatioBar。

**状态**: 已完成

---

## 背景

任务级分析已有完整的 spam 维度体系（4D 分布 + 3 层图表预计算 + 排序控件），但项目级切片在合并多任务数据时完全丢失了 spam 信息。这导致项目级的实体和话题无法区分推广/有机来源，降低了分析的可信度。

**目标**: 在项目级切片的实体和话题上添加 4D spam 分布数据，前端展示 SpamRatioBar。

---

## 价值分析

只在 foundation 层的实体和话题上添加 spam_distribution（4D），下游视图自然继承。不做图表 3 层预计算（ROI 低，项目级图表与任务级差异大）。

---

## 实施步骤（已完成）

### Step 1: service.py — 查询 spam_score ✅

- SELECT 加入 `PostAnalysis.spam_score`
- `outerjoin(PostAnalysis, PostAnalysis.post_id == SocialPost.id)`
- `post_info_by_key` 写入 `spam_score`
- 传递 `spam_threshold=6.0` 给 `build_project_slice_result()`

### Step 2: project_slice.py — 核心逻辑 ✅

- 新增 `_compute_spam_dist_4d_by_key()` 辅助函数（基于 post_key 而非 post_id）
- 函数签名加 `spam_threshold: float = 6.0`
- 构建 `spam_map_by_key`（post_key → "high"/"low"）
- Entity/Topic bucket 加 `post_source_keys` / `comment_source_keys` 集合
- 合并循环中从任务级实体/话题读取 `post_source_ids` / `comment_source_ids`，分类归入对应 keys 集合
- Finalization 调用 `_compute_spam_dist_4d_by_key()` 计算 spam_distribution
- meta 加 `spam_config: { threshold }`

### Step 3: entity_aggregation.py — Stage 2 传递 ✅

- Bucket 加 `_spam_*` 累加器（4 个 int + 1 个 bool）
- 合并循环读取 `e.get("spam_distribution")`，累加 4 维计数
- 输出构建 `spam_distribution` dict

### Step 4: opinion_aggregation.py — Stage 2 传递 ✅

- 同 Step 3 模式

### Step 5: 前端类型 + 展示 ✅

- `ProjectTopicOrEntity` 接口加 `spam_distribution?: SpamDistribution`
- 导入 `SpamRatioBar` 组件和 `SpamDistribution` 类型
- 证据面板话题行、实体行、实体侧边栏展示 SpamRatioBar

---

## 关键文件

| 文件 | 改动类型 |
|------|----------|
| `backend/src/social_media/analysis/service.py` | 查询加 PostAnalysis join |
| `backend/src/social_media/analysis/project_slice.py` | 核心：spam_map + 来源追踪 + 4D 计算 |
| `backend/.../project_slice/entity_aggregation.py` | Stage 2 传递 |
| `backend/.../project_slice/opinion_aggregation.py` | Stage 2 传递 |
| `frontend/.../projects/[id]/analysis.vue` | 类型 + SpamRatioBar 展示 |

---

## 验证结果

- `pnpm be:lint` (src/) — 通过
- `pnpm fe:typecheck` — 0 errors
- `pnpm fe:lint` — 通过
