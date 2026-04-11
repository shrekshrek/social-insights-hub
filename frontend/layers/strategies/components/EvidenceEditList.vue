<template>
  <div v-if="modelValue?.length" class="mt-2 space-y-2">
    <p class="text-xs font-medium text-gray-500 dark:text-gray-400">数据论据</p>
    <div
      v-for="(item, idx) in modelValue"
      :key="idx"
      class="flex items-start gap-2 text-xs"
    >
      <UBadge
        v-if="item.type"
        color="neutral"
        variant="subtle"
        size="xs"
        class="shrink-0 mt-1.5"
      >
        {{ item.type }}
      </UBadge>
      <UTextarea
        :model-value="item.description"
        :rows="1"
        class="flex-1 text-xs"
        @update:model-value="updateDescription(idx, $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StageEvidence } from '../types'
import { UBadge, UTextarea } from '#components'

const props = defineProps<{
  modelValue?: StageEvidence[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: StageEvidence[]): void
}>()

const updateDescription = (idx: number, value: string) => {
  if (!props.modelValue) return
  const updated = props.modelValue.map((item, i) =>
    i === idx ? { ...item, description: value } : item
  )
  emit('update:modelValue', updated)
}
</script>
