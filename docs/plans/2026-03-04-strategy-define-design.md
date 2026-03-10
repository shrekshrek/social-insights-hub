# Strategy Define 模块设计

> 状态: 待实施
> 创建日期: 2026-03-04

---

## 1. 定位

**模块名称**: 策略定义 (Strategy Define)

**核心定位**: 数据驱动的策略草案生成器。基于 Discover 阶段的切片数据，AI 自动推导社交传播策略全链路，Planner 在平台上迭代优化后导出方案文档。

**目标用户**: 社媒策略 Planner

**核心价值**:
- 降低门槛：让经验不足的 Planner 也能产出可用的策略草案
- 提升效率：省去从数据到策略的手动推导过程
- 数据驱动：确保策略建议有数据支撑而非纯经验拍脑袋

**在工作流中的位置**: Step 3 (Discover) → **Step 4 (Define)** → Step 5 (Develop)

---

## 2. 数据模型

Strategy 是与 Project 平级的顶级实体，通过关联表引用任意项目的切片。

这样设计的理由：
- **概念独立**：Project 是数据采集+分析的工作空间，Strategy 是基于数据的策略决策。一个是数据层，一个是决策层，本质上是引用关系而非从属关系
- **跨项目自然**：一个策略经常需要综合多个项目的数据（品类大盘 + 竞品对比 + Campaign 效果），不存在"属于哪个项目"的问题
- **管理清晰**：策略有独立的列表和生命周期，不会散落在各个项目中难以查找

```
Strategy S1 (顶级实体)
  ├── 关联 Slices:
  │     ├── Project A / Slice A1 (品类大盘)
  │     ├── Project A / Slice A2 (时间对比)
  │     └── Project B / Slice B1 (竞品分析)
  ├── Brand Brief (可选, JSON)
  ├── 外部参考文档 (可选, 0..n, 文件上传)
  ├── Phase 1 结果: Social Tension + Brand Opportunity (洞察层)
  ├── Phase 2 结果: Brand Social Role + Social Strategy (策略层)
  ├── Phase 3 结果: Big Idea + Content Strategy (创意层)
  └── 状态: draft / phase1_done / phase2_done / completed
```

权限模型：
- 策略模块有独立的权限 (access / read / write)
- 创建策略时，切片选择器只展示用户有权访问的项目的切片
- 策略创建者拥有该策略的完整权限

### 核心表: `strategies`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| name | varchar | 策略名称 |
| created_by | int FK | 创建者用户 ID |
| status | enum | draft / phase1_done / phase2_done / completed |
| brand_brief | jsonb | 可选 Brief 信息 |
| phase1_result | jsonb | Tension + Opportunity |
| phase2_result | jsonb | Role + Social Strategy |
| phase3_result | jsonb | Big Idea + Content Strategy |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 关联表: `strategy_slices`

| 字段 | 类型 | 说明 |
|------|------|------|
| strategy_id | int FK | |
| slice_id | int FK | 可来自任意项目, 仅受用户权限约束 |

### 关联表: `strategy_references` (Phase 3)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| strategy_id | int FK | |
| filename | varchar | 原始文件名 |
| file_path | varchar | 存储路径 |
| extracted_text | text | 提取的文本内容 |

---

## 3. 策略产物定义

### 6 个产物

