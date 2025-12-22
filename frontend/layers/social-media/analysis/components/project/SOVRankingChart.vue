<script setup lang="ts">
import { computed, ref } from 'vue'

interface SOVRankingItem {
  name: string
  parent?: string
  role?: string
  heat: number
  mentions: number
  share: number
  sentiment?: number
  sentiment_distribution?: Record<string, number>
  platform_distribution?: Record<string, number>
}

const props = defineProps<{
  data: SOVRankingItem[]
  maxItems?: number
}>()

const maxItems = computed(() => props.maxItems ?? 15)
const items = computed(() => (props.data || []).slice(0, maxItems.value))

// 颜色映射：按 role
const roleColors: Record<string, string> = {
  Target: '#10b981',     // emerald-500
  Competitor: '#f59e0b', // amber-500
  Context: '#6b7280',    // gray-500
}

const getRoleColor = (role?: string) => roleColors[role || 'Context'] || roleColors.Context

// 找到最大热度用于进度条宽度计算
const maxHeat = computed(() => {
  const heats = items.value.map(i => i.heat || 0)
  return Math.max(...heats, 1)
})

// 计算进度条宽度百分比
const getBarWidth = (heat: number) => {
  return `${Math.round((heat / maxHeat.value) * 100)}%`
}

// 格式化数字
const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

// 展开状态
const expandedRow = ref<string | null>(null)
const toggleRow = (name: string) => {
  expandedRow.value = expandedRow.value === name ? null : name
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SOV 排行榜</h3>
      <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }}</span>
    </div>

    <div class="space-y-1.5">
      <div
        v-for="(item, idx) in items"
        :key="item.name"
        class="group"
      >
        <!-- 主行 -->
        <div
          class="flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
          @click="toggleRow(item.name)"
        >
          <!-- 排名 -->
          <span
            class="w-5 h-5 flex items-center justify-center rounded text-xs font-medium shrink-0"
            :class="idx < 3 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'"
          >
            {{ idx + 1 }}
          </span>

          <!-- 名称 + 角色标签 -->
          <div class="flex items-center gap-1.5 min-w-0 flex-1">
            <span class="text-sm text-gray-900 dark:text-white truncate">{{ item.name }}</span>
            <span
              v-if="item.role && item.role !== 'Context'"
              class="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
              :style="{ backgroundColor: `${getRoleColor(item.role)}20`, color: getRoleColor(item.role) }"
            >
              {{ item.role === 'Target' ? '主体' : '竞品' }}
            </span>
          </div>

          <!-- 热度进度条 -->
          <div class="w-24 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden shrink-0">
            <div
              class="h-full rounded-full transition-all"
              :style="{ width: getBarWidth(item.heat), backgroundColor: getRoleColor(item.role) }"
            />
          </div>

          <!-- 份额 -->
          <span class="text-xs font-mono text-gray-600 dark:text-gray-400 w-12 text-right shrink-0">
            {{ ((item.share || 0) * 100).toFixed(1) }}%
          </span>

          <!-- 展开指示器 -->
          <UIcon
            name="i-heroicons-chevron-down"
            class="w-4 h-4 text-gray-400 transition-transform shrink-0"
            :class="{ 'rotate-180': expandedRow === item.name }"
          />
        </div>

        <!-- 展开详情 -->
        <Transition
          enter-active-class="transition-all duration-200 ease-out"
          leave-active-class="transition-all duration-150 ease-in"
          enter-from-class="opacity-0 max-h-0"
          enter-to-class="opacity-100 max-h-40"
          leave-from-class="opacity-100 max-h-40"
          leave-to-class="opacity-0 max-h-0"
        >
          <div
            v-if="expandedRow === item.name"
            class="ml-7 mr-2 py-2 px-3 rounded-md bg-gray-50 dark:bg-gray-800/50 overflow-hidden"
          >
            <div class="grid grid-cols-3 gap-3 text-xs">
              <div>
                <div class="text-gray-500 dark:text-gray-400">热度值</div>
                <div class="font-mono text-gray-900 dark:text-white">{{ formatNumber(item.heat) }}</div>
              </div>
              <div>
                <div class="text-gray-500 dark:text-gray-400">提及帖数</div>
                <div class="font-mono text-gray-900 dark:text-white">{{ formatNumber(item.mentions) }}</div>
              </div>
              <div>
                <div class="text-gray-500 dark:text-gray-400">效能倍数</div>
                <div class="font-mono text-gray-900 dark:text-white">
                  {{ item.mentions > 0 ? (item.heat / item.mentions).toFixed(1) : '-' }}x
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <div v-if="!items.length" class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无 SOV 排行数据
    </div>
  </div>
</template>

