<template>
  <UCard>
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 flex-wrap">
          <UBadge :color="stageColor" variant="soft" size="sm">第 {{ stageIndex }} 层</UBadge>
          <h3 class="text-lg font-semibold">{{ title }}</h3>
          <DataProvenanceBadge v-if="provenance" :provenance="provenance" />
        </div>
        <div class="flex items-center gap-2">
          <UButton
            v-if="canGenerate"
            size="sm"
            :loading="generating"
            :disabled="generating"
            icon="i-heroicons-sparkles"
            @click="handleGenerateClick"
          >
            {{ hasResult ? '重新生成' : '生成' }}
          </UButton>
        </div>
      </div>
    </template>

    <div v-if="!hasResult && !generating" class="text-center py-8">
      <p class="text-gray-400">{{ noResultText }}</p>
    </div>

    <div v-else-if="generating" class="text-center py-8">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin text-2xl text-primary-500 mb-2" />
      <p class="text-gray-500">AI 正在生成中，请稍候...</p>
    </div>

    <div v-else>
      <slot />
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { MarketReportStage } from '../composables/useStrategies'
import type { DataProvenance } from '../types'
import { UCard, UBadge, UButton, UIcon } from '#components'

const props = defineProps<{
  stage: MarketReportStage
  title: string
  hasResult: boolean
  canGenerate: boolean
  generating?: boolean
  result?: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  (e: 'generate'): void
}>()

const { $confirm } = useNuxtApp()

const STAGE_INDEX: Record<MarketReportStage, number> = {
  agenda_map: 1,
  landscape: 2,
  strategic_brief: 3,
}

const STAGE_PREV_LABEL: Record<MarketReportStage, string> = {
  agenda_map: '',
  landscape: '请先完成第 1 层 Agenda Map（媒体议程图）',
  strategic_brief: '请先完成第 2 层 Landscape（竞争格局）',
}

const stageIndex = computed(() => STAGE_INDEX[props.stage])

const handleGenerateClick = async () => {
  if (props.hasResult) {
    const confirmed = await $confirm({
      title: '确认重新生成',
      message: `重新生成将覆盖当前第 ${stageIndex.value} 层的结果，同时清除下游阶段的已生成内容，确定继续？`,
      confirmText: '确认重新生成',
      type: 'warning',
    })
    if (!confirmed) return
  }
  emit('generate')
}

const stageColor = computed(() => {
  if (props.stage === 'agenda_map') return 'info' as const
  if (props.stage === 'landscape') return 'warning' as const
  return 'success' as const
})

const provenance = computed<DataProvenance | null>(() => {
  const r = props.result as { data_provenance?: DataProvenance } | null
  return r?.data_provenance ?? null
})

const noResultText = computed(() => {
  if (!props.canGenerate) {
    return STAGE_PREV_LABEL[props.stage]
  }
  return '点击「生成」开始 AI 分析'
})
</script>
