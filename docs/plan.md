# 模块方案: Spam 分布前端展示增强

> 后端 spam_distribution 数据管道已完成，所有分析模块均已携带 spam 分布数据。本方案聚焦**前端展示层**，将 4 维/2 维 spam 分布数据以更直观、可交互的方式呈现给用户。

---

## 当前状态

后端已为每个分析模块输出 spam 分布数据：

| 数据类型 | 字段 | 维度 | 当前前端展示 |
|----------|------|------|-------------|
| EntityStat | `spam_distribution` | 4 维 (high_spam/low_spam × post/comment) | 仅展示 total（`推广 N / 有机 N`） |
| OpinionStat | `spam_distribution` | 4 维 | 仅展示 total |
| QuadrantItem | `spam_group` | 单值 ("high"/"low"/null) | 未展示 |
| KolVoice | `spam_group` | 单值 | Badge 标签 |
| IpaPoint | `spam_distribution` | 2 维 (high/low) | 未展示 |
| CompetitorSeries | `spam_distribution` | 2 维 | 未展示 |
| TimeDistributionItem | `spam_breakdown` | 2 维 | 未展示 |
| TaskAnalysisMetrics | `nsr_by_spam` | 2 值 | 数字展示 |

**核心问题**：
1. 实体/观点的 4 维数据（post/comment 拆分）完全未展示，用户无法区分"有机原文"和"有机评论"
2. 无法按 spam 维度排序，不能快速定位"推广占比最高"或"有机提及最多"的实体/观点
3. 时间分布、IPA、竞品雷达的 spam 数据完全未利用
4. 四象限点未可视化 spam_group

---

## 设计原则

1. **渐进披露**：默认展示最重要的 2 维比例，hover/展开时才显示 4 维明细
2. **视觉一致性**：全局统一色彩语言 — 绿色=有机(low_spam)、橙色=推广(high_spam)、灰色=未初筛
3. **不新增页面**：所有信息嵌入现有 `TaskAnalysisReport.vue` 各区域
4. **数据驱动降级**：`spam_distribution` 为 `null` 时优雅隐藏，不影响现有布局

---

## 1. 数据模型

**无后端变更**。所有数据已由后端 `spam_distribution_builder.py` 计算并输出。

前端类型已定义完毕（`analysis/types/index.ts`）：
- `SpamDistribution` / `SpamSourceBreakdown`（4 维）
- `SpamCountBreakdown`（2 维）
- `NsrBySpam`（标量拆分）

---

## 2. 组件设计

### 2.1 新增共享组件

#### `SpamRatioBar.vue`（新建）

**路径**: `frontend/layers/social-media/analysis/components/shared/SpamRatioBar.vue`

**Props**:
```typescript
interface Props {
  // 4 维模式（实体/观点）
  spamDistribution?: SpamDistribution | null
  // 2 维模式（IPA/竞品/时间）
  spamBreakdown?: SpamCountBreakdown | null
  // 展示选项
  showLabels?: boolean       // 是否显示文字标签，默认 true
  size?: 'xs' | 'sm'         // 尺寸，默认 'sm'
}
```

**渲染逻辑**:
- 水平双色条形图：绿色(有机) + 橙色(推广)，宽度按比例
- 4 维模式：默认显示 total 比例，hover 时 popover 展示 post/comment 明细
- 2 维模式：直接显示 high/low 比例
- 总数为 0 时：不渲染（v-if）

**Hover Popover 内容（4 维模式）**:
```
推广 (N):  原文 X / 评论 Y
有机 (M):  原文 A / 评论 B
```

### 2.2 复用已有共享组件

#### `TabSwitch.vue`（已有）

**路径**: `frontend/layers/social-media/analysis/components/shared/TabSwitch.vue`

已有的通用 Tab 切换组件，接口：`v-model: string` + `options: { value: string, label: string }[]`。
已被 `PlatformDNAChart`、`SOVRankingChart`、`GroupShareTable`、`IndustryQuadrantChart` 使用，是项目中模式切换的标准模式。

用于实体排序选择器和时间分布视图切换。

### 2.3 修改 TaskAnalysisReport.vue

#### 实体列表区域（热门实体 section）

1. 在 section header 右侧（"查看全部"按钮之前）添加 `TabSwitch`（排序选项：综合评分/推广占比/有机提及）
2. 替换现有 spam 文字（`推广 N / 有机 N`）为 `SpamRatioBar` 组件
3. 新增 computed `sortedTopEntities`：根据排序模式重排实体列表
   - `default`: 保持原始顺序（后端按 score 排序）
   - `promo_ratio`: 按 `high_spam.total / (high_spam.total + low_spam.total)` 降序
   - `organic_count`: 按 `low_spam.total` 降序

