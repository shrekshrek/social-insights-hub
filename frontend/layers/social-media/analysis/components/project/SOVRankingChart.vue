<script setup lang="ts">
import { computed, ref } from 'vue'
import TabSwitch from '../shared/TabSwitch.vue'

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
  selected?: string | null
}>()

const emit = defineEmits<{
  (e: 'select', item: SOVRankingItem): void
}>()

type SortMode = 'share' | 'mentions' | 'efficiency'

const maxItems = computed(() => props.maxItems ?? 15)
const sortMode = ref<SortMode>('share')

const sortModeOptions = [
  { value: 'share', label: '份额' },
  { value: 'mentions', label: '提及' },
  { value: 'efficiency', label: '效能' },
]

const sortedItems = computed(() => {
  const list = (props.data || []).slice()
  const byEfficiency = (x: SOVRankingItem) => (x.mentions > 0 ? (x.heat || 0) / x.mentions : -Infinity)

  if (sortMode.value === 'mentions') {
    list.sort((a, b) => (b.mentions || 0) - (a.mentions || 0))
  } else if (sortMode.value === 'efficiency') {
    list.sort((a, b) => byEfficiency(b) - byEfficiency(a))
  } else {
    // default: SOV should align with share/heat
    list.sort((a, b) => (b.share || 0) - (a.share || 0))
  }

  return list
})

const items = computed(() => sortedItems.value.slice(0, maxItems.value))

const isSelected = (item: SOVRankingItem) => {
  const selected = (props.selected || '').toString()
  return selected && selected === item.name
}

// 颜色映射：按 role
const roleColors: Record<string, string> = {
  Target: '#10b981',     // emerald-500
  Competitor: '#f59e0b', // amber-500
  Context: '#6b7280',    // gray-500
}

const getRoleColor = (role?: string) => roleColors[role || 'Context'] || roleColors.Context

// 找到最大份额用于进度条宽度计算（更符合 SOV）
const maxShare = computed(() => {
  const shares = items.value.map(i => i.share || 0)
  return Math.max(...shares, 0.000001)
})

// 计算进度条宽度百分比
const getBarWidth = (share: number) => {
  return `${Math.round(((share || 0) / maxShare.value) * 100)}%`
}

// 格式化数字
const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SOV 排行榜</h3>
        <TabSwitch v-model="sortMode" :options="sortModeOptions" />
      </div>
      <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }}</span>
    </div>

    <div class="space-y-0.5">
      <div
        v-for="(item, idx) in items"
        :key="item.name"
        class="group"
      >
        <div
          class="py-1.5 px-2 rounded-md transition-colors cursor-pointer"
          :class="isSelected(item) ? 'bg-primary-50/70 dark:bg-primary-900/20 ring-1 ring-primary-200/60 dark:ring-primary-800/40' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'"
          @click="emit('select', item)"
        >
          <!-- 主行 -->
          <div class="flex items-center gap-2">
            <!-- 排名 -->
            <span
              class="w-5 h-5 flex items-center justify-center rounded text-xs font-medium shrink-0"
              :class="idx < 3 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'"
            >
              {{ idx + 1 }}
            </span>

            <div class="min-w-0 flex-1 flex items-center gap-2">
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

              <!-- 行内指标：不展开，直接展示关键数 -->
              <div class="shrink-0 flex items-center gap-2 sm:gap-3 text-[10px] sm:text-[11px] text-gray-500 dark:text-gray-400 whitespace-nowrap">
                <span title="热度值">
                  热 <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(item.heat) }}</span>
                </span>
                <span title="提及帖数">
                  帖 <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(item.mentions) }}</span>
                </span>
                <span title="效能倍数 (heat / mentions)">
                  效 <span class="font-mono text-gray-700 dark:text-gray-300">{{ item.mentions > 0 ? (item.heat / item.mentions).toFixed(1) : '-' }}</span>x
                </span>
              </div>
            </div>

            <!-- SOV 份额进度条 -->
            <div class="hidden sm:block w-16 md:w-20 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden shrink-0">
              <div
                class="h-full rounded-full transition-all"
                :style="{ width: getBarWidth(item.share), backgroundColor: getRoleColor(item.role) }"
              />
            </div>

            <!-- 份额 -->
            <span class="text-xs font-mono text-gray-600 dark:text-gray-400 w-12 text-right shrink-0">
              {{ ((item.share || 0) * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!items.length" class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无 SOV 排行数据
    </div>
  </div>
</template>
