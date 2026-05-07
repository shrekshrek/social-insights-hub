/**
 * 策略模块 - TypeScript 类型定义
 *
 * 对齐后端 strategies/schemas.py (Strategy Research Engine)
 */

import type { PaginatedResponse } from '~/types/common'

// ==================== 策略状态 ====================

export type StrategyStatus =
  | 'draft'
  | 'planned'
  | 'probing'
  | 'collecting'
  | 'ready'
  // campaign_strategy 产出路径
  | 'insight_done'
  | 'brand_role_done'
  // market_report 产出路径
  | 'agenda_map_done'
  | 'landscape_done'
  | 'completed'

// ==================== 产出类型 ====================

/**
 * 产出路径（两条独立路径）
 * - campaign_strategy: 消费者洞察主导（依赖 social_media 主源）
 *     → 第 1 层 Insight → 第 2 层 Brand Role → 第 3 层 Big Idea
 * - market_report:  媒体视角主导（依赖 news_media 主源）
 *     → 第 1 层 Agenda Map → 第 2 层 Landscape → 第 3 层 Strategic Brief
 * - full_strategy:  双渠道综合（依赖 social_media + news_media）
 *     → Agenda Map → Landscape → Insight → Brand Role → Big Idea
 */
export type OutputType = 'campaign_strategy' | 'market_report' | 'full_strategy'

/** 主数据源：直接输入到 prompt 的主数据通道 */
export type PrimarySource = 'social_media' | 'news_media'

// ==================== 数据来源（两层模型）====================

/**
 * Phase 结果中的 data_provenance 字段，记录本次生成实际使用的数据来源。
 * 两层结构：primary 是直接输入到 prompt 的主数据，research 是行业研究第三视角。
 * 对齐后端 _build_data_provenance 函数的输出结构。
 */
export interface DataProvenance {
  primary: {
    channel: PrimarySource
    social_media_slice_count: number
    news_media_slice_count: number
  }
  research: {
    industry_research: boolean
  }
}

// ==================== chain_inputs（section 级溯源）====================

/**
 * 切片引用（chain_inputs 中的 social_slices / news_slices 元素）
 * monitor_id 用于前端跳详情页（社媒 slice 路由需要 monitor_id）
 */
export interface SliceRef {
  id: number
  name: string | null
  monitor_id: number | null
}

/**
 * 研究任务引用（chain_inputs 中的 research_findings / creative_references 元素）
 */
export interface ResearchRef {
  id: number
  profile: 'industry' | 'creative'
}

/**
 * Phase 结果中的 chain_inputs 字段：本次 LLM 调用 prompt 中实际注入的上游数据 ID 清单。
 *
 * 与 LLM 输出无关，由 orchestrator 在调用前确定，无幻觉风险。
 * 用于前端 section 级"查看原始数据"drawer，反查上游切片 / 研究产出。
 *
 * 对齐后端 _build_chain_inputs 函数的输出结构。
 */
export interface ChainInputs {
  social_slices: SliceRef[]
  news_slices: SliceRef[]
  research_findings: ResearchRef[]
  creative_references: ResearchRef[]
}

// ==================== Brand Brief ====================

export interface ChannelPlanItem {
  type: string
  available: boolean
  solvable: string[]
  unsolvable: string[]
  channel_brief: string
}

export interface AudienceSegment {
  label: string
  description?: string
  behavior_signals?: string[] | null
}

export interface BrandBrief {
  subject: string
  analysis_goal: string
  constraints?: string | null
  channel_plan?: ChannelPlanItem[] | null

  // 策略 Brief Framework 字段（brief 未提及时为 null/undefined）
  target_audiences?: AudienceSegment[] | null
  audience_insights?: string[] | null
  core_propositions?: string[] | null
  competitors?: string[] | null
}

// ==================== 切片摘要 ====================

export type SliceChannel = 'social' | 'news'

