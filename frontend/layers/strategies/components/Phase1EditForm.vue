<template>
  <div class="space-y-6">
    <!-- Social Tensions -->
    <div>
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Social Tension</h4>
      <div class="space-y-4">
        <div
          v-for="(tension, idx) in localData.social_tensions"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg space-y-2"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-500 shrink-0">{{ idx + 1 }}.</span>
            <UTextarea
              v-model="tension.statement"
              :rows="2"
              placeholder="描述该矛盾"
              class="flex-1"
            />
            <USelect
              v-model="tension.confidence"
              :items="confidenceOptions"
              class="w-28 shrink-0"
            />
          </div>
          <EvidenceEditList v-model="tension.evidence" />
        </div>
      </div>
    </div>

    <!-- Brand Opportunities -->
    <div>
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Brand Opportunity</h4>
      <div class="space-y-4">
        <div
          v-for="(opp, idx) in localData.brand_opportunities"
          :key="idx"
          class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg space-y-2"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-500 shrink-0">{{ idx + 1 }}.</span>
            <UTextarea
              v-model="opp.statement"
              :rows="2"
              placeholder="描述品牌机会"
              class="flex-1"
            />
          </div>
          <EvidenceEditList v-model="opp.evidence" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Phase1Result } from '../types'
import { UTextarea, USelect } from '#components'

const props = defineProps<{
  result: Phase1Result
}>()

const localData = ref<Phase1Result>(JSON.parse(JSON.stringify(props.result)))

const confidenceOptions = [
  { label: 'High', value: 'high' },
  { label: 'Medium', value: 'medium' },
  { label: 'Low', value: 'low' },
]

defineExpose({
  getResult: () => JSON.parse(JSON.stringify(localData.value)),
})
</script>
