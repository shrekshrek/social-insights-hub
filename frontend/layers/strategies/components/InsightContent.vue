<template>
  <div v-if="result" class="space-y-5">
    <!-- Social Tensions -->
    <div v-if="result.social_tensions?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">社会张力 Social Tension</h4>
      <div class="space-y-2">
        <div
          v-for="(tension, idx) in result.social_tensions"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-start justify-between gap-2">
            <p class="font-medium text-sm text-gray-900 dark:text-white">
              {{ idx + 1 }}. {{ tension.statement }}
            </p>
            <UBadge
              v-if="tension.confidence"
              :color="tension.confidence === 'high' ? 'success' : tension.confidence === 'medium' ? 'warning' : 'neutral'"
              variant="subtle"
              size="sm"
              class="shrink-0"
            >
              {{ confidenceLabel(tension.confidence) }}
            </UBadge>
          </div>
          <div v-if="tension.conventional_wisdom || tension.data_reality" class="mt-2 grid md:grid-cols-2 gap-2">
            <p v-if="tension.conventional_wisdom" class="text-xs text-gray-500 dark:text-gray-400 p-2 bg-white dark:bg-gray-900 rounded">
              <span class="font-medium text-gray-600 dark:text-gray-300 block mb-0.5">行业通常认为</span>
              {{ tension.conventional_wisdom }}
            </p>
            <p v-if="tension.data_reality" class="text-xs text-blue-700 dark:text-blue-300 p-2 bg-blue-50 dark:bg-blue-900/30 rounded">
              <span class="font-medium block mb-0.5">数据揭示</span>
              {{ tension.data_reality }}
            </p>
          </div>
          <!-- 回应的研究问题（RQ traceability） -->
          <div v-if="tension.research_questions_addressed?.length" class="mt-2 flex items-center gap-1 flex-wrap">
            <span class="text-[10px] text-gray-400">回应：</span>
            <span
              v-for="rqId in tension.research_questions_addressed"
              :key="rqId"
              class="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
            >
              {{ rqId.toUpperCase() }}
            </span>
          </div>
          <StrategyEvidenceList :evidence="tension.evidence" />
        </div>
      </div>
    </div>

    <!-- Brand Opportunities -->
    <div v-if="result.brand_opportunities?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">品牌机会 Brand Opportunity</h4>
      <div class="space-y-2">
        <div
          v-for="(opp, idx) in result.brand_opportunities"
          :key="idx"
          class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg"
        >
          <div class="flex items-start justify-between gap-2">
            <p class="font-medium text-sm text-gray-900 dark:text-white">
              {{ idx + 1 }}. {{ opp.statement }}
            </p>
            <span v-if="opp.related_tensions?.length" class="text-[10px] text-gray-400 shrink-0">
              关联 #{{ opp.related_tensions.map((i: number) => i + 1).join(', #') }}
            </span>
          </div>
          <p v-if="opp.why_non_obvious" class="mt-1.5 text-xs text-gray-600 dark:text-gray-400 p-2 bg-white/60 dark:bg-gray-800 rounded">
            <span class="font-medium text-gray-700 dark:text-gray-300">为何非显而易见：</span>{{ opp.why_non_obvious }}
          </p>
          <!-- 回应的研究问题 -->
          <div v-if="opp.research_questions_addressed?.length" class="mt-2 flex items-center gap-1 flex-wrap">
            <span class="text-[10px] text-gray-400">回应：</span>
            <span
              v-for="rqId in opp.research_questions_addressed"
              :key="rqId"
              class="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
            >
              {{ rqId.toUpperCase() }}
            </span>
          </div>
          <StrategyEvidenceList :evidence="opp.evidence" />
        </div>
      </div>
    </div>

    <!-- section 级"查看原始数据"入口 -->
    <SectionDataDrawer
      :chain-inputs="result.chain_inputs"
      title="Insight 洞察 · 原始数据来源"
    />
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { InsightResult } from '../types'
import { UBadge, SectionDataDrawer } from '#components'

defineProps<{
  result: InsightResult | null
}>()

const confidenceLabel = (c: string) => {
  if (c === 'high') return '高置信'
  if (c === 'medium') return '中置信'
  return '低置信'
}
</script>
