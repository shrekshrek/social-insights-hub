# Strategy Research Engine — 完整设计方案

> 将策略模块从"末端消费者"重构为"智能研究编排者"。
> 用户全程留在策略页面，系统自动完成 Monitor 创建、任务管理、切片创建。

---

## 设计理念

**用户做决策，系统做操作。**

现有流程要求用户在策略页和监测页之间来回跳转，手动建切片、手动关联。新方案中，策略是唯一的编排者：自动创建 Monitor、自动创建任务、自动创建切片。用户只在 4 个节点做判断：

1. 确认研究计划
2. 处理探测异常（大多数情况自动通过）
3. 确认数据就绪
4. 编辑产出

---

## 整体流程

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ① 告诉我你要什么                                             │
│                                                              │
│  用户填 Brief（或上传文档）                                    │
│  → AI 生成研究计划（研究问题 + 关键词方案 + 切片蓝图）          │
│  → 用户在策略页内编辑确认                                      │
│                                                              │
│  ② 让我先看看数据对不对                                        │
│                                                              │
│  系统自动：创建 Monitor → 创建探测任务 → 爬虫采 15 条          │
│  → 完整分析 → AI 审查质量                                     │
│  → 全部合格：自动继续全量采集（用户无需操作）                    │
│  → 有问题：通知用户，在策略页内调整关键词                       │
│                                                              │
│  ③ 数据准备好了                                               │
│                                                              │
│  全量采集+分析完成                                             │
│  → 系统按照切片蓝图自动创建切片                                 │
│  → AI 验证切片是否覆盖所有研究问题                              │
│  → 用户看到：数据全景 + 已创建的切片 + 验证结果                 │
│  → 用户可微调切片或直接确认                                    │
│                                                              │
│  ④ 出结果                                                     │
│                                                              │
│  Phase 1 → 2 → 3（或按产出类型选模板）                         │
│  → 编辑 → 导出                                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 阶段详细设计

### ① 告诉我你要什么

**目的**：把一份模糊的 Brief 转化为可执行的研究计划。

#### 用户操作

1. 创建策略，填写 Brief（手动 或 上传文档自动解析）
2. 点击「生成研究计划」
3. 看到 AI 产出：
   - **需求理解**：一段话概括对 Brief 的理解
   - **研究问题**：Brief 被拆解成 2-4 个具体问题
   - **数据采集方案**：每个研究问题对应的关键词×平台组合
   - **切片蓝图**：预计最终如何切片，每个切片服务哪些研究问题
   - **建议产出类型**：品牌策略 / 洞察报告
4. 用户可编辑所有字段
5. 确认 → 系统自动创建 Monitor + 探测任务

#### AI: research_design_chain

替代现有 consult_chain。

输入：Brief（brand_name + analysis_goal + constraints）+ 用户补充说明

输出：
```json
{
  "understanding_summary": "理解品牌在XX品类的竞争格局...",

  "research_questions": [
    {
      "id": "rq1",
      "question": "大魔王在零食品类���的消费者认知如何？",
      "dimension": "brand_voice",
      "priority": "high"
    },
    {
      "id": "rq2",
      "question": "主要竞品的社媒表现如何？",
      "dimension": "competitive",
      "priority": "high"
    }
  ],

  "data_plan": [
    {
      "dimension_name": "品牌声量",
      "keywords": ["大魔王", "大魔王素毛肚"],
      "platforms": ["xiaohongshu", "douyin"],
      "probe_size": 15,
      "full_size": 50,
      "rationale": "零食品类在小红书和抖音讨论最活跃"
    },
    {
      "dimension_name": "品类大盘",
      "keywords": ["魔芋爽零食"],
      "platforms": ["xiaohongshu", "douyin"],
      "probe_size": 15,
      "full_size": 50,
      "rationale": "了解品类整体热度和消费趋势"
    }
  ],

  "slice_blueprint": [
    {
      "name": "大魔王品牌诊断",
      "mode": "品牌聚焦",
      "subject": "大魔王",
      "competitors": ["卫龙", "良品铺子"],
      "source_dimensions": ["品牌声量"],
      "serves_questions": ["rq1"]
    },
    {
      "name": "零食品类竞争格局",
      "mode": "大盘分析",
      "subject": "",
      "competitors": [],
      "source_dimensions": ["品类大盘", "竞品声量"],
      "serves_questions": ["rq2"]
    }
  ],

  "output_type": "brand_strategy",
  "output_type_rationale": "Brief 要求制定社媒策略"
}
```

