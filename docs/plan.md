# 实施方案：news_media 模块重设计

> 规划日期：2026-04-05
> 状态：待实施
> 参考文档：`docs/channel-architecture-plan.md`，`docs/strategy-multi-source-architecture.md`

---

## 背景与目标

现有 news_media 模块基于 SerpAPI 实现，已被废弃。新方案：

- 搜索渠道：**百度新闻（Crawl4AI）+ DuckDuckGo（ddgs）**双渠道聚合
- 架构更简洁：删除 `search_provider` 字段，渠道作为内部实现细节
- 前端对齐社媒结构：新闻监测（项目）+ 新闻采集（跨项目任务列表）两级导航
- Monitor 级新增聚合分析视图（统计聚合自动，叙事聚合按需）

---

## 设计决策

| 决策 | 结论 |
|------|------|
| probe 渠道 | 仅百度（快速稳定，10条）|
| collect 渠道 | 百度 + DuckDuckGo 并发（各 50 条，URL 去重合并）|
| 分析层级 | 任务级内联分析（无独立 AnalysisJob / Slice）|
| collect 执行 | 异步（`asyncio.create_task`），前端轮询状态 |
| Monitor 级聚合 | 统计聚合（无 LLM，自动）+ 叙事聚合（news_insight_chain，按需）|
| DDG 失败处理 | 尽力而为，限速时指数退避，不影响主流程 |

---

## 模块结构变更

### 后端

```
backend/src/news_media/
├── __init__.py
├── models.py           # 删除 search_provider；NewsArticle 新增 search_source；NewsMonitor 新增 aggregated_result
├── schemas.py          # 同步字段变更
├── crud.py             # 新增 get_articles_by_monitor
├── service.py          # _search_and_store_articles 改调 aggregator；collect 改异步；新增 monitor 聚合函数
├── router.py           # 新增 monitor 聚合端点；collect 改异步触发
├── dependencies.py     # 不变
├── news_search/        # 新增，替换 serpapi_client.py
│   ├── __init__.py
│   ├── baidu_crawler.py    # Crawl4AI 爬百度新闻搜索页
│   ├── ddg_searcher.py     # ddgs 封装，含退避重试
│   └── aggregator.py       # 双渠道并发 → URL 去重 → source_tier 分类
└── article_crawler.py  # 不变（全文抓取复用）
```

**删除**：`serpapi_client.py`

### 前端

```
frontend/layers/news-media/
├── nuxt.config.ts
├── types/index.ts           # 删除 search_provider；新增 search_source、MonitorAggregated 类型
├── composables/
│   └── useNewsMedia.ts      # 新增 monitor 聚合 API
└── pages/news-media/
    ├── index.vue             # 监测项目列表（不变）
    ├── create.vue            # 创建项目（不变）
    ├── [id]/
    │   └── index.vue         # 项目详情（新增统计聚合 + 叙事聚合按钮）
    └── tasks/
        ├── index.vue         # 跨项目任务列表（对齐社媒，独立页）
        └── [id]/
            └── index.vue     # 任务详情（文章列表新增渠道 badge）
```

---

## 数据模型变更

### Alembic 迁移内容

```sql
ALTER TABLE news_monitors DROP COLUMN search_provider;
ALTER TABLE news_monitors ADD COLUMN aggregated_result JSON;
ALTER TABLE news_tasks DROP COLUMN search_provider;
ALTER TABLE news_articles ADD COLUMN search_source VARCHAR(20) NOT NULL DEFAULT 'baidu';
```

---

## 搜索模块接口

`aggregator.py` 对外暴露唯一接口：

```python
async def search_news(
    query: str,
    max_results: int = 50,
    channels: list[str] = ("baidu", "duckduckgo"),
) -> list[dict]
# 每条含：url, title, snippet, source_name, source_tier, published_at, image_url, raw_data, search_source
```

---

