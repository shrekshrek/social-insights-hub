import type {
  DocumentListResponse,
  DocumentUploadResponse,
  CrawlerStatusResponse,
  CrawlerRunResponse,
  SearchResponse,
  KnowledgeDocument,
} from '../types'

export function useKnowledgeBase() {
  const { apiRequest, useApiData } = useApi()

  // 获取文档列表（使用 useApiData 模式）
  const getDocuments = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<DocumentListResponse>('/knowledge-base/documents', {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `documents-list-${p?.page || 1}-${p?.page_size || 20}-${p?.source_type || 'all'}`
      }),
    })
  }

  // 获取单个文档
  const getDocument = (id: number) => {
    return useApiData<KnowledgeDocument>(`/knowledge-base/documents/${id}`, {
      key: `document-${id}`,
    })
  }

  // 上传文档（保持 apiRequest 用于写操作）
  async function uploadDocument(file: File, title?: string): Promise<DocumentUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)

    return apiRequest<DocumentUploadResponse>('/knowledge-base/documents/upload', {
      method: 'POST',
      body: form,
    })
  }

  // 搜索文档（RAG 检索）- 保持 apiRequest 用于写操作
  async function searchDocuments(query: string, topK = 6): Promise<SearchResponse> {
    return apiRequest<SearchResponse>('/knowledge-base/search', {
      method: 'POST',
      body: { query, top_k: topK },
    })
  }

  // 获取爬虫状态（使用 useApiData 模式）
  const getCrawlerStatus = () => {
    return useApiData<CrawlerStatusResponse>('/knowledge-base/crawlers/status', {
      key: 'crawler-status',
    })
  }

  // 手动触发爬虫（保持 apiRequest 用于写操作）
  async function runCrawler(sourceType: string): Promise<CrawlerRunResponse> {
    return apiRequest<CrawlerRunResponse>(`/knowledge-base/crawlers/${sourceType}/run`, {
      method: 'POST',
    })
  }

  // 删除文档（保持 apiRequest 用于写操作）
  async function deleteDocument(id: number) {
    return apiRequest(`/knowledge-base/documents/${id}`, {
      method: 'DELETE',
    })
  }

  // 来源类型标签辅助
  function sourceTypeLabel(sourceType: string): string {
    const labels: Record<string, string> = {
      'cnnic': 'CNNIC 统计报告',
      'cnnic_research': 'CNNIC 专题研究',
      'nbs': 'NBS 月报',
      'govsite': 'gov.cn 政策',
      'upload': '用户上传',
    }
    return labels[sourceType] ?? sourceType
  }

  // 状态标签
  function statusLabel(status: string): string {
    const labels: Record<string, string> = {
      'pending': '等待处理',
      'processing': '处理中',
      'ready': '就绪',
      'failed': '失败',
    }
    return labels[status] ?? status
  }

  // 状态颜色
  function statusColor(status: string): 'neutral' | 'info' | 'success' | 'error' {
    const colors: Record<string, 'neutral' | 'info' | 'success' | 'error'> = {
      'pending': 'neutral',
      'processing': 'info',
      'ready': 'success',
      'failed': 'error',
    }
    return colors[status] ?? 'neutral'
  }

  // 文件大小格式化
  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
  }

  return {
    getDocuments,
    getDocument,
    uploadDocument,
    searchDocuments,
    getCrawlerStatus,
    runCrawler,
    deleteDocument,
    sourceTypeLabel,
    statusLabel,
    statusColor,
    formatFileSize,
  }
}
