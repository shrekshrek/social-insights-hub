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
          <UButton variant="outline" icon="i-heroicons-arrow-down-tray" @click="handleExport">
            导出 Word
          </UButton>
          <UButton variant="outline" color="error" icon="i-heroicons-trash" @click="handleDelete">
            删除
          </UButton>
        </div>
      </ClientOnly>
    </div>

    <!-- 阶段进度指示器 -->
    <ClientOnly>
      <div v-if="strategy" class="flex items-center justify-center gap-0 py-2">
        <template v-for="(stage, i) in STAGES" :key="stage.key">
          <div class="flex flex-col items-center min-w-24">
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
              <span v-else>{{ i + 1 }}</span>
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

      <!-- ===== ① 研究设计 (draft / planned) ===== -->
      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-bold text-primary-600">①</span>
            <h2 class="text-lg font-semibold">研究设计</h2>
          </div>
        </template>

        <!-- Brand Brief 摘要 -->
        <div
          v-if="strategy.brand_brief"
          class="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm"
        >
          <div v-if="!editingBrief">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <span class="font-medium">{{ strategy.brand_brief.subject }}</span>
                <span class="text-gray-400 mx-1.5">·</span>
                <span class="text-gray-600 dark:text-gray-400">{{ strategy.brand_brief.analysis_goal }}</span>
              </div>
              <UButton variant="ghost" size="xs" icon="i-heroicons-pencil-square" class="shrink-0" @click="startEditBrief" />
            </div>
            <div v-if="strategy.brand_brief.constraints" class="text-gray-400 mt-1">
              {{ strategy.brand_brief.constraints }}
            </div>
            <div
              v-if="strategy.brand_brief.channel_plan?.length"
              class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700 space-y-1.5"
            >
              <div
                v-for="item in strategy.brand_brief.channel_plan"
                :key="item.type"
                class="flex items-start gap-1.5 text-xs"
              >
                <UIcon
                  :name="item.available ? 'i-heroicons-check-circle' : 'i-heroicons-lock-closed'"
                  class="w-3.5 h-3.5 mt-0.5 flex-shrink-0"
                  :class="item.available ? 'text-primary-500' : 'text-gray-400'"
                />
                <div class="min-w-0 flex items-center gap-1.5 flex-wrap">
                  <span :class="item.available ? 'font-medium text-gray-700 dark:text-gray-300' : 'text-gray-400'">
                    {{ CHANNEL_LABELS[item.type] ?? item.type }}
                  </span>
                  <span
                    v-if="item.solvable.length > 0"
                    class="text-gray-400"
                  >{{ item.solvable.length }} 项</span>
                  <span v-if="item.solvable.length" class="text-gray-400">
                    · {{ item.solvable.join(' · ') }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="flex flex-col gap-3">
            <div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">研究主体</label>
              <UInput v-model="editBrief.subject" placeholder="输入品牌或产品名称" size="sm" class="w-full" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">分析目标</label>
              <UTextarea v-model="editBrief.analysis_goal" placeholder="描述分析目标" :rows="2" size="sm" class="w-full" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">补充说明（可选）</label>
              <UTextarea v-model="editBrief.constraints" placeholder="例如：重点关注某些竞品..." :rows="2" size="sm" class="w-full" />
            </div>
            <div class="flex items-center gap-2">
              <UButton size="xs" :loading="savingBrief" :disabled="!editBrief.subject.trim() || !editBrief.analysis_goal.trim()" @click="handleSaveBrief">
                保存
              </UButton>
              <UButton size="xs" variant="ghost" @click="editingBrief = false">取消</UButton>
            </div>
          </div>
        </div>

        <!-- 未生成研究计划 -->
        <div v-if="!hasResearchDesign">
          <UButton :loading="designLoading" icon="i-heroicons-sparkles" @click="handleDesignResearch">
            生成研究计划
          </UButton>
        </div>

        <!-- 已有研究计划 -->
        <div v-else>
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400">AI 研究计划</h3>
            <UButton
              v-if="!editingPlan"
              variant="ghost" size="xs" icon="i-heroicons-pencil-square"
              @click="editingPlan = true"
            >
              编辑
            </UButton>
            <UButton
              v-else
              variant="ghost" size="xs" icon="i-heroicons-check"
              @click="editingPlan = false"
            >
              完成编辑
            </UButton>
          </div>

          <ResearchPlanEditor
            :understanding-summary="researchDesign?.understanding_summary"
            :research-questions="researchDesign?.research_questions || []"
            :data-plan="editableDataPlan"
            :slice-blueprint="editableBlueprint"
            :output-type="researchDesign?.output_type"
            :output-type-rationale="researchDesign?.output_type_rationale"
            :editing="editingPlan"
            :notes-per-task="notesPerTask"
            @update:data-plan="editableDataPlan = $event"
            @update:slice-blueprint="editableBlueprint = $event"
            @update:notes-per-task="notesPerTask = $event"
          />

          <div class="mt-4 flex items-center gap-3">
            <UButton
              :loading="confirmResearchLoading"
              icon="i-heroicons-check-circle"
              :disabled="!editableDataPlan.length || isPollingActive"
              @click="handleConfirmResearch"
            >
              {{ currentStatusOrder >= STATUS_ORDER.probing ? '重新确认并采集' : '确认并开始采集' }}
            </UButton>
            <UButton variant="outline" :loading="designLoading" icon="i-heroicons-arrow-path" @click="handleDesignResearch">
              重新生成计划
            </UButton>
          </div>
        </div>

        <!-- 已进入后续阶段 -->
        <div
          v-if="currentStatusOrder >= STATUS_ORDER.probing"
          class="pt-4 mt-2 border-t border-gray-100 dark:border-gray-800 flex items-center gap-2"
        >
          <UIcon name="i-heroicons-check-circle" class="text-green-500 size-4" />
          <span class="text-sm text-green-600 dark:text-green-400">研究计划已确认，采集进行中</span>
        </div>
      </UCard>

      <!-- ===== ② 探测验证 (probing) ===== -->
      <UCard v-if="currentStatusOrder >= STATUS_ORDER.probing">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-bold text-primary-600">②</span>
            <h2 class="text-lg font-semibold">探测验证</h2>
            <UBadge v-if="strategy.probe_round > 0" variant="soft" size="xs" color="neutral">
              第 {{ strategy.probe_round + 1 }} 轮
            </UBadge>
          </div>
        </template>

        <ProbeReportPanel
          :tasks="probeData.tasks"
          :analyzed-count="probeData.analyzedCount"
          :total-count="probeData.totalCount"
          :all-analyzed="probeData.allAnalyzed"
          :probe-review="probeData.probeReview"
          :task-dimension-map="taskDimensionMap"
          :dimension-names="dimensionNames"
        />

        <div v-if="probeData.probeReview && strategy.status === 'probing'" class="flex items-center gap-3 mt-4">
          <UButton :loading="approveProbeLoading" icon="i-heroicons-check-circle" @click="handleApproveProbe">
            {{ probeData.probeReview?.overall_verdict === 'all_pass' ? '确认继续' : '忽略问题，继续采集' }}
          </UButton>
          <UButton
            v-if="probeData.probeReview?.overall_verdict !== 'all_pass' && probeData.probeReview?.refinement_suggestions?.length"
            variant="outline" :loading="refineProbeLoading" icon="i-heroicons-arrow-path"
            @click="handleRefineProbe"
          >
            按建议调整关键词
          </UButton>
        </div>

        <div
          v-if="currentStatusOrder >= STATUS_ORDER.collecting"
          class="pt-4 mt-2 border-t border-gray-100 dark:border-gray-800 flex items-center gap-2"
        >
          <UIcon name="i-heroicons-check-circle" class="text-green-500 size-4" />
          <span class="text-sm text-green-600 dark:text-green-400">探测已通过，全量采集进行中</span>
        </div>
      </UCard>

      <!-- ===== ③ 数据就绪 (collecting / ready) ===== -->
      <UCard v-if="currentStatusOrder >= STATUS_ORDER.collecting">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-bold text-primary-600">③</span>
              <h2 class="text-lg font-semibold">数据就绪</h2>
            </div>
            <UButton
              v-if="collectionData.slices.length"
              variant="outline" size="sm" icon="i-heroicons-adjustments-horizontal"
              @click="sliceAdjustOpen = true"
            >
              微调切片
            </UButton>
          </div>
        </template>

        <DataOverviewPanel
          :slices="collectionData.slices"
          :completed-count="collectionData.completedCount"
          :total-count="collectionData.totalCount"
          :all-analyzed="collectionData.allAnalyzed"
          :show-progress="!collectionData.allAnalyzed"
          :coverage-result="collectionData.coverageResult"
        />

        <div
          v-if="currentStatusOrder >= STATUS_ORDER.ready"
          class="pt-4 mt-2 border-t border-gray-100 dark:border-gray-800 flex items-center gap-2"
        >
          <UIcon name="i-heroicons-check-circle" class="text-green-500 size-4" />
          <span class="text-sm text-green-600 dark:text-green-400">数据已就绪，可进行策略生成</span>
        </div>

        <SliceAdjustModal
          v-model:open="sliceAdjustOpen"
          :slices="collectionData.slices"
          :saving="adjustSlicesLoading"
          @save="handleAdjustSlices"
        />
      </UCard>

      <!-- ===== ④ 产出生成 ===== -->
      <div v-if="currentStatusOrder >= STATUS_ORDER.ready" class="space-y-4">
        <div class="flex items-center gap-2">
          <span class="font-bold text-primary-600">④</span>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">产出生成</h2>
        </div>

        <StrategyPhaseCard
          :phase="1" title="洞察层"
          :has-result="!!strategy.phase1_result" :can-generate="true" :can-edit="true"
          :generating="generatingPhase === 1" :saving="savingPhase === 1" :result="strategy.phase1_result"
          @generate="handleGenerate(1)" @save="(r: Record<string, unknown>) => handleSavePhase(1, r)"
        >
          <Phase1Content :result="phase1Data" />
        </StrategyPhaseCard>

        <StrategyPhaseCard
          :phase="2" title="策略层"
          :has-result="!!strategy.phase2_result" :can-generate="canGeneratePhase2" :can-edit="true"
          :generating="generatingPhase === 2" :saving="savingPhase === 2" :result="strategy.phase2_result"
          @generate="handleGenerate(2)" @save="(r: Record<string, unknown>) => handleSavePhase(2, r)"
        >
          <Phase2Content :result="phase2Data" />
        </StrategyPhaseCard>

        <StrategyPhaseCard
          :phase="3" title="创意层"
          :has-result="!!strategy.phase3_result" :can-generate="canGeneratePhase3" :can-edit="true"
          :generating="generatingPhase === 3" :saving="savingPhase === 3" :result="strategy.phase3_result"
          @generate="handleGenerate(3)" @save="(r: Record<string, unknown>) => handleSavePhase(3, r)"
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
  DataPlanItem,
  SliceBlueprintItem,
  AdjustSliceItem,
} from '../../../types'
import { STATUS_MAP, STATUS_ORDER, formatDate, CHANNEL_LABELS } from '../../../composables/useStrategyConstants'
import { useStrategyPolling } from '../../../composables/useStrategyPolling'