## 新增 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/news-media/monitors/{id}/aggregated` | 获取 Monitor 统计聚合（自动计算）|
| POST | `/news-media/monitors/{id}/aggregate` | 触发叙事聚合（运行 news_insight_chain）|

---

## 前端路由结构

```
导航一级：新闻监测  →  /news-media
导航二级：新闻采集  →  /news-media/tasks

/news-media              监测项目列表
/news-media/create       创建项目
/news-media/[id]         项目详情
                           ├── 任务列表 + 创建任务 Modal
                           ├── 统计聚合摘要（自动展示）
                           └── 叙事聚合报告（「生成聚合报告」按钮）
/news-media/tasks        跨项目任务列表（筛选：状态、阶段、关键词）
/news-media/tasks/[id]   任务详情
                           ├── 文章列表（含搜索渠道 badge：百度 / DuckDuckGo）
                           └── 分析报告（probe: 摘要 / collect: 完整洞察）
```

---

## 实施步骤

### Step 1：清理旧代码 + 数据库迁移
**文件**：`serpapi_client.py`（删除），`models.py`，`schemas.py`，Alembic 迁移

- 删除 `backend/src/news_media/serpapi_client.py`
- `NewsMonitor`：删除 `search_provider`，新增 `aggregated_result`
- `NewsTask`：删除 `search_provider`
- `NewsArticle`：新增 `search_source`
- `schemas.py` 同步字段
- 创建并执行 Alembic 迁移

**验证**：`pnpm be:migrate:up` 成功；`pnpm be:lint`

---

### Step 2：实现 news_search 模块
**文件**：`news_search/` 目录下 4 个文件（新建）

**baidu_crawler.py**：
- Crawl4AI REST API，目标 URL `https://news.baidu.com/ns?word={query}&rn=50`
- `fit_markdown` 提取内容，正则解析标题/链接/来源/时间
- 每条结果含 `search_source="baidu"`

**ddg_searcher.py**：
- `DDGS().news(query, region="cn-zh", max_results=n)`
- 指数退避重试 3 次，`RatelimitException` 时返回空列表（不抛异常）
- 每条含 `search_source="duckduckgo"`

**aggregator.py**：
- `asyncio.gather` 并发两渠道
- URL 归一化去重
- `classify_source_tier()` 分层（逻辑从旧 `serpapi_client.py` 迁移）

**验证**：`pnpm be:lint`

---

### Step 3：更新 crud.py + service.py
**文件**：`crud.py`，`service.py`

**crud.py**：
- 新增 `get_articles_by_monitor(db, monitor_id)` —— 查询 monitor 下所有任务的文章

**service.py**：
- `_search_and_store_articles()` 改调 `aggregator.search_news()`
- `execute_news_probe()` 中 channels 固定为 `("baidu",)`，`max_results=10`
- `execute_news_collect()` 中 channels 为 `("baidu", "duckduckgo")`，`max_results=50`
- 新增 `get_monitor_aggregated_stats(db, monitor_id)` —— 从各 task.analysis_result 统计聚合，无 LLM
- 新增 `run_monitor_narrative_aggregate(db, monitor, analysis_goal, subject)` —— 合并所有 collect 任务文章跑 `news_insight_chain`，写入 `monitor.aggregated_result`

**验证**：`pnpm be:lint`

---

### Step 4：更新 router.py
**文件**：`router.py`

- `execute_task` 端点：collect 改为 `asyncio.create_task(...)` 后立即返回 running 状态
- 新增 `GET /monitors/{id}/aggregated`
- 新增 `POST /monitors/{id}/aggregate`

**验证**：`pnpm be:lint`；`pnpm be:test`

---

### Step 5：前端 types + composable
**文件**：`types/index.ts`，`composables/useNewsMedia.ts`

**types/index.ts**：
- 删除 `search_provider` 字段
- `NewsArticle` 新增 `search_source: 'baidu' | 'duckduckgo'`
- 新增 `MonitorAggregatedStats`（统计聚合）、`MonitorNarrativeResult`（叙事聚合）接口