与现有 consult_chain 的区别：
- 多了**研究问题层**（关键词选择有可追溯的理由）
- 切片蓝图带 `serves_questions` 映射（后续验证可按问题检查覆盖度）
- 带 `probe_size` / `full_size` 指导增量采集
- 带产出类型预判

#### 系统行为

用户确认后（confirm_research）：
1. 创建一个 Monitor（名称 = 策略名称）
2. 为 data_plan 中每个关键词组×平台创建 DataTask：
   - `task_params.probe_size = 15`
   - `task_params.max_notes_count = 50`（full_size）
   - `auto_analyze = true`
3. 记录 monitor_id 和所有 task_id 到策略
4. 策略状态 → `probing`

#### 快速路径

用户已有数据和切片 → 跳过 ①②③，直接关联切片进入 ④。

---

### ② 让我先看看数据对不对

**目的**：用最少的采集成本验证关键词质量。大多数情况下自动通过，不打断用户。

#### 为什么需要探测

采集是整个流程中最耗时的环节（含视频转写）。50 条 vs 15 条差异显著。先验证方向再全量采集，避免浪费。

#### 系统行为

1. 爬虫看到 `task_params.probe_size = 15`，先采 15 条（含转写）
2. 上传 15 条 → 后端存入，任务状态 → `probe_ready`
3. 自动触发完整分析管线（screening → deep → aggregation）
4. 分析完成后，任务的 `analysis_result` 就绪

当策略关联的**所有探测任务都分析完成**时，自动触发 probe_review_chain。

#### AI: probe_review_chain

输入：
- 每个任务的 analysis_result 摘要（实体列表、话题列表、screening 通过率、spam 比例）
- 原始研究计划中的研究问题和预期

输出：
```json
{
  "assessments": [
    {
      "keyword": "大魔王",
      "platform": "xiaohongshu",
      "quality": "good",
      "relevance_rate": 0.84,
      "entity_match": true,
      "topic_relevance": "high",
      "verdict": "proceed",
      "note": null
    },
    {
      "keyword": "素毛肚",
      "platform": "douyin",
      "quality": "poor",
      "relevance_rate": 0.33,
      "entity_match": false,
      "topic_relevance": "low",
      "verdict": "refine",
      "note": "大量烹饪教程，品牌相关内容极少。建议改用「魔芋爽零食」"
    }
  ],
  "overall_verdict": "partial_pass",
  "refinement_suggestions": [
    {
      "original_keyword": "素毛肚",
      "suggested_keyword": "魔芋爽零食",
      "platform": "douyin",
      "reason": "原关键词在抖音返回大量烹饪教程"
    }
  ]
}
```

#### 自动化逻辑

- `all_pass`（所有 verdict = proceed）→ **自动**标记所有任务 approved，爬虫继续采集。策略状态 → `collecting`。用户无需操作。
- `partial_pass` / `fail` → 通知用户。策略页面显示探测报告。

#### 用户操作（仅在有问题时）

```
┌─────────────────────────────────────────────────────┐
│  探测报告                                            │
│                                                     │
│  ✅ 大魔王 × 小红书     相关率 84%   品牌命中 ✓      │
│     发现实体: 大魔王、卫龙、素毛肚                     │
│     主要话题: 零食测评、口感对比                       │
│     → 已自动继续采集                                  │
│                                                     │
│  ⚠️ 素毛肚 × 抖音       相关率 33%   品牌命中 ✗      │
│     发现实体: 毛肚、火锅                              │
│     主要话题: 烹饪教程、火锅食材                       │
│     → AI 建议: 关键词改为「魔芋爽零食」                │
│                                                     │
│  [接受建议并重新探测]  [忽略问题继续采集]  [放弃该维度] │
└───────────────��─────────────────────────────────────┘
```

