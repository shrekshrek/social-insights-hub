/**
 * 爬虫任务API
 */

import type {
  CrawlerTask,
  CrawlerTaskDetail,
  TaskCreateRequest,
  TaskUpdateRequest,
  TaskStatistics,
  TaskLog,
  PlatformType,
  TaskStatus
} from '../types'
import type { PaginatedResponse } from '~/types/common'

export const useCrawlerTasksApi = () => {
  const { apiRequest, useApiData, showSuccess, showError } = useApi()

  /**
   * 获取任务列表
   */
  const getTasks = (params?: {
    page?: number
    page_size?: number
    platform?: PlatformType
    status?: TaskStatus
  }) => {
    return useApiData<PaginatedResponse<CrawlerTask>>('/crawler-tasks/', {
      query: params,
      key: computed(() => `crawler-tasks-${params?.page || 1}-${params?.platform || 'all'}-${params?.status || 'all'}`)
    })
  }

  /**
   * 获取任务详情
   */
  const getTaskDetail = (taskId: number) => {
    return useApiData<CrawlerTaskDetail>(`/crawler-tasks/${taskId}`, {
      key: `crawler-task-detail-${taskId}`
    })
  }

  /**
   * 创建任务
   */
  const createTask = async (data: TaskCreateRequest) => {
    try {
      const result = await apiRequest<CrawlerTask>('/crawler-tasks/', {
        method: 'POST',
        body: data
      })
      showSuccess('任务创建成功')
      return result
    } catch (error) {
      showError('任务创建失败')
      throw error
    }
  }

  /**
   * 更新任务
   */
  const updateTask = async (taskId: number, data: TaskUpdateRequest) => {
    try {
      const result = await apiRequest<CrawlerTask>(`/crawler-tasks/${taskId}`, {
        method: 'PATCH',
        body: data
      })
      showSuccess('任务更新成功')
      return result
    } catch (error) {
      showError('任务更新失败')
      throw error
    }
  }

  /**
   * 删除任务
   */
  const deleteTask = async (taskId: number) => {
    try {
      await apiRequest(`/crawler-tasks/${taskId}`, {
        method: 'DELETE'
      })
      showSuccess('任务删除成功')
    } catch (error) {
      showError('任务删除失败')
      throw error
    }
  }

  /**
   * 启动任务
   */
  const startTask = async (taskId: number) => {
    try {
      const result = await apiRequest<CrawlerTask>(`/crawler-tasks/${taskId}/start`, {
        method: 'POST'
      })
      showSuccess('任务已启动')
      return result
    } catch (error) {
      showError('任务启动失败')
      throw error
    }
  }

  /**
   * 暂停任务
   */
  const pauseTask = async (taskId: number) => {
    try {
      const result = await apiRequest<CrawlerTask>(`/crawler-tasks/${taskId}/pause`, {
        method: 'POST'
      })
      showSuccess('任务已暂停')
      return result
    } catch (error) {
      showError('任务暂停失败')
      throw error
    }
  }

  /**
   * 停止任务
   */
  const stopTask = async (taskId: number) => {
    try {
      const result = await apiRequest<CrawlerTask>(`/crawler-tasks/${taskId}/stop`, {
        method: 'POST'
      })
      showSuccess('任务已停止')
      return result
    } catch (error) {
      showError('任务停止失败')
      throw error
    }
  }

  /**
   * 获取任务日志
   */
  const getTaskLogs = (taskId: number, limit = 100) => {
    return useApiData<TaskLog[]>(`/crawler-tasks/${taskId}/logs`, {
      query: { limit },
      key: `crawler-task-logs-${taskId}`
    })
  }

  /**
   * 获取任务统计
   */
  const getStatistics = () => {
    return useApiData<TaskStatistics>('/crawler-tasks/statistics', {
      key: 'crawler-tasks-statistics'
    })
  }

  return {
    getTasks,
    getTaskDetail,
    createTask,
    updateTask,
    deleteTask,
    startTask,
    pauseTask,
    stopTask,
    getTaskLogs,
    getStatistics
  }
}