**useNewsMedia.ts**：
- 删除 `search_provider` 相关参数
- 新增 `getMonitorAggregated(monitorId)`
- 新增 `runMonitorAggregate(monitorId)`

**验证**：`pnpm fe:typecheck`

---

### Step 6：前端页面
**文件**：`pages/news-media/` 各页面

**`[id]/index.vue`（项目详情）**：
- 保留任务列表 + 创建任务 Modal
- 新增统计聚合摘要区块（自动加载：文章总数、情感分布、实体 Top5、来源分布）
- 新增叙事聚合区块（折叠，「生成聚合报告」按钮 → POST → 轮询）

**`tasks/index.vue`（跨项目任务列表，新建）**：
- 筛选：状态、阶段、关键词
- 列：任务名、所属项目、关键词、阶段 badge、状态 badge、文章数、创建时间、操作
- 分页

**`tasks/[id]/index.vue`（任务详情）**：
- 文章列表新增「搜索渠道」列（百度 / DuckDuckGo badge）
- 分析报告展示不变

**验证**：`pnpm fe:typecheck`；`pnpm fe:lint`

---

## 边界情况处理

| 场景 | 处理 |
|------|------|
| DDG 被限速 | 返回空列表，仅用百度结果，不报错 |
| 百度爬取失败 | 抛异常，任务标记 failed |
| collect 后台任务异常 | 捕获后写 `task.status=failed`，`task.error_message` 记录详情 |
| 叙事聚合无 collect 任务 | 返回 400，前端禁用按钮 |
| Monitor 无文章 | 统计聚合返回全零，不调 LLM |

---

## 验收标准

- [ ] `pnpm be:lint` 通过
- [ ] `pnpm be:test` 通过
- [ ] `pnpm fe:typecheck` 通过
- [ ] `pnpm fe:lint` 通过
- [ ] probe 任务执行成功，articles 含 `search_source=baidu`
- [ ] collect 任务执行成功，articles 含百度和 DuckDuckGo 两种来源
- [ ] Monitor 详情页展示统计聚合摘要
- [ ] 跨项目任务列表页正常渲染、筛选可用
- [ ] 任务详情文章列表展示渠道 badge

## 架构决策

**爬虫功能边界**：爬虫作为知识库的数据来源管理，暂不独立为单独模块。未来以下条件满足 2-3 个时再考虑拆分：
- 数据源 > 5-6 个（目前 3 个）
- 需要调度 UI（查看下次执行时间、修改 cron、暂停/恢复）
- 爬取内容不仅入 KB，还流向其他模块
- 出现独立的"数据管理员"角色

**当前设计**：
- 爬虫状态面板：内嵌在 `index.vue` 底部折叠区块
- 搜索功能：独立页面 `/knowledge-base/search`

---

## 实施步骤

### Step 1：修复数据类型定义（types/index.ts）
**文件**：`frontend/layers/knowledge-base/types/index.ts`（修改）

修正 `KnowledgeDocument` 接口对齐后端 `DocumentRead` schema：

```typescript
interface KnowledgeDocument {
  id: number
  workspace_id: number | null        // null = 平台公共
  title: string
  source_type: string                // 'upload' | 'cnnic' | 'nbs' | 'govsite'
  source_url: string | null          // 新增，爬取来源 URL
  file_name: string | null           // 改名（原 filename）
  industry_tags: string[]
  chunk_count: number
  processing_status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null        // 新增，处理失败原因
  created_at: string
  updated_at: string
}

// 修正后的 DocumentUploadResponse
interface DocumentUploadResponse {
  id: number
  title: string
  processing_status: string
  message: string
}

// 新增爬虫相关类型
interface CrawlerStatusItem {
  source_type: string
  total_docs: number
  ready_docs: number
  failed_docs: number
  last_crawled_at: string | null
}

interface CrawlerStatusResponse {
  items: CrawlerStatusItem[]
}

interface CrawlerRunResponse {
  source_type: string
  task_id: string
  message: string
}
```

