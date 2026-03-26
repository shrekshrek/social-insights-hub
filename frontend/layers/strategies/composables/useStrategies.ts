import type {
  Strategy,
  StrategyCreate,
  StrategyUpdate,
  StrategyListResponse,
  ResearchDesign,
  ConfirmResearchRequest,
  ConfirmResearchResponse,
  ProbeStatusResponse,
  ApproveProbeResponse,
  RefineProbeRequest,
  RefineProbeResponse,
  CollectionStatusResponse,
  DataOverviewResponse,
  AdjustSlicesRequest,
  ParseBriefResponse,
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
    await apiRequest(`/strategies/${id}`, { method: 'DELETE' })
    showSuccess('策略已删除')
    return true
  }

  // ==================== ① 研究设计 ====================

  // 重置到研究设计阶段
  const resetToDesign = async (id: number) => {
    const result = await apiRequest<Strategy>(
      `/strategies/${id}/reset-to-design`,
      { method: 'POST' }
    )
    showSuccess('已重置到研究设计阶段')
    return result
  }

  // AI 生成研究计划
  const designResearch = async (id: number, userInput: string = '') => {
    const result = await apiRequest<ResearchDesign>(
      `/strategies/${id}/design-research`,
      {
        method: 'POST',
        body: { user_input: userInput },
      }
    )
    showSuccess('研究计划已生成')
    return result
  }

  // 确认研究计划，创建 Monitor + 探测任务
  const confirmResearch = async (id: number, request: ConfirmResearchRequest) => {
    const result = await apiRequest<ConfirmResearchResponse>(
      `/strategies/${id}/confirm-research`,
      {
        method: 'POST',
        body: request,
      }
    )
    showSuccess(`已创建 ${result.created_task_count} 个采集任务`)
    return result
  }

  // ==================== ② 探测验证 ====================

  // 查询探测进度（轮询用）
  const getProbeStatus = async (id: number) => {
    return await apiRequest<ProbeStatusResponse>(`/strategies/${id}/probe-status`)
  }

  // 手动确认探测通过
  const approveProbe = async (id: number) => {
    const result = await apiRequest<ApproveProbeResponse>(
      `/strategies/${id}/approve-probe`,
      { method: 'POST' }
    )
    showSuccess('探测已确认，开始全量采集')
    return result
  }

  // 调整关键词，创建新探测任务
  const refineProbe = async (id: number, request: RefineProbeRequest) => {
    const result = await apiRequest<RefineProbeResponse>(
      `/strategies/${id}/refine-probe`,
      {
        method: 'POST',
        body: request,
      }
    )
    showSuccess(`已替换 ${result.removed_task_ids.length} 个任务`)
    return result
  }

  // ==================== ③ 数据就绪 ====================

  // 查询全量采集进度（轮询用）
  const getCollectionStatus = async (id: number) => {
    return await apiRequest<CollectionStatusResponse>(
      `/strategies/${id}/collection-status`
    )
  }

  // 数据全景
  const getDataOverview = async (id: number) => {
    return await apiRequest<DataOverviewResponse>(
      `/strategies/${id}/data-overview`
    )
  }

  // 微调切片配置
  const adjustSlices = async (id: number, request: AdjustSlicesRequest) => {
    const result = await apiRequest<Strategy>(
      `/strategies/${id}/adjust-slices`,
      {
        method: 'POST',
        body: request,
      }
    )
    showSuccess('切片配置已更新')
    return result
  }

  // ==================== ④ 产出生成 ====================

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

  // ==================== 导出 + Brief ====================

  // 导出 Word 文档
  const exportStrategy = async (id: number, name: string) => {
    await apiDownload(`/strategies/${id}/export`, `${name}_策略报告.docx`)
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

  // 输入 Brief 文本，AI 自动解析填充
  const parseBriefText = async (text: string) => {
    return await apiRequest<ParseBriefResponse>('/strategies/parse-brief-text', {
      method: 'POST',
      body: { text },
    })
  }

  return {
    getStrategies,
    getStrategy,
    fetchStrategy,
    createStrategy,
    updateStrategy,
    deleteStrategy,
    resetToDesign,
    designResearch,
    confirmResearch,
    getProbeStatus,
    approveProbe,
    refineProbe,
    getCollectionStatus,
    getDataOverview,
    adjustSlices,
    generatePhase,
    editPhase,
    exportStrategy,
    parseBrief,
    parseBriefText,
  }
}
