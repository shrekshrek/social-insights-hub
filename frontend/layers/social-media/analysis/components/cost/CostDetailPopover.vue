<template>
  <UPopover :popper="{ placement: 'bottom-end' }">
    <UButton
      color="gray"
      variant="ghost"
      size="sm"
      icon="i-heroicons-information-circle"
      :label="buttonLabel"
    />

    <template #panel>
      <div class="p-4 w-80 max-h-96 overflow-y-auto">
        <div v-if="!stats" class="text-center text-gray-500 py-4">
          暂无详细数据
        </div>

        <div v-else class="space-y-4">
          <!-- 标题 -->
          <div class="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 pb-2">
            <h4 class="font-semibold text-gray-900 dark:text-gray-100">
              成本详情
            </h4>
            <UBadge
              :color="getCostLevel(stats.summary.total_cost_cny).color"
              variant="subtle"
            >
              {{ getCostLevel(stats.summary.total_cost_cny).label }}
            </UBadge>
          </div>

          <!-- 总览 -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-600 dark:text-gray-400">
                总成本
              </span>
              <span class="font-semibold text-gray-900 dark:text-gray-100">
                {{ formatCost(stats.summary.total_cost_cny) }}
              </span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-600 dark:text-gray-400">
                总Token数
              </span>
              <span class="text-sm text-gray-900 dark:text-gray-100">
                {{ formatTokens(stats.summary.total_tokens) }}
              </span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-600 dark:text-gray-400">
                调用次数
              </span>
              <span class="text-sm text-gray-900 dark:text-gray-100">
                {{ stats.summary.total_calls }} 次
              </span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-600 dark:text-gray-400">
                平均每次成本
              </span>
              <span class="text-sm text-gray-900 dark:text-gray-100">
                {{ formatCost(stats.summary.avg_cost_per_call) }}
              </span>
            </div>
          </div>

          <!-- Token分布 -->
          <div class="border-t border-gray-200 dark:border-gray-700 pt-3 space-y-2">
            <h5 class="text-sm font-medium text-gray-700 dark:text-gray-300">
              Token分布
            </h5>

            <div class="space-y-1">
              <div class="flex items-center justify-between text-xs">
                <span class="text-gray-600 dark:text-gray-400">
                  输入Token
                </span>
                <span class="text-gray-900 dark:text-gray-100">
                  {{ formatTokens(stats.summary.total_input_tokens) }}
                  <span class="text-gray-400 ml-1">
                    ({{ ((stats.summary.total_input_tokens / stats.summary.total_tokens) * 100).toFixed(1) }}%)
                  </span>
                </span>
              </div>

              <div class="flex items-center justify-between text-xs">
                <span class="text-gray-600 dark:text-gray-400">
                  输出Token
                </span>
                <span class="text-gray-900 dark:text-gray-100">
                  {{ formatTokens(stats.summary.total_output_tokens) }}
                  <span class="text-gray-400 ml-1">
                    ({{ ((stats.summary.total_output_tokens / stats.summary.total_tokens) * 100).toFixed(1) }}%)
                  </span>
                </span>
              </div>
            </div>
          </div>

          <!-- 调用明细 -->
          <div
            v-if="showCallDetails && stats.call_details?.length"
            class="border-t border-gray-200 dark:border-gray-700 pt-3 space-y-2"
          >
            <div class="flex items-center justify-between">
              <h5 class="text-sm font-medium text-gray-700 dark:text-gray-300">
                调用明细
              </h5>
              <span class="text-xs text-gray-500">
                最近{{ Math.min(maxCallDetails, stats.call_details.length) }}次
              </span>
            </div>

            <div class="space-y-2 max-h-48 overflow-y-auto">
              <div
                v-for="(call, index) in stats.call_details.slice(0, maxCallDetails)"
                :key="index"
                class="flex items-center justify-between text-xs p-2 bg-gray-50 dark:bg-gray-800 rounded"
              >
                <div class="flex flex-col gap-1">
                  <span class="text-gray-600 dark:text-gray-400">
                    第{{ call.call_index }}次调用
                  </span>
                  <span class="text-gray-500 dark:text-gray-500 text-[10px]">
                    {{ formatTokens(call.total_tokens) }} tokens
                  </span>
                </div>
                <div class="flex flex-col items-end gap-1">
                  <span class="font-medium text-gray-900 dark:text-gray-100">
                    {{ formatCost(call.cost_cny) }}
                  </span>
                  <span class="text-gray-500 dark:text-gray-500 text-[10px]">
                    {{ call.duration_seconds.toFixed(2) }}秒
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div v-if="showExport" class="border-t border-gray-200 dark:border-gray-700 pt-3">
            <UButton
              block
              color="gray"
              variant="soft"
              size="sm"
              icon="i-heroicons-arrow-down-tray"
              @click="$emit('export')"
            >
              导出详细报告
            </UButton>
          </div>
        </div>
      </div>
    </template>
  </UPopover>
</template>

<script setup lang="ts">
import type { TokenUsageStats } from '../../types'

interface Props {
  stats: TokenUsageStats | null
  buttonLabel?: string
  showCallDetails?: boolean
  maxCallDetails?: number
  showExport?: boolean
}

const _props = withDefaults(defineProps<Props>(), {
  buttonLabel: '成本详情',
  showCallDetails: true,
  maxCallDetails: 10,
  showExport: true,
})

const _emit = defineEmits<{
  'export': []
}>()

const { formatTokens, formatCost, getCostLevel } = useTokenUsage()
</script>
