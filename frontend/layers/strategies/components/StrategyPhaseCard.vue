<template>
  <UCard>
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <UBadge :color="phaseColor" variant="soft" size="sm">Phase {{ phase }}</UBadge>
          <h3 class="text-lg font-semibold">{{ title }}</h3>
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
        <Phase1EditForm v-if="phase === 1" ref="editFormRef" :result="typedResult1!" />
        <Phase2EditForm v-if="phase === 2" ref="editFormRef" :result="typedResult2!" />
        <Phase3EditForm v-if="phase === 3" ref="editFormRef" :result="typedResult3!" />
      </div>

      <!-- 展示模式: 插槽 -->
      <div v-else>
        <slot />
      </div>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { Phase1Result, Phase2Result, Phase3Result } from '../types'
import { UCard, UBadge, UButton, UIcon } from '#components'

const props = defineProps<{
  phase: 1 | 2 | 3
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

const handleGenerateClick = async () => {
  if (props.hasResult) {
    const confirmed = await $confirm({
      title: '确认重新生成',
      message: `重新生成将覆盖当前 Phase ${props.phase} 的结果，同时清除下游阶段的已生成内容，确定继续？`,
      confirmText: '确认重新生成',
      type: 'warning',
    })
    if (!confirmed) return
  }
  emit('generate')
}

const phaseColor = computed(() => {
  if (props.phase === 1) return 'info' as const
  if (props.phase === 2) return 'warning' as const
  return 'success' as const
})

const noResultText = computed(() => {
  if (!props.canGenerate) {
    return props.phase === 2 ? '请先完成 Phase 1' : '请先完成 Phase 2'
  }
  return '点击「生成」开始 AI 分析'
})

const typedResult1 = computed(() => props.result as Phase1Result | null)
const typedResult2 = computed(() => props.result as Phase2Result | null)
const typedResult3 = computed(() => props.result as Phase3Result | null)

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
