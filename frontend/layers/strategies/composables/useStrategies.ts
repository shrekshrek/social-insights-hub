import type {
  Strategy,
  StrategyCreate,
  StrategyUpdate,
  StrategyListResponse,
  ConsultResponse,
  ConfirmPlanResponse,
  ConfirmSupplementaryResponse,
  EvaluationResult,
  MonitorSuggestion,
  ParseBriefResponse,
  SlicePlanItem,
} from '../types'

export const useStrategies = () => {
  const { apiRequest, useApiData, apiDownload, showSuccess } = useApi()

  // 获取策略列表
  const getStrategies = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<StrategyListResponse>(
      computed(() => {
        const p = unref(params) || {}
        const searchParams = new URLSearchParams()
        if (p.page) searchParams.set('page', String(p.page))
        if (p.page_size) searchParams.set('page_size', String(p.page_size))
        if (p.search) searchParams.set('search', String(p.search))
        const query = searchParams.toString()
        return `/strategies${query ? `?${query}` : ''}`
      }),
      {
        key: computed(() => {
          const p = unref(params) || {}
          return `strategies-list-${p.page || 1}-${p.page_size || 10}-${p.search || ''}`
        }),
      }
    )
  }

  // 获取策略详情（lazy: true 避免 SSR/Client 水合不一致）
  const getStrategy = (id: MaybeRef<number>) => {
    return useApiData<Strategy>(
      computed(() => `/strategies/${unref(id)}`),
      {
        key: computed(() => `strategy-${unref(id)}`),
        lazy: true,
      }
    )
  }

  // 直接拉取策略（用于 mutation 后刷新，绕过 useFetch 缓存）
  const fetchStrategy = async (id: number) => {
    return await apiRequest<Strategy>(`/strategies/${id}`)
  }

  // 创建策略
  const createStrategy = async (data: StrategyCreate) => {
    const result = await apiRequest<Strategy>('/strategies', {
      method: 'POST',
      body: data,
    })
    showSuccess('策略创建成功')
    return result
  }

  // 更新策略
  const updateStrategy = async (id: number, data: StrategyUpdate) => {
    const result = await apiRequest<Strategy>(`/strategies/${id}`, {
      method: 'PUT',
      body: data,
    })
    showSuccess('策略更新成功')
    return result
  }

  // 删除策略
  const deleteStrategy = async (id: number) => {
    await apiRequest(`/strategies/${id}`, {
      method: 'DELETE',
    })
    showSuccess('策略已删除')
    return true
  }

  // 生成 Phase
  const generatePhase = async (id: number, phase: 1 | 2 | 3) => {
    const result = await apiRequest<Strategy>(
      `/strategies/${id}/generate/phase${phase}`,
      { method: 'POST' }
    )
    showSuccess(`Phase ${phase} 生成完成`)
    return result
  }

  // 编辑 Phase 结果
  const editPhase = async (id: number, phase: 1 | 2 | 3, result: Record<string, unknown>) => {
    const updated = await apiRequest<Strategy>(
      `/strategies/${id}/phase${phase}`,
      {
        method: 'PUT',
        body: { result },
      }
    )
    showSuccess('已保存修改')
    return updated
  }

  // 导出 Word 文档
  const exportStrategy = async (id: number, name: string) => {
    await apiDownload(`/strategies/${id}/export`, `${name}_策略报告.docx`)
  }

  // AI 生成监测方案
  const consult = async (id: number, input: string = '') => {
    const result = await apiRequest<ConsultResponse>(`/strategies/${id}/consult`, {
      method: 'POST',
      body: { user_input: input },
    })
    showSuccess('监测方案已生成')
    return result
  }

  // 确认 AI 建议，一键创建监测
  const confirmPlan = async (
    id: number,
    suggestions: MonitorSuggestion[],
    notesPerTask: number = 50,
    slicePlan?: SlicePlanItem[],
  ) => {
    const result = await apiRequest<ConfirmPlanResponse>(`/strategies/${id}/confirm-plan`, {
      method: 'POST',
      body: {
        monitor_suggestions: suggestions,
        slice_plan: slicePlan || null,
        notes_per_task: notesPerTask,
      },
    })
    showSuccess(`已创建 ${result.created_monitor_ids.length} 个监测`)
    return result
  }

  // 批量关联切片
  const addSlices = async (id: number, sliceIds: number[]) => {
    const result = await apiRequest<Strategy>(`/strategies/${id}/slices`, {
      method: 'POST',
      body: { slice_ids: sliceIds },
    })
    showSuccess(`已关联 ${sliceIds.length} 个切片`)
    return result
  }

  // 移除关联切片
  const removeSlice = async (id: number, sliceId: number) => {
    const result = await apiRequest<Strategy>(`/strategies/${id}/slices/${sliceId}`, {
      method: 'DELETE',
    })
    showSuccess('已移除切片')
    return result
  }

  // AI 评估切片充分性
  const evaluate = async (id: number) => {
    const result = await apiRequest<EvaluationResult>(`/strategies/${id}/evaluate`, {
      method: 'POST',
    })
    showSuccess('评估完成')
    return result
  }

  // 确认补充采集
  const confirmSupplementary = async (id: number, suggestions: MonitorSuggestion[], notesPerTask: number = 50) => {
    const result = await apiRequest<ConfirmSupplementaryResponse>(`/strategies/${id}/confirm-supplementary`, {
      method: 'POST',
      body: { monitor_suggestions: suggestions, notes_per_task: notesPerTask },
    })
    showSuccess(`已创建 ${result.task_count} 个补充采集任务`)
    return result
  }

  // 确认数据就绪
  const confirmReady = async (id: number) => {
    const result = await apiRequest<Strategy>(`/strategies/${id}/confirm-ready`, {
      method: 'POST',
    })
    showSuccess('数据已标记就绪')
    return result
  }

  // 上传 Brief 文档，AI 自动解析填充
  const parseBrief = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return await apiRequest<ParseBriefResponse>('/strategies/parse-brief', {
      method: 'POST',
      body: formData,
    })
  }

  return {
    getStrategies,
    getStrategy,
    fetchStrategy,
    createStrategy,
    updateStrategy,
    deleteStrategy,
    generatePhase,
    editPhase,
    exportStrategy,
    consult,
    confirmPlan,
    addSlices,
    removeSlice,
    evaluate,
    confirmSupplementary,
    confirmReady,
    parseBrief,
  }
}