**验证**：`pnpm fe:typecheck`

---

### Step 2：扩展 Composable（useKnowledgeBase.ts）
**文件**：`frontend/layers/knowledge-base/composables/useKnowledgeBase.ts`（修改）

修正 API 调用参数对齐，新增搜索/爬虫功能：

```typescript
export function useKnowledgeBase() {
  const { apiRequest } = useApi()

  // 修正：listDocuments 改用 source_type 过滤（对应后端参数）
  async function listDocuments(params?: { page?: number; page_size?: number; source_type?: string }): Promise<DocumentListResponse> {
    const query = new URLSearchParams()
    if (params?.page) query.set('page', String(params.page))
    if (params?.page_size) query.set('page_size', String(params.page_size))
    if (params?.source_type) query.set('source_type', params.source_type)  // 新增

    return apiRequest<DocumentListResponse>(`/knowledge-base/documents${query.toString()}`)
  }

  // 修正：uploadDocument 移除 industry_tags / isPublic（后端不支持）
  async function uploadDocument(file: File, title?: string): Promise<DocumentUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)

    return apiRequest<DocumentUploadResponse>('/knowledge-base/documents/upload', {
      method: 'POST',
      body: form,
    })
  }

  // 新增：搜索文档（RAG 检索）
  async function searchDocuments(query: string, topK = 6): Promise<SearchResponse> {
    return apiRequest<SearchResponse>('/knowledge-base/search', {
      method: 'POST',
      body: { query, top_k: topK },
    })
  }

  // 新增：获取爬虫状态
  async function getCrawlerStatus(): Promise<CrawlerStatusResponse> {
    return apiRequest<CrawlerStatusResponse>('/knowledge-base/crawlers/status')
  }

  // 新增：手动触发爬虫
  async function runCrawler(sourceType: string): Promise<CrawlerRunResponse> {
    return apiRequest<CrawlerRunResponse>(`/knowledge-base/crawlers/${sourceType}/run`, {
      method: 'POST',
    })
  }

  // 新增：来源类型标签辅助
  function sourceTypeLabel(sourceType: string): string {
    const labels: Record<string, string> = {
      'cnnic': 'CNNIC 统计报告',
      'nbs': 'NBS 月报',
      'govsite': 'gov.cn 政策',
    }
    return labels[sourceType] ?? sourceType
  }

  return {
    listDocuments,
    uploadDocument,
    searchDocuments,
    getCrawlerStatus,
    runCrawler,
    deleteDocument,  // 保持现有
    statusLabel,       // 保持现有
    statusColor,       // 保持现有
    formatFileSize,     // 保持现有
  }
}
```

**验证**：`pnpm fe:typecheck`

**依赖**：Step 1

---

### Step 3：修正主页面（pages/knowledge-base/index.vue）
**文件**：`frontend/layers/knowledge-base/pages/knowledge-base/index.vue`（修改）

修正字段引用、调整过滤器、新增爬虫状态面板区块：

