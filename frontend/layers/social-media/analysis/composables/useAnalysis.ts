import type {
  AnalysisJob,
  AnalysisJobListResponse,
  AnalysisJobFilterParams,
  RunAnalysisResponse,
  AnalysisProgressResponse,
  PostAnalysisListResponse,
  DeepAnalysisPreview,
  TaskAnalysisResultResponse,
  RunAggregationResponse,
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
        // 禁用缓存，确保轮询时能获取最新数据
        getCachedData: () => undefined,
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
      postIds?: MaybeRef<number[] | null>
    }
  ) => {
    const page = options?.page ?? 1
    const pageSize = options?.pageSize ?? 20
    const filterAnalyzed = options?.filterAnalyzed ?? true
    const searchQuery = options?.searchQuery ?? ''
    const searchId = options?.searchId ?? null
    const postIds = options?.postIds ?? null

    return useApiData<PostAnalysisListResponse>(
      computed(() => {
        const params = new URLSearchParams({
          page: String(unref(page)),
          page_size: String(unref(pageSize)),
          filter_analyzed: String(unref(filterAnalyzed)),
        })

        const query = unref(searchQuery)
        const id = unref(searchId)
        const ids = unref(postIds)
        if (query) {
          params.set('search_query', query)
        }
        if (id != null) {
          params.set('search_id', String(id))
        }
        if (ids && ids.length > 0) {
          params.set('post_ids', ids.join(','))
        }

        return `/social-media/analysis/tasks/${unref(taskId)}/posts?${params}`
      }),
      {
        key: computed(() => {
          const query = unref(searchQuery)
          const id = unref(searchId)
          const ids = unref(postIds)
          const idsKey = ids ? ids.slice(0, 10).join('-') : ''  // 只用前10个ID作为key的一部分
          return `task-post-analyses-${unref(taskId)}-${unref(page)}-${unref(pageSize)}-${query}-${id}-${idsKey}`
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

  /**
   * 删除任务下所有分析结果（方便重新分析）
   */
  const deleteTaskAnalyses = async (taskId: number) => {
    const result = await apiRequest<{ success: boolean; deleted_count: number; message: string }>(
      `/social-media/analysis/tasks/${taskId}/analyses`,
      {
        method: 'DELETE',
      }
    )
    showSuccess(result.message)
    return result
  }

  /**
   * 运行聚合分析，生成任务级分析报告
   */
  const runTaskAggregation = async (taskId: number) => {
    const result = await apiRequest<RunAggregationResponse>(
      `/social-media/analysis/tasks/${taskId}/aggregation`,
      {
        method: 'POST',
      }
    )
    return result
  }

  /**
   * 获取任务级聚合分析结果
   * 使用 silent404 静默处理 404 错误，因为聚合结果可能尚未生成
   */
  const getTaskAggregation = (taskId: MaybeRef<number>) => {
    return useApiData<TaskAnalysisResultResponse>(
      computed(() => `/social-media/analysis/tasks/${unref(taskId)}/aggregation`),
      {
        key: computed(() => `task-aggregation-${unref(taskId)}`),
        silent404: true,
        // 禁用缓存，确保能获取最新的聚合结果
        getCachedData: () => undefined,
      }
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

  /**
   * 手动生成项目级合并分析快照（同步完成）
   */
  const createProjectSnapshot = async (
    projectId: number,
    taskIds: number[],
    name?: string,
    options?: {
      subject?: string | null
      competitors?: string[] | null
      platform_weights?: Record<string, number> | null
    }
  ) => {
    const result = await apiRequest<{ id: number; name: string | null }>(
      `/social-media/analysis/projects/${projectId}/snapshots`,
      {
        method: 'POST',
        body: {
          task_ids: taskIds,
          name: name || null,
          subject: options?.subject ?? null,
          competitors: options?.competitors ?? null,
          platform_weights: options?.platform_weights ?? null,
        },
      }
    )
    showSuccess('项目快照已生成')
    return result
  }

  /**
   * 删除项目级合并分析快照
   */
  const deleteProjectSnapshot = async (projectId: number, snapshotId: number) => {
    await apiRequest(
      `/social-media/analysis/projects/${projectId}/snapshots/${snapshotId}`,
      {
        method: 'DELETE',
      }
    )
    showSuccess('快照已删除')
    return true
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
    deleteTaskAnalyses,
    runTaskAggregation,
    getTaskAggregation,

    // 项目级分析操作（预留）
    runTopicClustering,
    runCompetitiveAnalysis,

    // 项目级合并快照（Phase 1）
    createProjectSnapshot,
    deleteProjectSnapshot,
  }
}
