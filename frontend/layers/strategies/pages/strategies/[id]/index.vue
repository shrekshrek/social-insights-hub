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
              <span>{{ strategy.user_username }}</span>
              <span>|</span>
              <span>{{ formatDate(strategy.created_at) }}</span>
            </div>
            <div v-if="strategy" class="flex items-center gap-2 mt-1 text-sm text-gray-500">
              <span class="shrink-0">参与者:</span>
              <template v-if="strategy.participant_ids?.length">
                <UBadge
                  v-for="(pid, i) in strategy.participant_ids"
                  :key="pid"
                  color="neutral"
                  variant="soft"
                  size="sm"
                >
                  {{ strategy.participant_usernames?.[i] || pid }}
                </UBadge>
              </template>
              <span v-else class="text-gray-400">暂无</span>
              <UButton
                v-if="strategy.user_id === currentUserId"
                variant="ghost"
                size="xs"
                icon="i-heroicons-pencil-square"
                @click="showParticipantsModal = true"
              />
            </div>
          </ClientOnly>
        </div>
      </div>

      <ClientOnly>
        <div v-if="strategy" class="flex items-center gap-2">
          <UButton variant="outline" icon="i-heroicons-arrow-down-tray" @click="handleExport">
            导出 Word
          </UButton>
          <UButton v-if="canDelete" variant="ghost" color="error" icon="i-heroicons-trash" @click="handleDelete">
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
              <UButton v-if="canEdit" variant="ghost" size="xs" icon="i-heroicons-pencil-square" class="shrink-0" @click="startEditBrief" />
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
              v-if="canEdit && !editingPlan"
              variant="ghost" size="xs" icon="i-heroicons-pencil-square"
              @click="editingPlan = true"
            >
              编辑
            </UButton>
            <UButton
              v-if="canEdit && editingPlan"
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
            :output-type="selectedOutputType"
            :output-type-rationale="researchDesign?.output_type_rationale"
            :editing="editingPlan"
            :notes-per-task="notesPerTask"
            @update:data-plan="editableDataPlan = $event"
            @update:slice-blueprint="editableBlueprint = $event"
            @update:notes-per-task="notesPerTask = $event"
            @update:output-type="selectedOutputType = $event"
          />

          <div class="mt-4 flex flex-col gap-2">
            <div class="flex items-center gap-3">
              <UButton
                :loading="confirmResearchLoading"
                icon="i-heroicons-check-circle"
                :disabled="!!confirmResearchIssue || isPollingActive"
                @click="handleConfirmResearch"
              >
                {{ currentStatusOrder >= STATUS_ORDER.probing ? '重新确认并采集' : '确认并开始采集' }}
              </UButton>
              <UButton variant="outline" :loading="designLoading" icon="i-heroicons-arrow-path" @click="handleDesignResearch">
                重新生成计划
              </UButton>
            </div>
            <p v-if="confirmResearchIssue" class="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
              <UIcon name="i-heroicons-exclamation-triangle" class="size-3.5" />
              {{ confirmResearchIssue }}
            </p>
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
          <UBadge variant="soft" size="xs" :color="isBrandStrategyPath ? 'primary' : 'warning'">
            {{ isBrandStrategyPath ? '品牌策略路径' : '市场分析报告路径' }}
          </UBadge>
        </div>

        <!-- brand_strategy 路径：Insight → Brand Role → Big Idea -->
        <template v-if="isBrandStrategyPath">
          <BrandStrategyStageCard
            stage="insight" title="Insight 洞察"
            :has-result="!!strategy.insight_result" :can-generate="true" :can-edit="canEdit"
            :generating="generatingBrandStrategyStage === 'insight'" :saving="savingBrandStrategyStage === 'insight'"
            :result="strategy.insight_result"
            @generate="handleGenerateBrandStrategyStage('insight')"
            @save="(r: Record<string, unknown>) => handleSaveBrandStrategyStage('insight', r)"
          >
            <InsightContent :result="insightData" />
          </BrandStrategyStageCard>

          <BrandStrategyStageCard
            stage="brand_role" title="Brand Role 品牌角色"
            :has-result="!!strategy.brand_role_result" :can-generate="canGenerateBrandRole" :can-edit="canEdit"
            :generating="generatingBrandStrategyStage === 'brand_role'" :saving="savingBrandStrategyStage === 'brand_role'"
            :result="strategy.brand_role_result"
            @generate="handleGenerateBrandStrategyStage('brand_role')"
            @save="(r: Record<string, unknown>) => handleSaveBrandStrategyStage('brand_role', r)"
          >
            <BrandRoleContent :result="brandRoleData" />
          </BrandStrategyStageCard>

          <BrandStrategyStageCard
            stage="big_idea" title="Big Idea 创意"
            :has-result="!!strategy.big_idea_result" :can-generate="canGenerateBigIdea" :can-edit="canEdit"
            :generating="generatingBrandStrategyStage === 'big_idea'" :saving="savingBrandStrategyStage === 'big_idea'"
            :result="strategy.big_idea_result"
            @generate="handleGenerateBrandStrategyStage('big_idea')"
            @save="(r: Record<string, unknown>) => handleSaveBrandStrategyStage('big_idea', r)"
          >
            <BigIdeaContent :result="bigIdeaData" />
          </BrandStrategyStageCard>
        </template>

        <!-- market_report 路径：Agenda Map → Landscape → Strategic Brief -->
        <template v-else-if="isMarketReportPath">
          <MarketReportStageCard
            stage="agenda_map" title="Agenda Map 媒体议程图"
            :has-result="!!strategy.agenda_map_result" :can-generate="true"
            :generating="generatingMarketReportStage === 'agenda_map'" :result="strategy.agenda_map_result"
            @generate="handleGenerateMarketReportStage('agenda_map')"
          >
            <AgendaMapContent :result="agendaMapData" />
          </MarketReportStageCard>

          <MarketReportStageCard
            stage="landscape" title="Landscape 竞争格局"
            :has-result="!!strategy.landscape_result" :can-generate="canGenerateLandscape"
            :generating="generatingMarketReportStage === 'landscape'" :result="strategy.landscape_result"
            @generate="handleGenerateMarketReportStage('landscape')"
          >
            <LandscapeContent :result="landscapeData" />
          </MarketReportStageCard>

          <MarketReportStageCard
            stage="strategic_brief" title="Strategic Brief 战略简报"
            :has-result="!!strategy.strategic_brief_result" :can-generate="canGenerateStrategicBrief"
            :generating="generatingMarketReportStage === 'strategic_brief'" :result="strategy.strategic_brief_result"
            @generate="handleGenerateMarketReportStage('strategic_brief')"
          >
            <StrategicBriefContent :result="strategicBriefData" />
          </MarketReportStageCard>
        </template>
      </div>
    </ClientOnly>

    <!-- 参与者管理弹窗 -->
    <ClientOnly>
      <UModal
        v-model:open="showParticipantsModal"
        title="管理参与者"
        :ui="{ footer: 'justify-end' }"
      >
        <template #body>
          <UFormField help="参与者变更会立即生效，无需点保存">
            <ParticipantsManager
              v-if="strategy"
              :participants="(strategy!.participant_ids || []).map((id: number, i: number) => ({ id, username: strategy!.participant_usernames?.[i] || String(id) }))"
              :owner-id="strategy!.user_id"
              :can-manage="true"
              :on-add="async (ids: number[]) => { await strategiesApi.addParticipant(strategyId, ids); await refreshStrategy() }"
              :on-remove="async (uid: number) => { await strategiesApi.removeParticipant(strategyId, uid); await refreshStrategy() }"
            />
          </UFormField>
        </template>
        <template #footer>
          <UButton variant="outline" @click="showParticipantsModal = false">
            关闭
          </UButton>
        </template>
      </UModal>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import type {
  StrategyStatus,
  InsightResult,
  BrandRoleResult,
  BigIdeaResult,
  AgendaMapResult,
  LandscapeResult,
  StrategicBriefResult,
  DataPlanItem,
  SliceBlueprintItem,
  AdjustSliceItem,
  OutputType,
} from '../../../types'
import type { BrandStrategyStage, MarketReportStage } from '../../../composables/useStrategies'
import { STATUS_MAP, STATUS_ORDER, formatDate, CHANNEL_LABELS } from '../../../composables/useStrategyConstants'
import { useStrategyPolling } from '../../../composables/useStrategyPolling'
import { PERMISSIONS } from '~/config/permissions'

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
const { currentUserId, hasPermission } = usePermissions()
const canEdit = computed(() =>
  hasPermission(PERMISSIONS.STRATEGY_WRITE) || strategy.value?.user_id === currentUserId.value
)
const canDelete = computed(() =>
  hasPermission(PERMISSIONS.STRATEGY_DELETE) || strategy.value?.user_id === currentUserId.value
)

