import type {
  TaskAnalysisResult,
  ProjectAnalysisResult,
  RunScreeningRequest,
  RunDeepAnalysisRequest,
  RunClusteringRequest,
  RunCompetitiveRequest,
  RunAnalysisResponse,
  AnalysisProgressResponse,
  PaginatedResponse,
} from '../types'

/**
 * 分析操作 Composable
 *
 * 提供任务级和项目级分析操作的API封装
 */
export const useAnalysis = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  // ==================== 任务级分析 ====================

  /**
   * 获取任务的分析结果列表
   */
  const getTaskAnalysisResults = (taskId: MaybeRef<number>) => {
    return useApiData<PaginatedResponse<TaskAnalysisResult>>(
      computed(() => `/social-media/analysis/tasks/${unref(taskId)}/results`),
      {
        key: computed(() => `task-analysis-results-${unref(taskId)}`),
      }
    )
  }

  /**
   * 获取单个任务分析结果详情
   */
  const getTaskAnalysisResult = (resultId: number) => {
    return useApiData<TaskAnalysisResult>(
      `/social-media/analysis/tasks/results/${resultId}`,
      {
        key: `task-analysis-result-${resultId}`,
      }
    )
  }

  /**
   * 运行帖子AI初筛分析
   */
  const runPostScreening = async (data: RunScreeningRequest) => {
    const result = await apiRequest<RunAnalysisResponse>(
      '/social-media/analysis/tasks/screening/posts',
      {
        method: 'POST',
        body: data,
      }
    )
    showSuccess('帖子初筛任务已启动')
    return result
  }

  /**
   * 运行帖子深度分析
   */
  const runPostDeepAnalysis = async (data: RunDeepAnalysisRequest) => {
    const result = await apiRequest<RunAnalysisResponse>(
      '/social-media/analysis/tasks/deep/posts',
      {
        method: 'POST',
        body: data,
      }
    )
    showSuccess('帖子深度分析任务已启动')
    return result
  }

  /**
   * 运行评论深度分析
   */
  const runCommentDeepAnalysis = async (data: RunDeepAnalysisRequest) => {
    const result = await apiRequest<RunAnalysisResponse>(
      '/social-media/analysis/tasks/deep/comments',
      {
        method: 'POST',
        body: data,
      }
    )
    showSuccess('评论深度分析任务已启动')
    return result
  }

  /**
   * 获取分析任务进度
   */
  const getAnalysisProgress = (resultId: MaybeRef<number>) => {
    return useApiData<AnalysisProgressResponse>(
      computed(() => `/social-media/analysis/tasks/results/${unref(resultId)}/progress`),
      {
        key: computed(() => `analysis-progress-${unref(resultId)}`),
      }
    )
  }

  /**
   * 取消分析任务
   */
  const cancelAnalysis = async (resultId: number) => {
    await apiRequest(`/social-media/analysis/tasks/results/${resultId}/cancel`, {
      method: 'POST',
    })
    showSuccess('分析任务已取消')
    return true
  }

  /**
   * 删除分析结果
   */
  const deleteAnalysisResult = async (resultId: number) => {
    await apiRequest(`/social-media/analysis/tasks/results/${resultId}`, {
      method: 'DELETE',
    })
    showSuccess('分析结果已删除')
    return true
  }

  // ==================== 项目级分析 ====================

  /**
   * 获取项目的分析结果列表
   */
  const getProjectAnalysisResults = (projectId: MaybeRef<number>) => {
    return useApiData<PaginatedResponse<ProjectAnalysisResult>>(
      computed(() => `/social-media/analysis/projects/${unref(projectId)}/results`),
      {
        key: computed(() => `project-analysis-results-${unref(projectId)}`),
      }
    )
  }

  /**
   * 获取单个项目分析结果详情
   */
  const getProjectAnalysisResult = (resultId: number) => {
    return useApiData<ProjectAnalysisResult>(
      `/social-media/analysis/projects/results/${resultId}`,
      {
        key: `project-analysis-result-${resultId}`,
      }
    )
  }

  /**
   * 运行主题聚类分析
   */
  const runTopicClustering = async (data: RunClusteringRequest) => {
    const result = await apiRequest<RunAnalysisResponse>(
      '/social-media/analysis/projects/clustering',
      {
        method: 'POST',
        body: data,
      }
    )
    showSuccess('主题聚类任务已启动')
    return result
  }

  /**
   * 运行竞品分析
   */
  const runCompetitiveAnalysis = async (data: RunCompetitiveRequest) => {
    const result = await apiRequest<RunAnalysisResponse>(
      '/social-media/analysis/projects/competitive',
      {
        method: 'POST',
        body: data,
      }
    )
    showSuccess('竞品分析任务已启动')
    return result
  }

  /**
   * 删除项目分析结果
   */
  const deleteProjectAnalysisResult = async (resultId: number) => {
    await apiRequest(`/social-media/analysis/projects/results/${resultId}`, {
      method: 'DELETE',
    })
    showSuccess('分析结果已删除')
    return true
  }

  return {
    // 任务级分析
    getTaskAnalysisResults,
    getTaskAnalysisResult,
    runPostScreening,
    runPostDeepAnalysis,
    runCommentDeepAnalysis,
    getAnalysisProgress,
    cancelAnalysis,
    deleteAnalysisResult,

    // 项目级分析
    getProjectAnalysisResults,
    getProjectAnalysisResult,
    runTopicClustering,
    runCompetitiveAnalysis,
    deleteProjectAnalysisResult,
  }
}
