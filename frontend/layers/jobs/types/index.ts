/**
 * 跨渠道 AnalysisJob 类型定义
 *
 * 所有渠道（社媒 / 新闻 / 策略 / 知识库）共享的分析任务模型与 token 用量结构。
 * 渠道专属的分析类型（例如 PostAnalysis、TaskAnalysisResult 等）放在各渠道 layer。
 */

import type { PaginatedResponse } from "~/types/common";

// ==================== Token Usage ====================

export interface CallDetail {
  call_index: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_cny: number;
  duration_seconds: number;
  timestamp?: string;
}

export interface TokenUsageSummary {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_cny: number;
  total_duration_seconds: number;
  avg_tokens_per_call: number;
  avg_cost_per_call: number;
}

export interface TokenUsageStats {
  summary: TokenUsageSummary;
  call_details: CallDetail[];
}

// ==================== Analysis Job (统一模型) ====================

/**
 * 分析类型
 * - 社媒: screening_posts, deep_posts, deep_comments, aggregation,
 *        entity_normalization, opinion_normalization, monitor_slice_summary
 * - 策略 campaign_strategy 路径: strategy_insight / strategy_brand_role / strategy_big_idea
 * - 策略 market_report 路径: strategy_agenda_map / strategy_landscape / strategy_strategic_brief
 * - 策略共享: strategy_social_probe_review, strategy_news_probe_review, strategy_coverage_check
 * - 新闻: news_tagging, news_insight
 * - 专题研究: research
 */
export type AnalysisType =
  | "screening_posts"
  | "deep_posts"
  | "deep_comments"
  | "aggregation"
  | "entity_normalization"
  | "opinion_normalization"
  | "monitor_slice_summary"
  | "strategy_social_probe_review"
  | "strategy_news_probe_review"
  | "strategy_coverage_check"
  | "strategy_insight"
  | "strategy_brand_role"
  | "strategy_big_idea"
  | "strategy_agenda_map"
  | "strategy_landscape"
  | "strategy_strategic_brief"
  | "news_tagging"
  | "news_insight"
  | "research";

export type AnalysisStatus = "pending" | "running" | "completed" | "failed";

/**
 * 分析任务（跨渠道统一模型）
 *
 * 通过各关联 ID 字段区分来源渠道：
 * - social_monitor_id / social_task_id: 社媒监测模块
 * - news_monitor_id / news_task_id: 新闻媒体模块
 */
export interface AnalysisJob {
  id: number;
  social_monitor_id: number | null;
  social_task_id: number | null;
  news_monitor_id: number | null;
  news_task_id: number | null;
  user_id: number;
  analysis_type: AnalysisType;
  celery_task_id: string;
  status: AnalysisStatus;

  // 配置
  analysis_config: Record<string, unknown> | null;
  source_task_ids: number[] | null;

  // 统计
  source_count: number;
  analyzed_count: number;
  failed_count: number;

  // 结果
  result_data: Record<string, unknown> | null;
  analysis_summary: string | null;

  // 性能
  started_at: string | null;
  completed_at: string | null;
  processing_time: number | null;
  token_usage: TokenUsageStats | null;

  // 错误
  error_message: string | null;

  // 时间戳
  created_at: string;
  updated_at: string;

  // 关联信息（从列表接口返回）
  social_monitor_name?: string;
  social_task_name?: string;
  news_monitor_name?: string;
  news_task_name?: string;
  slice_id?: number;
  slice_name?: string | null;
  user_name?: string;
}

export type AnalysisJobListResponse = PaginatedResponse<AnalysisJob>;

export interface AnalysisJobFilterParams {
  page?: number;
  page_size?: number;
  social_monitor_id?: number;
  social_task_id?: number;
  news_monitor_id?: number;
  news_task_id?: number;
  /**
   * 策略级聚合筛选：覆盖该策略下的所有 AnalysisJob。
   *
   * 包括其 social_monitor / news_monitor 触发的所有渠道分析、以及策略自身的
   * chain（insight / brand_role / big_idea / agenda_map / landscape /
   * strategic_brief / probe_review / coverage_check 等）。
   */
  strategy_id?: number;
  analysis_type?: AnalysisType;
  status?: AnalysisStatus;
  start_date?: string;
  end_date?: string;
}

export interface AnalysisProgressResponse {
  job_id: number;
  status: AnalysisStatus;
  progress: number;
  analyzed_count: number;
  total_count: number;
  estimated_time_remaining: number | null;
  current_cost: number;
  current_tokens: number;
}