const strategyId = computed(() => Number(route.params.id))
const { data: strategy, pending, refresh: refreshStrategy } = strategiesApi.getStrategy(strategyId)
const showParticipantsModal = ref(false)

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
  return 3               // ready, insight_done, brand_role_done, agenda_map_done, landscape_done, completed → ④
})

// brand_strategy 路径门控：Insight → Brand Role → Big Idea
const canGenerateBrandRole = computed(() => currentStatusOrder.value >= STATUS_ORDER.insight_done)
const canGenerateBigIdea = computed(() => currentStatusOrder.value >= STATUS_ORDER.brand_role_done)

// market_report 路径门控：Agenda Map → Landscape → Strategic Brief
const canGenerateLandscape = computed(() => currentStatusOrder.value >= STATUS_ORDER.agenda_map_done)
const canGenerateStrategicBrief = computed(() => currentStatusOrder.value >= STATUS_ORDER.landscape_done)

/** 策略实际的产出路径（以 strategy.output_type 为准；编辑研究计划时以用户选择为准） */
const effectivePathType = computed<OutputType>(() =>
  strategy.value?.output_type ?? selectedOutputType.value,
)
const isBrandStrategyPath = computed(() => effectivePathType.value === 'brand_strategy')
const isMarketReportPath = computed(() => effectivePathType.value === 'market_report')

