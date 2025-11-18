import type {
  AnalysisStats,
  TaskAnalysisStats,
  ProjectAnalysisStats,
  PostAnalysis,
  CommentAnalysis,
} from '../types'

/**
 * 分析统计 Composable
 *
 * 提供分析统计数据的查询和展示功能
 */
export const useAnalysisStats = () => {
  const { apiRequest, useApiData } = useApi()

  /**
   * 获取全局分析统计
   */
  const getGlobalStats = () => {
    return useApiData<AnalysisStats>('/analysis/stats/global', {
      key: 'analysis-global-stats',
    })
  }

  /**
   * 获取任务级分析统计
   */
  const getTaskStats = (taskId: MaybeRef<number>) => {
    return useApiData<TaskAnalysisStats>(
      computed(() => `/analysis/stats/tasks/${unref(taskId)}`),
      {
        key: computed(() => `analysis-task-stats-${unref(taskId)}`),
      }
    )
  }

  /**
   * 获取项目级分析统计
   */
  const getProjectStats = (projectId: MaybeRef<number>) => {
    return useApiData<ProjectAnalysisStats>(
      computed(() => `/analysis/stats/projects/${unref(projectId)}`),
      {
        key: computed(() => `analysis-project-stats-${unref(projectId)}`),
      }
    )
  }

  /**
   * 获取帖子的分析结果
   */
  const getPostAnalysis = (postId: MaybeRef<number>) => {
    return useApiData<PostAnalysis>(
      computed(() => `/analysis/posts/${unref(postId)}`),
      {
        key: computed(() => `post-analysis-${unref(postId)}`),
      }
    )
  }

  /**
   * 获取评论的分析结果
   */
  const getCommentAnalysis = (commentId: MaybeRef<number>) => {
    return useApiData<CommentAnalysis>(
      computed(() => `/analysis/comments/${unref(commentId)}`),
      {
        key: computed(() => `comment-analysis-${unref(commentId)}`),
      }
    )
  }

  /**
   * 导出分析结果
   */
  const exportAnalysisResults = async (params: {
    result_id: number
    format?: 'excel' | 'pdf' | 'json'
  }) => {
    const result = await apiRequest<Blob>(
      '/analysis/export',
      {
        method: 'POST',
        body: params,
        responseType: 'blob',
      }
    )
    return result
  }

  return {
    getGlobalStats,
    getTaskStats,
    getProjectStats,
    getPostAnalysis,
    getCommentAnalysis,
    exportAnalysisResults,
  }
}
