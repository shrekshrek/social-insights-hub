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
              <span v-if="strategy.slices.length > 0">|</span>
              <span v-for="(s, idx) in strategy.slices" :key="s.slice_id" class="text-gray-400">
                {{ s.project_name }}/{{ s.slice_name || `切片#${s.slice_id}` }}{{ idx < strategy.slices.length - 1 ? '、' : '' }}
              </span>
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

    <!-- Loading -->
    <div v-if="pending" class="text-center py-16">
      <p class="text-gray-500">加载中...</p>
    </div>

    <!-- Phase Cards -->
    <ClientOnly v-if="strategy">
      <template #fallback>
        <div class="space-y-4">
          <div v-for="i in 3" :key="i" class="h-48 bg-gray-100 rounded-lg animate-pulse" />
        </div>
      </template>

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
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import type {
  StrategyStatus,
  Phase1Result,
  Phase2Result,
  Phase3Result,
} from '../../../types'
import { UBadge, UButton } from '#components'

definePageMeta({ title: '策略详情' })

const route = useRoute()
const strategiesApi = useStrategies()

const strategyId = computed(() => Number(route.params.id))

const { data: strategy, pending, refresh } = strategiesApi.getStrategy(strategyId)

const generatingPhase = ref<1 | 2 | 3 | null>(null)
const savingPhase = ref<1 | 2 | 3 | null>(null)

const STATUS_MAP: Record<StrategyStatus, { label: string; color: 'neutral' | 'info' | 'warning' | 'success' }> = {
  draft: { label: '草稿', color: 'neutral' },
  phase1_done: { label: '洞察完成', color: 'info' },
  phase2_done: { label: '策略完成', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
}

const STATUS_ORDER: Record<StrategyStatus, number> = {
  draft: 0,
  phase1_done: 1,
  phase2_done: 2,
  completed: 3,
}

const statusInfo = computed(() => {
  const s = strategy.value?.status as StrategyStatus
  return STATUS_MAP[s] || { label: s, color: 'neutral' as const }
})

const currentStatusOrder = computed(() => {
  const s = strategy.value?.status as StrategyStatus
  return STATUS_ORDER[s] ?? 0
})

const canGeneratePhase2 = computed(() => currentStatusOrder.value >= 1)
const canGeneratePhase3 = computed(() => currentStatusOrder.value >= 2)

const phase1Data = computed(() => (strategy.value?.phase1_result || null) as Phase1Result | null)
const phase2Data = computed(() => (strategy.value?.phase2_result || null) as Phase2Result | null)
const phase3Data = computed(() => (strategy.value?.phase3_result || null) as Phase3Result | null)

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

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
