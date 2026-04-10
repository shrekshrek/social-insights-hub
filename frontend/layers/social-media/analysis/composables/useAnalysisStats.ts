import type { AnalysisStats } from '../types'

/**
 * 分析统计 Composable
 *
 * 提供全局分析统计数据的查询功能
 */
export const useAnalysisStats = () => {
  const { useApiData } = useApi()

  /**
   * 获取全局分析统计
   */
  const getGlobalStats = () => {
    return useApiData<AnalysisStats>('/social-media/analysis/stats', {
      key: 'analysis-global-stats',
    })
  }

  return {
    getGlobalStats,
  }
}
