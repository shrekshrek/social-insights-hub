export interface ProgressEntry {
  step: string
  label: string
  round: number
  status: 'completed'
  ts: string
  detail: string
}

export type ResearchProfileName = 'industry' | 'creative'

export interface ResearchProfileOption {
  name: ResearchProfileName | string
  display_name: string
}

export interface ResearchTask {
  id: number
  title: string | null
  analysis_goal: string
  research_questions: string[] | null
  search_config: Record<string, unknown> | null
  profile_name: ResearchProfileName | string
  strategy_id: number | null
  user_id: number
  job_id: number | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  error_message: string | null
  stats: ResearchTaskStats | null
  progress: ProgressEntry[] | null
  created_at: string
  updated_at: string
  participant_ids: number[]
  participant_usernames: string[]
  owner_username: string
}

export interface ResearchTaskStats {
  rounds: number
  candidates_total: number
  documents_analyzed: number
  synthesis_length: number
}

export type SuitabilityVerdict = 'suitable' | 'partial' | 'not_suitable'
export type SuitabilityRedirectHint = 'strategy' | 'monitor_social' | 'monitor_news' | ''

export interface ParseBriefTextRequest {
  text: string
  profile_name?: ResearchProfileName | string
}

export interface ParseBriefResponse {
  title: string
  analysis_goal: string
  research_questions: string[]
  keywords: string[]
  search_angles: string[]
  verdict: SuitabilityVerdict
  recommended_profile: string
  redirect_hint: SuitabilityRedirectHint
  note: string
  brief_text: string
}

export interface ResearchTaskCreate {
  analysis_goal: string
  title: string
  brief?: string
  research_questions?: string[]
  search_config?: Record<string, unknown>
  profile_name?: ResearchProfileName | string
}

export interface ResearchTaskUpdate {
  title?: string
}

export interface DataPoint {
  metric: string
  value: string
  period: string
  source: string
}

export interface QuestionFinding {
  answer_summary: string
  confidence: 'high' | 'medium' | 'low'
  data_points: DataPoint[]
  source_refs: string[]
}

export interface ResearchSource {
  id: string
  title: string
  url: string
  source: string
  source_tier: 'tier1' | 'tier2' | 'tier3'
  content_type: string
  relevance_score: number
  published_date: string
}

export interface ResearchCoverage {
  questions_covered: number
  questions_total: number
  high_confidence_count: number
  source_quality: Record<string, number>
}

export interface ResearchTaskResult {
  id: number
  analysis_goal: string
  status: string
  findings_by_question: Record<string, QuestionFinding> | null
  synthesis: string | null
  sources: ResearchSource[] | null
  coverage: ResearchCoverage | null
  information_gaps: string[] | null
  stats: ResearchTaskStats | null
}
