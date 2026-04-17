<template>
  <div v-if="result" class="space-y-6">
    <!-- Big Idea -->
    <div v-if="result.big_idea">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Big Idea</h4>
      <div class="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border-l-4 border-green-500">
        <p class="font-bold text-xl text-gray-900 dark:text-white">
          {{ result.big_idea.statement }}
        </p>
        <p v-if="result.big_idea.elaboration" class="mt-2 text-gray-600 dark:text-gray-400">
          {{ result.big_idea.elaboration }}
        </p>
        <div v-if="result.big_idea.tension_echo" class="mt-2 p-2 bg-white/50 dark:bg-gray-800/50 rounded">
          <span class="text-xs font-medium text-gray-500">与核心矛盾的呼应:</span>
          <p class="text-sm text-gray-700 dark:text-gray-300 mt-0.5">{{ result.big_idea.tension_echo }}</p>
        </div>
        <StrategyEvidenceList :evidence="result.big_idea.evidence" />
      </div>
    </div>

    <!-- Content Strategy -->
    <div v-if="result.content_strategy">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Content Strategy</h4>
      <div class="space-y-3">
        <div
          v-for="(pillar, idx) in result.content_strategy.pillars"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-center gap-2">
            <p class="font-semibold text-gray-900 dark:text-white">
              支柱 {{ idx + 1 }}: {{ pillar.name }}
            </p>
            <UBadge v-if="pillar.strategic_role" :color="ROLE_COLOR[pillar.strategic_role] ?? 'neutral'" variant="soft" size="xs">
              {{ ROLE_LABEL[pillar.strategic_role] ?? pillar.strategic_role }}
            </UBadge>
          </div>
          <p v-if="pillar.description" class="mt-1 text-sm text-gray-600 dark:text-gray-400">
            {{ pillar.description }}
          </p>
          <div v-if="pillar.reference_examples?.length" class="mt-2">
            <p class="text-xs font-medium text-gray-500 mb-1">参考案例:</p>
            <ul class="list-disc list-inside text-sm text-gray-600 dark:text-gray-400">
              <li v-for="(ex, eidx) in pillar.reference_examples" :key="eidx">{{ ex }}</li>
            </ul>
          </div>
        </div>
      </div>
      <StrategyEvidenceList :evidence="result.content_strategy.evidence" />
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { BigIdeaResult } from '../types'
import { UBadge } from '#components'

const ROLE_LABEL: Record<string, string> = {
  anchor: '核心表达',
  leverage: '借势扩散',
  conversion: '行为转变',
  disruption: '品类颠覆',
}

const ROLE_COLOR: Record<string, 'info' | 'warning' | 'success' | 'error'> = {
  anchor: 'info',
  leverage: 'warning',
  conversion: 'success',
  disruption: 'error',
}

defineProps<{
  result: BigIdeaResult | null
}>()
</script>
