import type {
  Strategy,
  StrategyCreate,
  StrategyUpdate,
  StrategyListResponse,
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

  return {
    getStrategies,
    getStrategy,
    createStrategy,
    updateStrategy,
    deleteStrategy,
    generatePhase,
    editPhase,
    exportStrategy,
  }
}