definePageMeta({ title: '策略详情' })

const STAGES = [
  { key: '1', label: '研究设计' },
  { key: '2', label: '探测验证' },
  { key: '3', label: '数据就绪' },
  { key: '4', label: '产出生成' },
] as const

// ── 基础数据 ──────────────────────────────────────────────────────────────────

const route = useRoute()
const strategiesApi = useStrategies()

const strategyId = computed(() => Number(route.params.id))
const { data: strategy, pending } = strategiesApi.getStrategy(strategyId)

// ── 轮询 ──────────────────────────────────────────────────────────────────────

const {
  probeData,
  collectionData,
  isPollingActive,
  startProbePolling,
  stopProbePolling,
  startCollectionPolling,
  stopCollectionPolling,
  initPollingFromStatus,
  initFromStrategy,
} = useStrategyPolling(strategyId, strategy)

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
  if (o <= 1) return 0   // draft, planned → ①
  if (o === 2) return 1   // probing → ②
  if (o <= 3) return 2   // collecting → ③
  return 3               // ready, phase1_done, phase2_done, completed → ④
})

const canGeneratePhase2 = computed(() => currentStatusOrder.value >= STATUS_ORDER.phase1_done)
const canGeneratePhase3 = computed(() => currentStatusOrder.value >= STATUS_ORDER.phase2_done)

