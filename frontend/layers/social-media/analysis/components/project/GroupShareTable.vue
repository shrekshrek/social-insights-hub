<script setup lang="ts">
import { computed, ref } from 'vue'
import TabSwitch from '../shared/TabSwitch.vue'
import SpamRatioBar from '../shared/SpamRatioBar.vue'

interface SpamDistribution {
  high_spam: { total: number; post: number; comment: number }
  low_spam: { total: number; post: number; comment: number }
}

interface GroupShareItem {
  name: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  mentions: number
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  spam_distribution?: SpamDistribution
}

const props = defineProps<{
  data: GroupShareItem[]
  entities?: Array<{
    name: string
    parent?: string
    heat?: number
    organic_heat?: number
    promo_heat?: number
    mentions?: number
    role?: string
    sentiment?: number
    organic_sentiment?: number
    promo_sentiment?: number
    spam_distribution?: SpamDistribution
  }>
  maxItems?: number
}>()

const maxItems = computed(() => props.maxItems ?? 10)

// ==================== 声量视角 ====================

type SpamView = 'all' | 'promo' | 'organic'
const spamView = ref<SpamView>('all')

const spamViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 指标模式（不含有机/推广，已移至视角）====================

type MetricMode = 'heat' | 'mentions' | 'efficiency'
const metricMode = ref<MetricMode>('heat')

const metricModeOptions = [
  { value: 'heat', label: '热度' },
  { value: 'mentions', label: '提及' },
  { value: 'efficiency', label: '效能' },
]

// ==================== 能力检测 ====================

const hasSpamData = computed(() =>
  (props.data || []).some(i => i.spam_distribution != null),
)

// ==================== 有机/推广指标辅助 ====================

const getOrganicMentions = (item: { spam_distribution?: SpamDistribution }): number =>
  item.spam_distribution?.low_spam.total ?? 0

const getPromoMentions = (item: { spam_distribution?: SpamDistribution }): number =>
  item.spam_distribution?.high_spam.total ?? 0

// ==================== 动态标签 ====================

const metricLabel = computed(() => {
  if (metricMode.value === 'efficiency') return '效能'
  if (metricMode.value === 'mentions') {
    if (spamView.value === 'organic') return '有机提及'
    if (spamView.value === 'promo') return '推广提及'
    return '提及'
  }
  if (spamView.value === 'organic') return '有机热度'
  if (spamView.value === 'promo') return '推广热度'
  return '热度'
})

const shareLabel = computed(() => {
  if (spamView.value === 'organic') return '有机份额'
  if (spamView.value === 'promo') return '推广份额'
  if (metricMode.value === 'mentions') return '份额(提及)'
  return '份额(热度)'
})

const innerShareLabel = computed(() => {
  if (spamView.value === 'organic') return '集团内(有机)'
  if (spamView.value === 'promo') return '集团内(推广)'
  if (metricMode.value === 'mentions') return '集团内(提及)'
  return '集团内(热度)'
})

// ==================== 指标计算（结合视角）====================

const getEffectiveMentions = (item: { mentions?: number; spam_distribution?: SpamDistribution }): number => {
  if (spamView.value === 'organic') return getOrganicMentions(item)
  if (spamView.value === 'promo') return getPromoMentions(item)
  return item.mentions || 0
}

const getEffectiveHeat = (item: { heat?: number; organic_heat?: number; promo_heat?: number; spam_distribution?: SpamDistribution }): number => {
  if (spamView.value === 'organic') return item.organic_heat ?? getOrganicMentions(item)
  if (spamView.value === 'promo') return item.promo_heat ?? getPromoMentions(item)
  return item.heat || 0
}

const getMetricValue = (item: { heat?: number; organic_heat?: number; promo_heat?: number; mentions?: number; spam_distribution?: SpamDistribution }): number => {
  if (metricMode.value === 'efficiency') {
    const denom = getEffectiveMentions(item)
    return denom > 0 ? getEffectiveHeat(item) / denom : 0
  }
  if (metricMode.value === 'mentions') return getEffectiveMentions(item)
  if (spamView.value === 'organic') return item.organic_heat ?? getOrganicMentions(item)
  if (spamView.value === 'promo') return item.promo_heat ?? getPromoMentions(item)
  return item.heat || 0
}

