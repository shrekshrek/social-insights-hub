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
  purpose: string
  expected_sources?: string[]
}

export interface ConsultResponse {
  round_number: number
  understanding_summary: string
  clarification_questions: Array<{ id: string; question: string }>
  monitor_suggestions: MonitorSuggestion[]
  slice_plan: SlicePlanItem[]
  confidence: number
}

export interface ConsultRound {
  round_number: number
  user_input: string
  answers?: Record<string, string> | null
  ai_response: ConsultResponse
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

export interface EvaluationResult {
  overall_score: number
  is_sufficient: boolean
  coverage_analysis: CoverageAnalysis[]
  slice_suggestions: Array<{ slice_name: string; issue: string; suggestion: string }>
  gap_analysis: GapAnalysis[]
  supplementary_tasks?: Array<{ platform: string; keywords: string[]; reason: string }> | null
}

// ==================== 策略 ====================

export interface Strategy {
  id: number
  name: string
  status: StrategyStatus
  brand_brief: BrandBrief | null
  consultation_rounds: ConsultRound[]
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
  confidence?: string
  evidence?: PhaseEvidence[]
}

export interface BrandOpportunity {
  statement: string
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
