<script setup lang="ts">
import { computed, ref } from 'vue'
import TabSwitch from '../shared/TabSwitch.vue'

interface GroupShareItem {
  name: string
  heat: number
  mentions: number
}

const props = defineProps<{
  data: GroupShareItem[]
  entities?: Array<{
    name: string
    parent?: string
    heat?: number
    mentions?: number
    role?: string
  }>
  maxItems?: number
}>()

const maxItems = computed(() => props.maxItems ?? 10)
type MetricMode = 'heat' | 'mentions' | 'efficiency'
const metricMode = ref<MetricMode>('heat')

const metricModeOptions = [
  { value: 'heat', label: '热度' },
  { value: 'mentions', label: '提及' },
  { value: 'efficiency', label: '效能' },
]

const metricLabel = computed(() => (metricMode.value === 'mentions' ? '提及' : metricMode.value === 'efficiency' ? '效能' : '热度'))
const shareLabel = computed(() => (metricMode.value === 'mentions' ? '份额(提及)' : '份额(热度)'))
const innerShareLabel = computed(() => (metricMode.value === 'mentions' ? '集团内(提及)' : '集团内(热度)'))

// 构建树结构：parent -> children
interface TreeNode {
  name: string
  heat: number
  mentions: number
  share: number
  innerShare?: number
  isGroup: boolean
  role?: string
  memberCount?: number
  top3Share?: number
  children: TreeNode[]
}

const treeData = computed<TreeNode[]>(() => {
  const groups = props.data || []
  const entities = props.entities || []
  if (!groups.length) return []

  // 计算总热度
  const totalHeat = groups.reduce((sum, g) => sum + (g.heat || 0), 0)
  const totalMentions = groups.reduce((sum, g) => sum + (g.mentions || 0), 0)
  const shareMode = metricMode.value === 'mentions' ? 'mentions' : 'heat'
  const totalShareBase = shareMode === 'mentions' ? totalMentions : totalHeat

  const getMetricValue = (item: { heat?: number; mentions?: number }) => {
    const heat = item.heat || 0
    const mentions = item.mentions || 0
    if (metricMode.value === 'mentions') return mentions
    if (metricMode.value === 'efficiency') return mentions > 0 ? heat / mentions : 0
    return heat
  }

  // 构建 parent -> entity 映射
  const entityByParent: Record<string, typeof entities> = {}
  for (const e of entities) {
    const parent = (e.parent || '').trim() || e.name
    if (!entityByParent[parent]) entityByParent[parent] = []
    entityByParent[parent].push(e)
  }

  // 构建树
  const tree: TreeNode[] = []
  const sortedGroups = groups
    .slice()
    .sort((a, b) => getMetricValue(b) - getMetricValue(a))
    .slice(0, maxItems.value)

  for (const g of sortedGroups) {
    const childrenAll = (entityByParent[g.name] || [])
      .filter(e => e.name !== g.name)
      .map(e => ({
        name: e.name,
        heat: e.heat || 0,
        mentions: e.mentions || 0,
        share: totalShareBase > 0 ? ((shareMode === 'mentions' ? (e.mentions || 0) : (e.heat || 0)) / totalShareBase) : 0,
        isGroup: false,
        role: e.role,
        children: [],
      }))
      .sort((a, b) => getMetricValue(b) - getMetricValue(a))

    const groupShareBase = shareMode === 'mentions' ? (g.mentions || 0) : (g.heat || 0)
    const totalShareValue = shareMode === 'mentions' ? (g.mentions || 0) : (g.heat || 0)
    const top3Value = childrenAll.slice(0, 3).reduce((sum, c) => {
      const v = shareMode === 'mentions' ? (c.mentions || 0) : (c.heat || 0)
      return sum + v
    }, 0)

    const children = childrenAll
      .map(child => ({
        ...child,
        innerShare: groupShareBase > 0
          ? ((shareMode === 'mentions' ? (child.mentions || 0) : (child.heat || 0)) / groupShareBase)
          : 0,
      }))

    tree.push({
      name: g.name,
      heat: g.heat || 0,
      mentions: g.mentions || 0,
      share: totalShareBase > 0 ? totalShareValue / totalShareBase : 0,
      isGroup: true,
      memberCount: childrenAll.length,
      top3Share: groupShareBase > 0 ? top3Value / groupShareBase : 0,
      children: children.slice(0, 5),
    })
  }

  return tree
})

// 展开状态
const expandedGroups = ref<Set<string>>(new Set())
const toggleGroup = (name: string) => {
  const s = new Set(expandedGroups.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedGroups.value = s
}
const isExpanded = (name: string) => expandedGroups.value.has(name)

// 格式化
const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toFixed(0)
}

const formatPercent = (n: number) => `${(n * 100).toFixed(1)}%`

