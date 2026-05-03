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

/**
 * campaign_strategy 路径三个递进层：
 *   insight → brand_role → big_idea
 */
export type BrandStrategyStage = 'insight' | 'brand_role' | 'big_idea'

/**
 * market_report 路径三个递进层：
 *   agenda_map → landscape → strategic_brief
 */
export type MarketReportStage = 'agenda_map' | 'landscape' | 'strategic_brief'

const BRAND_STRATEGY_STAGE_LABELS: Record<BrandStrategyStage, string> = {
  insight: 'Insight 洞察',
  brand_role: 'Brand Role 品牌角色',
  big_idea: 'Big Idea 创意',
}

const MARKET_REPORT_STAGE_LABELS: Record<MarketReportStage, string> = {
  agenda_map: 'Agenda Map 媒体议程图',
  landscape: 'Landscape 竞争格局',
  strategic_brief: 'Strategic Brief 战略简报',
}

const toKebab = (stage: string) => stage.replace(/_/g, '-')

export const useStrategiesApi = () => {
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
    showSuccess(`已替换 ${result.removed_social_task_ids.length} 个任务`)
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

  // 生成 campaign_strategy 路径的某一层
  // brand_role / big_idea 支持子集模式：传 tensionIds=[0,2] 仅生成这两个分支
  // 不传或传 undefined：全跑模式（insight 是单一结果，不接受 tensionIds）
  const generateBrandStrategyStage = async (
    id: number,
    stage: BrandStrategyStage,
    tensionIds?: number[],
  ) => {
    const body = tensionIds && tensionIds.length > 0
      ? { tension_ids: tensionIds }
      : undefined
    const result = await apiRequest<Strategy>(
      `/strategies/${id}/generate/${toKebab(stage)}`,
      { method: 'POST', body }
    )
    const subsetLabel = tensionIds?.length ? `（${tensionIds.length} 个分支）` : ''
    showSuccess(`${BRAND_STRATEGY_STAGE_LABELS[stage]} 生成完成${subsetLabel}`)
    return result
  }

  // 编辑 campaign_strategy 路径的某一层结果
  // brand_role / big_idea 是多分支：tensionId 必填，定位要编辑的分支；
  // insight 单一结果，tensionId 不传。
  const editBrandStrategyStage = async (
    id: number,
    stage: BrandStrategyStage,
    result: Record<string, unknown>,
    tensionId?: number,
  ) => {
    const body: Record<string, unknown> = { result }
    if (stage !== 'insight') {
      if (tensionId === undefined) {
        throw new Error(`编辑 ${stage} 必须指定 tension_id`)
      }
      body.tension_id = tensionId
    }
    const updated = await apiRequest<Strategy>(
      `/strategies/${id}/${toKebab(stage)}`,
      {
        method: 'PUT',
        body,
      }
    )
    showSuccess('已保存修改')
    return updated
  }

  // ==================== 多分支专属操作 ====================

  // 选定分支（仅一条 selected=true，影响导出和 UI 默认展示）
  const selectBrandStrategyBranch = async (id: number, tensionId: number) => {
    const updated = await apiRequest<Strategy>(
      `/strategies/${id}/branches/select`,
      {
        method: 'POST',
        body: { tension_id: tensionId },
      }
    )
    showSuccess('已设为主推分支')
    return updated
  }

  // 单分支重生成 brand_role（同步作废该分支 big_idea）
  const regenerateBrandRoleBranch = async (id: number, tensionId: number) => {
    const updated = await apiRequest<Strategy>(
      `/strategies/${id}/branches/regenerate-brand-role`,
      {
        method: 'POST',
        body: { tension_id: tensionId },
      }
    )
    showSuccess(`分支 #${tensionId + 1} Brand Role 重生成完成`)
    return updated
  }

  // 单分支重生成 big_idea
  const regenerateBigIdeaBranch = async (id: number, tensionId: number) => {
    const updated = await apiRequest<Strategy>(
      `/strategies/${id}/branches/regenerate-big-idea`,
      {
        method: 'POST',
        body: { tension_id: tensionId },
      }
    )
    showSuccess(`分支 #${tensionId + 1} Big Idea 重生成完成`)
    return updated
  }

  // 生成 market_report 路径的某一层
  const generateMarketReportStage = async (id: number, stage: MarketReportStage) => {
    const result = await apiRequest<Strategy>(
      `/strategies/${id}/generate/${toKebab(stage)}`,
      { method: 'POST' }
    )
    showSuccess(`${MARKET_REPORT_STAGE_LABELS[stage]} 生成完成`)
    return result
  }

  // 编辑 market_report 路径的某一层结果
  const editMarketReportStage = async (
    id: number,
    stage: MarketReportStage,
    result: Record<string, unknown>,
  ) => {
    const updated = await apiRequest<Strategy>(
      `/strategies/${id}/${toKebab(stage)}`,
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

  // ==================== Participants ====================

  const addParticipant = async (id: number, userIds: number[]) => {
    const result = await apiRequest<Strategy>(`/strategies/${id}/participants`, {
      method: 'POST',
      body: { user_ids: userIds },
    })
    showSuccess('参与者添加成功')
    return result
  }

  const removeParticipant = async (id: number, userId: number) => {
    const result = await apiRequest<Strategy>(`/strategies/${id}/participants/${userId}`, {
      method: 'DELETE',
    })
    showSuccess('参与者移除成功')
    return result
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
    generateBrandStrategyStage,
    editBrandStrategyStage,
    selectBrandStrategyBranch,
    regenerateBrandRoleBranch,
    regenerateBigIdeaBranch,
    generateMarketReportStage,
    editMarketReportStage,
    exportStrategy,
    parseBrief,
    parseBriefText,
    addParticipant,
    removeParticipant,
  }
}