```vue
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          市场知识库
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          上传研报、行业资料，AI 策略生成时自动引用
        </p>
      </div>
      <UButton icon="i-heroicons-arrow-up-tray" @click="showUploadModal = true">
        上传文档
      </UButton>
    </div>

    <!-- 文档列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">文档列表</h2>
          <div class="flex items-center gap-2">
            <!-- 过滤器从 workspace 改为 source_type -->
            <USelect v-model="sourceTypeFilter" :items="sourceTypeOptions" class="w-40" />
            <UButton
              variant="outline"
              icon="i-heroicons-arrow-path"
              :loading="loading"
              @click="refresh"
            >
              刷新
            </UButton>
          </div>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8 text-gray-500">加载文档列表中...</div>
        </template>

        <div v-if="loading" class="text-center py-8 text-gray-500">
          加载中...
        </div>

        <div v-else-if="!documents.length" class="text-center py-12">
          <UIcon name="i-heroicons-document-text" class="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p class="text-gray-500">暂无文档，点击上方按钮上传</p>
        </div>

        <div v-else class="divide-y divide-gray-100 dark:divide-gray-800">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="flex items-center justify-between py-4 px-2"
          >
            <div class="flex items-center gap-3 min-w-0">
              <UIcon name="i-heroicons-document-text" class="w-5 h-5 text-gray-400 shrink-0" />
              <div class="min-w-0">
                <p class="font-medium text-gray-900 dark:text-white truncate">{{ doc.title }}</p>
                <p class="text-sm text-gray-500">
                  {{ doc.file_name }} · {{ formatFileSize(doc.chunk_count * 500) }}  <!-- 估算 -->
                  <span v-if="doc.chunk_count > 0"> · {{ doc.chunk_count }} 段</span>
                  <span v-if="doc.source_type !== 'upload'" class="ml-1">
                    · {{ doc.source_type.toUpperCase() }}
                  </span>
                </p>
              </div>
            </div>

            <div class="flex items-center gap-3 shrink-0">
              <UBadge :color="statusColor(doc.processing_status)" variant="subtle">
                {{ statusLabel(doc.processing_status) }}
              </UBadge>
              <!-- 仅上传者可删除，或 workspace_id 不为 null（平台文档）不显示删除 -->
              <UButton
                v-if="doc.workspace_id !== null"
                variant="ghost"
                color="error"
                icon="i-heroicons-trash"
                size="sm"
                :loading="deletingId === doc.id"
                @click="handleDelete(doc)"
              />
            </div>
          </div>
        </div>
      </ClientOnly>
    </UCard>

    <!-- 爬虫状态面板（新增折叠区块） -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between cursor-pointer" @click="showCrawlerPanel = !showCrawlerPanel">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <UIcon name="i-heroicons-cloud-arrow-down" class="w-4 h-4" />
            数据源状态
          </h2>
          <UButton variant="ghost" size="sm" icon="i-heroicons-arrow-path" />
        </div>
      </template>

      <div v-if="showCrawlerPanel">
        <ClientOnly>
          <template #fallback>
            <div class="text-center py-4 text-gray-500">加载状态中...</div>
          </template>

          <div v-if="loadingCrawler" class="text-center py-4 text-gray-500">
            加载中...
          </div>

          <table v-else class="w-full">
            <thead class="text-xs text-gray-500 bg-gray-50 dark:bg-gray-900">
              <tr>
                <th class="text-left py-2 px-4">数据源</th>
                <th class="text-right py-2 px-4">总数</th>
                <th class="text-right py-2 px-4">就绪</th>
                <th class="text-right py-2 px-4">失败</th>
                <th class="text-right py-2 px-4">最后更新</th>
                <th class="text-center py-2 px-4">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in crawlerStatus.items" :key="item.source_type" class="border-b border-gray-200 dark:border-gray-800">
                <td class="py-3 px-4">
                  <span class="font-medium">{{ sourceTypeLabel(item.source_type) }}</span>
                </td>
                <td class="text-right py-3 px-4">{{ item.total_docs }}</td>
                <td class="text-right py-3 px-4 text-green-600">{{ item.ready_docs }}</td>
                <td class="text-right py-3 px-4 text-red-600">{{ item.failed_docs }}</td>
                <td class="text-right py-3 px-4">
                  {{ item.last_crawled_at ? formatDate(item.last_crawled_at) : '-' }}
                </td>
                <td class="text-center py-3 px-4">
                  <UButton
                    variant="ghost"
                    size="xs"
                    :loading="runningCrawler === item.source_type"
                    @click="handleRunCrawler(item.source_type)"
                  >
                    触发
                  </UButton>
                </td>
              </tr>
            </tbody>
          </table>
        </ClientOnly>
      </div>
    </UCard>

    <!-- 上传弹窗（移除可见范围选项） -->
    <UModal v-model:open="showUploadModal" title="上传文档">
      <template #body>
        <div class="space-y-4">
          <UFormField label="文档标题（可选）">
            <UInput v-model="uploadForm.title" placeholder="留空则使用文件名" />
          </UFormField>

          <UFormField label="选择文件">
            <input
              ref="fileInputRef"
              type="file"
              accept=".pdf,.docx,.txt,.md"
              class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
              @change="handleFileChange"
            >
            <p class="text-xs text-gray-400 mt-1">支持 PDF、DOCX、TXT、MD，最大 50 MB</p>
          </UFormField>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="outline" @click="showUploadModal = false">取消</UButton>
          <UButton
            :loading="uploading"
            :disabled="!uploadForm.file"
            @click="handleUpload"
          >
            上传
          </UButton>
        </div>
      </template>
    </UModal>

    <!-- 删除确认弹窗 -->
    <UModal v-model:open="showDeleteModal" title="确认删除">
      <template #body>
        <p class="text-gray-700 dark:text-gray-300">
          确定要删除文档「{{ deletingDoc?.title }}」吗？此操作不可撤销。
        </p>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="outline" @click="showDeleteModal = false">取消</UButton>
          <UButton color="error" :loading="!!deletingId" @click="confirmDelete">删除</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
import type { KnowledgeDocument } from '../../types'
import type { CrawlerStatusItem } from '../../types'

definePageMeta({ layout: 'default' })
useHead({ title: '市场知识库' })

const { listDocuments, uploadDocument, deleteDocument, searchDocuments, getCrawlerStatus, runCrawler, sourceTypeLabel } = useKnowledgeBase()
const toast = useToast()
const { hasPermission } = usePermissions()

// 列表状态
const documents = ref<KnowledgeDocument[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const sourceTypeFilter = ref<'all' | 'upload' | 'cnnic' | 'nbs' | 'govsite'>('all')

const sourceTypeOptions = [
  { label: '全部', value: 'all' },
  { label: '上传', value: 'upload' },
  { label: 'CNNIC', value: 'cnnic' },
  { label: 'NBS', value: 'nbs' },
  { label: 'gov.cn', value: 'govsite' },
]

// 爬虫状态面板
const showCrawlerPanel = ref(false)
const crawlerStatus = ref<CrawlerStatusItem[]>([])
const loadingCrawler = ref(false)
const runningCrawler = ref<string | null>(null)

// 上传
const showUploadModal = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadForm = reactive<{ title: string; file: File | null }>({
  title: '',
  file: null,
})

// 删除
const showDeleteModal = ref(false)
const deletingDoc = ref<KnowledgeDocument | null>(null)
const deletingId = ref<number | null>(null)

// 检查删除权限
const canDelete = (doc: KnowledgeDocument) => {
  // 上传者可删除
  return doc.workspace_id !== null && hasPermission('KB_DELETE')
}

async function refresh() {
  loading.value = true
  try {
    const params: { page?: number; page_size?: number; source_type?: string } = {
      page: page.value,
      page_size: pageSize,
    }
    if (sourceTypeFilter.value !== 'all') params.source_type = sourceTypeFilter.value
    const res = await listDocuments(params)
    documents.value = res.items
    total.value = res.total
  } catch {
    toast.add({ title: '加载失败', color: 'error' })
  } finally {
    loading.value = false
  }
}

watch([page, sourceTypeFilter], refresh)
onMounted(refresh)

// 上传
function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadForm.file = input.files?.[0] ?? null
}

async function handleUpload() {
  if (!uploadForm.file) return
  uploading.value = true
  try {
    await uploadDocument(uploadForm.file, uploadForm.title || undefined)
    toast.add({ title: '上传成功，后台处理中', color: 'success' })
    showUploadModal.value = false
    uploadForm.title = ''
    uploadForm.file = null
    if (fileInputRef.value) fileInputRef.value.value = ''
    await refresh()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '上传失败'
    toast.add({ title: msg, color: 'error' })
  } finally {
    uploading.value = false
  }
}

// 删除
function handleDelete(doc: KnowledgeDocument) {
  deletingDoc.value = doc
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (!deletingDoc.value) return
  deletingId.value = deletingDoc.value.id
  try {
    await deleteDocument(deletingDoc.value.id)
    toast.add({ title: '删除成功', color: 'success' })
    showDeleteModal.value = false
    deletingDoc.value = null
    await refresh()
  } catch {
    toast.add({ title: '删除失败', color: 'error' })
  } finally {
    deletingId.value = null
  }
}

// 爬虫状态
async function refreshCrawlerStatus() {
  loadingCrawler.value = true
  try {
    const res = await getCrawlerStatus()
    crawlerStatus.value = res.items
  } catch {
    toast.add({ title: '加载状态失败', color: 'error' })
  } finally {
    loadingCrawler.value = false
  }
}

async function handleRunCrawler(sourceType: string) {
  if (!hasPermission('KB_WRITE')) {
    toast.add({ title: '无操作权限', color: 'error' })
    return
  }
  runningCrawler.value = sourceType
  try {
    const res = await runCrawler(sourceType)
    toast.add({ title: res.message || '已派发爬取任务', color: 'success' })
  } catch {
    toast.add({ title: '触发失败', color: 'error' })
  } finally {
    runningCrawler.value = null
  }
}

// 格式化日期
function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 页面展开时刷新爬虫状态
watch(showCrawlerPanel, (val) => {
  if (val) refreshCrawlerStatus()
})
</script>
```

