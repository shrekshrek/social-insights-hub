/**
 * 项目快照分析 - 类型定义
 * 对应后端 Step 3 分层指标计算输出
 */

// ===========================================
// 基础类型 (Base Types)
// ===========================================

/** 原话记录 */
export interface OriginalTerm {
  text: string
  count: number
}

/** 来源任务引用 */
export interface SourceTask {
  task_id: number
  mentions: number
}

/** 帖子引用 (用于追溯) */
export interface PostRef {
  task_id: number
  post_id: number
}

/** 平台分布 */
export type PlatformDistribution = Record<string, number>

/** 关键词分布 */
export type KeywordDistribution = Record<string, number>

// ===========================================
// 实体与话题 (Entities & Topics)
// ===========================================

/** 实体属性项 (features/issues/expectations 等) */
export interface EntityAttributeItem {
  text: string
  mentions: number
  original_terms?: OriginalTerm[]
  post_ids_sample?: PostRef[]
  platform_distribution?: PlatformDistribution
  keyword_distribution?: KeywordDistribution
}

/** 归一化后的实体 */
export interface AlignedEntity {
  name: string
  role?: 'Target' | 'Competitor' | 'Context'
  type?: string
  parent?: string
  heat: number
  mentions: number
  score: number
  sentiment?: number
  sentiment_distribution?: {
    positive: number
    negative: number
    neutral: number
  }
  original_terms?: OriginalTerm[]
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
  platform_distribution?: PlatformDistribution
  keyword_distribution?: KeywordDistribution
  top_features?: EntityAttributeItem[]
  top_issues?: EntityAttributeItem[]
  top_expectations?: EntityAttributeItem[]
  top_audience?: EntityAttributeItem[]
  top_scenarios?: EntityAttributeItem[]
  top_market_factors?: EntityAttributeItem[]
  top_competitors?: EntityAttributeItem[]
}

/** 归一化后的话题/观点 */
export interface AlignedTopic {
  name: string
  category?: string
  heat: number
  mentions: number
  score: number
  sentiment?: number
  sentiment_distribution?: {
    positive: number
    negative: number
    neutral: number
  }
  original_terms?: OriginalTerm[]
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
  platform_distribution?: PlatformDistribution
  keyword_distribution?: KeywordDistribution
}

// ===========================================
// Landscape Layer (大盘层)
// ===========================================

