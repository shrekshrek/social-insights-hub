/**
 * AI分析模块 - TypeScript 类型定义
 *
 * 包含：
 * - Token使用统计
 * - 分析结果模型
 * - 任务级分析
 * - 项目级分析
 */

// ==================== Token Usage ====================

export interface CallDetail {
  call_index: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cost_cny: number
  duration_seconds: number
  timestamp?: string
}

export interface TokenUsageSummary {
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  total_cost_cny: number
  total_duration_seconds: number
  avg_tokens_per_call: number
  avg_cost_per_call: number
}

export interface TokenUsageStats {
  summary: TokenUsageSummary
  call_details: CallDetail[]
}

// ==================== Post Analysis ====================

export interface PostAnalysis {
  id: number
  task_id: number
  post_id: number
  spam_score: number | null
  value_score: number | null
  relevance_score: number | null
  sentiment: -1 | 0 | 1 | null
  depth_analysis_result: Record<string, unknown> | null
  analyzed_at: string | null
  analysis_model: string | null
  created_at: string
  updated_at: string
}

export interface PostAnalysisCreate {
  task_id: number
  post_id: number
  spam_score?: number
  value_score?: number
  relevance_score?: number
  sentiment?: -1 | 0 | 1
  depth_analysis_result?: Record<string, unknown>
}

// ==================== Comment Analysis ====================

export interface CommentAnalysis {
  id: number
  task_id: number
  comment_id: number
  spam_score: number | null
  value_score: number | null
  relevance_score: number | null
  sentiment: -1 | 0 | 1 | null
  depth_analysis_result: Record<string, unknown> | null
  analyzed_at: string | null
  analysis_model: string | null
  created_at: string
  updated_at: string
}

export interface CommentAnalysisCreate {
  task_id: number
  comment_id: number
  spam_score?: number
  value_score?: number
  relevance_score?: number
  sentiment?: -1 | 0 | 1
  depth_analysis_result?: Record<string, unknown>
}

// ==================== Task Analysis Result ====================

export type AnalysisType =
  | 'screening_posts'
  | 'screening_comments'
  | 'deep_posts'
  | 'deep_comments'

export type AnalysisStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface TaskAnalysisResult {
  id: number
  task_id: number
  analysis_type: AnalysisType
  result_data: Record<string, unknown> | null
  analysis_summary: string | null
  source_count: number
  analyzed_count: number
  failed_count: number
  celery_task_id: string
  status: AnalysisStatus
  started_at: string | null
  completed_at: string | null
  processing_time: number | null
  token_usage: TokenUsageStats | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface TaskAnalysisResultCreate {
  task_id: number
  analysis_type: AnalysisType
  celery_task_id: string
  source_count?: number
}

export interface TaskAnalysisResultUpdate {
  status?: AnalysisStatus
  result_data?: Record<string, unknown>
  analysis_summary?: string
  analyzed_count?: number
  failed_count?: number
  started_at?: string
  completed_at?: string
  processing_time?: number
  token_usage?: TokenUsageStats
  error_message?: string
}

// ==================== Project Analysis Result ====================

export type ProjectAnalysisType =
  | 'topic_clustering'
  | 'competitive_analysis'

export interface ProjectAnalysisConfig {
  // 主题聚类配置
  num_clusters?: number
  clustering_method?: 'kmeans' | 'hierarchical' | 'dbscan'

  // 竞品分析配置
  competitor_keywords?: string[]
  comparison_metrics?: string[]

  // 通用配置
  [key: string]: unknown
}

export interface ProjectAnalysisResult {
  id: number
  project_id: number
  user_id: number
  analysis_type: ProjectAnalysisType
  analysis_config: ProjectAnalysisConfig | null
  source_task_ids: number[] | null
  source_data_count: number
  result_data: Record<string, unknown> | null
  analysis_summary: string | null
  celery_task_id: string
  status: AnalysisStatus
  processing_time: number | null
  token_usage: TokenUsageStats | null
  error_message: string | null
  created_at: string
  completed_at: string | null
  updated_at: string
}

export interface ProjectAnalysisResultCreate {
  project_id: number
  analysis_type: ProjectAnalysisType
  analysis_config?: ProjectAnalysisConfig
  source_task_ids?: number[]
}

export interface ProjectAnalysisResultUpdate {
  status?: AnalysisStatus
  result_data?: Record<string, unknown>
  analysis_summary?: string
  processing_time?: number
  token_usage?: TokenUsageStats
  error_message?: string
  completed_at?: string
}

// ==================== Analysis Statistics ====================

export interface AnalysisStats {
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  pending_tasks: number
  processing_tasks: number
  total_cost_cny: number
  total_tokens: number
  avg_processing_time: number
}

export interface TaskAnalysisStats {
  task_id: number
  task_name: string
  total_analyses: number
  screening_count: number
  deep_analysis_count: number
  total_cost: number
  total_tokens: number
  last_analysis_at: string | null
}

export interface ProjectAnalysisStats {
  project_id: number
  project_name: string
  total_analyses: number
  clustering_count: number
  competitive_count: number
  total_cost: number
  total_tokens: number
  last_analysis_at: string | null
}

// ==================== API Requests ====================

export interface RunScreeningRequest {
  task_id: number
  post_ids?: number[]
  comment_ids?: number[]
  analyze_all?: boolean
}

export interface RunDeepAnalysisRequest {
  task_id: number
  post_ids?: number[]
  comment_ids?: number[]
  analysis_focus?: string[]
}

export interface RunClusteringRequest {
  project_id: number
  task_ids?: number[]
  num_clusters?: number
  method?: 'kmeans' | 'hierarchical' | 'dbscan'
}

export interface RunCompetitiveRequest {
  project_id: number
  task_ids?: number[]
  competitor_keywords: string[]
  metrics?: string[]
}

// ==================== API Responses ====================

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface RunAnalysisResponse {
  celery_task_id: string
  result_id: number
  status: AnalysisStatus
  message: string
}

export interface AnalysisProgressResponse {
  result_id: number
  status: AnalysisStatus
  progress: number
  analyzed_count: number
  total_count: number
  estimated_time_remaining: number | null
  current_cost: number
  current_tokens: number
}
