/**
 * 新闻监测模块类型定义
 */

export interface NewsMonitor {
  id: number
  name: string
  description: string | null
  user_id: number
  participant_ids: number[]
  created_at: string
  updated_at: string
}

export interface NewsMonitorWithOwner extends NewsMonitor {
  owner_username: string
  participant_usernames: string[]
}

export interface NewsTask {
  id: number
  name: string
  monitor_id: number
  strategy_id: number | null
  keywords: string
  phase: string | null
  status: string
  search_params: Record<string, unknown> | null
  articles_count: number
  analysis_result: NewsTaskAnalysisResult | null
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  user_id: number
  created_at: string
  updated_at: string
}

export interface NewsTaskWithRelations extends NewsTask {
  monitor_name: string | null
  user_username: string | null
}

export interface NewsMonitorCreate {
  name: string
  description?: string | null
  participant_ids?: number[]
}

export interface NewsMonitorUpdate {
  name?: string
  description?: string | null
}

export interface NewsTaskCreate {
  name: string
  keywords: string
  phase?: 'probe' | 'collect' | null
  search_params?: Record<string, unknown> | null
}

/**
 * 单渠道的采集量（原始召回 vs 去重入库）
 * - raw：去重前原始召回量（渠道健康度指标）
 * - deduped：URL 跨渠道去重后实际入库的文章数（最终可用数据）
 */
export interface ChannelCount {
  raw: number
  deduped: number
}

/**
 * 新闻任务的渠道采集量分布
 * 每渠道含 raw + deduped 两个数字；任务未完成或旧任务 raw 可能为 0
 */
export interface NewsTaskChannelStats {
  baidu: ChannelCount
  sogou: ChannelCount
  wechat_mp: ChannelCount
  raw_total: number
  deduped_total: number
}

// ==================== Task Analysis Result ====================
// task.analysis_result 仅含 meta 子字段，由 _compute_task_stats 派生（无 LLM）。
// 所有归一/聚类/解读层产出在 slice 层，不在 task 层。

export interface NewsTaskTopQuote {
  speaker: string
  quote: string
  source_name: string
  source_tier: string
  article_id: number
}

export interface NewsTaskCoverageDay {
  date: string
  count: number
  count_by_tier: { tier1: number; tier2: number; tier3: number; wechat_mp: number }
  sentiment_avg: number | null
}

export interface NewsTaskMeta {
  keywords: string
  articles_crawled?: number
  channel_raw_counts?: Record<string, number>

  articles_total: number
  articles_high: number
  articles_medium: number
  articles_low: number

  source_tier_distribution: { tier1: number; tier2: number; tier3: number; wechat_mp: number }
  search_source_distribution: { baidu: number; sogou: number; wechat_mp: number }
  article_type_distribution: { report: number; opinion: number; pr: number; analysis: number }
  sentiment_distribution: { positive: number; neutral: number; negative: number }

  sentiment_overall: number | null
  sentiment_by_tier: {
    tier1: number | null
    tier2: number | null
    tier3: number | null
    wechat_mp: number | null
  }

  coverage_by_day: NewsTaskCoverageDay[]
  top_entities_raw: Array<{ name: string; mention_count: number }>
  top_quotes: NewsTaskTopQuote[]

  // probe 阶段独有：搜索到的来源样本
  source_samples?: string[]
}

export interface NewsTaskAnalysisResult {
  meta: NewsTaskMeta
}

// ==================== Slice Result Types（ADR-003 新 schema） ====================

export type TierKey = 'tier1' | 'tier2' | 'tier3' | 'wechat_mp'
export type SpeakerRole = 'official' | 'executive' | 'analyst' | 'kol' | 'other'
export type EntityRole = 'target' | 'competitor' | 'context'

export type TierBreakdown = Record<TierKey, number>
export type TierBreakdownNullable = Record<TierKey, number | null>

export interface NewsSliceCrossTaskOverlap {
  distribution: { single_task: number; two_tasks: number; three_plus: number }
  high_overlap_articles: Array<{
    url: string
    task_ids: number[]
    title: string
    article_id: number
    task_count: number
  }>
}

export interface NewsSliceCoverageDay {
  date: string
  count: number
  count_by_tier: TierBreakdown
}

export interface NewsSliceSentimentDay {
  date: string
  sentiment_avg: number | null
  sentiment_weighted_by_tier: number | null
}

export interface NewsSliceDescriptive {
  articles_total: number
  articles_unique: number
  articles_filtered: number

  source_tier_distribution: TierBreakdown
  search_source_distribution: { baidu: number; sogou: number; wechat_mp: number }
  article_type_distribution: { report: number; opinion: number; pr: number; analysis: number }
  sentiment_distribution: { positive: number; neutral: number; negative: number }
  sentiment_overall: number | null
  sentiment_by_tier: TierBreakdownNullable

