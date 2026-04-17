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
          <UButton
            v-if="hasResult && canEdit"
            size="sm"
            variant="outline"
            icon="i-heroicons-pencil-square"
            @click="toggleEdit"
          >
            {{ editing ? '取消' : '编辑' }}
          </UButton>
          <UButton
            v-if="editing"
            size="sm"
            color="primary"
            icon="i-heroicons-check"
            :loading="saving"
            @click="handleSave"
          >
            保存
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
      <!-- 编辑模式: 结构化表单 -->
      <div v-if="editing">
        <InsightEditForm v-if="stage === 'insight'" ref="editFormRef" :result="insightResult!" />
        <BrandRoleEditForm v-if="stage === 'brand_role'" ref="editFormRef" :result="brandRoleResult!" />
        <BigIdeaEditForm v-if="stage === 'big_idea'" ref="editFormRef" :result="bigIdeaResult!" />
      </div>

      <!-- 展示模式: 插槽 -->
      <div v-else>
        <slot />
      </div>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { BrandStrategyStage } from '../composables/useStrategiesApi'
import type {
  InsightResult,
  BrandRoleResult,
  BigIdeaResult,
  DataProvenance,
} from '../types'
import { UCard, UBadge, UButton, UIcon } from '#components'

const props = defineProps<{
  stage: BrandStrategyStage
  title: string
  hasResult: boolean
  canGenerate: boolean
  canEdit?: boolean
  generating?: boolean
  saving?: boolean
  result?: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  (e: 'generate'): void
  (e: 'save', result: Record<string, unknown>): void
}>()

const { $confirm } = useNuxtApp()

const editing = ref(false)
const editFormRef = ref<{ getResult: () => Record<string, unknown> } | null>(null)

const STAGE_INDEX: Record<BrandStrategyStage, number> = {
  insight: 1,
  brand_role: 2,
  big_idea: 3,
}

const STAGE_PREV_LABEL: Record<BrandStrategyStage, string> = {
  insight: '',
  brand_role: '请先完成第 1 层 Insight 洞察',
  big_idea: '请先完成第 2 层 Brand Role 品牌角色',
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
  if (props.stage === 'insight') return 'info' as const
  if (props.stage === 'brand_role') return 'warning' as const
  return 'success' as const
})

const noResultText = computed(() => {
  if (!props.canGenerate) {
    return STAGE_PREV_LABEL[props.stage]
  }
  return '点击「生成」开始 AI 分析'
})

const insightResult = computed(() => props.result as InsightResult | null)
const brandRoleResult = computed(() => props.result as BrandRoleResult | null)
const bigIdeaResult = computed(() => props.result as BigIdeaResult | null)

const provenance = computed<DataProvenance | null>(() => {
  const r = props.result as { data_provenance?: DataProvenance } | null
  return r?.data_provenance ?? null
})

const toggleEdit = () => {
  editing.value = !editing.value
}

const handleSave = () => {
  const data = editFormRef.value?.getResult()
  if (data) {
    editing.value = false
    emit('save', data)
  }
}
</script>
