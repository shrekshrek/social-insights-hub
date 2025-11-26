/**
 * AI分析模块 - TypeScript 类型定义
 *
 * 统一使用 AnalysisJob 模型，通过 task_id 是否为空区分任务级/项目级分析
 */

import type { PaginatedResponse } from '~/types/common'

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

// ==================== Deep Analysis Results ====================

/**
 * 实体信息
 */
export interface EntityInfo {
  name: string
  type: '品牌' | '商品' | '服务' | '其他'
  sentiment: 1 | 0 | -1
  features: string[]
  issues: string[]
  expectations: string[]
  audience: string[]
  scenarios: string[]
  market_factors: string[]
  competitors: string[]
}

/**
 * 通用观点
 */
export interface GeneralOpinion {
  category: string
  opinions: string[]
  sentiment: 1 | 0 | -1
}

/**
 * 帖子深度分析结果
 */
export interface PostDeepResult {
  entities: EntityInfo[]
  general_opinions: GeneralOpinion[]
  summary: string
}

/**
 * 评论深度分析结果（按帖子聚合）
 */
export interface CommentDeepResult {
  entities: EntityInfo[]
  general_opinions: GeneralOpinion[]
}

// ==================== Post Analysis ====================

/**
 * 帖子AI分析结果（唯一的分析表）
 *
 * 包含三个层次的分析：
 * 1. 初筛分析：spam_score, value_score, relevance_score, sentiment
 * 2. 帖子深度分析：post_deep_result (实体、观点、摘要)
 * 3. 评论深度分析：comment_deep_result (评论的实体和观点聚合)
 */
export interface PostAnalysis {
  id: number
  task_id: number
  post_id: number
  spam_score: number | null
  value_score: number | null
  relevance_score: number | null
  sentiment: -1 | 0 | 1 | null
  post_deep_result: PostDeepResult | null
  comment_deep_result: CommentDeepResult | null
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
  post_deep_result?: PostDeepResult
  comment_deep_result?: CommentDeepResult
}

// ==================== Analysis Job (统一模型) ====================

/**
 * 分析类型
 * - 任务级: screening_posts, deep_posts, deep_comments
 * - 项目级: topic_clustering, competitive
 */
export type AnalysisType =
  | 'screening_posts'
  | 'deep_posts'
  | 'deep_comments'
  | 'topic_clustering'
  | 'competitive'

export type AnalysisStatus = 'pending' | 'processing' | 'completed' | 'failed'

/**
 * 分析任务（统一模型）
 *
 * 合并原 TaskAnalysisResult 和 ProjectAnalysisResult
 * task_id 为空表示项目级分析，非空表示任务级分析
 */
export interface AnalysisJob {
  id: number
  project_id: number
  task_id: number | null
  user_id: number
  analysis_type: AnalysisType
  celery_task_id: string
  status: AnalysisStatus

  // 配置
  analysis_config: Record<string, unknown> | null
  source_task_ids: number[] | null

  // 统计
  source_count: number
  analyzed_count: number
  failed_count: number

  // 结果
  result_data: Record<string, unknown> | null
  analysis_summary: string | null

  // 性能
  started_at: string | null
  completed_at: string | null
  processing_time: number | null
  token_usage: TokenUsageStats | null

  // 错误
  error_message: string | null

  // 时间戳
  created_at: string
  updated_at: string

  // 关联信息（从列表接口返回）
  project_name?: string
  task_name?: string
  user_name?: string
}

export type AnalysisJobListResponse = PaginatedResponse<AnalysisJob>

// ==================== Analysis Statistics ====================

export interface AnalysisStats {
  total_jobs: number
  completed_jobs: number
  failed_jobs: number
  pending_jobs: number
  processing_jobs: number
  total_cost_cny: number
  total_tokens: number
  avg_processing_time: number
}

// ==================== API Requests ====================

export interface RunScreeningRequest {
  task_id: number
  post_ids?: number[]
  analyze_all?: boolean
}

export interface RunDeepAnalysisRequest {
  task_id: number
  post_ids?: number[]
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

export interface RunAnalysisResponse {
  celery_task_id: string
  job_id: number
  status: AnalysisStatus
  message: string
}

export interface AnalysisProgressResponse {
  job_id: number
  status: AnalysisStatus
  progress: number
  analyzed_count: number
  total_count: number
  estimated_time_remaining: number | null
  current_cost: number
  current_tokens: number
}

// ==================== Post Analysis with Post Info ====================

export interface PostAnalysisWithPostInfo {
  // 帖子基本信息
  post_id: number
  post_id_on_platform: string | null  // 平台上的帖子ID，用于关联原文数据
  title: string | null
  content: string | null
  author_name: string | null
  likes_count: number
  comments_count: number
  shares_count: number
  collected_count: number
  views_count: number
  danmaku_count: number
  published_at: string | null
  url: string | null

  // 初筛分析
  spam_score: number | null
  value_score: number | null
  relevance_score: number | null
  sentiment: -1 | 0 | 1 | null

  // 深度分析
  post_deep_result: PostDeepResult | null
  comment_deep_result: CommentDeepResult | null

  // 元数据
  analyzed_at: string | null
  analysis_model: string | null
}

export type PostAnalysisListResponse = PaginatedResponse<PostAnalysisWithPostInfo>

// ==================== 深度分析预览 ====================
export interface DeepAnalysisPreview {
  total_posts: number
  screened_count: number
  matched_count: number
  deep_done: number
  comment_done: number
  deep_candidate_ids: number[]
  comment_candidate_ids: number[]
}

// ==================== 筛选参数 ====================

export interface AnalysisJobFilterParams {
  page?: number
  page_size?: number
  project_id?: number
  task_id?: number
  analysis_type?: AnalysisType
  status?: AnalysisStatus
  start_date?: string
  end_date?: string
}