const taskDimensionMap = computed(() => {
  const rd = strategy.value?.research_design as Record<string, unknown> | null | undefined
  return (rd?._task_dimension_map as Record<string, string> | undefined) ?? {}
})
const dimensionNames = computed(() =>
  strategy.value?.research_design?.data_plan?.map(d => d.dimension_name) ?? []
)

const phase1Data = computed(() => (strategy.value?.phase1_result || null) as Phase1Result | null)
const phase2Data = computed(() => (strategy.value?.phase2_result || null) as Phase2Result | null)
const phase3Data = computed(() => (strategy.value?.phase3_result || null) as Phase3Result | null)

// 初始化轮询（页面加载时策略已处于 probing/collecting 状态）
// immediate: true 确保 SSR payload 已有数据时也能触发
let pollingInitialized = false
watch(() => strategy.value, (s) => {
  if (s && !pollingInitialized) {
    pollingInitialized = true
    initFromStrategy(s)
    initPollingFromStatus(s.status)
  }
}, { immediate: true })

// ── ① 研究设计 ────────────────────────────────────────────────────────────────

const researchDesign = computed(() => strategy.value?.research_design || null)
const hasResearchDesign = computed(() => {
  const rd = researchDesign.value
  return rd && rd.data_plan?.length > 0
})

