<template>
  <div v-if="result" class="space-y-5">
    <!-- Brand Social Role -->
    <div v-if="result.brand_social_role">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">品牌社媒角色 Brand Social Role</h4>
      <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <p class="font-bold text-base text-gray-900 dark:text-white leading-relaxed">
          {{ result.brand_social_role.statement }}
        </p>
        <p
          v-if="result.brand_social_role.elaboration"
          class="mt-2 text-sm text-gray-600 dark:text-gray-400 leading-relaxed"
        >
          {{ result.brand_social_role.elaboration }}
        </p>
        <StrategyEvidenceList :evidence="result.brand_social_role.evidence" />
      </div>
    </div>

    <!-- Social Strategy -->
    <div v-if="result.social_strategy">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">社媒策略 Social Strategy</h4>
      <div class="p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
        <p class="font-bold text-base text-gray-900 dark:text-white leading-relaxed">
          {{ result.social_strategy.statement }}
        </p>

        <!-- 核心信息突出展示 -->
        <div
          v-if="result.social_strategy.core_message"
          class="mt-3 p-3 bg-white dark:bg-gray-900 rounded-lg border-l-4 border-amber-400"
        >
          <p class="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">核心信息</p>
          <p class="text-sm font-medium text-gray-900 dark:text-white leading-relaxed">
            {{ result.social_strategy.core_message }}
          </p>
        </div>

        <!-- 传播节奏 -->
        <p
          v-if="result.social_strategy.rhythm"
          class="mt-3 text-sm text-gray-600 dark:text-gray-400 leading-relaxed"
        >
          <span class="font-medium text-gray-700 dark:text-gray-300">传播节奏：</span>{{ result.social_strategy.rhythm }}
        </p>

        <StrategyEvidenceList :evidence="result.social_strategy.evidence" />
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { BrandRoleResult } from '../types'

defineProps<{
  result: BrandRoleResult | null
}>()
</script>
