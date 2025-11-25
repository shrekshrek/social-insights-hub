import type {
  AnalysisJob,
  AnalysisJobListResponse,
  AnalysisJobFilterParams,
  RunAnalysisResponse,
  AnalysisProgressResponse,
  PostAnalysisListResponse,
  DeepAnalysisPreview,
} from '../types'

/**
 * 分析操作 Composable
 *
 * 使用统一的 AnalysisJob 模型，通过 task_id 是否为空区分任务级/项目级分析
 */
export const useAnalysis = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  // ==================== 分析任务（全局）====================

  /**
   * 获取全局分析任务列表
   */
  const getAnalysisJobs = (params?: MaybeRef<AnalysisJobFilterParams>) => {
    return useApiData<AnalysisJobListResponse>(
      computed(() => {
        const p = unref(params) || {}
        const searchParams = new URLSearchParams()

        if (p.page) searchParams.set('page', String(p.page))
        if (p.page_size) searchParams.set('page_size', String(p.page_size))
        if (p.project_id) searchParams.set('project_id', String(p.project_id))
        if (p.task_id) searchParams.set('task_id', String(p.task_id))
        if (p.analysis_type) searchParams.set('analysis_type', p.analysis_type)
        if (p.status) searchParams.set('status', p.status)
        if (p.start_date) searchParams.set('start_date', p.start_date)
        if (p.end_date) searchParams.set('end_date', p.end_date)

        const query = searchParams.toString()
        return `/social-media/analysis/jobs${query ? `?${query}` : ''}`
      }),
      {
        key: computed(() => {
          const p = unref(params) || {}
          return `analysis-jobs-${JSON.stringify(p)}`
        }),
      }
    )
  }

  /**
   * 获取单个分析任务详情
   */
  const getAnalysisJob = (jobId: MaybeRef<number>) => {
    return useApiData<AnalysisJob>(
      computed(() => `/social-media/analysis/jobs/${unref(jobId)}`),
      {
        key: computed(() => `analysis-job-${unref(jobId)}`),
      }
    )
  }

  /**
   * 获取分析任务进度
   */
  const getAnalysisProgress = (jobId: MaybeRef<number>) => {
    return useApiData<AnalysisProgressResponse>(
      computed(() => `/social-media/analysis/jobs/${unref(jobId)}/progress`),
      {
        key: computed(() => `analysis-progress-${unref(jobId)}`),
      }
    )
  }

  /**
   * 取消分析任务
   */
  const cancelAnalysisJob = async (jobId: number) => {
    await apiRequest(`/social-media/analysis/jobs/${jobId}/cancel`, {
      method: 'POST',
    })
    showSuccess('分析任务已取消')
    return true
  }

  /**
   * 删除分析任务
   */
  const deleteAnalysisJob = async (jobId: number) => {
    await apiRequest(`/social-media/analysis/jobs/${jobId}`, {
      method: 'DELETE',
    })
    showSuccess('分析任务已删除')
    return true
  }

  // ==================== 任务级分析操作 ====================

  /**
   * 运行帖子AI初筛分析
   */
  const runPostScreening = async (taskId: number) => {
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/tasks/${taskId}/screening`,
      {
        method: 'POST',
      }
    )
    showSuccess('帖子初筛任务已启动')
    return result
  }

  /**
   * 运行帖子深度分析
   */
  const runPostDeepAnalysis = async (
    taskId: number,
    params?: { spam_max?: number; value_min?: number; relevance_min?: number }
  ) => {
    const searchParams = new URLSearchParams()
    if (params?.spam_max != null) searchParams.set('spam_max', String(params.spam_max))
    if (params?.value_min != null) searchParams.set('value_min', String(params.value_min))
    if (params?.relevance_min != null) searchParams.set('relevance_min', String(params.relevance_min))

    const query = searchParams.toString()
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/tasks/${taskId}/deep-posts${query ? `?${query}` : ''}`,
      {
        method: 'POST',
      }
    )
    showSuccess('帖子深度分析任务已启动')
    return result
  }

  /**
   * 运行评论深度分析
   */
  const runCommentDeepAnalysis = async (
    taskId: number,
    params?: { spam_max?: number; value_min?: number; relevance_min?: number }
  ) => {
    const searchParams = new URLSearchParams()
    if (params?.spam_max != null) searchParams.set('spam_max', String(params.spam_max))
    if (params?.value_min != null) searchParams.set('value_min', String(params.value_min))
    if (params?.relevance_min != null) searchParams.set('relevance_min', String(params.relevance_min))

    const query = searchParams.toString()
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/tasks/${taskId}/deep-comments${query ? `?${query}` : ''}`,
      {
        method: 'POST',
      }
    )
    showSuccess('评论深度分析任务已启动')
    return result
  }

  /**
   * 获取任务下所有帖子的分析结果
   */
  const getTaskPostAnalyses = (
    taskId: MaybeRef<number>,
    options?: {
      page?: MaybeRef<number>
      pageSize?: MaybeRef<number>
      filterAnalyzed?: MaybeRef<boolean>
      searchQuery?: MaybeRef<string>
      searchId?: MaybeRef<number | null>
    }
  ) => {
    const page = options?.page ?? 1
    const pageSize = options?.pageSize ?? 20
    const filterAnalyzed = options?.filterAnalyzed ?? true
    const searchQuery = options?.searchQuery ?? ''
    const searchId = options?.searchId ?? null

    return useApiData<PostAnalysisListResponse>(
      computed(() => {
        const params = new URLSearchParams({
          page: String(unref(page)),
          page_size: String(unref(pageSize)),
          filter_analyzed: String(unref(filterAnalyzed)),
        })

        const query = unref(searchQuery)
        const id = unref(searchId)
        if (query) {
          params.set('search_query', query)
        }
        if (id != null) {
          params.set('search_id', String(id))
        }

        return `/social-media/analysis/tasks/${unref(taskId)}/posts?${params}`
      }),
      {
        key: computed(() => {
          const query = unref(searchQuery)
          const id = unref(searchId)
          return `task-post-analyses-${unref(taskId)}-${unref(page)}-${unref(pageSize)}-${query}-${id}`
        }),
      }
    )
  }

  /**
   * 深度分析预览（基于初筛阈值）
   */
  const getDeepAnalysisPreview = async (
    taskId: number,
    params: { spam_max?: number; value_min?: number; relevance_min?: number }
  ) => {
    const searchParams = new URLSearchParams()
    if (params.spam_max != null) searchParams.set('spam_max', String(params.spam_max))
    if (params.value_min != null) searchParams.set('value_min', String(params.value_min))
    if (params.relevance_min != null) searchParams.set('relevance_min', String(params.relevance_min))

    return apiRequest<DeepAnalysisPreview>(
      `/social-media/analysis/tasks/${taskId}/preview?${searchParams.toString()}`
    )
  }

  // ==================== 项目级分析操作（预留）====================

  /**
   * 运行主题聚类分析（预留）
   */
  const runTopicClustering = async (projectId: number, taskIds?: number[]) => {
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/projects/${projectId}/clustering`,
      {
        method: 'POST',
        body: { task_ids: taskIds },
      }
    )
    showSuccess('主题聚类任务已启动')
    return result
  }

  /**
   * 运行竞品分析（预留）
   */
  const runCompetitiveAnalysis = async (
    projectId: number,
    competitors: string[],
    taskIds?: number[]
  ) => {
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/projects/${projectId}/competitive`,
      {
        method: 'POST',
        body: { task_ids: taskIds, competitors },
      }
    )
    showSuccess('竞品分析任务已启动')
    return result
  }

  return {
    // 全局分析任务
    getAnalysisJobs,
    getAnalysisJob,
    getAnalysisProgress,
    cancelAnalysisJob,
    deleteAnalysisJob,

    // 任务级分析操作
    runPostScreening,
    runPostDeepAnalysis,
    runCommentDeepAnalysis,
    getTaskPostAnalyses,
    getDeepAnalysisPreview,

    // 项目级分析操作（预留）
    runTopicClustering,
    runCompetitiveAnalysis,
  }
}