const editingBrief = ref(false)
const editBrief = ref({ subject: '', analysis_goal: '', constraints: '' })
const savingBrief = ref(false)
const designLoading = ref(false)
const confirmResearchLoading = ref(false)
const editingPlan = ref(false)
const editableDataPlan = ref<DataPlanItem[]>([])
const editableBlueprint = ref<SliceBlueprintItem[]>([])
const notesPerTask = ref(50)

// 深拷贝研究计划（确保嵌套数组不共享引用）
const deepCopyDataPlan = (items: DataPlanItem[]): DataPlanItem[] =>
  items.map(dp => ({ ...dp, keywords: [...(dp.keywords || [])], platforms: [...(dp.platforms || [])] }))

const deepCopyBlueprint = (items: SliceBlueprintItem[]): SliceBlueprintItem[] =>
  items.map(sb => ({
    ...sb,
    source_dimensions: [...(sb.source_dimensions || [])],
    competitors: sb.competitors ? [...sb.competitors] : undefined,
    serves_questions: sb.serves_questions ? [...sb.serves_questions] : undefined,
  }))

watch(researchDesign, (rd) => {
  if (rd) {
    if (rd.data_plan?.length && !editableDataPlan.value.length) {
      editableDataPlan.value = deepCopyDataPlan(rd.data_plan)
    }
    if (rd.slice_blueprint?.length && !editableBlueprint.value.length) {
      editableBlueprint.value = deepCopyBlueprint(rd.slice_blueprint)
    }
  }
}, { immediate: true })

// 新创建的策略自动生成研究计划
watch(() => strategy.value, (s) => {
  if (s && s.status === 'draft' && !s.research_design) {
    handleDesignResearch()
  }
}, { once: true })

const startEditBrief = () => {
  const b = strategy.value?.brand_brief
  editBrief.value = {
    subject: b?.subject || '',
    analysis_goal: b?.analysis_goal || '',
    constraints: b?.constraints || '',
  }
  editingBrief.value = true
}

const handleSaveBrief = async () => {
  if (!editBrief.value.subject.trim() || !editBrief.value.analysis_goal.trim()) return
  savingBrief.value = true
  try {
    await strategiesApi.updateStrategy(strategyId.value, {
      brand_brief: {
        subject: editBrief.value.subject.trim(),
        analysis_goal: editBrief.value.analysis_goal.trim(),
        constraints: editBrief.value.constraints.trim() || undefined,
        channel_plan: strategy.value?.brand_brief?.channel_plan ?? undefined,
      },
    })
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    editingBrief.value = false
    if (hasResearchDesign.value) {
      await handleDesignResearch()
    }
  } catch {
    // 错误已由 useApi 处理
  } finally {
    savingBrief.value = false
  }
}

