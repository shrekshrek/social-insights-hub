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
  | 'phase1_done'
  | 'phase2_done'
  | 'completed'

// ==================== Brand Brief ====================

export interface ChannelPlanItem {
  type: string
  available: boolean
  solvable: string[]
  unsolvable: string[]
  channel_brief: string
}

export interface BrandBrief {
  subject: string
  analysis_goal: string
  constraints?: string | null
  channel_plan?: ChannelPlanItem[] | null
}

// ==================== 切片摘要 ====================

export interface SliceSummary {
  slice_id: number
  slice_name: string | null
  monitor_id: number
  monitor_name: string
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
  rationale?: string
}

export interface SliceBlueprintItem {
  name: string
  mode?: string
  subject?: string
  competitors?: string[]
  source_dimensions: string[]
  serves_questions?: string[]
}

export interface ResearchDesign {
  understanding_summary: string
  research_questions: ResearchQuestion[]
  data_plan: DataPlanItem[]
  slice_blueprint: SliceBlueprintItem[]
  output_type: string
  output_type_rationale: string
}

// ==================== 探测验证 ====================

export interface ProbeTaskStatus {
  task_id: number
  keyword: string
  platform: string
  status: string
  has_analysis: boolean
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
}

export interface RefinementSuggestion {
  task_id: number
  original_keyword: string
  suggested_keyword: string
  platform: string
  reason: string
}

export interface ProbeReviewResult {
  assessments: ProbeAssessment[]
  overall_verdict: 'all_pass' | 'partial_pass' | 'fail'
  refinement_suggestions: RefinementSuggestion[]
}

export interface ProbeStatusResponse {
  all_analyzed: boolean
  tasks: ProbeTaskStatus[]
  analyzed_count: number
  total_count: number
  probe_review_result: ProbeReviewResult | null
  strategy: Strategy | null
}

// ==================== 数据就绪 ====================

export interface CollectionTaskStatus {
  task_id: number
  status: string
  has_analysis: boolean
}

export interface QuestionCoverage {
  question_id: string
  question: string
  covered: boolean
  covered_by: string
  note: string
}

export interface SliceAdjustmentSuggestion {
  slice_name: string
  issue: string
  suggestion: string
}

export interface CoverageCheckResult {
  question_coverage: QuestionCoverage[]
  overall_ready: boolean
  data_highlights: string[]
  slice_adjustments: SliceAdjustmentSuggestion[]
}

export interface CollectionStatusResponse {
  all_completed: boolean
  all_analyzed: boolean
  slices_created: boolean
  tasks: CollectionTaskStatus[]
  completed_count: number
  total_count: number
  coverage_check_result: CoverageCheckResult | null
  strategy: Strategy | null
}

export interface DataOverviewResponse {
  slices: SliceSummary[]
  coverage_check_result: CoverageCheckResult | null
  strategy: Strategy
}

// ==================== 策略 ====================

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
  output_type: string | null
  phase1_result: Record<string, unknown> | null
  phase2_result: Record<string, unknown> | null
  phase3_result: Record<string, unknown> | null

  // 关联
  social_monitor_id: number | null
  news_monitor_id: number | null
  slices: SliceSummary[]

  // 参与者
  participant_ids: number[]
  participant_usernames: string[]

  // 元信息
  created_by: number
  creator_name: string
  created_at: string
  updated_at: string
}

export interface StrategyListItem {
  id: number
  name: string
  status: StrategyStatus
  slice_count: number
  created_by: number
  creator_name: string
  created_at: string
  updated_at: string
}

export type StrategyListResponse = PaginatedResponse<StrategyListItem>

// ==================== 请求体 ====================

export interface StrategyCreate {
  name: string
  slice_ids?: number[]
  brand_brief?: BrandBrief | null
}

export interface StrategyUpdate {
  name?: string
  brand_brief?: BrandBrief | null
}

export interface ConfirmResearchRequest {
  research_design: Record<string, unknown>
  notes_per_task?: number
}

export interface ConfirmResearchResponse {
  created_monitor_id: number
  created_task_count: number
  created_news_task_count: number
  partial_errors: string[]
  strategy: Strategy
}

export interface RefinementItem {
  task_id: number
  new_keyword: string
  platform: string
}

export interface RefineProbeRequest {
  refinements: RefinementItem[]
}

export interface RefineProbeResponse {
  removed_task_ids: number[]
  created_task_ids: number[]
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

// ==================== Phase 结果类型 ====================

export interface PhaseEvidence {
  type: string
  description: string
  source?: string
}

export interface SocialTension {
  statement: string
  conventional_wisdom?: string
  data_reality?: string
  confidence?: string
  evidence?: PhaseEvidence[]
}

export interface BrandOpportunity {
  statement: string
  why_non_obvious?: string
  related_tensions?: number[]
  evidence?: PhaseEvidence[]
}

export interface Phase1Result {
  social_tensions: SocialTension[]
  brand_opportunities: BrandOpportunity[]
}

export interface BrandSocialRole {
  statement: string
  elaboration?: string
  evidence?: PhaseEvidence[]
}

export interface SocialStrategy {
  statement: string
  core_message?: string
  rhythm?: string
  evidence?: PhaseEvidence[]
}

export interface Phase2Result {
  brand_social_role: BrandSocialRole
  social_strategy: SocialStrategy
}

export interface BigIdea {
  statement: string
  elaboration?: string
  tension_echo?: string
  evidence?: PhaseEvidence[]
}

export interface ContentPillar {
  name: string
  description?: string
  reference_examples?: string[]
}

export interface ContentStrategy {
  pillars: ContentPillar[]
  evidence?: PhaseEvidence[]
}

export interface Phase3Result {
  big_idea: BigIdea
  content_strategy: ContentStrategy
}

// ==================== Brief 文档解析 ====================

export interface ParseBriefResponse {
  strategy_name: string
  subject: string
  analysis_goal: string
  constraints: string
  platform_verdict: 'sufficient' | 'partial' | 'insufficient'
  platform_note: string
  channel_plan: ChannelPlanItem[]
}
