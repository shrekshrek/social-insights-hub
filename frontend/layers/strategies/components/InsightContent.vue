<template>
  <div v-if="result" class="space-y-6">
    <!-- Social Tensions -->
    <div v-if="result.social_tensions?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Social Tension</h4>
      <div class="space-y-3">
        <div
          v-for="(tension, idx) in result.social_tensions"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-start justify-between">
            <p class="font-medium text-gray-900 dark:text-white">
              {{ idx + 1 }}. {{ tension.statement }}
            </p>
            <UBadge
              v-if="tension.confidence"
              :color="tension.confidence === 'high' ? 'success' : tension.confidence === 'medium' ? 'warning' : 'neutral'"
              variant="subtle"
              size="xs"
            >
              {{ tension.confidence }}
            </UBadge>
          </div>
          <div v-if="tension.conventional_wisdom || tension.data_reality" class="mt-2 space-y-1 text-sm">
            <p v-if="tension.conventional_wisdom" class="text-gray-500 dark:text-gray-400">
              <span class="font-medium text-gray-600 dark:text-gray-300">行业通常认为：</span>{{ tension.conventional_wisdom }}
            </p>
            <p v-if="tension.data_reality" class="text-blue-700 dark:text-blue-300">
              <span class="font-medium">数据揭示：</span>{{ tension.data_reality }}
            </p>
          </div>
          <StrategyEvidenceList :evidence="tension.evidence" />
        </div>
      </div>
    </div>

    <!-- Brand Opportunities -->
    <div v-if="result.brand_opportunities?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Brand Opportunity</h4>
      <div class="space-y-3">
        <div
          v-for="(opp, idx) in result.brand_opportunities"
          :key="idx"
          class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg"
        >
          <p class="font-medium text-gray-900 dark:text-white">
            {{ idx + 1 }}. {{ opp.statement }}
          </p>
          <p v-if="opp.why_non_obvious" class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            <span class="font-medium text-gray-600 dark:text-gray-300">为何非显而易见：</span>{{ opp.why_non_obvious }}
          </p>
          <p v-if="opp.related_tensions?.length" class="text-xs text-gray-500 mt-1">
            关联 Tension: {{ opp.related_tensions.map(i => `#${(i as number) + 1}`).join(', ') }}
          </p>
          <StrategyEvidenceList :evidence="opp.evidence" />
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { InsightResult } from '../types'
import { UBadge } from '#components'

defineProps<{
  result: InsightResult | null
}>()
</script>
