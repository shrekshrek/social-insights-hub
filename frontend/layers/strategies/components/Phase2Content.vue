<template>
  <div v-if="result" class="space-y-6">
    <!-- Brand Social Role -->
    <div v-if="result.brand_social_role">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Brand Social Role</h4>
      <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <p class="font-bold text-lg text-gray-900 dark:text-white">
          {{ result.brand_social_role.statement }}
        </p>
        <p v-if="result.brand_social_role.elaboration" class="mt-2 text-gray-600 dark:text-gray-400">
          {{ result.brand_social_role.elaboration }}
        </p>
        <StrategyEvidenceList :evidence="result.brand_social_role.evidence" />
      </div>
    </div>

    <!-- Social Strategy -->
    <div v-if="result.social_strategy">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Social Strategy</h4>
      <div class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
        <p class="font-bold text-lg text-gray-900 dark:text-white">
          {{ result.social_strategy.statement }}
        </p>
        <div v-if="result.social_strategy.core_message" class="mt-2">
          <span class="text-sm font-medium text-gray-500">核心信息:</span>
          <span class="ml-1 text-gray-700 dark:text-gray-300">{{ result.social_strategy.core_message }}</span>
        </div>
        <div v-if="result.social_strategy.rhythm" class="mt-1">
          <span class="text-sm font-medium text-gray-500">传播节奏:</span>
          <span class="ml-1 text-gray-700 dark:text-gray-300">{{ result.social_strategy.rhythm }}</span>
        </div>
        <StrategyEvidenceList :evidence="result.social_strategy.evidence" />
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { Phase2Result } from '../types'

defineProps<{
  result: Phase2Result | null
}>()
</script>