| # | 产物 | 阶段 | 核心问题 | 推导依据 | 输出形式 |
|---|------|------|---------|---------|---------|
| 1 | **Social Tension** | Phase 1 (洞察层) | 消费者在该品类/话题上的核心矛盾或未被满足的需求 | 话题情感分布、消费者观点聚类、高热度争议点 | 1-3 条 Tension 陈述 + 数据论据 |
| 2 | **Brand Opportunity** | Phase 1 (洞察层) | 基于 Tension，品牌可以在哪里切入 | Tension + 竞品空白区 (SOV/四象限) + 品牌现有资产 | 1-2 条机会陈述 + 竞品对比论据 |
| 3 | **Brand Social Role** | Phase 2 (策略层) | 品牌在社交场域应该扮演什么角色 | Opportunity + KOL 声音风格 + Brief 中的品牌定位 | 角色定义 (一句话) + 角色阐释 |
| 4 | **Social Strategy** | Phase 2 (策略层) | 整体社交传播的策略方向 | Role + 平台特征 + 时间趋势 | 策略主张 + 核心沟通信息 + 传播节奏建议 |
| 5 | **Big Idea** | Phase 3 (创意层) | 用什么创意概念统领整个传播 | Strategy + Tension 中的核心矛盾 + 品牌资产 | 创意概念 (一句话) + 概念阐释 + 与 Tension 的呼应关系 |
| 6 | **Content Strategy** | Phase 3 (创意层) | 内容怎么做 | Big Idea + 高互动内容分析 + KOL 生态 | 内容支柱 (2-4 个) + 内容方向描述 + 参考案例 |

### 输出结构

每个产物都是「结论 + 数据论据」的结构:

```json
{
  "social_tensions": [
    {
      "statement": "消费者对 XX 品类存在 YY 矛盾...",
      "evidence": [
        {"type": "topic_sentiment", "description": "话题 A 负面情感占比 62%", "source": "slice:xxx"},
        {"type": "opinion_cluster", "description": "高频观点: ...", "source": "slice:xxx"}
      ],
      "confidence": "high"
    }
  ],
  "brand_opportunities": [
    {
      "statement": "品牌可在 XX 维度建立差异化...",
      "evidence": [...],
      "related_tensions": [0]
    }
  ]
}
```

Phase 2/3 结构类似，每个产物都有 statement + evidence + 对上游产物的引用。Big Idea 额外包含 `tension_echo` 字段，说明创意概念如何回应核心矛盾。

### 数据依赖矩阵

每个 Phase 从切片 `result_data` 中读取的字段：

| 切片字段路径 | Phase 1 | Phase 2 | Phase 3 | 切片中是否存在 |
|------------|---------|---------|---------|--------------|
| `meta.subject / competitors` | ✓ 品类上下文 | | | ✅ |
| `foundation.aligned_entities[:10]` | ✓ 实体排名 (name/role/heat/sentiment/top_issues) | | | ✅ |
| `foundation.aligned_entities[:20]` | | | ✓ 实体特征 (name/role/heat/top_features) | ✅ |
| `foundation.aligned_topics[:15]` | ✓ 话题情感 (name/category/heat/sentiment) | | | ✅ |
| `layers.landscape.sov_ranking[:10]` | ✓ 竞品声量份额 | | | ✅ |
| `layers.landscape.overview.unique_platform_volume` | | ✓ 平台分布 | | ✅ |
| `layers.landscape.platform_dna[:10]` | | ✓ 各实体平台声量占比 (name/role/platform_shares) | | ✅ |
| ~~`layers.landscape.time_distribution`~~ | | ~~✓ 时间趋势~~ | | ✅ 已补全但已从 Chain 移除 |
| `layers.landscape.kol_voices[:10]` | | ✓ KOL 声音风格 | ✓ KOL 生态 | ✅ 已补全 |
| `layers.intent.topic_radar.pains[:10]` | ✓ 痛点话题 (Tension 核心数据源) | | | ✅ |
| `layers.intent.topic_radar.controversies[:5]` | ✓ 争议话题 (正负提及量) | | | ✅ |
| `layers.intent.topic_radar.gains[:5]` | ✓ 增益话题 (机会发现) | | | ✅ |
| `layers.intent.unmet_needs` | ✓ 未满足需求 | | | ✅ |
| `layers.intent.topic_aspects[:8]` | | | ✓ 话题分类维度 (内容支柱数据源) | ✅ |
| ~~`layers.intent.ipa_analysis`~~ | | | ~~✓ IPA 四象限~~ | ✅ 已补全但已从 Chain 移除 |
| `layers.focus.swot` | ✓ 竞品维度 (dimension + delta) | | | ✅ |
| `layers.focus.gap.dimensions[:5]` | ✓ 竞品盲区维度 (Opportunity 数据源) | | | ✅ |
| Phase 1 结果 (上游) | — | ✓ 全量 | ✓ 全量 | N/A |
| Phase 2 结果 (上游) | — | — | ✓ 全量 | N/A |
| Brand Brief (用户输入) | ✓ 可选 | ✓ 可选 | ✓ 可选 | N/A |