/** SOV 排行榜项 */
export interface SOVRankingItem {
  name: string
  role?: string
  heat: number
  mentions: number
  score: number
  /** 热度份额 (%) */
  share: number
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

/** 集团军声量项 */
export interface GroupShareItem {
  parent: string
  total_heat: number
  total_mentions: number
  share: number
  members: Array<{
    name: string
    heat: number
    mentions: number
    contribution: number
  }>
}

/** 平台阵地 DNA 项 */
export interface PlatformDNAItem {
  entity: string
  platforms: Record<string, number>
}

/** 行业象限数据点 (实体级) */
export interface IndustryQuadrantPoint {
  name: string
  role?: string
  heat: number
  sentiment: number
  mentions: number
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

/** Landscape 层完整数据 */
export interface LandscapeLayer {
  overview?: {
    total_volume?: number
    global_sentiment?: number
    platform_volume?: PlatformDistribution
    keyword_volume?: KeywordDistribution
  }
  /** SOV 排行榜 */
  sov_ranking?: SOVRankingItem[]
  /** 集团军声量 */
  group_share?: GroupShareItem[]
  /** 平台阵地 DNA */
  platform_dna?: PlatformDNAItem[]
  /** 行业象限 (实体级 Heat x Sentiment) */
  industry_quadrant?: IndustryQuadrantPoint[]
  freshness?: Record<string, unknown>
}

// ===========================================
// Topic Layer (话题层)
// ===========================================

/** 话题雷达项 */
export interface TopicRadarItem {
  name: string
  category?: string
  heat: number
  sentiment: number
  mentions: number
  original_terms?: OriginalTerm[]
  platform_distribution?: PlatformDistribution
  keyword_distribution?: KeywordDistribution
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
  coverage?: number
  platform_coverage?: number
  keyword_coverage?: number
}

/** Topic 层完整数据 */
export interface TopicLayer {
  /** 话题分类聚合 */
  topic_aspects?: Array<{
    category: string
    heat: number
    sentiment: number
    mention_count?: number
    top_keywords?: string[]
    platform_distribution?: PlatformDistribution
    keyword_distribution?: KeywordDistribution
  }>
  /** 话题雷达：痛点/爽点/争议点 */
  topic_radar?: {
    pains?: TopicRadarItem[]
    gains?: TopicRadarItem[]
    controversies?: TopicRadarItem[]
  }
  /** 未被满足的需求 */
  unmet_needs?: TopicRadarItem[]
}

// ===========================================
// Focus Layer (聚焦层) - 条件触发
// ===========================================

/** SWOT 矩阵项 */
export interface SWOTItem {
  dimension: string
  mentions: number
  sentiment: number
  original_terms?: OriginalTerm[]
}

/** SWOT 矩阵 */
export interface SWOTMatrix {
  strengths: SWOTItem[]
  weaknesses: SWOTItem[]
  opportunities: SWOTItem[]
  threats: SWOTItem[]
}

/** 产品线健康度项 */
export interface ProductLineHealthItem {
  name: string
  heat: number
  mentions: number
  /** 对 Target 总声量的贡献度 (%) */
  contribution: number
  sentiment: number
  /** Top 1 痛点 */
  top_pain?: string
  platform_distribution?: PlatformDistribution
  keyword_distribution?: KeywordDistribution
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

/** 平台剪刀差项 */
export interface PlatformScissorsItem {
  platform: string
  subject_share: number
  industry_avg_share: number
  gap: number
}

/** Gap 分析项 */
export interface GapAnalysisItem {
  dimension: string
  competitor_sentiment: number
  competitor_mentions: number
  subject_sentiment?: number
  subject_mentions?: number
}

/** Focus 层完整数据 */
export interface FocusLayer {
  /** SWOT 矩阵 */
  swot?: SWOTMatrix
  /** 产品线健康度 */
  product_line_health?: ProductLineHealthItem[]
  /** 平台剪刀差 */
  platform_scissors?: PlatformScissorsItem[]
  /** Gap 分析 */
  gap_analysis?: GapAnalysisItem[]
}

// ===========================================
// 完整快照结构
// ===========================================

/** 快照元数据 */
export interface SnapshotMeta {
  project_id: number
  generated_at: string
  subject?: string | null
  competitors?: string[]
  weights_used?: Record<string, number>
  scope?: Record<string, unknown>
}

/** 快照基础数据 (归一化后) */
export interface SnapshotFoundation {
  dedup_stats?: Record<string, unknown>
  aligned_entities?: AlignedEntity[]
  aligned_topics?: AlignedTopic[]
}

/** 分层分析结果 */
export interface SnapshotLayers {
  landscape?: LandscapeLayer
  topic?: TopicLayer
  focus?: FocusLayer | null
}

/** AI 报告 */
export interface SnapshotReport {
  content?: string
}

export interface SnapshotReports {
  landscape_report?: SnapshotReport | null
  topic_report?: SnapshotReport | null
  focus_report?: SnapshotReport | null
}

/** Stage2 处理状态 */
export interface Stage2Status {
  status: 'completed' | 'processing' | 'failed' | 'skipped'
  started_at?: string
  updated_at?: string
  generated_at?: string
  llm?: { used?: boolean }
  steps?: Record<string, {
    status: 'pending' | 'processing' | 'completed' | 'failed'
    llm_used?: boolean
  }>
  category_alignment?: {
    used?: boolean
    category_map?: Record<string, string>
  }
  alias_normalization?: {
    entities?: {
      used?: boolean
      before_count?: number
      after_count?: number
      entity_mapping?: Record<string, string>
    }
    topics?: {
      used?: boolean
      before_count?: number
      after_count?: number
      topic_mapping_by_category?: Record<string, Record<string, string>>
    }
  }
  drivers?: {
    min_cell_mentions?: number
    dimensions_top?: string[]
    entity_matrix?: Array<{
      entity: string
      dimensions: Record<string, {
        mentions: number
        pos: number
        neg: number
        sentiment: number
      }>
    }>
  }
}

/** Stage3 处理状态 */
export interface Stage3Status {
  status: 'pending' | 'processing' | 'completed' | 'failed'
  started_at?: string
  updated_at?: string
  generated_at?: string
  llm?: { used?: boolean }
  error?: string
}

/** 快照结果数据 */
export interface ProjectSnapshotResultData {
  meta?: SnapshotMeta
  foundation?: SnapshotFoundation
  layers?: SnapshotLayers
  reports?: SnapshotReports
  stage2?: Stage2Status
  stage3?: Stage3Status
}

/** 项目快照完整结构 */
export interface ProjectSnapshot {
  id: number
  name: string | null
  project_id: number
  user_id: number
  included_task_ids: number[]
  result_data: ProjectSnapshotResultData
  created_at: string
  updated_at: string
}