#### 热门话题区域（热门问题 / 热门特性 section）

1. 替换现有 spam 文字为 `SpamRatioBar`（size="xs"）
2. 不加排序控件（话题区域已按 sentiment 分组，排序维度冲突）

#### 四象限分布区域

在每个象限统计数字下方，增加一行小字，显示该象限内的 spam 分布：
- 计算逻辑：从 `data.charts.quadrant` 中筛选该象限的 items，统计 `spam_group` 分布
- 展示形式：`推广 N / 有机 M` 小字（沿用现有颜色）

#### 时间分布图表

**修改文件**: `frontend/layers/social-media/analysis/components/task/TimeDistributionChart.vue`

**前置修改**：组件当前使用本地 `TimeDistributionItem` 接口（缺少 `spam_breakdown` 字段），需替换为从 `../../types` 导入，或在本地接口中补充 `spam_breakdown?: SpamCountBreakdown` 字段。

在现有单线折线图基础上增加 stacked area chart 模式：
- 使用已有 `TabSwitch` 组件切换"总量"/"分组"视图
- "分组"视图：两条面积线 — 绿色(有机) + 橙色(推广)，堆叠展示
- 数据来源：每个 `TimeDistributionItem.spam_breakdown`
- 降级：如果所有日期的 `spam_breakdown` 都为 null，隐藏 toggle

#### IPA 图表

**修改文件**: `frontend/layers/social-media/analysis/components/task/IpaChart.vue`

在现有 tooltip 中追加 spam 分布信息：
- 每个 IPA 点的 tooltip 末尾追加：`推广 N / 有机 M`
- 数据来源：`IpaPoint.spam_distribution`（SpamCountBreakdown）
- 降级：`spam_distribution` 为 null 时不展示该行

#### 竞品雷达图表

**修改文件**: `frontend/layers/social-media/analysis/components/task/CompetitorRadarChart.vue`

在 bar 模式下的 tooltip 中追加 spam 分布信息：
- 每个竞品 series 的 tooltip 追加：`推广 N / 有机 M`
- 数据来源：`CompetitorSeries.spam_distribution`（SpamCountBreakdown）
- 降级：`spam_distribution` 为 null 时不展示

---

## 3. 实施步骤

### Step 1: 新建 SpamRatioBar 共享组件 [需要测试 — 4维/2维渲染、比例计算、边界case]

**新建文件**: `frontend/layers/social-media/analysis/components/shared/SpamRatioBar.vue`

实现内容：
- 接收 `spamDistribution`（4 维）或 `spamBreakdown`（2 维）
- 计算 total / organic / promo 数量和比例
- 渲染水平双色条（Tailwind CSS `bg-orange-400` + `bg-green-400`）
- 4 维模式：用 `UPopover` 展示 post/comment 明细（hover 触发）
- 总数为 0 或 props 为 null 时不渲染

### Step 2: 实体列表 — 集成 SpamRatioBar + TabSwitch 排序 [需要测试 — 排序逻辑]

**修改文件**: `frontend/layers/social-media/analysis/components/task/TaskAnalysisReport.vue`

修改内容：
1. 导入 `TabSwitch` 共享组件
2. 新增 `entitySortMode` ref（默认 `'default'`）和 `entitySortOptions` 常量（综合评分/推广占比/有机提及）
3. 新增 `sortedTopEntities` computed：按排序模式重排
4. 在实体 section header 添加 `TabSwitch`（仅当有 spam 数据时显示）
5. 替换实体 spam 文字为 `SpamRatioBar`（替换现有 `推广 {{ entity.spam_distribution.high_spam.total }} / 有机 {{ entity.spam_distribution.low_spam.total }}` 文字）
6. `v-for` 从 `data.insights.top_entities` 改为 `sortedTopEntities`

### Step 3: 话题列表 — 集成 SpamRatioBar [无需测试]

**修改文件**: `frontend/layers/social-media/analysis/components/task/TaskAnalysisReport.vue`

修改内容：
- 热门问题和热门特性区域：替换 spam 文字为 `SpamRatioBar`（size="xs"）

### Step 4: 四象限 — 添加 spam 分布统计 [无需测试]

**修改文件**: `frontend/layers/social-media/analysis/components/task/TaskAnalysisReport.vue`

修改内容：
- 新增 `getQuadrantSpamBreakdown(quadrant: string)` 函数：从 quadrant items 中统计 spam_group 分布
- 在每个象限按钮内添加一行小字显示 spam 分布

