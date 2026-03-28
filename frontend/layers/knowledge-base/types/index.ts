export interface KnowledgeDocument {
  id: number
  title: string
  filename: string
  file_type: string
  file_size: number
  industry_tags: string[]
  processing_status: 'pending' | 'processing' | 'ready' | 'failed'
  chunk_count: number
  workspace_id: number | null
  uploaded_by: number
  source_meta: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface DocumentUploadResponse {
  document_id: number
  title: string
  status: string
}

export interface ChunkResult {
  chunk_id: number
  document_id: number
  document_title: string
  content: string
  score: number
}

export interface SearchResponse {
  query: string
  results: ChunkResult[]
  total: number
}

export interface DocumentListResponse {
  items: KnowledgeDocument[]
  total: number
  page: number
  page_size: number
}