const handleDesignResearch = async () => {
  designLoading.value = true
  try {
    await strategiesApi.designResearch(strategyId.value, '')
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    const rd = strategy.value?.research_design
    if (rd) {
      editableDataPlan.value = deepCopyDataPlan(rd.data_plan || [])
      editableBlueprint.value = deepCopyBlueprint(rd.slice_blueprint || [])
    }
    editingPlan.value = false
  } catch {
    // 错误已由 useApi 处理
  } finally {
    designLoading.value = false
  }
}

const handleConfirmResearch = async () => {
  if (!editableDataPlan.value.length) return
  // 如果已有采集任务，需要确认
  if (currentStatusOrder.value >= STATUS_ORDER.probing) {
    const { $confirm } = useNuxtApp()
    const confirmed = await $confirm('将删除已创建的采集任务和切片，重新开始采集。确定继续？')
    if (!confirmed) return
  }
  confirmResearchLoading.value = true
  try {
    if (currentStatusOrder.value >= STATUS_ORDER.probing) {
      stopProbePolling()
      stopCollectionPolling()
      await strategiesApi.resetToDesign(strategyId.value)
    }
    const rd = researchDesign.value
    await strategiesApi.confirmResearch(strategyId.value, {
      research_design: {
        ...(rd || {}),
        data_plan: editableDataPlan.value,
        slice_blueprint: editableBlueprint.value,
      },
      notes_per_task: notesPerTask.value,
      probe_notes: 20,
    })
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    editingPlan.value = false
    // 重置探测数据，避免旧结果残留
    probeData.tasks = []
    probeData.analyzedCount = 0
    probeData.totalCount = 0
    probeData.allAnalyzed = false
    probeData.probeReview = null
    startProbePolling()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    confirmResearchLoading.value = false
  }
}

// ── ② 探测验证 ────────────────────────────────────────────────────────────────

const approveProbeLoading = ref(false)
const refineProbeLoading = ref(false)

const handleApproveProbe = async () => {
  approveProbeLoading.value = true
  try {
    const result = await strategiesApi.approveProbe(strategyId.value)
    strategy.value = result.strategy
    startCollectionPolling()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    approveProbeLoading.value = false
  }
}

const handleRefineProbe = async () => {
  const suggestions = probeData.probeReview?.refinement_suggestions
  if (!suggestions?.length) return

  const detail = suggestions
    .map(s => `${s.original_keyword} → ${s.suggested_keyword}`)
    .join('、')
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm(`将替换 ${suggestions.length} 个关键词：${detail}，确定继续？`)
  if (!confirmed) return

  refineProbeLoading.value = true
  try {
    const result = await strategiesApi.refineProbe(strategyId.value, {
      refinements: suggestions.map(s => ({
        task_id: s.task_id,
        new_keyword: s.suggested_keyword,
        platform: s.platform,
      })),
    })
    strategy.value = result.strategy
    probeData.probeReview = null
    startProbePolling()
  } catch {
    // 错误已由 useApi 处理
  } finally {
    refineProbeLoading.value = false
  }
}

// ── ③ 数据就绪 ────────────────────────────────────────────────────────────────

const sliceAdjustOpen = ref(false)
const adjustSlicesLoading = ref(false)

const handleAdjustSlices = async (adjustments: AdjustSliceItem[]) => {
  adjustSlicesLoading.value = true
  try {
    const result = await strategiesApi.adjustSlices(strategyId.value, { adjustments })
    strategy.value = result
    collectionData.slices = result.slices
    collectionData.coverageResult = result.coverage_check_result
    sliceAdjustOpen.value = false
  } catch {
    // 错误已由 useApi 处理
  } finally {
    adjustSlicesLoading.value = false
  }
}

// ── ④ Phase 生成 ────────────────────────────────────────────────────────────

const generatingPhase = ref<1 | 2 | 3 | null>(null)
const savingPhase = ref<1 | 2 | 3 | null>(null)

const handleGenerate = async (phase: 1 | 2 | 3) => {
  generatingPhase.value = phase
  try {
    await strategiesApi.generatePhase(strategyId.value, phase)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
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
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    savingPhase.value = null
  }
}

// ── 工具函数 ────────────────────────────────────────────────────────────────────

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