选择：
- **接受建议并重新探测**：取消不合格任务，用新关键词创建新探测任务 → 回到 probing
- **忽略问题继续采集**：标记 approved，爬虫继续
- **放弃该维度**：取消任务，从切片蓝图中移除该数据来源

#### 循环限制

- 调整关键词后重新探测 → 最多 3 轮
- 合格的任务不等待不合格的，先行继续采集

---

### ③ 数据准备好了

**目的**：全量数据采集分析完成后，自动组织切片，让用户确认。

#### 增量采集协议（方案 B）

爬虫侧支持同一 DataTask 分两次上传：

```
爬虫端                              后端
  │                                  │
  │  采集 15 条 → 上传 (首次)         │
  │                → 存入 DB          │
  │                → status=probe_ready│
  │                → 触发完整分析      │
  │                                  │
  │  轮询任务状态                      │
  │  (等待 approved / rejected)       │
  │                                  │
  │  status=approved → 继续采集 35 条  │
  │  → 追加上传 (第二次)              │
  │                → 追加到现有数据     │
  │                → 清空旧分析结果     │
  │                → 用全部 50 条重跑分析│
  │                → status=completed  │
```

upload_result 行为矩阵：

| 当前 status | 上传行为 | 新 status |
|-------------|----------|-----------|
| accepted / running | 首次存入。有 probe_size → 不标记完成 | probe_ready |
| accepted / running | 首次存入。无 probe_size → 正常完成 | completed |
| approved | 追加数据（不清空），重跑分析 | completed |
| completed | 覆盖（现有 re-upload 逻辑） | completed |

Agent API 新增：

| 端点 | 说明 |
|------|------|
| `GET /agent/tasks/{id}` | 返回任务当前 status，供爬虫轮询 |

DataTask.status 扩展：

```
现有:  pending → accepted → running → completed / failed
新增:  ... → running → probe_ready → approved → completed / failed
```

#### 自动建切片

当策略关联的所有正式任务（status=completed）分析完成后，系统自动：

1. 读取切片蓝图（slice_blueprint）
2. 将 data_plan 中的 dimension_name 映射到实际创建的 task_id
3. 按蓝图创建 AnalysisSlice：
   - 选择对应维度的任务
   - 设置 name / subject / competitors
   - 触发切片分析管线（现有 monitor_slice 流程）
4. 切片分析完成后，自动关联到策略（StrategySlice）
5. 触发 coverage_check_chain 验证覆盖度

映射示例：
```
slice_blueprint:
  "大魔王品牌诊断" → source_dimensions: ["品牌声量"]

data_plan → task 映射:
  "品牌声量" → task_1 (大魔王-xhs), task_2 (大魔王-dy)

自动创建:
  AnalysisSlice(name="大魔王品牌诊断", subject="大魔王",
                competitors=["卫龙","良品铺子"], tasks=[task_1, task_2])
```

#### AI: coverage_check_chain

替代现有 architect_chain + evaluate_chain 的组合。

输入：
- research_questions
- 已创建切片的 result_data 摘要（实体、话题、帖子量、平台覆盖）
- Brief

输出：
```json
{
  "question_coverage": [
    {
      "question_id": "rq1",
      "question": "大魔王在零食品类中的消费者认知如何？",
      "covered": true,
      "covered_by": "大魔王品牌诊断",
      "note": null
    },
    {
      "question_id": "rq2",
      "question": "主要竞品的社媒表现如何？",
      "covered": true,
      "covered_by": "零食品类竞争格局",
      "note": "良品铺子数据较薄（15条），但竞品格局分析仍可进行"
    }
  ],
  "overall_ready": true,
  "data_highlights": [
    "品牌声量数据充足（200+帖子），情感倾向以正面为主",
    "发现未预期的高频实体「海底捞」，可能代表跨界竞争视角"
  ],
  "slice_adjustments": []
}
```

如果 `overall_ready = false`，给出原因和建议：
- 切片配置问题 → 建议调整切片（如"把 task_5 也加入竞争格局切片"）
- 研究设计遗漏 → 建议回 ① 扩展计划