**设计决策**：不使用切片报告（landscape_report / topic_report / focus_report）作为 Chain 输入。报告是对同一份结构化数据的 LLM 叙事总结，结构化字段已足够全面，避免 LLM→LLM 二手信息传递。

**数据依赖精简**：3 个字段已由切片流水线补全，但经评估后仅 `kol_voices` 保留为 Chain 输入。`time_distribution`（采集样本分布会误导 LLM 节奏建议）和 `ipa_analysis`（与 topic_aspects + top_features + SWOT 冗余）已从 Chain format 函数移除，数据仍在切片中生成供未来前端使用。

---

## 4. 用户流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 创建策略                                                      │
│    - 输入策略名称                                                 │
│    - 选择关联切片 (1+个)                                          │
│    - 可选: 填写 Brand Brief                                      │
│    - 可选: 上传外部参考文档 (开发 Phase 3)                         │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Phase 1 生成 (洞察层)                                         │
│    - AI 分析切片数据 → 生成 Social Tension + Brand Opportunity    │
│    - Planner 浏览结果 (结论 + 数据论据)                           │
│    - 可编辑/调整/重新生成单项                                      │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼ (确认 Phase 1)
┌─────────────────────────────────────────────────────────────────┐
│ 3. Phase 2 生成 (策略层)                                         │
│    - AI 基于已确认的 Phase 1 → 生成 Brand Social Role + Strategy  │
│    - Planner 浏览/编辑/重新生成                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼ (确认 Phase 2)
┌─────────────────────────────────────────────────────────────────┐
│ 4. Phase 3 生成 (创意层)                                         │
│    - AI 基于已确认的 Phase 1+2 → 生成 Big Idea + Content Strategy │
│    - Planner 浏览/编辑/重新生成                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. 迭代 & 导出                                                   │
│    - 可返回任意阶段重新调整 (下游阶段需重新生成)                     │
│    - 导出 Word 文档                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 技术实现

### 后端

#### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/strategies` | 创建策略 (关联切片, 可选 Brief) |
| GET | `/strategies` | 策略列表 (按项目筛选) |
| GET | `/strategies/{id}` | 策略详情 |
| PUT | `/strategies/{id}` | 更新策略 (名称/Brief) |
| DELETE | `/strategies/{id}` | 删除策略 |
| POST | `/strategies/{id}/generate/phase1` | 生成 Phase 1 (洞察层) |
| POST | `/strategies/{id}/generate/phase2` | 生成 Phase 2 (策略层, 需 Phase 1 已确认) |
| POST | `/strategies/{id}/generate/phase3` | 生成 Phase 3 (创意层, 需 Phase 2 已确认) |
| PUT | `/strategies/{id}/phase1` | 编辑 Phase 1 结果 |
| PUT | `/strategies/{id}/phase2` | 编辑 Phase 2 结果 |
| PUT | `/strategies/{id}/phase3` | 编辑 Phase 3 结果 |
| GET | `/strategies/{id}/export` | 导出 Word |

#### LLM Chain

新增 3 条 LangChain 链:

1. **strategy_phase1_chain**: 输入切片数据 (+ Brief) → 输出 Tension + Opportunity (JSON)
2. **strategy_phase2_chain**: 输入 Phase 1 结果 + 切片数据 (+ Brief) → 输出 Role + Strategy (JSON)
3. **strategy_phase3_chain**: 输入 Phase 1+2 结果 + 切片数据 (+ Brief) → 输出 Big Idea + Content Strategy (JSON)

切片数据输入: 先给 LLM 全量数据，后续根据实际效果裁剪不需要的维度。

#### 模块结构

```
backend/src/strategies/
├── models.py       # Strategy, StrategySlice ORM
├── schemas.py      # 请求/响应 Pydantic 模型
├── service.py      # 业务逻辑 (创建/生成/编辑)
├── router.py       # API 端点
└── export_docx.py  # Word 导出
```

LangChain 链:
```
backend/src/langchain/chains/
├── strategy_phase1_chain.py
├── strategy_phase2_chain.py
└── strategy_phase3_chain.py
```

### 前端

#### 页面结构

```
frontend/layers/
├── strategies/                          # 独立 Layer
│   ├── components/
│   │   ├── StrategyCreateDialog.vue     # 创建对话框
│   │   ├── StrategyPhaseCard.vue        # 阶段结果展示卡片
│   │   ├── StrategyItemEditor.vue       # 单项编辑组件
│   │   └── StrategyEvidenceList.vue     # 数据论据展示
│   ├── composables/
│   │   └── useStrategy.ts              # API 请求封装
│   └── types/
│       └── strategy.ts                 # TypeScript 类型
```

#### 路由

| 路由 | 页面 |
|------|------|
| `/strategies` | 策略列表 (顶级入口) |
| `/strategies/:id` | 策略详情/编辑 |

---

## 6. 开发分期

### Phase 1 — MVP (核心链路跑通)

**后端**:
- Strategy 数据模型 + Alembic 迁移
- CRUD API (创建/列表/详情/删除)
- Phase 1 / Phase 2 / Phase 3 LLM 链 (基于单切片数据)
- 生成 API (同步或异步, 视 LLM 响应时间决定)
- Phase 1 / Phase 2 / Phase 3 结果编辑 API
- Word 导出

**前端**:
- 策略列表页 (侧边栏顶级入口)
- 创建策略对话框 (选 1+ 个切片, 支持跨项目搜索)
- 策略详情页: Phase 1 结果展示 + 确认按钮
- 策略详情页: Phase 2 结果展示 + 确认按钮
- 策略详情页: Phase 3 结果展示
- 内联编辑 (修改结论文本)
- 单项重新生成按钮
- Word 导出按钮

**权限**:
- `rbac/init_data.py` 注册 strategies 模块权限
- 前端路由权限配置

### Phase 2 — 增强输入

- Brand Brief 表单 (品牌定位、目标人群、传播目标、预算级别等)
- Brief 数据注入 LLM prompt
- Prompt 优化 (根据 Phase 1 使用反馈调整)

### Phase 3 — 外部参考 + 高级功能

- 外部文档上传 (PDF/Word), 提取文本作为 LLM 上下文
- `strategy_references` 表 + 文件存储
- 策略版本历史 (每次重新生成保留旧版本)
- 多策略对比视图

---

## 7. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 模块层级 | 顶级独立模块 | Strategy 是决策层, Project 是数据层, 不是从属关系。跨项目引用切片时不需要强制选"主项目" |
| 生成阶段数 | 3 阶段分步 (洞察→策略→创意) | 每层 2 个产物, 上游定偏会导致下游全废, 需要人工卡点。3 层概念边界清晰 |
| Brief 必填 vs 可选 | 可选 | 不同项目情况不同, 纯数据驱动也要能用 |
| LLM 输入范围 | 先全量后裁剪 | LLM 擅长从大量上下文中提取相关信息, 不预设限制 |
| 输出结构 | 结论 + 数据论据 | Planner 需要看到推导依据, 也方便向客户论证 |
