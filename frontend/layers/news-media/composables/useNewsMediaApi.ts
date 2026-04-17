/**
 * 新闻监测 API composable
 */

import type {
  NewsArticle,
  NewsMonitor,
  NewsMonitorWithOwner,
  NewsMonitorCreate,
  NewsMonitorUpdate,
  NewsTask,
  NewsTaskWithRelations,
  NewsTaskCreate,
  NewsSlice,
  NewsSliceCreate,
  NewsSliceWithRelations,
} from '../types'

export const useNewsMonitors = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  const getMonitors = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<NewsMonitorWithOwner>>('/news-media/monitors', {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `news-monitors-list-${p?.page || 1}-${p?.page_size || 10}`
      }),
    })
  }

  const getMonitor = (id: number) => {
    return useApiData<NewsMonitorWithOwner>(`/news-media/monitors/${id}`, {
      key: `news-monitor-${id}`,
    })
  }

  const createMonitor = async (data: NewsMonitorCreate) => {
    const result = await apiRequest<NewsMonitor>('/news-media/monitors', {
      method: 'POST',
      body: data,
    })
    showSuccess('新闻监测项目创建成功！')
    return result
  }

  const updateMonitor = async (id: number, data: NewsMonitorUpdate) => {
    const result = await apiRequest<NewsMonitor>(`/news-media/monitors/${id}`, {
      method: 'PUT',
      body: data,
    })
    showSuccess('新闻监测更新成功！')
    return result
  }

  const deleteMonitor = async (id: number) => {
    await apiRequest(`/news-media/monitors/${id}`, {
      method: 'DELETE',
    })
    showSuccess('新闻监测删除成功！')
    return true
  }

  const addParticipant = async (monitorId: number, userIds: number[]) => {
    const result = await apiRequest<NewsMonitorWithOwner>(
      `/news-media/monitors/${monitorId}/participants`,
      { method: 'POST', body: { user_ids: userIds } },
    )
    showSuccess('参与者添加成功！')
    return result
  }

  const removeParticipant = async (monitorId: number, userId: number) => {
    const result = await apiRequest<NewsMonitorWithOwner>(
      `/news-media/monitors/${monitorId}/participants/${userId}`,
      { method: 'DELETE' },
    )
    showSuccess('参与者移除成功！')
    return result
  }

  return {
    getMonitors,
    getMonitor,
    createMonitor,
    updateMonitor,
    deleteMonitor,
    addParticipant,
    removeParticipant,
  }
}

export const useNewsTasks = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  const getAllTasks = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<NewsTaskWithRelations>>('/news-media/tasks', {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `news-all-tasks-${p?.page || 1}-${p?.page_size || 10}`
      }),
    })
  }

  const getTasks = (monitorId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<NewsTaskWithRelations>>(
      `/news-media/monitors/${monitorId}/tasks`,
      {
        query: params,
        key: computed(() => {
          const p = unref(params)
          return `news-tasks-${monitorId}-${p?.page || 1}-${p?.page_size || 10}`
        }),
      },
    )
  }

  const getTask = (taskId: number) => {
    return useApiData<NewsTaskWithRelations>(`/news-media/tasks/${taskId}`, {
      key: `news-task-${taskId}`,
    })
  }

  const createTask = async (monitorId: number, data: NewsTaskCreate) => {
    const result = await apiRequest<NewsTask>(
      `/news-media/monitors/${monitorId}/tasks`,
      {
        method: 'POST',
        body: data,
      },
    )
    showSuccess('新闻任务创建成功！')
    return result
  }

  const deleteTask = async (taskId: number) => {
    await apiRequest(`/news-media/tasks/${taskId}`, {
      method: 'DELETE',
    })
    showSuccess('任务删除成功！')
    return true
  }

  const executeTask = async (taskId: number) => {
    const result = await apiRequest<NewsTask>(`/news-media/tasks/${taskId}/execute`, {
      method: 'POST',
    })
    showSuccess('任务已开始执行')
    return result
  }

  const getTaskArticles = (taskId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<NewsArticle>>(
      `/news-media/tasks/${taskId}/articles`,
      {
        query: params,
        key: computed(() => {
          const p = unref(params)
          return `news-articles-${taskId}-${p?.page || 1}-${p?.page_size || 20}`
        }),
      },
    )
  }

  return {
    getAllTasks,
    getTasks,
    getTask,
    createTask,
    deleteTask,
    executeTask,
    getTaskArticles,
  }
}

export const useNewsSlices = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  const getSlices = (monitorId: number) => {
    return useApiData<NewsSlice[]>(`/news-media/monitors/${monitorId}/slices`, {
      key: `news-slices-${monitorId}`,
    })
  }

  const getSlice = (sliceId: number) => {
    return useApiData<NewsSliceWithRelations>(`/news-media/slices/${sliceId}`, {
      key: `news-slice-${sliceId}`,
    })
  }

  const createSlice = async (monitorId: number, data: NewsSliceCreate) => {
    const result = await apiRequest<NewsSlice>(
      `/news-media/monitors/${monitorId}/slices`,
      { method: 'POST', body: data },
    )
    showSuccess('切片创建成功！')
    return result
  }

  const analyzeSlice = async (
    sliceId: number,
    params?: { analysis_goal?: string; subject?: string },
  ) => {
    const result = await apiRequest<NewsSlice>(`/news-media/slices/${sliceId}/analyze`, {
      method: 'POST',
      body: params || {},
    })
    showSuccess('切片分析已完成')
    return result
  }

  const deleteSlice = async (sliceId: number) => {
    await apiRequest(`/news-media/slices/${sliceId}`, {
      method: 'DELETE',
    })
    showSuccess('切片已删除')
    return true
  }

  return {
    getSlices,
    getSlice,
    createSlice,
    analyzeSlice,
    deleteSlice,
  }
}