export interface SliceSummary {
  slice_id: number
  slice_name: string | null
  monitor_id: number
  monitor_name: string
  channel: SliceChannel
  status: string
}

// ==================== 研究设计 ====================

export interface ResearchQuestion {
  id: string
  question: string
  dimension: string
  priority: string
}

export interface DataPlanItem {
  dimension_name: string
  keywords: string[]
  platforms: string[]
  /** 数据渠道：social_media（默认）| news_media */
  channel?: 'social_media' | 'news_media'
  /** 新闻维度专属：是否额外搜索微信公众号（通过搜狗微信入口） */
  enable_wechat_mp?: boolean
  rationale?: string
  /** 该维度数据采集服务的 research_question id 列表 */
  question_ids?: string[]
}

export interface SliceBlueprintItem {
  name: string
  mode?: string
  subject?: string
  competitors?: string[]
  source_dimensions: string[]
  serves_questions?: string[]
}

export interface ResearchDesignAdvisory {
  code: string
  severity: 'warning'
  message: string
}

export interface ResearchDesign {
  understanding_summary: string
  research_questions: ResearchQuestion[]
  data_plan: DataPlanItem[]
  slice_blueprint: SliceBlueprintItem[]
  primary_sources: PrimarySource[]
  output_type: OutputType
  output_type_rationale: string
  advisories?: ResearchDesignAdvisory[]
}

// ==================== 探测验证 ====================

export interface SocialProbeTaskStatus {
  task_id: number
  keyword: string
  platform: string
  status: string
  /** 是否已成功完成可供审查；failed 任务恒为 false（强制等待 retry 或人工删除）*/
  has_analysis: boolean
  /** 任务最近更新时间 ISO string，用于展示"失败于 X 分钟前" */
  last_updated_at: string | null
}

export interface ProbeAssessment {
  task_id: number
  keyword: string
  platform: string
  verdict: 'pass' | 'fail'
  note: string
  suggested_keyword?: string | null
  suggestion_reason?: string | null
  entity_match?: boolean
  /** 识别到的 target 实体是否命中 expected_subjects（slice_blueprint 派生） */
  subject_match?: boolean
  /** 识别到的 competitor 实体是否命中 expected_competitors */
  competitor_match?: boolean
  /** 与 RQ 相关话题去重后的源帖数（防单帖伪相关） */
  relevant_source_posts?: number
}

export interface RefinementSuggestion {
  task_id: number
  original_keyword: string
  suggested_keyword: string
  platform: string
  reason: string
}

export interface ChannelSummary {
  total: number
  fail_count: number
  channel_verdict: 'all_pass' | 'partial_pass' | 'all_fail'
  note: string
}

export interface ProbeReviewResult {
  assessments: ProbeAssessment[]
  overall_verdict: 'all_pass' | 'partial_pass' | 'fail'
  channel_summary?: Record<string, ChannelSummary>
  refinement_suggestions: RefinementSuggestion[]
}

export interface NewsProbeTaskStatus {
  task_id: number
  keyword: string
  dimension: string
  status: string
  completed: boolean
  failed: boolean
  articles_count: number
}

export interface ResearchAgentStatus {
  has_task: boolean
  status: string
  task_id: number | null
}

export interface ProbeStatusResponse {
  all_analyzed: boolean
  social_tasks: SocialProbeTaskStatus[]
  news_tasks: NewsProbeTaskStatus[]
  analyzed_count: number
  total_count: number
  probe_review_result: ProbeReviewResult | null
  strategy: Strategy | null
}

// ==================== 数据就绪 ====================

export interface CollectionTaskStatus {
  task_id: number
  keyword: string
  platform: string
  status: string
  posts_count: number
  comments_count: number
  has_analysis: boolean
}

export interface NewsCollectionTaskStatus {
  task_id: number
  keyword: string
  dimension: string
  status: string
  articles_count: number
  has_analysis: boolean
}

export type QuestionCoverageStatus = 'covered' | 'partial' | 'uncovered'