### Step 5: 时间分布 — stacked area chart [需要测试 — 图表配置]

**修改文件**: `frontend/layers/social-media/analysis/components/task/TimeDistributionChart.vue`

修改内容：
1. 将本地 `TimeDistributionItem` 接口补充 `spam_breakdown?: SpamCountBreakdown` 字段（或改为从 `../../types` 导入）
2. 导入 `TabSwitch` 共享组件
3. 新增 `viewMode` ref（`'total'` | `'spam_split'`）
4. 新增 `hasSpamData` computed：检查是否有 spam_breakdown
5. 新增 `TabSwitch` toggle UI（仅当 `hasSpamData` 为 true 时显示）
6. `'spam_split'` 模式：构建两条 series（推广/有机），使用 stacked area chart
7. ECharts option 根据 viewMode 切换

### Step 6: IPA + 竞品雷达 — tooltip 增强 [无需测试]

**修改文件**:
- `frontend/layers/social-media/analysis/components/task/IpaChart.vue`
- `frontend/layers/social-media/analysis/components/task/CompetitorRadarChart.vue`

修改内容：
- IPA: 在 tooltip formatter 中追加 spam 分布行
- 竞品雷达（bar 模式）: 在 tooltip formatter 中追加 spam 分布行
- 两者均从各自 props 的 `spam_distribution` 字段取值

---

## 4. 边界情况与错误处理

| 场景 | 处理方式 |
|------|---------|
| `spam_distribution` 为 `null`（历史报告/未初筛） | `SpamRatioBar` 不渲染（v-if），排序控件隐藏 |
| 实体全部无 spam 数据 | 排序控件不显示，保持默认排序 |
| `spam_distribution` 的 total 为 0（所有帖子未初筛） | `SpamRatioBar` 不渲染 |
| 推广或有机某侧为 0 | 条形图只显示单侧颜色，比例 100% |
| 4 维模式下 post=0 且 comment>0 | popover 中原文显示 0，评论显示实际值 |
| 时间分布所有日期 spam_breakdown 为 null | 隐藏 toggle，保持原始单线图 |
| 四象限某象限所有 item 的 spam_group 为 null | 不显示 spam 统计行 |
| 排序模式切换时列表长度不变 | computed 重新排序，保持展开/收起状态 |
| IPA/竞品 tooltip 中 spam_distribution 为 null | 不追加 spam 行，tooltip 内容不变 |

---

## 5. 测试策略

### 单元测试

**SpamRatioBar 组件测试**:
- 4 维数据渲染：传入 SpamDistribution，验证条形宽度比例
- 2 维数据渲染：传入 SpamCountBreakdown，验证条形宽度比例
- null props：不渲染任何内容
- 全为 0：不渲染
- 单侧为 0：只显示一种颜色

**排序逻辑测试**:
- `sortedTopEntities` computed 在 `promo_ratio` 模式下按推广占比降序
- `sortedTopEntities` computed 在 `organic_count` 模式下按有机数降序
- 无 spam_distribution 的实体在 spam 排序模式下排到末尾
- `default` 模式保持原始顺序

### 集成验证

由于前端测试基础设施有限（项目无组件测试框架），以下通过手动验证：
- 报告页面加载正常，无类型错误
- 各区域 spam 展示正确渲染
- hover popover 正确显示 4 维明细
- 排序切换实时生效
- 暗色模式下颜色对比度正常
- 历史报告（无 spam 数据）不受影响

---

## 6. 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 展示方式 | **渐进披露**（默认 2 维比例条 + hover 展开 4 维） | 信息密度高但不拥挤，符合现有报告风格 |
| 排序控件 | 仅在实体列表添加，复用已有 `TabSwitch` | 话题已按 sentiment 分组，排序维度冲突；TabSwitch 已被 4 个组件使用，是项目标准模式 |
| 新增组件 | 仅新建 SpamRatioBar，排序/切换复用 TabSwitch | 避免功能重复，遵循"优先使用现有组件"原则 |
| 时间分布 | TabSwitch 切换（总量 vs 分组），非并行展示 | 图表面积有限，堆叠面积图已足够，与其他图表切换风格一致 |
| IPA/竞品 | 仅增强 tooltip，不改变图表本身 | 这两个图表数据密度已高，增加视觉维度会降低可读性 |
| 四象限 | 小字统计，非颜色编码 | 四象限的颜色已有语义（情感+互动），再加 spam 颜色会混淆 |
| 颜色方案 | 绿色=有机，橙色=推广 | 与现有 KOL badge 和 NSR 拆分的颜色一致 |