不输出补采建议。数据采集在 ②③ 已经完成。

#### 用户操作

```
┌────────────────────────────────────────────────────┐
│  数据就绪                                           │
│                                                    │
│  研究问题覆盖度:                                     │
│  ✅ rq1: 大魔王消费者认知 → 品牌诊断切片覆盖          │
│  ✅ rq2: 竞品格局 → 竞争格局切片覆盖                  │
│                                                    │
│  已创建切片:                                         │
│  📊 大魔王品牌诊断 (品牌聚焦, 120条, 2平台)           │
│  📊 零食品类竞争格局 (大盘分析, 180条, 3平台)          │
│                                                    │
│  💡 发现: 海底捞在数据中高频出现，可能值得关注         │
│                                                    │
│  [微调切片]  [确认，开始生成]                          │
└────────────────────────────────────────────────────┘
```

微调切片（弹窗，不离开策��页）：
- 给切片增加/移除任务
- 修改 subject / competitors
- 新建切片（从现有任务中选）
- 删除切片
- 修改后重新触发切片分析 + 覆盖度验证

---

### ④ 出结果

**与现有 Phase 1/2/3 逻辑基本一致。**

#### 改进点

1. **research_questions 注入**：Phase 1 chain 收到结构化的研究问题列表，洞察提取围绕具体问题，而非泛泛分析
2. **understanding_summary 贯穿**：研究设计的需求理解摘要传入所有 Phase chain
3. **一键生成**（可选）：自动跑完 Phase 1→2→3，出完整结果后统一编辑
4. **output_type 预留**：V1 只支持 `brand_strategy`（现有 Phase 1→2→3）。后续扩展 `insight_report`（Phase 1 → 跳过 Phase 2 → 洞察总结模板）

#### Phase 数据流（不变）

```
Phase 1 (洞察层): Brief + research_questions + understanding_summary + 切片数据
                  → social_tensions + brand_opportunities

Phase 2 (策略层): Phase 1 JSON + 切片 KOL/平台数据
                  → brand_social_role + social_strategy

Phase 3 (创意层): Phase 1+2 JSON + 切片内容特征数据
                  → big_idea + content_strategy
```

编辑 Phase 1 → 清空 Phase 2+3（现有行为保留）。

导出 Word（现有 export_docx 保留）。

---

## 状态机

```python
STATUS = {
    "draft":       0,   # Brief 已填写
    "planned":     1,   # 研究计划就绪
    "probing":     2,   # 探测采集+分析中
    "collecting":  3,   # 全量采集+分析中
    "ready":       4,   # 切片已创建+验证通过，数据就绪
    "completed":   5,   # 产出完成
}
```

状态转移：

```
draft ──[design_research]──→ planned ──[confirm]──→ probing
  ↑                            ↑                      │
  │                            │               ┌──────┴──────┐
  │                            │             全部合格      有不合格
  │                            │             (自���)       (��户决定)
  │                            │               │              │
  │                            │               ▼         调整关键词
  │                            │           collecting    → probing
  │                            │               │
  │                            │               ▼ 自动建切片+验证
  │                            │             ready
  │                            │               │
  │                            │          [generate]
  │                            │               ↓
  │                            │           completed
  │                            │
  │                            └── 研究设计遗漏（极少）──┘
  │
  └──── 快速路径: 用户自带切片，直接进入 ready ────────────┘
```

---

## 自动化逻辑

| 触发条件 | 自动行为 |
|----------|----------|
| 策略所有探测任务分析完成 | 运行 probe_review_chain |
| probe_review 全部 proceed | 标记所有任务 approved，策略状态 → collecting |
| 策略所有正式任务分析完成 | 按 slice_blueprint 创建 AnalysisSlice |
| 切片分析完成 | 运行 coverage_check_chain，策略状态 → ready |
| Phase 3 生成完成 | 策略状态 → completed |

---

## LLM Chain 清单

