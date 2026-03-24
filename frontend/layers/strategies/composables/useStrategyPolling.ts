import type {
  ProbeTaskStatus,
  ProbeReviewResult,
  SliceSummary,
  CoverageCheckResult,
  Strategy,
} from '../types'

/**
 * 策略详情页轮询逻辑：探测状态 + 采集状态
 *
 * 封装 setInterval 轮询、unmount 清理、race condition 防护。
 */
export const useStrategyPolling = (
  strategyId: Ref<number>,
  strategy: Ref<Strategy | null | undefined>,
) => {
  const strategiesApi = useStrategies()
  let isUnmounted = false

  // ── 探测轮询 ────────────────────────────────────────────────────────

  const probeData = reactive({
    tasks: [] as ProbeTaskStatus[],
    analyzedCount: 0,
    totalCount: 0,
    allAnalyzed: false,
    probeReview: null as ProbeReviewResult | null,
  })

  let probeTimer: ReturnType<typeof setInterval> | null = null
  const probePolling = ref(false)

  const stopProbePolling = () => {
    if (probeTimer) {
      clearInterval(probeTimer)
      probeTimer = null
    }
    probePolling.value = false
  }

  const pollProbeStatus = async () => {
    if (isUnmounted) return
    try {
      const result = await strategiesApi.getProbeStatus(strategyId.value)
      if (isUnmounted) return

      probeData.tasks = result.tasks
      probeData.analyzedCount = result.analyzed_count
      probeData.totalCount = result.total_count
      probeData.allAnalyzed = result.all_analyzed

      if (result.probe_review_result) {
        probeData.probeReview = result.probe_review_result
      }

      if (result.strategy) {
        strategy.value = result.strategy
      }

      // 已全部分析完成且有审查结果 → 停止轮询
      if (result.all_analyzed && result.probe_review_result) {
        stopProbePolling()
      }

      // 状态已推进到 collecting → 切换到采集轮询
      if (strategy.value?.status === 'collecting') {
        stopProbePolling()
        startCollectionPolling()
      }
    } catch {
      // 静默失败，下次轮询重试
    }
  }

  const startProbePolling = () => {
    if (probePolling.value) return
    stopProbePolling()
    probePolling.value = true
    pollProbeStatus()
    probeTimer = setInterval(pollProbeStatus, 10000)
  }

  // ── 采集轮询 ────────────────────────────────────────────────────────

  const collectionData = reactive({
    slices: [] as SliceSummary[],
    completedCount: 0,
    totalCount: 0,
    allAnalyzed: false,
    coverageResult: null as CoverageCheckResult | null,
  })

  let collectionTimer: ReturnType<typeof setInterval> | null = null
  const collectionPolling = ref(false)

  const stopCollectionPolling = () => {
    if (collectionTimer) {
      clearInterval(collectionTimer)
      collectionTimer = null
    }
    collectionPolling.value = false
  }

  const pollCollectionStatus = async () => {
    if (isUnmounted) return
    try {
      const result = await strategiesApi.getCollectionStatus(strategyId.value)
      if (isUnmounted) return

      collectionData.completedCount = result.completed_count
      collectionData.totalCount = result.total_count
      collectionData.allAnalyzed = result.all_analyzed

      if (result.coverage_check_result) {
        collectionData.coverageResult = result.coverage_check_result
      }

      if (result.strategy) {
        strategy.value = result.strategy
        collectionData.slices = result.strategy.slices
      }

      // 已全部完成且有覆盖度结果 → 停止轮询
      if (result.all_analyzed && result.coverage_check_result) {
        stopCollectionPolling()
      }
    } catch {
      // 静默失败，下次轮询重试
    }
  }

  const startCollectionPolling = () => {
    if (collectionPolling.value) return
    stopCollectionPolling()
    collectionPolling.value = true
    pollCollectionStatus()
    collectionTimer = setInterval(pollCollectionStatus, 15000)
  }

  // ── 初始化 + 清理 ──────────────────────────────────────────────────

  const initPollingFromStatus = (status: string | undefined) => {
    if (status === 'probing') {
      startProbePolling()
    } else if (status === 'collecting') {
      startCollectionPolling()
    }
  }

  // 初始化切片/覆盖度数据（从已加载的策略对象）
  const initFromStrategy = (s: Strategy) => {
    if (s.slices?.length && !collectionData.slices.length) {
      collectionData.slices = s.slices
    }
    if (s.coverage_check_result && !collectionData.coverageResult) {
      collectionData.coverageResult = s.coverage_check_result
    }
  }

  onUnmounted(() => {
    isUnmounted = true
    stopProbePolling()
    stopCollectionPolling()
  })

  const isPollingActive = computed(() => probePolling.value || collectionPolling.value)

  return {
    probeData,
    collectionData,
    isPollingActive,
    startProbePolling,
    stopProbePolling,
    startCollectionPolling,
    stopCollectionPolling,
    initPollingFromStatus,
    initFromStrategy,
  }
}