// ==================== 份额分母 ====================

const totalOrganicMentions = computed(() =>
  (props.data || []).reduce((s, g) => s + getOrganicMentions(g), 0),
)

const totalPromoMentions = computed(() =>
  (props.data || []).reduce((s, g) => s + getPromoMentions(g), 0),
)

const totalOrganicHeat = computed(() =>
  (props.data || []).reduce((s, g) => s + (g.organic_heat ?? getOrganicMentions(g)), 0),
)

const totalPromoHeat = computed(() =>
  (props.data || []).reduce((s, g) => s + (g.promo_heat ?? getPromoMentions(g)), 0),
)

// ==================== 树结构 ====================

interface TreeNode {
  name: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  mentions: number
  share: number
  innerShare?: number
  isGroup: boolean
  role?: string
  memberCount?: number
  top3Share?: number
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  spam_distribution?: SpamDistribution
  children: TreeNode[]
}

const treeData = computed<TreeNode[]>(() => {
  const groups = props.data || []
  const entities = props.entities || []
  if (!groups.length) return []

  const totalHeat = groups.reduce((sum, g) => sum + (g.heat || 0), 0)
  const totalMentions = groups.reduce((sum, g) => sum + (g.mentions || 0), 0)
  const totalOrganic = totalOrganicMentions.value
  const totalPromo = totalPromoMentions.value

  // 份额分母：视角优先，视角为 all 时由指标模式决定
  const getShareBase = (): number => {
    if (spamView.value === 'organic') return Math.max(totalOrganicHeat.value, 1)
    if (spamView.value === 'promo') return Math.max(totalPromoHeat.value, 1)
    if (metricMode.value === 'mentions') return Math.max(totalMentions, 1)
    return Math.max(totalHeat, 1)
  }

  const getItemShareMetric = (item: { heat?: number; organic_heat?: number; promo_heat?: number; mentions?: number; spam_distribution?: SpamDistribution }): number => {
    if (spamView.value === 'organic') return item.organic_heat ?? getOrganicMentions(item)
    if (spamView.value === 'promo') return item.promo_heat ?? getPromoMentions(item)
    if (metricMode.value === 'mentions') return item.mentions || 0
    return item.heat || 0
  }

  // parent → entities 映射
  const entityByParent: Record<string, typeof entities> = {}
  for (const e of entities) {
    const parent = (e.parent || '').trim() || e.name
    if (!entityByParent[parent]) entityByParent[parent] = []
    entityByParent[parent].push(e)
  }

  const shareBase = getShareBase()

  const sortedGroups = groups
    .slice()
    .sort((a, b) => getMetricValue(b) - getMetricValue(a))
    .slice(0, maxItems.value)

  return sortedGroups.map(g => {
    const childrenAll = (entityByParent[g.name] || [])
      .filter(e => e.name !== g.name)
      .map(e => {
        const childShareMetric = getItemShareMetric(e)
        return {
          name: e.name,
          heat: e.heat || 0,
          organic_heat: e.organic_heat,
          promo_heat: e.promo_heat,
          mentions: e.mentions || 0,
          share: shareBase > 0 ? childShareMetric / shareBase : 0,
          isGroup: false as const,
          role: e.role,
          sentiment: e.sentiment,
          organic_sentiment: e.organic_sentiment,
          promo_sentiment: e.promo_sentiment,
          spam_distribution: e.spam_distribution,
          children: [] as TreeNode[],
          _shareMetric: childShareMetric,
        }
      })
      .sort((a, b) => getMetricValue(b) - getMetricValue(a))

    const groupShareMetric = getItemShareMetric(g)
    const top3Value = childrenAll.slice(0, 3).reduce((sum, c) => sum + c._shareMetric, 0)

    const children = childrenAll.map(child => ({
      ...child,
      innerShare: groupShareMetric > 0 ? child._shareMetric / groupShareMetric : 0,
    }))

    return {
      name: g.name,
      heat: g.heat || 0,
      organic_heat: g.organic_heat,
      promo_heat: g.promo_heat,
      mentions: g.mentions || 0,
      share: shareBase > 0 ? groupShareMetric / shareBase : 0,
      isGroup: true,
      memberCount: childrenAll.length,
      top3Share: groupShareMetric > 0 ? top3Value / groupShareMetric : 0,
      sentiment: g.sentiment,
      organic_sentiment: g.organic_sentiment,
      promo_sentiment: g.promo_sentiment,
      spam_distribution: g.spam_distribution,
      children: children.slice(0, 5),
    }
  })
})