| Chain | 新/改/删 | 用途 |
|-------|---------|------|
| research_design_chain | **新**（替代 consult） | Brief → 研究问题 + 数据方案 + 切片蓝图 |
| probe_review_chain | **新** | 审查探测分析结果，判断关键词质量 |
| coverage_check_chain | **新**（替代 architect + evaluate 组合） | 对照研究问题验证切片覆盖度 |
| phase1_chain | **改** | 注入 research_questions + understanding_summary |
| phase2_chain | **改** | 注入 research_questions |
| phase3_chain | **改** | 注入 research_questions |
| brief_parser_chain | **不变** | Brief 文档解析 |
| consult_chain | **删** | 被 research_design_chain 替代 |
| architect_chain | **删** | 功能被 coverage_check_chain 吸收 |
| evaluate_chain | **删** | 功能被 coverage_check_chain 吸收 |

---

## Strategy 数据模型

```python
class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int]
    name: Mapped[str]
    created_by: Mapped[int]        # FK → users

    # 状态
    status: Mapped[str]            # draft / planned / probing / collecting / ready / completed

    # Brief
    brand_brief: Mapped[dict | None]  # BrandBrief JSON

    # ① 研究设计
    research_design: Mapped[dict | None]  # research_design_chain 完整输出

    # ② 探测
    probe_review_result: Mapped[dict | None]  # probe_review_chain 输出
    probe_round: Mapped[int]                  # 当前探测轮次 (最多3)

    # ③ 数据
    coverage_check_result: Mapped[dict | None]  # coverage_check_chain 输出

    # ④ 产出
    output_type: Mapped[str | None]    # brand_strategy / insight_report (V2)
    phase1_result: Mapped[dict | None]
    phase2_result: Mapped[dict | None]
    phase3_result: Mapped[dict | None]

    # 关联
    monitor_id: Mapped[int | None]     # 策略创建的 Monitor（单个）
    task_ids: Mapped[list]             # 策略创建的所有 DataTask ID

    # 时间戳
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # 关系
    creator: relationship → User
    slices: relationship → StrategySlice (自动创建+关联)
```

与现有模型的对比：

| 现有字段 | 新方案 | 说明 |
|----------|--------|------|
| consultation_rounds | **移除** → research_design | 研究设计替代咨询 |
| suggested_monitor_ids | **简化** → monitor_id | 始终只有一个 Monitor |
| slice_plan | **移除** | 已包含在 research_design.slice_blueprint |
| evaluation_result | **替换** → coverage_check_result | 简化评估 |
| phase1/2/3_result | **保留** | |
| brand_brief | **保留** | |

新增字段：

| 字段 | 用途 |
|------|------|
| research_design | 研究设计 chain 的完整输出 |
| probe_review_result | 探测审查结果 |
| probe_round | 当前探测轮次 |
| coverage_check_result | 覆盖度验证结果 |
| output_type | 产出类型 |
| monitor_id | 策略创建的 Monitor |
| task_ids | 策略创建的所有任务 ID |

---

## API 端点

### 新增

| 方法 | 路径 | 说明 | 状态变化 |
|------|------|------|----------|
| POST | `/strategies/{id}/design-research` | AI 生成研究计划 | draft → planned |
| POST | `/strategies/{id}/confirm-research` | 确认计划，创建 Monitor + 探测任务 | planned → probing |
| GET | `/strategies/{id}/probe-status` | 探测任务完成进度（轮询） | — |
| POST | `/strategies/{id}/approve-probe` | 确认探测通过（或自动触发） | probing → collecting |
| POST | `/strategies/{id}/refine-probe` | 调整关键词，创建新探测任务 | probing → probing |
| GET | `/strategies/{id}/collection-status` | 全量采集+分析进度（轮询） | — |
| GET | `/strategies/{id}/data-overview` | 获取数据全景 + 切片 + 覆盖度 | — |
| POST | `/strategies/{id}/adjust-slices` | 微调切片配置 | ready → ready（重新验证） |