export interface QuestionCoverage {
  question_id: string
  question: string
  /** 三态判定：covered（充分）/ partial（部分）/ uncovered（无支撑） */
  status: QuestionCoverageStatus
  covered_by: string[]
  /** 量化证据摘要（含 mentions / sources 数字） */
  evidence_summary: string
}

export interface SliceAdjustmentSuggestion {
  slice_name: string
  issue: string
  suggestion: string
}

export interface CoverageCheckResult {
  question_coverage: QuestionCoverage[]
  overall_ready: boolean
  /** 跨 RQ 共性诊断（如"slice X 数据稀疏，影响 rq2/rq3"） */
  warnings: string[]
  data_highlights: string[]
  slice_adjustments: SliceAdjustmentSuggestion[]
}

export interface CollectionStatusResponse {
  all_completed: boolean
  all_analyzed: boolean
  slices_created: boolean
  tasks: CollectionTaskStatus[]
  news_tasks: NewsCollectionTaskStatus[]
  completed_count: number
  total_count: number
  coverage_check_result: CoverageCheckResult | null
  industry_research: ResearchAgentStatus
  creative_research: ResearchAgentStatus
  strategy: Strategy | null
}

export interface DataOverviewResponse {
  slices: SliceSummary[]
  coverage_check_result: CoverageCheckResult | null
  strategy: Strategy
}

// ==================== 策略 ====================

/** brand_strategy 多分支条目：每个 insight tension 一条，独立 brand_role + big_idea 路径 */
export interface BrandStrategyBranch {
  tension_id: number
  tension_summary: string
  brand_role: Record<string, unknown> | null
  big_idea: Record<string, unknown> | null
  selected: boolean
  /** pending | brand_role_done | big_idea_done | failed */
  status: string
  /** 失败时填充失败原因 */
  error_message?: string
}

export interface Strategy {
  id: number
  name: string
  status: StrategyStatus
  brand_brief: BrandBrief | null

  // ① 研究设计
  research_design: ResearchDesign | null

  // ② 探测验证
  probe_review_result: ProbeReviewResult | null
  probe_round: number

  // ③ 数据就绪
  coverage_check_result: CoverageCheckResult | null

  // ④ 产出生成
  output_type: OutputType | null
  // campaign_strategy 路径：
  //   第 1 层 insight（单一） → 第 2/3 层多分支（每个 tension 独立 brand_role + big_idea 路径）
  insight_result: Record<string, unknown> | null
  brand_strategy_branches: BrandStrategyBranch[] | null
  // market_report 路径：第 1 层 → 第 2 层 → 第 3 层
  agenda_map_result: Record<string, unknown> | null
  landscape_result: Record<string, unknown> | null
  strategic_brief_result: Record<string, unknown> | null

  // 关联
  social_monitor_id: number | null
  news_monitor_id: number | null
  slices: SliceSummary[]

  // 参与者
  participant_ids: number[]
  participant_usernames: string[]

  // 元信息
  user_id: number
  user_username: string
  created_at: string
  updated_at: string
}

export interface StrategyListItem {
  id: number
  name: string
  status: StrategyStatus
  slice_count: number
  user_id: number
  user_username: string
  created_at: string
  updated_at: string
}

export type StrategyListResponse = PaginatedResponse<StrategyListItem>

// ==================== 请求体 ====================

export interface StrategyCreate {
  name: string
  brand_brief?: BrandBrief | null
}

export interface StrategyUpdate {
  name?: string
  brand_brief?: BrandBrief | null
}

export interface ConfirmResearchRequest {
  research_design: Record<string, unknown>
  /** 用户显式选择的产出路径（campaign_strategy 需含 social_media 维度，market_report 需含 news_media 维度） */
  output_type: OutputType
  notes_per_task?: number
}

export interface ConfirmResearchResponse {
  created_monitor_id: number
  created_task_count: number
  created_news_task_count: number
  partial_errors: string[]
  strategy: Strategy
}

