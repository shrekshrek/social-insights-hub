<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          to="/strategies"
        />
        <div>
          <ClientOnly>
            <template #fallback>
              <h1 class="text-2xl font-bold text-gray-900 dark:text-white">加载中...</h1>
            </template>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ strategy?.name || '加载中...' }}
              </h1>
              <UBadge
                v-if="strategy"
                :color="statusInfo.color"
                variant="soft"
                size="sm"
              >
                {{ statusInfo.label }}
              </UBadge>
            </div>
            <div v-if="strategy" class="flex items-center gap-2 mt-1 text-sm text-gray-500">
              <span>{{ strategy.creator_name }}</span>
              <span>|</span>
              <span>{{ formatDate(strategy.created_at) }}</span>
            </div>
          </ClientOnly>
        </div>
      </div>

      <ClientOnly>
        <div v-if="strategy" class="flex items-center gap-2">
          <UButton
            variant="outline"
            icon="i-heroicons-arrow-down-tray"
            size="sm"
            @click="handleExport"
          >
            导出 Word
          </UButton>
          <UButton
            variant="outline"
            color="error"
            icon="i-heroicons-trash"
            size="sm"
            @click="handleDelete"
          >
            删除
          </UButton>
        </div>
      </ClientOnly>
    </div>

    <!-- 阶段进度指示器 -->
    <ClientOnly>
      <div v-if="strategy" class="flex items-center justify-center gap-0 py-2">
        <template v-for="(stage, i) in STAGES" :key="stage.key">
          <div class="flex flex-col items-center min-w-20">
            <div
              :class="[
                'w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold transition-colors',
                currentStageIndex > i
                  ? 'bg-primary-500 text-white'
                  : currentStageIndex === i
                    ? 'bg-primary-100 text-primary-700 ring-2 ring-primary-500'
                    : 'bg-gray-100 text-gray-400',
              ]"
            >
              <UIcon v-if="currentStageIndex > i" name="i-heroicons-check" class="text-base" />
              <span v-else>{{ stage.key }}</span>
            </div>
            <span
              :class="[
                'text-xs mt-1 text-center',
                currentStageIndex >= i ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400',
              ]"
            >{{ stage.label }}</span>
          </div>
          <div
            v-if="i < STAGES.length - 1"
            :class="[
              'h-0.5 flex-1 mb-4 transition-colors',
              currentStageIndex > i ? 'bg-primary-400' : 'bg-gray-200',
            ]"
          />
        </template>
      </div>
    </ClientOnly>

    <!-- Loading -->
    <div v-if="pending" class="text-center py-16">
      <p class="text-gray-500">加载中...</p>
    </div>

    <ClientOnly v-if="strategy">
      <template #fallback>
        <div class="space-y-4">
          <div v-for="i in 3" :key="i" class="h-48 bg-gray-100 rounded-lg animate-pulse" />
        </div>
      </template>

      <!-- ===== 阶段 A: 需求对齐 ===== -->
      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-bold text-primary-600">A</span>
            <h2 class="text-lg font-semibold">需求对齐</h2>
          </div>
        </template>

        <!-- Brand Brief 摘要 -->
        <div
          v-if="strategy.brand_brief"
          class="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm space-y-1"
        >
          <div class="flex gap-2">
            <span class="text-gray-400 w-16 shrink-0">品牌</span>
            <span class="font-medium">{{ strategy.brand_brief.brand_name }}</span>
          </div>
          <div class="flex gap-2">
            <span class="text-gray-400 w-16 shrink-0">目标</span>
            <span>{{ strategy.brand_brief.analysis_goal }}</span>
          </div>
          <div v-if="strategy.brand_brief.competitors?.length" class="flex gap-2">
            <span class="text-gray-400 w-16 shrink-0">竞品</span>
            <span>{{ strategy.brand_brief.competitors.join('、') }}</span>
          </div>
          <div v-if="strategy.brand_brief.industry" class="flex gap-2">
            <span class="text-gray-400 w-16 shrink-0">行业</span>
            <span>{{ strategy.brand_brief.industry }}</span>
          </div>
        </div>
        <div v-else class="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-sm text-amber-700 dark:text-amber-300">
          未填写 Brand Brief，建议先更新策略信息以获得更好的 AI 咨询效果。
        </div>

        <!-- 咨询历史 -->
        <div
          v-if="strategy.consultation_rounds?.length"
          class="mb-4 space-y-3"
        >
          <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400">咨询记录</h3>
          <div
            v-for="round in strategy.consultation_rounds"
            :key="round.round_number"
            class="border border-gray-200 dark:border-gray-700 rounded-lg p-3 text-sm space-y-2"
          >
            <div class="text-gray-500">第 {{ round.round_number }} 轮 · 用户：{{ round.user_input }}</div>
            <div class="text-gray-700 dark:text-gray-300">{{ round.ai_response?.understanding_summary }}</div>
            <div v-if="round.ai_response?.monitor_suggestions?.length" class="text-gray-500">
              建议监测：{{ round.ai_response.monitor_suggestions.map(s => s.name).join('、') }}
            </div>
            <div
              v-if="round.ai_response?.clarification_questions?.length"
              class="text-amber-600 dark:text-amber-400"
            >
              追问：{{ round.ai_response.clarification_questions.map(q => q.question).join(' / ') }}
            </div>
          </div>
        </div>

        <!-- 发起新咨询 -->
        <div class="space-y-3">
          <UTextarea
            v-model="consultInput"
            :placeholder="strategy.consultation_rounds?.length ? '补充说明或回答 AI 的追问...' : '（可选）补充说明分析需求，AI 将结合品牌简报规划监测方案'"
            :rows="3"
            class="w-full"
          />
          <div class="flex items-center gap-3">
            <UButton
              :loading="consultLoading"
              :disabled="!!strategy?.consultation_rounds?.length && !consultInput.trim()"
              @click="handleConsult"
            >
              {{ strategy.consultation_rounds?.length ? '继续咨询' : '开始咨询' }}
            </UButton>
            <span v-if="strategy.consultation_rounds?.length" class="text-sm text-gray-500">
              已咨询 {{ strategy.consultation_rounds.length }} 轮
            </span>
          </div>
        </div>

        <!-- 确认计划（有监测建议时显示） -->
        <div
          v-if="latestMonitorSuggestions.length"
          class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700"
        >
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400">
              AI 推荐监测（{{ latestMonitorSuggestions.length }} 个）
            </h3>
          </div>
          <div class="space-y-2 mb-3">
            <div
              v-for="(s, i) in latestMonitorSuggestions"
              :key="i"
              class="flex items-start gap-2 text-sm p-2 bg-blue-50 dark:bg-blue-900/20 rounded"
            >
              <UIcon name="i-heroicons-chart-bar" class="text-blue-500 mt-0.5 shrink-0" />
              <div>
                <span class="font-medium text-blue-700 dark:text-blue-300">{{ s.name }}</span>
                <span v-if="s.rationale" class="text-gray-500 ml-1">— {{ s.rationale }}</span>
              </div>
            </div>
          </div>
          <UButton
            :loading="confirmPlanLoading"
            icon="i-heroicons-check-circle"
            @click="handleConfirmPlan"
          >
            一键创建监测
          </UButton>
          <span v-if="strategy.suggested_monitor_ids?.length" class="ml-3 text-sm text-gray-500">
            已创建 {{ strategy.suggested_monitor_ids.length }} 个监测
          </span>
        </div>
      </UCard>

      <!-- ===== 阶段 B: 数据采集 ===== -->
      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-bold text-primary-600">B</span>
            <h2 class="text-lg font-semibold">��据采集</h2>
          </div>
        </template>

        <div class="flex items-start gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <UIcon name="i-heroicons-information-circle" class="text-blue-500 mt-0.5 shrink-0 text-lg" />
          <div class="text-sm text-blue-700 dark:text-blue-300 space-y-1">
            <p>前往监测页面，启动数据采集任务，待切片分析完成后回来关联切片。</p>
            <UButton
              variant="link"
              size="xs"
              to="/social-media/monitors"
              class="p-0"
            >
              前往监测管理
            </UButton>
          </div>
        </div>
        <div
          v-if="strategy.suggested_monitor_ids?.length"
          class="mt-3 text-sm text-gray-500"
        >
          AI 已为本策略推荐创建 {{ strategy.suggested_monitor_ids.length }} 个监测，ID：
          {{ strategy.suggested_monitor_ids.join(', ') }}
        </div>
      </UCard>

      <!-- ===== 阶段 C: 数据评估 ===== -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-bold text-primary-600">C</span>
              <h2 class="text-lg font-semibold">数据评估</h2>
            </div>
            <span class="text-sm text-gray-500">{{ strategy.slices.length }} 个切片</span>
          </div>
        </template>

        <!-- 已关联切片列表 -->
        <div v-if="strategy.slices.length" class="mb-4">
          <div class="space-y-1">
            <div
              v-for="s in strategy.slices"
              :key="s.slice_id"
              class="flex items-center gap-2 text-sm py-1.5 border-b border-gray-100 dark:border-gray-800 last:border-0"
            >
              <UIcon name="i-heroicons-document-chart-bar" class="text-gray-400 shrink-0" />
              <span class="text-gray-600 dark:text-gray-400">{{ s.monitor_name }}</span>
              <span class="text-gray-300">/</span>
              <span class="font-medium">{{ s.slice_name || `切片 #${s.slice_id}` }}</span>
            </div>
          </div>
        </div>
        <div v-else class="mb-4 text-sm text-gray-400">
          暂未关联任何切片
        </div>

        <!-- 添加切片 -->
        <div class="mb-4">
          <UButton
            variant="outline"
            size="sm"
            icon="i-heroicons-plus"
            @click="showAddSlices = !showAddSlices"
          >
            添加切片
          </UButton>

          <div v-if="showAddSlices" class="mt-3 border border-gray-200 dark:border-gray-700 rounded-lg p-3">
            <div v-if="addMonitorsPending" class="text-sm text-gray-400 py-2">加载监测列表...</div>
            <div v-else-if="addMonitors.length === 0" class="text-sm text-gray-400 py-2">暂无监测</div>
            <div v-else class="space-y-2 max-h-64 overflow-y-auto">
              <div
                v-for="monitor in addMonitors"
                :key="monitor.id"
                class="border border-gray-100 dark:border-gray-700 rounded"
              >
                <button
                  class="w-full flex items-center justify-between p-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
                  @click="toggleAddMonitor(monitor.id)"
                >
                  <div class="flex items-center gap-1">
                    <UIcon
                      :name="addExpandedMonitors.has(monitor.id) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                      class="text-gray-400 text-xs"
                    />
                    <span>{{ monitor.name }}</span>
                  </div>
                </button>
                <div
                  v-if="addExpandedMonitors.has(monitor.id)"
                  class="border-t border-gray-100 dark:border-gray-700 p-2 space-y-1"
                >
                  <div
                    v-if="!addMonitorSlicesMap[monitor.id]?.length"
                    class="text-xs text-gray-400 py-1"
                  >
                    该监测暂无分析切片
                  </div>
                  <label
                    v-for="slice in (addMonitorSlicesMap[monitor.id] || [])"
                    :key="slice.id"
                    class="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer text-sm"
                  >
                    <input
                      type="checkbox"
                      :checked="selectedAddSliceIds.includes(slice.id)"
                      class="rounded border-gray-300"
                      :disabled="isSliceAlreadyLinked(slice.id)"
                      @change="toggleAddSlice(slice.id)"
                    >
                    <span :class="isSliceAlreadyLinked(slice.id) ? 'text-gray-400' : ''">
                      {{ slice.name || `切片 #${slice.id}` }}
                    </span>
                    <span v-if="isSliceAlreadyLinked(slice.id)" class="text-xs text-gray-400">已关联</span>
                  </label>
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2 mt-3">
              <UButton
                size="sm"
                :loading="addSlicesLoading"
                :disabled="selectedAddSliceIds.length === 0"
                @click="handleAddSlices"
              >
                确认关联 {{ selectedAddSliceIds.length > 0 ? `(${selectedAddSliceIds.length})` : '' }}
              </UButton>
              <UButton size="sm" variant="ghost" @click="showAddSlices = false">
                取消
              </UButton>
            </div>
          </div>
        </div>

        <!-- AI 评估 -->
        <div class="flex items-center gap-3 mb-4">
          <UButton
            :loading="evaluateLoading"
            variant="outline"
            icon="i-heroicons-magnifying-glass"
            @click="handleEvaluate"
          >
            AI 评估充分性
          </UButton>
        </div>

        <!-- 评估结果 -->
        <div
          v-if="strategy.evaluation_result"
          class="mb-4 p-3 rounded-lg border"
          :class="strategy.evaluation_result.is_sufficient
            ? 'border-green-200 bg-green-50 dark:bg-green-900/20'
            : 'border-amber-200 bg-amber-50 dark:bg-amber-900/20'"
        >
          <div class="flex items-center gap-2 mb-2">
            <UIcon
              :name="strategy.evaluation_result.is_sufficient ? 'i-heroicons-check-circle' : 'i-heroicons-exclamation-triangle'"
              :class="strategy.evaluation_result.is_sufficient ? 'text-green-500' : 'text-amber-500'"
            />
            <span class="font-medium text-sm">
              综合评分 {{ Math.round(strategy.evaluation_result.overall_score * 100) }}%
              ·
              {{ strategy.evaluation_result.is_sufficient ? '数据充分' : '数据待补充' }}
            </span>
          </div>
          <div v-if="strategy.evaluation_result.gap_analysis?.length" class="space-y-1">
            <div
              v-for="(gap, i) in strategy.evaluation_result.gap_analysis"
              :key="i"
              class="text-xs text-gray-600 dark:text-gray-400"
            >
              · {{ gap.description }}
            </div>
          </div>
        </div>

        <!-- 确认就绪 -->
        <UButton
          :loading="confirmReadyLoading"
          icon="i-heroicons-rocket-launch"
          :disabled="strategy.status === 'completed'"
          @click="handleConfirmReady"
        >
          确认数据就绪，进入策略生成
        </UButton>
        <span
          v-if="['slices_ready', 'phase1_done', 'phase2_done', 'completed'].includes(strategy.status)"
          class="ml-3 text-sm text-green-600 dark:text-green-400"
        >
          已就绪
        </span>
      </UCard>

      <!-- ===== 阶段 D: 策略生成 ===== -->
      <div class="space-y-4">
        <div class="flex items-center gap-2">
          <span class="font-bold text-primary-600">D</span>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">策略生成</h2>
        </div>

        <!-- Phase 1: 洞察层 -->
        <StrategyPhaseCard
          :phase="1"
          title="洞察层"
          :has-result="!!strategy.phase1_result"
          :can-generate="true"
          :can-edit="true"
          :generating="generatingPhase === 1"
          :saving="savingPhase === 1"
          :result="strategy.phase1_result"
          @generate="handleGenerate(1)"
          @save="(r: Record<string, unknown>) => handleSavePhase(1, r)"
        >
          <Phase1Content :result="phase1Data" />
        </StrategyPhaseCard>

        <!-- Phase 2: 策略层 -->
        <StrategyPhaseCard
          :phase="2"
          title="策略层"
          :has-result="!!strategy.phase2_result"
          :can-generate="canGeneratePhase2"
          :can-edit="true"
          :generating="generatingPhase === 2"
          :saving="savingPhase === 2"
          :result="strategy.phase2_result"
          @generate="handleGenerate(2)"
          @save="(r: Record<string, unknown>) => handleSavePhase(2, r)"
        >
          <Phase2Content :result="phase2Data" />
        </StrategyPhaseCard>

        <!-- Phase 3: 创意层 -->
        <StrategyPhaseCard
          :phase="3"
          title="创意层"
          :has-result="!!strategy.phase3_result"
          :can-generate="canGeneratePhase3"
          :can-edit="true"
          :generating="generatingPhase === 3"
          :saving="savingPhase === 3"
          :result="strategy.phase3_result"
          @generate="handleGenerate(3)"
          @save="(r: Record<string, unknown>) => handleSavePhase(3, r)"
        >
          <Phase3Content :result="phase3Data" />
        </StrategyPhaseCard>
      </div>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import type {
  StrategyStatus,
  Phase1Result,
  Phase2Result,
  Phase3Result,
  MonitorSuggestion,
} from '../../../types'
import { UBadge, UButton } from '#components'

