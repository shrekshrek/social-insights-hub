import type { ResearchProfileOption, ResearchTask, ResearchTaskCreate, ResearchTaskResult, ResearchTaskUpdate, ParseBriefTextRequest, ParseBriefResponse } from '../types'

export function useResearchAgentApi() {
  const { apiRequest, useApiData, apiDownload } = useApi()

  // 研究类型列表（industry / creative / ...）
  const getProfiles = () => {
    return useApiData<ResearchProfileOption[]>('/research/profiles', {
      key: 'research-profiles',
    })
  }

  // 获取任务列表（分页）
  const getTasks = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<{ items: ResearchTask[]; total: number; page: number; page_size: number }>('/research/tasks', {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `research-tasks-${p?.page || 1}-${p?.page_size || 20}-${p?.status || ''}-${p?.search || ''}`
      }),
    })
  }

  // 获取单个任务
  const getTask = (id: number) => {
    return useApiData<ResearchTask>(`/research/tasks/${id}`, {
      key: `research-task-${id}`,
    })
  }

  // 获取研究结果（任务未完成时 404 静默处理）
  const getTaskResult = (id: number) => {
    return useApiData<ResearchTaskResult>(`/research/tasks/${id}/result`, {
      key: `research-result-${id}`,
      silent404: true,
    })
  }

  // 解析 Brief 文件（合流点：摄入 + 诊断 + 方案）
  async function parseBrief(file: File, profileName: string): Promise<ParseBriefResponse> {
    const formData = new FormData()
    formData.append('file', file)
    return apiRequest<ParseBriefResponse>(
      `/research/parse-brief?profile_name=${encodeURIComponent(profileName)}`,
      {
        method: 'POST',
        body: formData,
      }
    )
  }

  // 解析 Brief 文本（合流点：摄入 + 诊断 + 方案）
  async function parseBriefText(data: ParseBriefTextRequest): Promise<ParseBriefResponse> {
    return apiRequest<ParseBriefResponse>('/research/parse-brief-text', {
      method: 'POST',
      body: data,
    })
  }

  // 创建任务
  async function createTask(data: ResearchTaskCreate): Promise<ResearchTask> {
    return apiRequest<ResearchTask>('/research/tasks', {
      method: 'POST',
      body: data,
    })
  }

  // 编辑研究任务（仅 title）
  async function updateTask(id: number, data: ResearchTaskUpdate): Promise<ResearchTask> {
    return apiRequest<ResearchTask>(`/research/tasks/${id}`, {
      method: 'PATCH',
      body: data,
    })
  }

  // 重新运行
  async function rerunTask(id: number): Promise<ResearchTask> {
    return apiRequest<ResearchTask>(`/research/tasks/${id}/rerun`, {
      method: 'POST',
    })
  }

  // 删除任务
  async function deleteTask(id: number): Promise<void> {
    return apiRequest(`/research/tasks/${id}`, {
      method: 'DELETE',
    })
  }

  // 添加参与者
  async function addParticipants(taskId: number, userIds: number[]): Promise<ResearchTask> {
    return apiRequest<ResearchTask>(`/research/tasks/${taskId}/participants`, {
      method: 'POST',
      body: { user_ids: userIds },
    })
  }

  // 移除参与者
  async function removeParticipant(taskId: number, userId: number): Promise<ResearchTask> {
    return apiRequest<ResearchTask>(`/research/tasks/${taskId}/participants/${userId}`, {
      method: 'DELETE',
    })
  }

  // 状态标签
  function statusLabel(status: string): string {
    const labels: Record<string, string> = {
      'pending': '等待中',
      'running': '研究中',
      'completed': '已完成',
      'failed': '失败',
    }
    return labels[status] ?? status
  }

  // 状态颜色
  function statusColor(status: string): 'neutral' | 'info' | 'success' | 'error' {
    const colors: Record<string, 'neutral' | 'info' | 'success' | 'error'> = {
      'pending': 'neutral',
      'running': 'info',
      'completed': 'success',
      'failed': 'error',
    }
    return colors[status] ?? 'neutral'
  }

  // 置信度标签
  function confidenceLabel(confidence: string): string {
    const labels: Record<string, string> = {
      'high': '高',
      'medium': '中',
      'low': '低',
    }
    return labels[confidence] ?? confidence
  }

  // 置信度颜色
  function confidenceColor(confidence: string): 'success' | 'warning' | 'error' {
    const colors: Record<string, 'success' | 'warning' | 'error'> = {
      'high': 'success',
      'medium': 'warning',
      'low': 'error',
    }
    return colors[confidence] ?? 'error'
  }

  // 来源层级标签
  function tierLabel(tier: string): string {
    const labels: Record<string, string> = {
      'tier1': '权威',
      'tier2': '行业',
      'tier3': '一般',
    }
    return labels[tier] ?? tier
  }

  // 来源层级颜色
  function tierColor(tier: string): 'success' | 'info' | 'neutral' {
    const colors: Record<string, 'success' | 'info' | 'neutral'> = {
      'tier1': 'success',
      'tier2': 'info',
      'tier3': 'neutral',
    }
    return colors[tier] ?? 'neutral'
  }

  // 研究类型标签（内置默认，后端 /research/profiles 返回时以后端为准）
  function profileLabel(profileName: string): string {
    const labels: Record<string, string> = {
      industry: '行业研究',
      creative: '创意研究',
    }
    return labels[profileName] ?? profileName
  }

  // 研究类型色（用于列表 Badge 区分）
  function profileColor(profileName: string): 'primary' | 'success' | 'neutral' {
    const colors: Record<string, 'primary' | 'success' | 'neutral'> = {
      industry: 'primary',
      creative: 'success',
    }
    return colors[profileName] ?? 'neutral'
  }

  // 导出研究结果 Markdown（按需，后端纯投影 result_data）
  const exportTaskMd = (id: number, title: string) =>
    apiDownload(
      `/research/tasks/${id}/export?format=md`,
      `${title || 'research'}_专题研究.md`,
    )

  return {
    getProfiles,
    getTasks,
    getTask,
    getTaskResult,
    exportTaskMd,
    parseBrief,
    parseBriefText,
    createTask,
    updateTask,
    rerunTask,
    deleteTask,
    addParticipants,
    removeParticipant,
    statusLabel,
    statusColor,
    confidenceLabel,
    confidenceColor,
    tierLabel,
    tierColor,
    profileLabel,
    profileColor,
  }
}
