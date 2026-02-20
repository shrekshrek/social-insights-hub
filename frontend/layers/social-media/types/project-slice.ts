/**
 * 项目切片洞察 - 类型定义
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
  /** 推广内容情感（spam_score >= 6.0 的帖子） */
  promo_sentiment?: number
  /** 有机内容情感（spam_score < 6.0 的帖子） */
  organic_sentiment?: number
  sentiment_distribution?: {
    positive: number
    negative: number
    neutral: number
  }
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
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
  organic_heat?: number
  promo_heat?: number
  mentions: number
  score: number
  sentiment?: number
  sentiment_distribution?: {
    positive: number
    negative: number
    neutral: number
  }
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
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
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

/** 集团军声量项 */
export interface GroupShareItem {
  parent: string
  total_heat: number
  total_mentions: number
  share: number
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  members: Array<{
    name: string
    heat: number
    mentions: number
    contribution: number
    spam_distribution?: {
      high_spam: { total: number; post: number; comment: number }
      low_spam: { total: number; post: number; comment: number }
    }
  }>
}

/** 平台阵地 DNA 项 */
export interface PlatformDNAItem {
  name: string
  role?: string
  total_mentions: number
  total_organic_mentions?: number
  total_promo_mentions?: number
  platform_shares: Record<string, number>
  organic_platform_shares?: Record<string, number>
  promo_platform_shares?: Record<string, number>
}

/** 行业象限数据点 (实体级) */
export interface IndustryQuadrantPoint {
  name: string
  role?: string
  heat: number
  sentiment: number
  mentions: number
  /** 有机内容情感（spam_score < 6.0 的帖子） */
  organic_sentiment?: number
  /** 推广内容情感（spam_score >= 6.0 的帖子） */
  promo_sentiment?: number
  /** 有机内容热度（spam_score < 6.0 的帖子热度总和） */
  organic_heat?: number
  /** 推广内容热度（spam_score >= 6.0 的帖子热度总和） */
  promo_heat?: number
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
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
    /** 全量实体的有机热度总和（用于计算全局口径的有机 SOV 份额） */
    total_organic_heat?: number
    /** 全量实体的推广热度总和（用于计算全局口径的推广 SOV 份额） */
    total_promo_heat?: number
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
  organic_heat?: number
  promo_heat?: number
  sentiment: number
  sentiment_distribution?: {
    positive: number
    negative: number
    neutral: number
  }
  mentions: number
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
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
    organic_heat?: number
    promo_heat?: number
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
  target_sentiment: number
  competitor_sentiment: number
  target_mentions: number
  competitor_mentions: number
  delta: number
  /** 有机内容分层情感（后端提供时使用，否则前端退回占比视图） */
  target_organic_sentiment?: number
  target_promo_sentiment?: number
  competitor_organic_sentiment?: number
  competitor_promo_sentiment?: number
  target_spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  competitor_spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  post_ids_sample?: PostRef[]
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
  /** 有机内容情感（spam_score < 6.0 的帖子） */
  organic_sentiment?: number
  /** 推广内容情感（spam_score >= 6.0 的帖子） */
  promo_sentiment?: number
  /** Top 1 痛点 */
  top_pain?: string
  platform_distribution?: PlatformDistribution
  keyword_distribution?: KeywordDistribution
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

/** 平台剪刀差项 */
export interface PlatformScissorsItem {
  platform: string
  subject_mentions: number
  industry_mentions: number
  subject_share: number
  industry_share: number
  delta: number
  /** 主体在该平台的有机/推广提及量 */
  subject_organic_mentions?: number
  subject_promo_mentions?: number
  /** 行业在该平台的有机/推广提及量 */
  industry_organic_mentions?: number
  industry_promo_mentions?: number
}

/** 平台剪刀差汇总 */
export interface PlatformScissorsData {
  subject_total_mentions: number
  industry_total_mentions: number
  by_platform: PlatformScissorsItem[]
  /** 主体/行业有机推广总量（用于跨平台份额归一化） */
  subject_total_organic_mentions?: number
  subject_total_promo_mentions?: number
  industry_total_organic_mentions?: number
  industry_total_promo_mentions?: number
}

/** Gap 分析项 */
export interface GapAnalysisItem {
  dimension: string
  target_sentiment: number
  competitor_sentiment: number
  target_mentions: number
  competitor_mentions: number
  delta: number
  target_spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  competitor_spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  post_ids_sample?: PostRef[]
  original_terms?: OriginalTerm[]
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
// 完整切片结构
// ===========================================

/** 切片元数据 */
export interface SliceMeta {
  project_id: number
  generated_at: string
  subject?: string | null
  competitors?: string[]
  weights_used?: Record<string, number>
  scope?: Record<string, unknown>
}

/** 切片基础数据 (归一化后) */
export interface SliceFoundation {
  dedup_stats?: Record<string, unknown>
  aligned_entities?: AlignedEntity[]
  aligned_topics?: AlignedTopic[]
  /** 程序化驱动因素矩阵（Stage2 衍生分析写入，Stage3 LLM 报告消费） */
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

/** 分层分析结果 */
export interface SliceLayers {
  landscape?: LandscapeLayer
  topic?: TopicLayer
  focus?: FocusLayer | null
}

/** AI 报告 */
export interface SliceReport {
  content?: string
}

export interface SliceReports {
  landscape_report?: SliceReport | null
  topic_report?: SliceReport | null
  focus_report?: SliceReport | null
}

/** Stage1 状态（同步，切片创建时写入） */
export interface Stage1Status {
  status: 'completed'
  completed_at?: string
  entities_count?: number
  topics_count?: number
}

/** Stage2 状态（异步 Celery：实体归一 / 观点归一 / 程序化衍生分析） */
export interface Stage2Status {
  status: 'completed' | 'processing' | 'failed' | 'skipped'
  started_at?: string
  updated_at?: string
  generated_at?: string
  celery_task_id?: string
  llm?: { used?: boolean }
  steps?: Record<string, {
    status: 'pending' | 'processing' | 'completed' | 'failed'
    llm_used?: boolean
    job_id?: number
  }>
  jobs?: Record<string, number>
  category_alignment?: {
    used?: boolean
    category_map?: Record<string, string>
    topic_aspects_aligned?: Record<string, unknown>[]
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
}

/** Stage3 状态（异步：LLM 报告生成，唯一追踪器） */
export interface Stage3Status {
  status: 'pending' | 'processing' | 'completed' | 'failed'
  job_id?: number
  started_at?: string
  updated_at?: string
  generated_at?: string
  llm?: { used?: boolean }
  error?: string
}

/** 流水线执行状态（stage1 同步 + stage2/3 异步） */
export interface PipelineStatus {
  stage1?: Stage1Status
  stage2?: Stage2Status
  stage3?: Stage3Status
}

/** 切片结果数据 */
export interface ProjectSliceResultData {
  meta?: SliceMeta
  foundation?: SliceFoundation
  layers?: SliceLayers
  reports?: SliceReports
  pipeline?: PipelineStatus
}

/** 项目切片完整结构 */
export interface ProjectSlice {
  id: number
  name: string | null
  project_id: number
  user_id: number
  included_task_ids: number[]
  result_data: ProjectSliceResultData
  created_at: string
  updated_at: string
}
