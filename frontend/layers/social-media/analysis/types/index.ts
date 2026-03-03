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
  type: '品牌' | '产品' | '服务' | '人物' | '其他'
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
  sentiment: -2 | -1 | 0 | 1 | 2 | null
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
  sentiment?: -2 | -1 | 0 | 1 | 2
  post_deep_result?: PostDeepResult
  comment_deep_result?: CommentDeepResult
}

// ==================== Analysis Job (统一模型) ====================

/**
 * 分析类型
 * - 任务级: screening_posts, deep_posts, deep_comments, aggregation
 * - 项目级: entity_normalization, opinion_normalization (task_id=null), project_slice_summary
 */
export type AnalysisType =
  | 'screening_posts'
  | 'deep_posts'
  | 'deep_comments'
  | 'aggregation'
  | 'entity_normalization'
  | 'opinion_normalization'
  | 'project_slice_summary'

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
  slice_id?: number
  slice_name?: string | null
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
  job_id: number | null  // 聚合分析不创建 AnalysisJob，可能为 null
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
  sentiment: -2 | -1 | 0 | 1 | 2 | null
  cii: number | null  // 内容影响力指数

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
  qualified_count: number // 符合阈值条件的已初筛帖子总数（不管是否已深度分析）
  matched_count: number // 符合条件且待深度分析的帖子数
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

// ==================== 任务级聚合分析结果 ====================

/** 数据量统计 */
export interface TaskAnalysisDataVolume {
  total: number
  screened: number
  deep_analyzed: number
  comment_analyzed: number
}

/** 营销浓度分析 */
export interface MarketingAnalysis {
  promotion_ratio: number
  organic_ratio: number
  promotion_count: number
  organic_count: number
}

/** 舆论反差度分析 */
export interface SentimentConflict {
  avg_conflict: number
  conflict_direction: 'post_positive' | 'comment_positive' | 'aligned'
  high_conflict_count: number
  risk_level: 'low' | 'medium' | 'high'
}

/** 核心指标 */
export interface TaskAnalysisMetrics {
  nsr: number
  avg_cii: number
  serp_health: number
  marketing_analysis: MarketingAnalysis
  sentiment_conflict: SentimentConflict
  nsr_by_spam?: NsrBySpam
}

/** 四象限数据项 */
export interface QuadrantItem {
  post_id: number
  x: number
  y: number
  quadrant: 'Q1_danger' | 'Q2_brand' | 'Q3_complaint' | 'Q4_niche' | 'neutral'
  label: string
  spam_group?: string
}

/** 四象限统计 */
export interface QuadrantSummary {
  Q1_danger: number
  Q2_brand: number
  Q3_complaint: number
  Q4_niche: number
  neutral: number
}

/** 时间分布数据项 */
export interface TimeDistributionItem {
  date: string
  count: number
  post_ids: number[]
  spam_breakdown?: SpamCountBreakdown
}

/** 数据新鲜度 */
export interface Freshness {
  last_7_days: number
  last_30_days: number
  avg_age_days: number
}

/** 原始观点词条 */
export interface OriginalTerm {
  text: string
  count: number
}

/** 实体属性项（features/issues/expectations 等） */
export interface EntityAttrItem {
  text: string
  post_ids: number[]
  original_terms?: OriginalTerm[]
}

/** IPA 分析点 */
export interface IpaPoint {
  name: string
  x: number        // 关注度 (Mentions)
  y: number        // 情感满意度 (Sentiment)
  z: number        // 气泡大小 (Log Smoothed Heat)
  heat: number     // 影响力 (Heat)
  post_ids: number[]
  spam_distribution?: SpamDistribution
  original_terms?: OriginalTerm[]  // 原始观点列表（仅当该点为观点集合时存在）
}

/** IPA 分析结果 */
export interface IpaAnalysis {
  quadrants: {
    strength: IpaPoint[]
    improvement: IpaPoint[]
    maintain: IpaPoint[]
    opportunity: IpaPoint[]
  }
  thresholds: {
    x: number
    y: number
  }
}

/** 关联网络节点 */
export interface ContextNode {
  name: string
  type: string
  weight: number
  co_occurrence: number
  sentiment?: number
  post_ids: number[]
}

/** 关联网络边 */
export interface ContextEdge {
  source: string
  target: string
  value: number
}

/** 关联网络图 */
export interface ContextGraph {
  center_node: string | null
  nodes: ContextNode[]
  edges: ContextEdge[]
}

/** 关联网络（支持维度筛选） */
export interface ContextGraphWithDimensions {
  all: ContextGraph
  organic: ContextGraph
  promo: ContextGraph
}

/** 竞品雷达系列数据 */
export interface CompetitorSeries {
  name: string
  data?: number[] // 雷达图数据
  sentiment?: number // 柱状图数据
  sentiment_distribution?: SentimentDistribution // 柱状图数据
  products?: string[] // 品牌聚合时包含的产品列表
  post_ids?: number[]
  spam_distribution?: SpamDistribution
}

/** 竞品雷达分析 */
export interface CompetitorRadar {
  mode: 'radar' | 'bar' | 'none'
  dimensions?: string[]
  series: CompetitorSeries[]
}

