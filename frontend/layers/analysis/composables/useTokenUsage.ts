import type { TokenUsageStats, TokenUsageSummary } from '../types'

/**
 * Token使用统计 Composable
 *
 * 提供Token使用量和成本的格式化、计算和展示功能
 */
export const useTokenUsage = () => {
  /**
   * 格式化Token数量（添加千位分隔符）
   */
  const formatTokens = (tokens: number): string => {
    return tokens.toLocaleString('zh-CN')
  }

  /**
   * 格式化成本（人民币）
   */
  const formatCost = (cost: number): string => {
    return `¥${cost.toFixed(4)}`
  }

  /**
   * 格式化时长（秒转为可读格式）
   */
  const formatDuration = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}秒`
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60)
      const remainingSeconds = seconds % 60
      return `${minutes}分${remainingSeconds.toFixed(0)}秒`
    } else {
      const hours = Math.floor(seconds / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      return `${hours}小时${minutes}分`
    }
  }

  /**
   * 计算Token使用效率（tokens/秒）
   */
  const calculateEfficiency = (tokens: number, duration: number): number => {
    if (duration === 0) return 0
    return tokens / duration
  }

  /**
   * 计算平均每次调用的成本
   */
  const calculateAvgCost = (totalCost: number, calls: number): number => {
    if (calls === 0) return 0
    return totalCost / calls
  }

  /**
   * 计算平均每次调用的Token数
   */
  const calculateAvgTokens = (totalTokens: number, calls: number): number => {
    if (calls === 0) return 0
    return totalTokens / calls
  }

  /**
   * 获取Token使用等级（根据使用量）
   */
  const getUsageLevel = (tokens: number): {
    level: 'low' | 'medium' | 'high' | 'very_high'
    color: string
    label: string
  } => {
    if (tokens < 10000) {
      return { level: 'low', color: 'green', label: '较低' }
    } else if (tokens < 100000) {
      return { level: 'medium', color: 'blue', label: '中等' }
    } else if (tokens < 1000000) {
      return { level: 'high', color: 'orange', label: '较高' }
    } else {
      return { level: 'very_high', color: 'red', label: '很高' }
    }
  }

  /**
   * 获取成本等级（根据花费）
   */
  const getCostLevel = (cost: number): {
    level: 'low' | 'medium' | 'high' | 'very_high'
    color: string
    label: string
  } => {
    if (cost < 1) {
      return { level: 'low', color: 'green', label: '较低' }
    } else if (cost < 10) {
      return { level: 'medium', color: 'blue', label: '中等' }
    } else if (cost < 100) {
      return { level: 'high', color: 'orange', label: '较高' }
    } else {
      return { level: 'very_high', color: 'red', label: '很高' }
    }
  }

  /**
   * 从TokenUsageStats中提取摘要信息
   */
  const extractSummary = (stats: TokenUsageStats | null): TokenUsageSummary | null => {
    if (!stats) return null
    return stats.summary
  }

  /**
   * 计算多个统计数据的总和
   */
  const aggregateStats = (statsList: (TokenUsageStats | null)[]): TokenUsageSummary => {
    const validStats = statsList.filter((s): s is TokenUsageStats => s !== null)

    if (validStats.length === 0) {
      return {
        total_calls: 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_tokens: 0,
        total_cost_cny: 0,
        total_duration_seconds: 0,
        avg_tokens_per_call: 0,
        avg_cost_per_call: 0,
      }
    }

    const totalCalls = validStats.reduce((sum, s) => sum + s.summary.total_calls, 0)
    const totalInputTokens = validStats.reduce((sum, s) => sum + s.summary.total_input_tokens, 0)
    const totalOutputTokens = validStats.reduce((sum, s) => sum + s.summary.total_output_tokens, 0)
    const totalTokens = validStats.reduce((sum, s) => sum + s.summary.total_tokens, 0)
    const totalCost = validStats.reduce((sum, s) => sum + s.summary.total_cost_cny, 0)
    const totalDuration = validStats.reduce((sum, s) => sum + s.summary.total_duration_seconds, 0)

    return {
      total_calls: totalCalls,
      total_input_tokens: totalInputTokens,
      total_output_tokens: totalOutputTokens,
      total_tokens: totalTokens,
      total_cost_cny: totalCost,
      total_duration_seconds: totalDuration,
      avg_tokens_per_call: calculateAvgTokens(totalTokens, totalCalls),
      avg_cost_per_call: calculateAvgCost(totalCost, totalCalls),
    }
  }

  /**
   * 估算剩余成本（基于进度）
   */
  const estimateRemainingCost = (
    currentCost: number,
    completedCount: number,
    totalCount: number
  ): number => {
    if (completedCount === 0 || totalCount === 0) return 0
    const avgCostPerItem = currentCost / completedCount
    const remainingCount = totalCount - completedCount
    return avgCostPerItem * remainingCount
  }

  /**
   * 获取Token使用趋势（相比上次）
   */
  const getTrend = (current: number, previous: number): {
    trend: 'up' | 'down' | 'stable'
    percentage: number
    label: string
  } => {
    if (previous === 0) {
      return { trend: 'stable', percentage: 0, label: '无变化' }
    }

    const change = ((current - previous) / previous) * 100

    if (Math.abs(change) < 5) {
      return { trend: 'stable', percentage: change, label: '基本持平' }
    } else if (change > 0) {
      return { trend: 'up', percentage: change, label: `增长${change.toFixed(1)}%` }
    } else {
      return { trend: 'down', percentage: change, label: `减少${Math.abs(change).toFixed(1)}%` }
    }
  }

  return {
    // 格式化函数
    formatTokens,
    formatCost,
    formatDuration,

    // 计算函数
    calculateEfficiency,
    calculateAvgCost,
    calculateAvgTokens,

    // 等级评估
    getUsageLevel,
    getCostLevel,

    // 统计聚合
    extractSummary,
    aggregateStats,
    estimateRemainingCost,
    getTrend,
  }
}
