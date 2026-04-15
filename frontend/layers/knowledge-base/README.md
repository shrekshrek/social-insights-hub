# Knowledge Base Layer

市场知识库模块 - 文档管理、RAG 向量检索、爬虫数据源。

## Public Interface

### Composable: `useKnowledgeBase()`

```typescript
const {
  getDocuments,       // 获取文档列表（useApiData 模式，自动缓存失效）
  getDocument,        // 获取单个文档
  uploadDocument,    // 上传文档（写操作，返回 Promise）
  searchDocuments,   // RAG 检索（写操作，返回 Promise）
  getCrawlerStatus,   // 获取爬虫状态（useApiData 模式）
  runCrawler,        // 手动触发爬虫（写操作，返回 Promise）
  deleteDocument,     // 删除文档（写操作，返回 Promise）
  sourceTypeLabel,    // 来源类型标签辅助
  statusLabel,        // 处理状态标签辅助
  statusColor,        // 处理状态颜色辅助
  formatFileSize,      // 文件大小格式化辅助
} = useKnowledgeBase()
```

#### 数据获取模式

- **useApiData 函数**（`getDocuments`, `getDocument`, `getCrawlerStatus`）：
  - 返回 `{ data, pending, refresh }`
  - 自动支持 SSR
  - 自动缓存失效（通过 computed key）
  - 自动 loading 状态管理
  - 统一错误处理

- **Promise 函数**（`uploadDocument`, `searchDocuments`, `runCrawler`, `deleteDocument`）：
  - 用于写操作（表单提交、删除）
  - 手动管理 loading 状态
  - 返回业务数据对象
  - 自动错误处理和 toast 提示

#### 使用示例

```typescript
// 文档列表（读操作）
const { data: documentsData, pending: loading } = getDocuments({
  page: 1,
  page_size: 20,
  source_type: 'all'
})
const documents = computed(() => documentsData.value?.items || [])

// 上传文档（写操作）
async function handleUpload() {
  try {
    const result = await uploadDocument(file, title)
    toast.add({ title: '上传成功', color: 'success' })
  } catch {
    // 错误已由 apiRequest 统一处理
  }
}
```

## Pages

### `/knowledge-base` - 文档列表和爬虫状态
- 文档列表展示
- 来源类型过滤（全部/上传/CNNIC/NBS/gov.cn）
- 爬虫状态面板（可折叠）
- 上传、删除操作（需要 `KB_WRITE` 和 `KB_DELETE` 权限）

### `/knowledge-base/search` - RAG 检索测试
- 查询词输入
- 返回结果数控制（topK）
- 结果展示（相关度、分块内容）

### `/knowledge-base/upload` - 文档上传
- 文件选择（PDF/DOCX/TXT/MD，最大 50MB）
- 可选标题设置
- 自动跳转回列表页

## Data Model

### KnowledgeDocument（文档）
```typescript
{
  id: number
  workspace_id: number | null        // null = 平台公共文档
  title: string
  source_type: string              // 'upload' | 'cnnic' | 'nbs' | 'govsite'
  source_url: string | null          // 爬取来源 URL
  file_name: string | null           // 原始文件名
  industry_tags: string[]
  chunk_count: number
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null       // 处理失败原因
  created_at: string
  updated_at: string
}
```

### ChunkResult（检索结果）
```typescript
{
  document_id: number
  document_title: string
  content: string
  score: number                  // 相似度 0-1
  chunk_index: number             // 分块序号
}
```

### CrawlerStatusItem（爬虫状态）
```typescript
{
  source_type: string
  total_docs: number
  ready_docs: number
  failed_docs: number
  last_crawled_at: string | null
}
```

## Important Notes

### 权限控制

| 权限 | 说明 |
|------|------|
| `KB_ACCESS` | 查看文档列表、爬虫状态 |
| `KB_READ` | RAG 检索测试 |
| `KB_WRITE` | 上传文档、触发爬虫 |
| `KB_DELETE` | 删除文档（仅用户上传文档） |

### 删除权限规则

- 平台公共文档（`workspace_id = null`）不显示删除按钮
- 用户上传文档（`workspace_id !== null`）需要 `KB_DELETE` 权限才能删除

### 爬虫架构决策

爬虫功能当前内嵌在知识库模块中，未来拆分条件：
1. 数据源 > 5-6 个（目前 3 个：CNNIC、NBS、gov.cn）
2. 需要调度 UI（查看下次执行时间、修改 cron、暂停/恢复）
3. 爬取内容不仅入 KB，还流向其他模块
4. 出现独立的"数据管理员"角色

### 数据获取最佳实践

- **列表数据**：使用 `getDocuments()` + computed 解构
  ```typescript
  const { data, pending, refresh } = getDocuments(params)
  const docs = computed(() => data.value?.items || [])
  ```

- **写操作**：使用 Promise 函数，手动管理 loading
  ```typescript
  const uploading = ref(false)
  async function handleUpload() {
    uploading.value = true
    await uploadDocument(...)
    uploading.value = false
  }
  ```

- **错误处理**：`apiRequest` 统一处理错误，自动显示 toast
  ```typescript
  try {
    await uploadDocument(...)
  } catch {
    // 无需手动 try-catch，apiRequest 已处理
  }
  ```

## API Endpoints

| 端点 | 方法 | 说明 |
|--------|------|------|
| `/knowledge-base/documents` | GET/POST | 文档列表、上传 |
| `/knowledge-base/documents/{id}` | GET/DELETE | 获取详情、删除 |
| `/knowledge-base/search` | POST | RAG 向量检索 |
| `/knowledge-base/crawlers/status` | GET | 爬虫状态 |
| `/knowledge-base/crawlers/{source_type}/run` | POST | 手动触发爬虫 |