// ==================== 展开状态 ====================

const expandedGroups = ref<Set<string>>(new Set())
const toggleGroup = (name: string) => {
  const s = new Set(expandedGroups.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedGroups.value = s
}
const isExpanded = (name: string) => expandedGroups.value.has(name)

// ==================== 情感显示 ====================

const getDisplaySentiment = (node: { sentiment?: number; organic_sentiment?: number; promo_sentiment?: number }): number | null => {
  if (spamView.value === 'organic') return node.organic_sentiment ?? node.sentiment ?? null
  if (spamView.value === 'promo') return node.promo_sentiment ?? node.sentiment ?? null
  return node.sentiment ?? null
}

const hasSentimentData = computed(() =>
  treeData.value.some(n => n.sentiment != null),
)

const fmtSentiment = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`

// ==================== 格式化 ====================

const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toFixed(0)
}

const formatPercent = (n: number) => `${(n * 100).toFixed(1)}%`

const formatMetricValue = (node: { heat: number; organic_heat?: number; promo_heat?: number; mentions: number; spam_distribution?: SpamDistribution }) => {
  if (metricMode.value === 'efficiency') {
    const denom = getEffectiveMentions(node)
    return `${denom > 0 ? (getEffectiveHeat(node) / denom).toFixed(1) : '-'}x`
  }
  return formatNumber(getEffectiveMentions(node))
}

const maxShare = computed(() => {
  const shares = treeData.value.map(t => t.share)
  return Math.max(...shares, 0.000001)
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 h-[520px] flex flex-col">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">集团军声量</h3>
      <div class="flex items-center gap-2">
        <TabSwitch v-model="metricMode" :options="metricModeOptions" />
        <TabSwitch v-if="hasSpamData" v-model="spamView" :options="spamViewOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">按 Parent 聚合</span>
      </div>
    </div>

    <!-- 视角说明 -->
    <div
      v-if="spamView !== 'all'"
      class="mb-2 px-2.5 py-1.5 rounded bg-blue-50 dark:bg-blue-900/20 text-[11px] text-blue-700 dark:text-blue-400"
    >
      <template v-if="spamView === 'organic'">
        <b>有机视角</b>：提及数与份额均以有机声量（低推广内容）为口径
      </template>
      <template v-else>
        <b>推广视角</b>：提及数与份额均以推广声量（高推广内容）为口径
      </template>
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
                <div class="flex items-center gap-2 mb-1">
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
                  <!-- 情感（后端填充后自动显示） -->
                  <span
                    v-if="hasSentimentData && getDisplaySentiment(node) != null"
                    class="text-[10px] font-mono"
                    :class="(getDisplaySentiment(node) ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
                    :title="spamView === 'organic' ? '有机情感' : spamView === 'promo' ? '推广情感' : '整体情感'"
                  >
                    {{ fmtSentiment(getDisplaySentiment(node) ?? 0) }}
                  </span>
                </div>
                <div v-if="node.spam_distribution" class="ml-5">
                  <SpamRatioBar :spam-distribution="node.spam_distribution" />
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
                  <div class="flex items-center gap-1.5 mb-1">
                    <span class="text-gray-600 dark:text-gray-400">{{ child.name }}</span>
                    <span
                      v-if="child.role && child.role !== 'Context'"
                      class="px-1 py-0.5 rounded text-[9px] font-medium"
                      :class="child.role === 'Target' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'"
                    >
                      {{ child.role === 'Target' ? '主体' : '竞品' }}
                    </span>
                    <!-- 子实体情感 -->
                    <span
                      v-if="hasSentimentData && getDisplaySentiment(child) != null"
                      class="text-[10px] font-mono"
                      :class="(getDisplaySentiment(child) ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
                    >
                      {{ fmtSentiment(getDisplaySentiment(child) ?? 0) }}
                    </span>
                  </div>
                  <div v-if="child.spam_distribution">
                    <SpamRatioBar :spam-distribution="child.spam_distribution" />
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
