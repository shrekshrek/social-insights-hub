/**
 * 策略模块 - TypeScript 类型定义
 */

import type { PaginatedResponse } from '~/types/common'

// ==================== 策略状态 ====================

export type StrategyStatus =
  | 'briefing'
  | 'consulting'
  | 'monitors_created'
  | 'slices_ready'
  | 'phase1_done'
  | 'phase2_done'
  | 'completed'

// ==================== 切片摘要 ====================

export interface SliceSummary {
  slice_id: number
  slice_name: string | null
  monitor_id: number
  monitor_name: string
}

// ==================== Brand Brief ====================

export interface BrandBrief {
  brand_name: string
  industry?: string
  analysis_goal: string
  competitors?: string[]
  focus_areas?: string[]
  time_range?: string
  constraints?: string
}

// ==================== 咨询相关 ====================

export interface MonitorSuggestion {
  name: string
  platforms?: string[]
  keywords?: string[]
  task_type?: string
  rationale?: string
}

export interface SlicePlanItem {
  name: string
  subject?: string
  purpose: string
  expected_sources?: string[]
}

export interface ConsultResponse {
  understanding_summary: string
  monitor_suggestions: MonitorSuggestion[]
  slice_plan: SlicePlanItem[]
}

// ==================== 确认计划 ====================

export interface ConfirmPlanResponse {
  created_monitor_ids: number[]
  partial_errors: string[]
  strategy: Strategy
}

// ==================== 评估相关 ====================

export interface CoverageAnalysis {
  dimension: string
  score: number
  status: string
  note: string
}

export interface GapAnalysis {
  gap_type: string
  description: string
  priority: string
}

export interface SupplementarySuggestion {
  name: string
  platforms: string[]
  keywords: string[]
  rationale: string
}

export interface StructureSliceIssue {
  slice_name: string
  issue_type: 'redundant' | 'misaligned' | 'overlapping' | 'too_granular'
  description: string
  suggestion: string
}

export interface UnusedOpportunity {
  monitor_name: string
  slice_name: string
  gap_addressed: string
  why_valuable: string
  recommended_mode: string
  recommended_subject: string
}

export interface RecommendedSlice {
  name: string
  mode: string
  subject: string
  purpose: string
  action: 'keep' | 'associate' | 'adjust' | 'supplement'
  source: string
  action_detail: string | null
}

export interface StructureAnalysis {
  summary: string
  current_slice_issues: StructureSliceIssue[]
  unused_opportunities: UnusedOpportunity[]
  recommended_structure: RecommendedSlice[]
  collection_still_needed: boolean
  collection_note: string | null
}

export interface EvaluationResult {
  overall_score: number
  is_sufficient: boolean
  coverage_analysis: CoverageAnalysis[]
  slice_suggestions: Array<{ slice_name: string; issue: string; suggestion: string }>
  gap_analysis: GapAnalysis[]
  supplementary_suggestions?: SupplementarySuggestion[] | null
  supplementary_slice_plan?: SlicePlanItem[] | null
  pending_supplementary_task_ids?: number[] | null
  structure_analysis?: StructureAnalysis | null
}

export interface ConfirmSupplementaryResponse {
  created_task_ids: number[]
  task_count: number
  partial_errors: string[]
  strategy: Strategy
}

// ==================== 策略 ====================

export interface Strategy {
  id: number
  name: string
  status: StrategyStatus
  brand_brief: BrandBrief | null
  consultation_rounds: Array<{ user_input: string; ai_response: ConsultResponse }>
  suggested_monitor_ids: number[]
  slice_plan: SlicePlanItem[]
  evaluation_result: EvaluationResult | null
  phase1_result: Record<string, unknown> | null
  phase2_result: Record<string, unknown> | null
  phase3_result: Record<string, unknown> | null
  slices: SliceSummary[]
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
  brand_brief?: Record<string, unknown> | null
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
  brand_name: string
  analysis_goal: string
  constraints: string
}