definePageMeta({ title: '策略详情' })

// ── 阶段定义 ───────────────────────────────────────────────────────────────��──

const STAGES = [
  { key: 'A', label: '需求对齐' },
  { key: 'B', label: '数据采集' },
  { key: 'C', label: '数据评估' },
  { key: 'D', label: '策略生成' },
] as const

const STATUS_MAP: Record<StrategyStatus, { label: string; color: 'neutral' | 'info' | 'warning' | 'success' }> = {
  briefing: { label: '需求阶段', color: 'neutral' },
  consulting: { label: '咨询中', color: 'info' },
  monitors_created: { label: '监测已创建', color: 'info' },
  slices_ready: { label: '数据就绪', color: 'warning' },
  phase1_done: { label: '洞察完成', color: 'warning' },
  phase2_done: { label: '策略完成', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
}

const STATUS_ORDER: Record<StrategyStatus, number> = {
  briefing: 0, consulting: 1, monitors_created: 2,
  slices_ready: 3, phase1_done: 4, phase2_done: 5, completed: 6,
}

// ── 基础数据 ──────────────────────────────────────────────────────────────────

const route = useRoute()
const strategiesApi = useStrategies()
const { apiRequest, useApiData: useApiDataFn } = useApi()

const strategyId = computed(() => Number(route.params.id))
const { data: strategy, pending, refresh } = strategiesApi.getStrategy(strategyId)

// ── 状态计算 ──────────────────────────────────────────────────────────────────

const statusInfo = computed(() => {
  const s = strategy.value?.status as StrategyStatus
  return STATUS_MAP[s] || { label: s, color: 'neutral' as const }
})

const currentStatusOrder = computed(() => {
  const s = strategy.value?.status as StrategyStatus
  return STATUS_ORDER[s] ?? 0
})

const currentStageIndex = computed(() => {
  const o = currentStatusOrder.value
  if (o <= 1) return 0
  if (o === 2) return 1
  if (o === 3) return 2
  return 3
})

const canGeneratePhase2 = computed(() => currentStatusOrder.value >= STATUS_ORDER.phase1_done)
const canGeneratePhase3 = computed(() => currentStatusOrder.value >= STATUS_ORDER.phase2_done)

const phase1Data = computed(() => (strategy.value?.phase1_result || null) as Phase1Result | null)
const phase2Data = computed(() => (strategy.value?.phase2_result || null) as Phase2Result | null)
const phase3Data = computed(() => (strategy.value?.phase3_result || null) as Phase3Result | null)

const latestMonitorSuggestions = computed<MonitorSuggestion[]>(() => {
  const rounds = strategy.value?.consultation_rounds
  if (!rounds?.length) return []
  return rounds[rounds.length - 1]?.ai_response?.monitor_suggestions ?? []
})

// ── Panel A: 咨询 ─────────────────────────────────────────────────────────────

const consultInput = ref('')
const consultLoading = ref(false)
const confirmPlanLoading = ref(false)

const handleConsult = async () => {
  // 第一轮：brand_brief 已包含品牌信息，输入可为空；后续轮次必须有输入
  const hasRounds = !!strategy.value?.consultation_rounds?.length
  if (hasRounds && !consultInput.value.trim()) return
  consultLoading.value = true
  try {
    const input = consultInput.value.trim() || '请根据品牌简报帮我规划监测方案'
    await strategiesApi.consult(strategyId.value, input)
    consultInput.value = ''
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    consultLoading.value = false
  }
}

const handleConfirmPlan = async () => {
  if (!latestMonitorSuggestions.value.length) return
  confirmPlanLoading.value = true
  try {
    await strategiesApi.confirmPlan(strategyId.value, latestMonitorSuggestions.value)
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    confirmPlanLoading.value = false
  }
}

// ── Panel C: 切片 + 评估 ──────────────────────────────────────────────────────

interface AddMonitorItem { id: number; name: string }
interface AddSliceItem { id: number; name: string | null; monitor_id: number; created_at: string }

const showAddSlices = ref(false)
const addExpandedMonitors = ref(new Set<number>())
const addMonitorSlicesMap = ref<Record<number, AddSliceItem[]>>({})
const selectedAddSliceIds = ref<number[]>([])
const addSlicesLoading = ref(false)
const evaluateLoading = ref(false)
const confirmReadyLoading = ref(false)

const { data: addMonitorsData, pending: addMonitorsPending } = useApiDataFn<{
  items: AddMonitorItem[]
}>('/social-media/monitors?page_size=100', { key: 'strategy-detail-monitors' })

const addMonitors = computed(() => addMonitorsData.value?.items || [])

const isSliceAlreadyLinked = (sliceId: number) => {
  return strategy.value?.slices.some(s => s.slice_id === sliceId) ?? false
}

const toggleAddMonitor = async (monitorId: number) => {
  if (addExpandedMonitors.value.has(monitorId)) {
    addExpandedMonitors.value.delete(monitorId)
  } else {
    addExpandedMonitors.value.add(monitorId)
    if (!addMonitorSlicesMap.value[monitorId]) {
      try {
        const result = await apiRequest<{ items: AddSliceItem[] }>(
          `/social-media/analysis/monitors/${monitorId}/slices`
        )
        addMonitorSlicesMap.value = { ...addMonitorSlicesMap.value, [monitorId]: result.items }
      } catch {
        addMonitorSlicesMap.value = { ...addMonitorSlicesMap.value, [monitorId]: [] }
      }
    }
  }
}

const toggleAddSlice = (sliceId: number) => {
  const idx = selectedAddSliceIds.value.indexOf(sliceId)
  if (idx >= 0) {
    selectedAddSliceIds.value = selectedAddSliceIds.value.filter(id => id !== sliceId)
  } else {
    selectedAddSliceIds.value = [...selectedAddSliceIds.value, sliceId]
  }
}

const handleAddSlices = async () => {
  if (!selectedAddSliceIds.value.length) return
  addSlicesLoading.value = true
  try {
    await strategiesApi.addSlices(strategyId.value, selectedAddSliceIds.value)
    selectedAddSliceIds.value = []
    showAddSlices.value = false
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    addSlicesLoading.value = false
  }
}

const handleEvaluate = async () => {
  evaluateLoading.value = true
  try {
    await strategiesApi.evaluate(strategyId.value)
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    evaluateLoading.value = false
  }
}

const handleConfirmReady = async () => {
  confirmReadyLoading.value = true
  try {
    await strategiesApi.confirmReady(strategyId.value)
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    confirmReadyLoading.value = false
  }
}

// ── Panel D: Phase 生成 ───────────────────────────────────────────────────────

const generatingPhase = ref<1 | 2 | 3 | null>(null)
const savingPhase = ref<1 | 2 | 3 | null>(null)

const handleGenerate = async (phase: 1 | 2 | 3) => {
  generatingPhase.value = phase
  try {
    await strategiesApi.generatePhase(strategyId.value, phase)
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    generatingPhase.value = null
  }
}

const handleSavePhase = async (phase: 1 | 2 | 3, result: Record<string, unknown>) => {
  savingPhase.value = phase
  try {
    await strategiesApi.editPhase(strategyId.value, phase, result)
    await refresh()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    savingPhase.value = null
  }
}

// ── 工具函数 ───────���──────────────────────────────────────────────────────────

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const handleExport = async () => {
  if (!strategy.value) return
  try {
    await strategiesApi.exportStrategy(strategyId.value, strategy.value.name)
  } catch {
    // 错误已由 useApi 处理
  }
}

const handleDelete = async () => {
  if (!strategy.value) return
  try {
    const { $confirm } = useNuxtApp()
    const confirmed = await $confirm(`确定要删除策略「${strategy.value.name}」吗？`)
    if (!confirmed) return

    await strategiesApi.deleteStrategy(strategyId.value)
    navigateTo('/strategies')
  } catch {
    // 错误已由 useApi 处理
  }
}
</script>