/**
 * 社媒 probe 关键词调整项，三种操作：
 * - 替换：task_id + new_keyword
 * - 移除：task_id + new_keyword=null
 * - 新增：task_id=null + new_keyword + dimension
 */
export interface SocialRefinementItem {
  task_id: number | null
  new_keyword: string | null
  platform: string
  dimension?: string | null
}

/** 新闻 probe 关键词调整项（与 SocialRefinementItem 对齐，无 platform 字段） */
export interface NewsRefinementItem {
  task_id: number | null
  new_keyword: string | null
  dimension?: string | null
}

export interface RefineProbeRequest {
  social_refinements: SocialRefinementItem[]
  news_refinements: NewsRefinementItem[]
}

export interface RefineProbeResponse {
  removed_social_task_ids: number[]
  created_social_task_ids: number[]
  removed_news_task_ids: number[]
  created_news_task_ids: number[]
  probe_round: number
  strategy: Strategy
}

export interface ApproveProbeResponse {
  approved_task_count: number
  strategy: Strategy
}

export interface AdjustSliceItem {
  slice_id: number
  name?: string | null
  subject?: string | null
  competitors?: string[] | null
}

export interface AdjustSlicesRequest {
  adjustments: AdjustSliceItem[]
}

// ==================== campaign_strategy 路径结果类型 ====================

export interface StageEvidence {
  type: string
  description: string
  source?: string
}

export interface SocialTension {
  statement: string
  conventional_wisdom?: string
  data_reality?: string
  /** 后端 prompt 严格枚举 high/medium/low；老数据可能为空 */
  confidence?: 'high' | 'medium' | 'low'
  evidence?: StageEvidence[]
  /** 该 tension 回应的 research_questions id 列表（如 ["rq1", "rq3"]）。
   *  prompt v2026.05+ 必填；老 insight 结果无此字段 */
  research_questions_addressed?: string[]
}

export interface BrandOpportunity {
  statement: string
  why_non_obvious?: string
  related_tensions?: number[]
  evidence?: StageEvidence[]
  /** 该 opportunity 回应的 research_questions id 列表（同 SocialTension） */
  research_questions_addressed?: string[]
}

/** campaign_strategy 第 1 层 Insight: Social Tension + Brand Opportunity */
export interface InsightResult {
  social_tensions: SocialTension[]
  brand_opportunities: BrandOpportunity[]
  data_provenance?: DataProvenance
  chain_inputs?: ChainInputs
}

export interface BrandSocialRole {
  statement: string
  elaboration?: string
  evidence?: StageEvidence[]
}

export interface SocialStrategy {
  statement: string
  core_message?: string
  rhythm?: string
  evidence?: StageEvidence[]
}

/** campaign_strategy 第 2 层 Brand Role: Brand Social Role + Social Strategy */
export interface BrandRoleResult {
  brand_social_role: BrandSocialRole
  social_strategy: SocialStrategy
  data_provenance?: DataProvenance
  chain_inputs?: ChainInputs
}

export interface BigIdea {
  statement: string
  elaboration?: string
  tension_echo?: string
  evidence?: StageEvidence[]
}

export interface ContentPillar {
  name: string
  description?: string
  strategic_role?: 'anchor' | 'leverage' | 'conversion' | 'disruption'
  reference_examples?: string[]
}

export interface ContentStrategy {
  pillars: ContentPillar[]
  evidence?: StageEvidence[]
}

/** campaign_strategy 第 3 层 Big Idea: Big Idea + Content Strategy */
export interface BigIdeaResult {
  big_idea: BigIdea
  content_strategy: ContentStrategy
  data_provenance?: DataProvenance
  chain_inputs?: ChainInputs
}

// ==================== market_report 路径结果类型 ====================

// —— 第 1 层 Agenda Map: 媒体议程图 ——

export interface NarrativeSupportingSources {
  tier1?: number
  tier2?: number
  tier3?: number
  wechat_mp?: number
}

