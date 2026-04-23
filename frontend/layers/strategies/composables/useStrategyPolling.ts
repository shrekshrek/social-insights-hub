import type {
  SocialProbeTaskStatus,
  NewsProbeTaskStatus,
  ProbeReviewResult,
  SliceSummary,
  CoverageCheckResult,
  Strategy,
} from '../types'
import { STATUS_ORDER } from './useStrategyConstants'

/**
 * 策略详情页轮询逻辑：探测状态 + 采集状态
 *
 * 封装 setInterval 轮询、unmount 清理、race condition 防护。
 */
export const useStrategyPolling = (
  strategyId: Ref<number>,
  strategy: Ref<Strategy | null | undefined>,
) => {
  const strategiesApi = useStrategiesApi()
  let isUnmounted = false

  // ── 探测轮询 ────────────────────────────────────────────────────────

  const probeData = reactive({
    socialTasks: [] as SocialProbeTaskStatus[],
    newsTasks: [] as NewsProbeTaskStatus[],
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

      probeData.socialTasks = result.social_tasks
      probeData.newsTasks = result.news_tasks
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
      // probe-status 失败时主动拉一次 strategy，检测阶段是否已推进
      // 场景：APScheduler 自动 approve 后 probe 任务被原地推进到 collect 阶段，
      // probe-status 查不到 phase=probe 任务会返回 400；此时应停止 probe 轮询，
      // 必要时切换到 collection 轮询，避免 10s 一次死循环弹错
      try {
        const latest = await strategiesApi.fetchStrategy(strategyId.value)
        if (isUnmounted) return
        strategy.value = latest
        if (latest.status !== 'probing') {
          stopProbePolling()
          if (latest.status === 'collecting') startCollectionPolling()
        }
      } catch {
        // 策略本身也拉不到（网络问题/权限问题），下次轮询再试
      }
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

      // 兜底：状态已推进到 ready 或更后阶段 → 停止轮询
      const currentStatus = strategy.value?.status
      if (currentStatus && (STATUS_ORDER[currentStatus as keyof typeof STATUS_ORDER] ?? 0) >= STATUS_ORDER.ready) {
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

  // 从已加载的策略对象初始化数据（避免等待第一次轮询的空白期）
  const initFromStrategy = (s: Strategy) => {
    // 探测数据
    if (s.probe_review_result && !probeData.probeReview) {
      probeData.probeReview = s.probe_review_result
      // 状态已过 probing 阶段时，标记探测已完成（此时不再轮询 probe-status）
      const order = STATUS_ORDER[s.status as keyof typeof STATUS_ORDER] ?? 0
      if (order >= STATUS_ORDER.collecting) {
        probeData.allAnalyzed = true
      }
    }
    // 采集数据
    if (s.slices?.length && !collectionData.slices.length) {
      collectionData.slices = s.slices
    }
    if (s.coverage_check_result && !collectionData.coverageResult) {
      collectionData.coverageResult = s.coverage_check_result
    }
    // 状态已过 collecting 阶段时，标记采集已完成（此时不再轮询 collection-status）
    const statusOrder = STATUS_ORDER[s.status as keyof typeof STATUS_ORDER] ?? 0
    if (statusOrder >= STATUS_ORDER.ready) {
      collectionData.allAnalyzed = true
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
