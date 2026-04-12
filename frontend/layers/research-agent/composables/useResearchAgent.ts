import type { ResearchTask, ResearchTaskCreate, ResearchTaskResult, ResearchType } from '../types'

// 研究类型选项（供前端 select 使用）
export const RESEARCH_TYPE_OPTIONS: { value: ResearchType; label: string; description: string }[] = [
  { value: 'industry_research', label: '行业报告研究', description: '搜索四大咨询/智库/研究机构的专业报告' },
  { value: 'ad_campaign', label: '广告营销案例', description: '搜索数英网/梅花网/SocialBeta 等营销案例' },
  { value: 'product_research', label: '产品设计研究', description: '搜索人人都是PM/PMCAFF 等产品分析文章' },
]

export function useResearchAgent() {
  const { apiRequest, useApiData } = useApi()

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

  // 获取研究结果
  const getTaskResult = (id: number) => {
    return useApiData<ResearchTaskResult>(`/research/tasks/${id}/result`, {
      key: `research-result-${id}`,
    })
  }

  // 创建任务
  async function createTask(data: ResearchTaskCreate): Promise<ResearchTask> {
    return apiRequest<ResearchTask>('/research/tasks', {
      method: 'POST',
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

  return {
    getTasks,
    getTask,
    getTaskResult,
    createTask,
    rerunTask,
    deleteTask,
    statusLabel,
    statusColor,
    confidenceLabel,
    confidenceColor,
    tierLabel,
    tierColor,
  }
}