### 保留

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/strategies` | 创建策略 |
| GET | `/strategies` | 策略列表 |
| GET | `/strategies/{id}` | 策略详情 |
| PUT | `/strategies/{id}` | 更新名称/Brief |
| DELETE | `/strategies/{id}` | 删除策略 |
| POST | `/strategies/{id}/generate/phase{1,2,3}` | 生成对应阶段 |
| PUT | `/strategies/{id}/phase{1,2,3}` | 编辑阶段结果 |
| GET | `/strategies/{id}/export` | 导出 Word |
| POST | `/strategies/{id}/parse-brief` | 上传 Brief 文档解析 |

### 移除

| 方法 | 路径 | 原因 |
|------|------|------|
| POST | `/strategies/{id}/consult` | 被 design-research 替代 |
| POST | `/strategies/{id}/confirm-plan` | 被 confirm-research 替代 |
| POST | `/strategies/{id}/slices` | 切片自动创建，不再手动关联 |
| DELETE | `/strategies/{id}/slices/{id}` | 改为 adjust-slices 统一处理 |
| POST | `/strategies/{id}/evaluate` | 被 coverage_check 自动触发替代 |
| POST | `/strategies/{id}/confirm-supplementary` | 移除补采循环 |
| GET | `/strategies/{id}/supplementary-status` | 移除补采循环 |
| POST | `/strategies/{id}/confirm-ready` | 自动验证后直接进入 ready |

### Agent API 变更

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agent/tasks/{id}` | **新增**：返回任务 status，供爬虫轮询 |
| POST | `/agent/tasks/{id}/result` | **改造**：支持 probe_ready 状态 + approved 追加模式 |

---

## 与现有系统的关系

### 保留不变

| 组件 | 说明 |
|------|------|
| Monitor 模型 | 后端仍用，但前端对用户透明 |
| DataTask 模型 | 扩展 probe 状态 |
| AnalysisSlice 模型 | 切片分析逻辑不变，创建方式从手动变为自动 |
| 分析管线 (screening → deep → aggregation) | 完全不变 |
| 切片分析管线 (monitor_slice) | 完全不变 |
| Phase 1/2/3 chain | 增强（注入 research_questions） |
| Brief 文档解析 | 不变 |
| Word 导出 | 不变 |

### 改造

| 组件 | 变更 |
|------|------|
| upload_result (agent service) | 支持 probe_ready + approved 追加模式 |
| confirm_plan → confirm_research | 增加 probe_size 参数 |
| 自动分析触发 | 探测完成后触发 probe_review；全量完成后触发自动建切片 |

### 移除

| 组件 | 原因 |
|------|------|
| consult_chain | 被 research_design_chain 替代 |
| architect_chain | 被 coverage_check_chain 吸收 |
| evaluate_chain | 被 coverage_check_chain 吸收 |
| confirm_supplementary / supplementary-status | 移除补采循环 |
| 策略页手动关联切片 | 切片自动创建 |

---

## 各阶段职责边界

| 阶段 | 核心问题 | 不合格时的出路 |
|------|---------|---------------|
| ① 研究设计 | 要采什么数据？ | 用户编辑计划 |
| ② 探测验证 | 关键词方向对不对？ | 调整关键词重新探测（最多3轮） |
| ③ 数据就绪 | 数据和切片是否覆盖所有研究问题？ | 微调切片配置；极端情况回 ① |
| ④ 产出生成 | 产出质量如何？ | 编辑后重新生成 |

每个阶段只解决一个问题。不做上一个阶段或下一个阶段的事。

---

## 实施阶段建议

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| P1 | 数据模型迁移 + research_design_chain + confirm_research | Brief → 研究计划 → 创建探测任务 |
| P2 | Agent 增量上传改造 + probe_review_chain + 自动审查逻辑 | 探测 → 审查 → 自动继续/通知用户 |
| P3 | 自动建切片 + coverage_check_chain + data_overview 端点 | 全量分析 → 自动切片 → 验证覆盖度 |
| P4 | Phase chain 增强 + output_type 预留 | 产出生成注入研究问题上下文 |
| P5 | 前端重构：策略详情页 4 阶段面板 | 用户全程不离开策略页 |
| P6 | output_type 扩展：insight_report 模板（可选，后续迭代） | 多产出类型支持 |