**关键断言**：
- 过滤器从 `workspace` 改为 `source_type`，下拉选项为全部/上传/CNNIC/NBS/govsite
- 文档卡片移除 `doc.file_size` 显示（后端不返回）
- 平台文档（`workspace_id = null`）不显示删除按钮
- 爬虫面板折叠/展开时自动刷新状态
- 触发按钮有独立 loading 状态，防止重复点击

**验证**：`pnpm fe:typecheck`

**依赖**：Step 1, Step 2

---

### Step 4：创建搜索页面（pages/knowledge-base/search.vue）
**文件**：`frontend/layers/knowledge-base/pages/knowledge-base/search.vue`（新建）

独立的 RAG 检索测试页面：

```vue
<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- 搜索输入区域 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            RAG 检索测试
          </h1>
          <p class="text-sm text-gray-600 dark:text-gray-400">
            测试向量检索功能，输入查询词获取最相关的文档分块
          </p>
        </div>
      </template>

      <template #body>
        <div class="space-y-4">
          <UFormField label="查询词">
            <UInput
              v-model="query"
              placeholder="例如：小米SU7 品牌口碑、社交媒体平台趋势..."
              @keyup.enter="handleSearch"
            />
          </UFormField>

          <UFormField label="返回结果数">
            <div class="flex items-center gap-4">
              <UInput v-model.number="topK" type="number" min="1" max="20" />
              <UButton @click="handleSearch" :loading="loading" class="shrink-0">
                检索
              </UButton>
            </div>
          </UFormField>

          <UFormField label="上次查询：{{ lastQuery || '-' }}"></UFormField>
        </div>
      </template>
    </UCard>

    <!-- 搜索结果 -->
    <UCard v-if="results.length > 0">
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            检索结果（共 {{ total }} 条）
          </h2>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-4 text-gray-500">加载结果中...</div>
        </template>

        <div class="divide-y divide-gray-100 dark:divide-gray-800">
          <div
            v-for="(result, idx) in results"
            :key="result.chunk_id"
            class="p-4 border-b border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div class="space-y-2">
              <!-- 相关度 -->
              <div class="flex items-center gap-2">
                <UIcon name="i-heroicons-sparkles" class="w-4 h-4 text-yellow-500" />
                <div class="min-w-0">
                  <p class="text-sm text-gray-600 dark:text-gray-400">
                    文档：<span class="font-medium text-gray-900 dark:text-white">{{ result.document_title }}</span>
                  </p>
                  <p class="text-sm text-gray-600 dark:text-gray-400">
                    相关度：{{ (result.score * 100).toFixed(1) }}%
                  </p>
                </div>
                <UBadge variant="subtle" class="shrink-0">分块 #{{ idx + 1 }}</UBadge>
              </div>

              <!-- 分块内容 -->
              <div class="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-sm">
                <p class="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
                  {{ result.content }}
                </p>
              </div>
            </div>
          </div>
        </ClientOnly>

      <template #footer>
        <div class="text-center py-2">
          <p class="text-sm text-gray-500">
            显示前 {{ results.length }} 条结果（按相关度排序）
          </p>
        </div>
      </template>
    </UCard>

    <!-- 无结果提示 -->
    <UCard v-else-if="query && !loading && results.length === 0">
      <div class="text-center py-12">
        <UIcon name="i-heroicons-magnifying-glass" class="w-12 h-12 text-gray-300 mx-auto mb-3" />
        <p class="text-gray-500">未找到相关文档分块</p>
        <p class="text-sm text-gray-400 mt-2">尝试调整查询词或上传更多相关文档</p>
      </div>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { ChunkResult, SearchResponse } from '../../types'

definePageMeta({ layout: 'default' })
useHead({ title: 'RAG 检索测试' })

const { searchDocuments } = useKnowledgeBase()
const toast = useToast()

const query = ref('')
const topK = ref(6)
const loading = ref(false)
const results = ref<ChunkResult[]>([])
const total = ref(0)
const lastQuery = ref('')

async function handleSearch() {
  if (!query.value.trim()) {
    toast.add({ title: '请输入查询词', color: 'warning' })
    return
  }

  loading.value = true
  try {
    const res = await searchDocuments(query.value, topK.value)
    results.value = res.results
    total.value = res.total
    lastQuery.value = query.value
  } catch {
    toast.add({ title: '检索失败', color: 'error' })
  } finally {
    loading.value = false
  }
}

// 允许 Enter 键触发
function handleSearch() {
  void handleSearch()
}
</script>
```

