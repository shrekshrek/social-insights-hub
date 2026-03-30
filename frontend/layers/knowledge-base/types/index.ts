export interface KnowledgeDocument {
  id: number
  workspace_id: number | null
  title: string
  source_type: string
  source_url: string | null
  file_name: string | null
  industry_tags: string[]
  chunk_count: number
  processing_status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DocumentUploadResponse {
  id: number
  title: string
  processing_status: string
  message: string
}

export interface ChunkResult {
  document_id: number
  document_title: string
  content: string
  score: number
  chunk_index: number
}

export interface DocumentListResponse {
  items: KnowledgeDocument[]
  total: number
  page: number
  page_size: number
}

export interface SearchResponse {
  query: string
  results: ChunkResult[]
  total: number
}

export interface CrawlerStatusItem {
  source_type: string
  total_docs: number
  ready_docs: number
  failed_docs: number
  last_crawled_at: string | null
}

export interface CrawlerStatusResponse {
  items: CrawlerStatusItem[]
}

export interface CrawlerRunResponse {
  source_type: string
  task_id?: string | null
  message: string
}