/** 与 backend agenda_map_chain prompt 对齐：source / source_tier 是 BE 实际字段名 */
export interface NarrativeRepresentativeVoice {
  quote: string
  speaker?: string
  source: string
  /** tier1 | tier2 | tier3 | wechat_mp */
  source_tier: string
}

export interface NarrativeMapItem {
  theme: string
  framing: string
  /** [-2, 2] 加权情感；缺失时为 null */
  sentiment: number | null
  heat_rank: number
  supporting_sources: NarrativeSupportingSources
  representative_voices: NarrativeRepresentativeVoice[]
  credibility: 'high' | 'medium' | 'low'
  /** 跨切片证据：佐证该 narrative 的 slice 名称列表 */
  cross_slice_evidence?: string[]
}

/** 议程博弈：tier 间分歧 / 正反争论的议题（与 backend agenda_map_chain prompt 对齐） */
export interface AgendaBattle {
  contested_topic: string
  camps: Array<{
    stance: string
    /** 支持该立场的 source_tier 列表（如 ["tier1", "tier2"]） */
    supporting_tiers: string[]
    /** 该立场的代表性引述（短句） */
    sample_quotes: string[]
  }>
  /** 该分歧对品牌/行业的含义 */
  implication: string
}

/** 媒体声量模式：三种子类型 schema 各异（与 backend agenda_map_chain prompt 对齐） */
export interface AuthoritativeConsensusItem {
  topic: string
  stance: string
  evidence: string
}

export interface IndustryDebateItem {
  topic: string
  positions: string[]
}

export interface EmergingNarrativeItem {
  topic: string
  why_unverified: string
  /** tier1 | tier2 | tier3 | wechat_mp */
  originating_tier: string
}

export interface MediaVoicePatterns {
  authoritative_consensus: AuthoritativeConsensusItem[]
  industry_debate: IndustryDebateItem[]
  emerging_narratives: EmergingNarrativeItem[]
}

/** 注意力缺口（与 backend agenda_map_chain prompt 对齐） */
export interface AttentionGapItem {
  topic: string
  risk_or_opportunity: 'risk' | 'opportunity'
  why_matters: string
}

/** market_report 第 1 层 Agenda Map: 媒体议程图 */
export interface AgendaMapResult {
  media_landscape_summary: string
  narrative_map: NarrativeMapItem[]
  agenda_battles: AgendaBattle[]
  media_voice_patterns: MediaVoicePatterns
  attention_gaps: AttentionGapItem[]
  data_provenance?: DataProvenance
  chain_inputs?: ChainInputs
}

// —— 第 2 层 Landscape: 竞争格局 ——

export interface EvidenceQuote {
  quote: string
  source?: string
  speaker?: string
}

export interface CompetitivePlayer {
  name: string
  role: 'target' | 'competitor' | 'context'
  media_sov_pct: number
  /** [-2, 2] 加权情感；0-source 玩家为 null */
  media_sentiment: number | null
  source_count: number
  narrative_position: string
  /** 媒体围绕该玩家的代表性论述（2-3 条要点列表） */
  key_claims?: string[]
  evidence_quote?: string | EvidenceQuote
}

/** 定位轴语义：label = 轴名，low/high = 两端语义 */
export interface PositioningAxis {
  label: string
  low: string
  high: string
}

/** 定位图（与 backend landscape_chain prompt 对齐） */
export interface PositioningMap {
  x_axis: PositioningAxis
  y_axis: PositioningAxis
  /** 为何选择这两条轴 */
  rationale: string
  /** 玩家定位坐标，x/y ∈ [-1, 1] */
  positions: Array<{
    player: string
    x: number
    y: number
    /** 定位到该象限的证据 */
    rationale: string
  }>
}

/** 话语权博弈阵营条目 */
export interface DiscourseBattleCamp {
  player: string
  stance: string
}