  cross_task_overlap: NewsSliceCrossTaskOverlap
  coverage_timeseries: NewsSliceCoverageDay[]
  sentiment_timeseries: NewsSliceSentimentDay[]
}

export interface NewsSliceEntity {
  name: string
  role: EntityRole
  mention_count: number
  source_count: number
  cross_task_count: number
  article_ids: number[]
  representative_article_ids: number[]
  sentiment_avg: number | null
  sentiment_weighted_by_tier: number | null
  sentiment_by_tier: TierBreakdownNullable
  top_quote_ids: number[]
}

export interface NewsSliceQuote {
  speaker: string
  speaker_role: SpeakerRole
  quote: string
  context: string
  article_id: number
  source_name: string
  source_tier: string
  published_at: string | null
}

export interface NewsSliceEventCluster {
  cluster_id: number
  article_ids: number[]
  article_count: number
  first_reported_at: string | null
  first_reporter: { source_name: string; source_tier: string } | null
  peak_date: string | null
  tier_weighted_score: number
  in_task_ids: number[]
  representative_article_ids: number[]
}

export interface NewsSliceMediaLandscape {
  source_pyramid: Array<{
    tier: TierKey
    article_count: number
    sentiment_avg: number | null
    top_source_names: string[]
    representative_articles: Array<{
      title: string
      article_id: number
      url: string
      source_name: string
    }>
  }>
  top_sources: Array<{ name: string; count: number; share: number }>
}

export interface NewsSliceCompetitivePlayer {
  name: string
  role: EntityRole
  tier_weighted_sov: number
  mention_count: number
  source_count: number
  cross_task_count: number
  sentiment_avg: number | null
  sentiment_by_tier: TierBreakdownNullable
  article_ids: number[]
  top_quote_ids: number[]
}

export interface NewsSliceCompetitive {
  players: NewsSliceCompetitivePlayer[]
  quote_share: Array<{ name: string; quote_count: number; official_quote_count: number }>
}

export interface NewsSlicePageSynthesis {
  briefing?: {
    headline?: string
    key_findings?: string[]
    risks?: string[]
  }
  event_titles?: Record<string, { title: string; dominant_frame: string }>
}

export interface NewsSliceResultData {
  descriptive: NewsSliceDescriptive
  entities?: NewsSliceEntity[]
  quotes?: NewsSliceQuote[]
  event_clusters?: NewsSliceEventCluster[]
  media_landscape?: NewsSliceMediaLandscape
  competitive?: NewsSliceCompetitive
  page_synthesis?: NewsSlicePageSynthesis
}

export interface NewsSliceStatsSummary {
  articles_total: number
  articles_filtered: number
  source_tier_distribution?: TierBreakdown
  sentiment_distribution?: { positive: number; neutral: number; negative: number }
  sentiment_overall?: number | null
  top_entities?: Array<{ name: string; mention_count: number }>
}

// ==================== Slice Types ====================

export interface NewsSlice {
  id: number
  name: string
  monitor_id: number
  included_task_ids: number[]
  /** 聚焦切片的主体品牌名（null = 大盘视角，无 target/competitor 区分） */
  subject: string | null
  /** 聚焦切片的竞品品牌名列表（subject 为 null 时应为空） */
  competitors: string[]
  status: string
  result_data: NewsSliceResultData | null
  stats: NewsSliceStatsSummary | null
  error_message: string | null
  user_id: number
  created_at: string
  updated_at: string
}

export interface NewsSliceCreate {
  name: string
  included_task_ids: number[]
  /** null = 大盘视角，不做 target/competitor 区分 */
  subject?: string | null
  competitors?: string[]
}

export interface NewsSliceWithRelations extends NewsSlice {
  monitor_name: string | null
  user_username: string | null
}

// ==================== Article Types ====================

export interface NewsArticle {
  id: number
  task_id: number
  url: string
  title: string
  snippet: string | null
  source_name: string
  source_tier: string
  // 'bing' 保留：历史文章（下线前的采集数据）仍可能带此值；新任务只会出 baidu/sogou/wechat_mp
  search_source: 'baidu' | 'sogou' | 'bing' | 'wechat_mp'
  author: string | null
  published_at: string | null
  image_url: string | null
  relevance: string | null
  sentiment: number | null
  article_type: string | null
  mentioned_entities: Array<{ name: string; role: string }> | null
  key_quotes: Array<{ speaker: string; quote: string }> | null
  summary: string | null
  created_at: string
  updated_at: string
}
