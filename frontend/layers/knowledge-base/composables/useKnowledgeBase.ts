import type { KnowledgeDocument, DocumentListResponse, DocumentUploadResponse } from '../types'

export function useKnowledgeBase() {
  const { apiRequest } = useApi()

  async function listDocuments(params?: { page?: number; page_size?: number; workspace?: 'public' | 'private' }): Promise<DocumentListResponse> {
    const query = new URLSearchParams()
    if (params?.page) query.set('page', String(params.page))
    if (params?.page_size) query.set('page_size', String(params.page_size))
    if (params?.workspace) query.set('workspace', params.workspace)
    const qs = query.toString()
    return apiRequest<DocumentListResponse>(`/knowledge-base/documents${qs ? `?${qs}` : ''}`)
  }

  async function uploadDocument(file: File, title?: string, industryTags?: string[], isPublic?: boolean): Promise<DocumentUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    if (industryTags?.length) form.append('industry_tags', JSON.stringify(industryTags))
    if (isPublic !== undefined) form.append('is_public', String(isPublic))

    return apiRequest<DocumentUploadResponse>('/knowledge-base/documents/upload', {
      method: 'POST',
      body: form,
    })
  }

  async function deleteDocument(docId: number): Promise<void> {
    await apiRequest(`/knowledge-base/documents/${docId}`, { method: 'DELETE' })
  }

  function statusLabel(status: KnowledgeDocument['processing_status']): string {
    const map: Record<KnowledgeDocument['processing_status'], string> = {
      pending: '等待处理',
      processing: '处理中',
      ready: '已就绪',
      failed: '处理失败',
    }
    return map[status] ?? status
  }

  function statusColor(status: KnowledgeDocument['processing_status']): 'neutral' | 'info' | 'success' | 'error' {
    const map: Record<KnowledgeDocument['processing_status'], 'neutral' | 'info' | 'success' | 'error'> = {
      pending: 'neutral',
      processing: 'info',
      ready: 'success',
      failed: 'error',
    }
    return map[status] ?? 'neutral'
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return {
    listDocuments,
    uploadDocument,
    deleteDocument,
    statusLabel,
    statusColor,
    formatFileSize,
  }
}