const taskDimensionMap = computed(() => {
  const rd = strategy.value?.research_design as Record<string, unknown> | null | undefined
  return (rd?._task_dimension_map as Record<string, string> | undefined) ?? {}
})
const dimensionNames = computed(() =>
  strategy.value?.research_design?.data_plan?.map(d => d.dimension_name) ?? []
)

const insightData = computed(() => (strategy.value?.insight_result || null) as InsightResult | null)
const brandRoleData = computed(() => (strategy.value?.brand_role_result || null) as BrandRoleResult | null)
const bigIdeaData = computed(() => (strategy.value?.big_idea_result || null) as BigIdeaResult | null)

const agendaMapData = computed(() => (strategy.value?.agenda_map_result || null) as AgendaMapResult | null)
const landscapeData = computed(() => (strategy.value?.landscape_result || null) as LandscapeResult | null)
const strategicBriefData = computed(() => (strategy.value?.strategic_brief_result || null) as StrategicBriefResult | null)

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
const selectedOutputType = ref<OutputType>('brand_strategy')

/** 确认研究计划的前置校验：output_type 必须与 data_plan 包含的渠道匹配 */
const confirmResearchIssue = computed<string | null>(() => {
  if (!editableDataPlan.value.length) return '请先生成研究计划'
  const hasSocial = editableDataPlan.value.some(
    dp => (dp.channel || 'social_media') === 'social_media',
  )
  const hasNews = editableDataPlan.value.some(dp => dp.channel === 'news_media')
  if (selectedOutputType.value === 'brand_strategy' && !hasSocial) {
    return '品牌策略路径需要至少一个 social_media 维度'
  }
  if (selectedOutputType.value === 'market_report' && !hasNews) {
    return '市场分析报告路径需要至少一个 news_media 维度'
  }
  return null
})

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
    if (rd.output_type) {
      selectedOutputType.value = rd.output_type
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
      output_type: selectedOutputType.value,
      notes_per_task: notesPerTask.value,
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

  // 按平台分流：news_media 走 news_refinements，其他走社媒 refinements
  const socialSuggestions = suggestions.filter(s => s.platform !== 'news_media')
  const newsSuggestions = suggestions.filter(s => s.platform === 'news_media')

  const detail = suggestions
    .map(s => `${s.original_keyword} → ${s.suggested_keyword ?? '(移除)'}`)
    .join('、')
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm(
    `将调整 ${suggestions.length} 个关键词（社媒 ${socialSuggestions.length} / 新闻 ${newsSuggestions.length}）：${detail}，确定继续？`,
  )
  if (!confirmed) return

  refineProbeLoading.value = true
  try {
    const result = await strategiesApi.refineProbe(strategyId.value, {
      refinements: socialSuggestions.map(s => ({
        task_id: s.task_id,
        new_keyword: s.suggested_keyword,
        platform: s.platform,
      })),
      news_refinements: newsSuggestions.map(s => ({
        task_id: s.task_id,
        new_keyword: s.suggested_keyword,
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

// ── ④ Brand Strategy 生成（Insight → Brand Role → Big Idea）──────────────────

const generatingBrandStrategyStage = ref<BrandStrategyStage | null>(null)
const savingBrandStrategyStage = ref<BrandStrategyStage | null>(null)

const handleGenerateBrandStrategyStage = async (stage: BrandStrategyStage) => {
  generatingBrandStrategyStage.value = stage
  try {
    await strategiesApi.generateBrandStrategyStage(strategyId.value, stage)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    generatingBrandStrategyStage.value = null
  }
}

const handleSaveBrandStrategyStage = async (
  stage: BrandStrategyStage,
  result: Record<string, unknown>,
) => {
  savingBrandStrategyStage.value = stage
  try {
    await strategiesApi.editBrandStrategyStage(strategyId.value, stage, result)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    savingBrandStrategyStage.value = null
  }
}

// ── ④ Market Report 生成（Agenda Map → Landscape → Strategic Brief）─────────

const generatingMarketReportStage = ref<MarketReportStage | null>(null)

const handleGenerateMarketReportStage = async (stage: MarketReportStage) => {
  generatingMarketReportStage.value = stage
  try {
    await strategiesApi.generateMarketReportStage(strategyId.value, stage)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    generatingMarketReportStage.value = null
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
