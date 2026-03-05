/**
 * 策略模块 - TypeScript 类型定义
 */

import type { PaginatedResponse } from '~/types/common'

// ==================== 策略状态 ====================

export type StrategyStatus = 'draft' | 'phase1_done' | 'phase2_done' | 'completed'

// ==================== 切片摘要 ====================

export interface SliceSummary {
  slice_id: number
  slice_name: string | null
  project_id: number
  project_name: string
}

// ==================== 策略 ====================

export interface Strategy {
  id: number
  name: string
  status: StrategyStatus
  brand_brief: Record<string, unknown> | null
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
  slice_ids: number[]
  brand_brief?: Record<string, unknown> | null
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
