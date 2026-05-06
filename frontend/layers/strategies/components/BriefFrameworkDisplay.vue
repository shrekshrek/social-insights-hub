<template>
  <div v-if="hasAny" class="space-y-2">
    <!-- target_audiences：嵌套结构 -->
    <div v-if="audiences?.length">
      <div class="text-xs text-gray-500 mb-1">目标受众</div>
      <div class="space-y-1.5">
        <div
          v-for="(audience, idx) in audiences"
          :key="idx"
          class="text-xs"
        >
          <div class="flex items-baseline gap-1.5 flex-wrap">
            <span class="font-medium text-gray-700 dark:text-gray-300">{{ audience.label }}</span>
            <span
              v-if="audience.description"
              class="text-gray-500 dark:text-gray-400"
            >— {{ audience.description }}</span>
          </div>
          <div
            v-if="audience.behavior_signals?.length"
            class="text-gray-400 mt-0.5 ml-2"
          >
            行为信号：{{ audience.behavior_signals.join('、') }}
          </div>
        </div>
      </div>
    </div>

    <!-- audience_insights / core_propositions / competitors：扁平列表 -->
    <div
      v-for="row in flatRows"
      :key="row.label"
      class="text-xs flex items-baseline gap-1.5"
    >
      <span class="text-gray-500 flex-shrink-0">{{ row.label }}：</span>
      <span class="text-gray-700 dark:text-gray-300">{{ row.text }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AudienceSegment } from '../types'

const props = defineProps<{
  audiences?: AudienceSegment[] | null
  insights?: string[] | null
  propositions?: string[] | null
  competitors?: string[] | null
}>()

const hasAny = computed(
  () => !!(
    props.audiences?.length
    || props.insights?.length
    || props.propositions?.length
    || props.competitors?.length
  ),
)

const flatRows = computed(() => {
  const rows: { label: string; text: string }[] = []
  if (props.insights?.length) rows.push({ label: '受众痛点', text: props.insights.join('；') })
  if (props.propositions?.length) rows.push({ label: '核心主张', text: props.propositions.join('；') })
  if (props.competitors?.length) rows.push({ label: '明确竞品', text: props.competitors.join('、') })
  return rows
})
</script>