/** 话语权博弈（与 backend landscape_chain prompt 对齐） */
export interface DiscourseBattle {
  /** 关联 agenda_map 的 contested_topic */
  battle: string
  leaders: DiscourseBattleCamp[]
  challengers: DiscourseBattleCamp[]
  /** momentum 方向："向 leaders" / "向 challengers" / "stable" */
  shift_direction: string
  /** 支持该判断的关键证据 */
  evidence: string
}

/** momentum 条目：gainers / losers 共用结构 */
export interface MomentumItem {
  player: string
  signal: string
}

/** 结构性变化条目 */
export interface StructuralShiftItem {
  shift: string
  implication: string
}

export interface MarketDynamics {
  momentum_gainers: MomentumItem[]
  momentum_losers: MomentumItem[]
  structural_shifts: StructuralShiftItem[]
}

/** market_report 第 2 层 Landscape: 竞争格局 + 话语权 */
export interface LandscapeResult {
  competitive_summary: string
  players: CompetitivePlayer[]
  positioning_map: PositioningMap
  discourse_battles: DiscourseBattle[]
  market_dynamics: MarketDynamics
  data_provenance?: DataProvenance
  chain_inputs?: ChainInputs
}

// —— 第 3 层 Strategic Brief: 战略简报 ——

export interface StrategicPriority {
  priority: string
  rationale: string
  answers_questions: string[]
  evidence_refs: string[]
  actions: string[]
  success_metric?: string
}

export interface MarketOpportunity {
  opportunity: string
  why_now: string
  entry_path: string
  evidence_refs: string[]
}

export interface RiskAndThreat {
  risk: string
  likelihood: 'high' | 'medium' | 'low'
  source: string
  mitigation: string
}

export interface RecommendedPositioning {
  statement: string
  target_position: {
    x_axis: string
    y_axis: string
    direction: string
  }
  differentiation_logic: string
  proof_points: Array<{
    claim: string
    agenda_map_narrative_ref: string
  }>
}

/** market_report 第 3 层 Strategic Brief: 战略简报（只消费 Agenda Map + Landscape） */
export interface StrategicBriefResult {
  executive_summary: string
  strategic_priorities: StrategicPriority[]
  market_opportunities: MarketOpportunity[]
  risks_and_threats: RiskAndThreat[]
  recommended_positioning: RecommendedPositioning
  data_provenance?: DataProvenance
  chain_inputs?: ChainInputs
  /** "media_only" | "comprehensive"（后端 _build_chain_inputs 注入） */
  generation_mode?: 'media_only' | 'comprehensive'
}

// ==================== Brief 文档解析 ====================

/**
 * insufficient 分诊原因（仅 platform_verdict === 'insufficient' 时非空）
 * - no_channel → 引导至研究分析（默认 profile）
 * - knowledge_industry → 引导至研究分析 industry profile（品类结构/市场/政策/技术型知识）
 * - knowledge_creative → 引导至研究分析 creative profile（Campaign 案例/创意参考型知识）
 * - diagnostic_social → 引导至社媒监测 + 切片分析
 * - diagnostic_news → 引导至新闻监测 + 切片分析
 * - diagnostic_dual → 引导至社媒和新闻两个监测入口
 */
export type InsufficientReason =
  | ''
  | 'no_channel'
  | 'knowledge_industry'
  | 'knowledge_creative'
  | 'diagnostic_social'
  | 'diagnostic_news'
  | 'diagnostic_dual'

export interface ParseBriefResponse {
  strategy_name: string
  subject: string
  analysis_goal: string
  constraints: string
  platform_verdict: 'sufficient' | 'partial' | 'insufficient'
  platform_note: string
  insufficient_reason: InsufficientReason
  channel_plan: ChannelPlanItem[]

  // 策略 Brief Framework 字段（brief 未提及时为 null）
  target_audiences?: AudienceSegment[] | null
  audience_insights?: string[] | null
  core_propositions?: string[] | null
  competitors?: string[] | null
}
