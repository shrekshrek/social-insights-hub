/**
 * 新闻监测模块类型定义
 */

export interface NewsMonitor {
  id: number
  name: string
  description: string | null
  owner_id: number
  aggregated_result: NewsAnalysisResult | null
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
  analysis_result: NewsAnalysisResult | null
  error_message: string | null
  created_by: number
  created_at: string
  updated_at: string
}

export interface NewsTaskWithRelations extends NewsTask {
  monitor_name: string | null
  creator_username: string | null
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

// ==================== Analysis Result Types ====================

export interface NewsAnalysisMeta {
  keywords: string
  articles_total: number
  articles_relevant?: number
  articles_crawled?: number
  articles_analyzed?: number
  source_tier_distribution?: { tier1: number; tier2: number; tier3: number }
}

export interface NewsAnalysisCoverage {
  media_coverage_index?: number
  intensity?: string
  trend?: string
  summary?: string
}

export interface NewsAnalysisSentiment {
  overall?: number
  distribution?: { positive: number; neutral: number; negative: number }
  by_source_tier?: { tier1: number; tier2: number; tier3: number }
}

export interface NewsNarrative {
  theme: string
  article_count: number
  sentiment: number
  summary: string
  representative_titles?: string[]
}

export interface NewsEntity {
  name: string
  role: string
  mention_count: number
  source_count: number
  sentiment: number
  key_claims?: string[]
}

export interface NewsCompetitiveLandscape {
  positioning_summary?: string
  entities_mentioned?: Array<{ name: string; mentions: number; sentiment: number }>
}

export interface NewsKeyQuote {
  speaker: string
  quote: string
  source_name?: string
  context?: string
}

export interface NewsAnalysisResult {
  meta?: NewsAnalysisMeta
  articles_summary?: Array<Record<string, unknown>>
  coverage?: NewsAnalysisCoverage
  sentiment?: NewsAnalysisSentiment
  narratives?: NewsNarrative[]
  entities?: NewsEntity[]
  competitive_landscape?: NewsCompetitiveLandscape
  key_quotes?: NewsKeyQuote[]
}

// ==================== Monitor 聚合类型 ====================

export interface MonitorAggregatedStats {
  articles_total: number
  articles_relevant: number
  source_tier_distribution: { tier1: number; tier2: number; tier3: number }
  sentiment_distribution: { positive: number; neutral: number; negative: number }
  sentiment_overall: number | null
  top_entities: Array<{ name: string; mention_count: number }>
  search_source_distribution: { baidu: number; duckduckgo: number }
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
  search_source: 'baidu' | 'duckduckgo'
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