/** 竞品雷达（支持维度筛选） */
export interface CompetitorRadarWithDimensions {
  all: CompetitorRadar
  organic: CompetitorRadar
  promo: CompetitorRadar
}

/** 图表数据 */
export interface TaskAnalysisCharts {
  quadrant: QuadrantItem[]
  quadrant_summary: QuadrantSummary
  time_distribution: TimeDistributionItem[]
  time_distribution_skipped?: number  // 无发布时间的帖子数
  ipa_analysis?: IpaAnalysis
  context_graph?: ContextGraphWithDimensions
  competitor_radar?: CompetitorRadarWithDimensions
}

/** 来源分布 */
export interface SourceDistribution {
  post: number
  comment: number
}

/** 情感分布 */
export interface SentimentDistribution {
  positive: number
  negative: number
  neutral: number
}

/** 实体归一化信息 */
export interface EntityNormalizedInfo {
  aliases: string[]           // 别名列表（被合并的同义名称）
  parent: string | null       // 父级实体（上位概念）
  children: string[]          // 子级实体（下位概念）
  related: string[]           // 关联实体（语义相关但不同义）
  merged_from: string[]       // 合并来源（被合并的原始实体名称）
}

/** 实体多维标签 */
export interface EntityTags {
  role: string  // Target/Competitor/Context
  parent: string  // 品牌归属
}

/** 实体统计 */
export interface EntityStat {
  name: string
  type: string
  role: 'target' | 'competitor' | 'other'
  heat: number
  mentions: number
  score: number  // 综合评分
  sentiment: number  // 派生情感值 [-1, 1]，CII 加权（混合全部数据）
  promo_sentiment: number  // 促销情感（仅 spam_score >= 6.0 的帖子）
  organic_sentiment: number  // 有机情感（仅 spam_score < 6.0 的帖子）
  sentiment_distribution: SentimentDistribution  // 情感分布
  source_distribution: SourceDistribution
  // 详细项（包含 original_terms，用于 UI 溯源展示）
  top_features: EntityAttrItem[]
  top_issues: EntityAttrItem[]
  top_expectations: EntityAttrItem[]
  post_ids: number[]  // 关联帖子ID，用于反向追溯
  post_source_ids?: number[]
  comment_source_ids?: number[]
  spam_distribution?: SpamDistribution
  tags?: EntityTags  // 多维标签（可选）
  original_terms?: OriginalTerm[]  // 原始词条（可选，仅在合并时存在）
  normalized_info?: EntityNormalizedInfo  // LLM 归一化信息（可选）
}

/** 观点明细 */
export interface OpinionDetail {
  text: string
  count: number
  post_ids: number[]
}

/** 观点统计 */
export interface OpinionStat {
  name: string
  category?: string
  heat: number
  mentions: number
  score: number  // 综合评分
  sentiment: number
  source_distribution?: SourceDistribution  // 来源分布
  post_ids: number[]  // 关联帖子ID，用于反向追溯
  post_source_ids?: number[]
  comment_source_ids?: number[]
  spam_distribution?: SpamDistribution
  original_terms?: OriginalTerm[]  // 原始词条（可选，仅在合并时存在）
  // legacy compatibility
  post_source_count?: number
  comment_source_count?: number
  opinions?: OpinionDetail[]  // 观点列表（可选）
}


/** KOL 声音 */
export interface KolVoice {
  author: string
  title: string
  sentiment: number
  summary: string
  post_id: number
  cii: number
  platform: string
  spam_group?: string
}

/** 洞察数据 */
export interface TaskAnalysisInsights {
  top_entities: EntityStat[]
  target_entities: EntityStat[]
  competitor_entities: EntityStat[]
  top_topics: OpinionStat[]
  kol_voices: KolVoice[]
}

/** 元数据 */
export interface TaskAnalysisMeta {
  task_id: number | null
  analyzed_at: string | null
  keywords: string[]
  data_volume: TaskAnalysisDataVolume
}

// ==================== Spam Distribution ====================

/** 4 维分布 - 单个 spam 组内的原文/评论拆分 */
export interface SpamSourceBreakdown {
  total: number
  post: number
  comment: number
}

/** 4 维分布 (高/低广告 × 原文/评论) */
export interface SpamDistribution {
  high_spam: SpamSourceBreakdown
  low_spam: SpamSourceBreakdown
}

/** 2 维分布 (高/低广告) */
export interface SpamCountBreakdown {
  high: number
  low: number
}

/** 按 spam 分组的 NSR */
export interface NsrBySpam {
  high: number
  low: number
}

/** 任务级分析聚合结果 */
export interface TaskAnalysisResultData {
  meta: TaskAnalysisMeta
  metrics: TaskAnalysisMetrics
  charts: TaskAnalysisCharts
  freshness: Freshness
  insights: TaskAnalysisInsights
  spam_config?: { threshold: number }
}

/** 任务级聚合分析结果 API 响应 */
export interface TaskAnalysisResultResponse {
  task_id: number
  analyzed_at: string | null
  result: TaskAnalysisResultData
}

/** 运行聚合分析响应（与其他分析任务一致，异步执行） */
export type RunAggregationResponse = RunAnalysisResponse