const formatMetricValue = (item: { heat: number; mentions: number }) => {
  if (metricMode.value === 'efficiency') {
    return `${item.mentions > 0 ? (item.heat / item.mentions).toFixed(1) : '-'}x`
  }
  return formatNumber(metricMode.value === 'mentions' ? item.mentions : item.heat)
}

// 最大份额用于进度条
const maxShare = computed(() => {
  const shares = treeData.value.map(t => t.share)
  return Math.max(...shares, 0.000001)
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 h-[520px] flex flex-col">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">集团军声量</h3>
      <div class="flex items-center gap-2">
        <TabSwitch v-model="metricMode" :options="metricModeOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">按 Parent 聚合</span>
      </div>
    </div>

    <div class="flex-1 overflow-auto">
      <table class="w-full text-sm">
        <thead class="sticky top-0 z-10 bg-white dark:bg-gray-900">
          <tr class="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
            <th class="py-2 pr-4 font-medium">集团/品牌</th>
            <th class="py-2 pr-4 font-medium text-right">{{ metricLabel }}</th>
            <th class="py-2 pr-4 font-medium text-right">{{ shareLabel }}</th>
            <th class="py-2 pr-4 font-medium text-right">{{ innerShareLabel }}</th>
            <th class="py-2 font-medium w-32">分布</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50 dark:divide-gray-800/50">
          <template v-for="node in treeData" :key="node.name">
            <!-- 集团行 -->
            <tr
              class="cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/30"
              :class="{ 'bg-gray-50/50 dark:bg-gray-800/20': isExpanded(node.name) }"
              @click="node.children.length && toggleGroup(node.name)"
            >
              <td class="py-2.5 pr-4">
                <div class="flex items-center gap-2">
                  <UIcon
                    v-if="node.children.length"
                    name="i-heroicons-chevron-right"
                    class="w-3.5 h-3.5 text-gray-400 transition-transform shrink-0"
                    :class="{ 'rotate-90': isExpanded(node.name) }"
                  />
                  <span v-else class="w-3.5" />
                  <span class="font-medium text-gray-900 dark:text-white">{{ node.name }}</span>
                  <span
                    v-if="node.memberCount"
                    class="text-[10px] text-gray-400 dark:text-gray-500"
                  >
                    ({{ node.memberCount }})
                  </span>
                  <span
                    v-if="node.memberCount && node.top3Share"
                    class="text-[10px] text-gray-400 dark:text-gray-500"
                  >
                    Top3 {{ formatPercent(node.top3Share) }}
                  </span>
                </div>
              </td>
              <td class="py-2.5 pr-4 text-right font-mono text-gray-700 dark:text-gray-300">
                {{ formatMetricValue(node) }}
              </td>
              <td class="py-2.5 pr-4 text-right font-mono text-gray-700 dark:text-gray-300">
                {{ formatPercent(node.share) }}
              </td>
              <td class="py-2.5 pr-4 text-right font-mono text-gray-400 dark:text-gray-500">
                —
              </td>
              <td class="py-2.5">
                <div class="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-primary-500 rounded-full transition-all"
                    :style="{ width: `${(node.share / maxShare) * 100}%` }"
                  />
                </div>
              </td>
            </tr>

            <!-- 子实体行 -->
            <template v-if="isExpanded(node.name)">
              <tr
                v-for="child in node.children"
                :key="`${node.name}-${child.name}`"
                class="bg-gray-50/50 dark:bg-gray-800/20"
              >
                <td class="py-2 pr-4 pl-8">
                  <div class="flex items-center gap-1.5">
                    <span class="text-gray-600 dark:text-gray-400">{{ child.name }}</span>
                    <span
                      v-if="child.role && child.role !== 'Context'"
                      class="px-1 py-0.5 rounded text-[9px] font-medium"
                      :class="child.role === 'Target' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'"
                    >
                      {{ child.role === 'Target' ? '主体' : '竞品' }}
                    </span>
                  </div>
                </td>
                <td class="py-2 pr-4 text-right font-mono text-xs text-gray-500 dark:text-gray-400">
                  {{ formatMetricValue(child) }}
                </td>
                <td class="py-2 pr-4 text-right font-mono text-xs text-gray-500 dark:text-gray-400">
                  {{ formatPercent(child.share) }}
                </td>
                <td class="py-2 pr-4 text-right font-mono text-xs text-gray-500 dark:text-gray-400">
                  {{ formatPercent(child.innerShare || 0) }}
                </td>
                <td class="py-2">
                  <div class="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div
                      class="h-full bg-primary-300 dark:bg-primary-600 rounded-full"
                      :style="{ width: `${(child.innerShare || 0) * 100}%` }"
                    />
                  </div>
                </td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>
    </div>

    <div v-if="!treeData.length" class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无集团声量数据
    </div>
  </div>
</template>