**关键断言**：
- 输入框支持 Enter 键提交
- 结果按相关度排序（后端已处理）
- 显示分块编号、文档标题、相关度
- 空结果提示调整查询词
- 动态内容用 `<ClientOnly>` 包装并提供 fallback

**验证**：`pnpm fe:typecheck`

**依赖**：Step 1, Step 2

---

## 边界情况 & 错误处理

| 场景 | 处理 |
|------|------|
| 后端返回错误消息 | 显示 `error_message` badge（红色） |
| 爬虫触发无权限 | 检查 `KB_WRITE` 权限，toast 提示 |
| 文件过大 | 后端 413 → 前端已限制文件选择（accept 属性） |
| RAG 检索无结果 | 显示友好提示，建议调整查询词 |
| 爬虫状态加载失败 | 显示 error toast，折叠面板保持折叠 |

---

## 测试策略

| 类型 | 测试点 |
|------|--------|
| Unit | `useKnowledgeBase` 函数调用正确性（通过集成测试间接验证） |
| Integration | 文档列表 CRUD 流程、上传/删除 API 调用 |
| E2E | 爬虫状态面板折叠/展开、搜索页面完整流程 |

---

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 爬虫状态面板位置 | 内嵌在 index.vue 底部 | 当前功能较小，内嵌简化导航；未来独立时可搬走 |
| 搜索页面 | 独立页面 `/knowledge-base/search` | 搜索是独立交互流程，不适合嵌入列表页 |
| source_type 过滤 | 替换 workspace 过滤器 | 对齐后端 API，支持爬虫来源过滤 |
| 移除 isPublic 参数 | 不发送 | 后端不支持，始终上传为私有 |
| 文件大小估算 | 用 `chunk_count * 500` 估算 | 后端不返回 `file_size`，提供粗略估算 |
