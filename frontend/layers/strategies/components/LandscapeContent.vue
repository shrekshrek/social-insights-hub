<template>
  <div v-if="result" class="space-y-5">
    <!-- 竞争格局摘要 -->
    <div v-if="result.competitive_summary">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">竞争格局摘要</h4>
      <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        {{ result.competitive_summary }}
      </p>
    </div>

    <!-- 玩家阵营 -->
    <div v-if="result.players?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">玩家阵营</h4>
      <div class="grid md:grid-cols-2 gap-2">
        <div
          v-for="(player, idx) in result.players"
          :key="idx"
          class="p-2.5 rounded-lg"
          :class="roleBgClass(player.role)"
        >
          <!-- 标题行 -->
          <div class="flex items-center justify-between gap-1">
            <div class="flex items-center gap-1.5 min-w-0">
              <span class="font-medium text-sm text-gray-900 dark:text-white truncate">{{ player.name }}</span>
              <UBadge :color="roleColor(player.role)" variant="subtle" size="sm" class="shrink-0">
                {{ roleLabel(player.role) }}
              </UBadge>
            </div>
            <div class="flex items-center gap-1.5 text-[11px] text-gray-500 shrink-0">
              <span>SoV {{ formatPct(player.media_sov_pct) }}</span>
              <UBadge :color="sentimentColor(player.media_sentiment)" variant="subtle" size="sm">
                {{ sentimentLabel(player.media_sentiment) }}
              </UBadge>
              <span>{{ player.source_count }} 源</span>
            </div>
          </div>
          <!-- 叙事定位 -->
          <p v-if="player.narrative_position" class="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
            {{ player.narrative_position }}
          </p>
          <!-- 引用 -->
          <div v-if="player.evidence_quote" class="mt-1 text-[11px] italic text-gray-400 border-l-2 border-gray-200 dark:border-gray-700 pl-2">
            <template v-if="typeof player.evidence_quote === 'object'">
              "{{ truncateText(player.evidence_quote.quote, 60) }}"
            </template>
            <template v-else>"{{ truncateText(player.evidence_quote, 60) }}"</template>
          </div>
        </div>
      </div>
    </div>

    <!-- 定位图 -->
    <div v-if="result.positioning_map?.placements?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">定位图</h4>
      <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div class="text-xs text-gray-500 mb-2 flex items-center gap-3">
          <span>X 轴：{{ result.positioning_map.x_axis }}</span>
          <span>Y 轴：{{ result.positioning_map.y_axis }}</span>
        </div>
        <p v-if="result.positioning_map.rationale" class="text-xs text-gray-500 mb-2">
          {{ result.positioning_map.rationale }}
        </p>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
          <div
            v-for="(placement, idx) in result.positioning_map.placements"
            :key="idx"
            class="p-2 bg-white dark:bg-gray-900 rounded text-xs"
          >
            <span class="font-medium">{{ placement.name }}</span>
            <div class="text-gray-400 mt-0.5">X: {{ placement.x }} · Y: {{ placement.y }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 话语权博弈 -->
    <div v-if="result.discourse_battles?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">话语权博弈</h4>
      <div class="space-y-2">
        <div
          v-for="(battle, idx) in result.discourse_battles"
          :key="idx"
          class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg"
        >
          <div class="flex items-center justify-between gap-2">
            <p class="font-medium text-sm text-gray-900 dark:text-white">{{ battle.topic }}</p>
            <UBadge v-if="battle.winner" color="warning" variant="subtle" size="sm">
              胜方：{{ battle.winner }}
            </UBadge>
          </div>
          <p v-if="battle.players_involved?.length" class="mt-1 text-xs text-gray-600 dark:text-gray-300">
            参与者：{{ battle.players_involved.join('、') }}
          </p>
          <p v-if="battle.note" class="mt-1 text-xs text-gray-500">{{ battle.note }}</p>
        </div>
      </div>
    </div>

    <!-- 市场动态 -->
    <div v-if="hasMarketDynamics">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">市场动态</h4>
      <div class="grid md:grid-cols-3 gap-3">
        <div
          v-for="section in marketDynamicSections"
          :key="section.key"
          class="p-3 rounded-lg"
          :class="section.bgClass"
        >
          <p class="text-xs font-medium mb-1.5" :class="section.titleClass">{{ section.label }}</p>
          <ul class="space-y-1.5">
            <li
              v-for="(item, iIdx) in section.items"
              :key="iIdx"
              class="text-xs text-gray-700 dark:text-gray-300"
            >
              <template v-if="typeof item === 'object'">
                <span class="font-medium">{{ item.player || item.shift || '' }}</span>
                <span v-if="item.signal || item.implication" class="text-gray-500 block mt-0.5 pl-2">
                  {{ truncateText(item.signal || item.implication || '', 100) }}
                </span>
              </template>
              <template v-else>· {{ item }}</template>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { LandscapeResult, MarketDynamicEntry } from '../types'
import { UBadge } from '#components'

const props = defineProps<{
  result: LandscapeResult | null
}>()

const truncateText = (text: string, max: number) => {
  if (!text || text.length <= max) return text
  return text.slice(0, max) + '…'
}

const hasMarketDynamics = computed(() => {
  const d = props.result?.market_dynamics
  if (!d) return false
  return (d.momentum_gainers?.length ?? 0) > 0
    || (d.momentum_losers?.length ?? 0) > 0
    || (d.structural_shifts?.length ?? 0) > 0
})

const marketDynamicSections = computed(() => {
  const d = props.result?.market_dynamics
  if (!d) return []
  const sections: Array<{ key: string; label: string; items: MarketDynamicEntry[]; bgClass: string; titleClass: string }> = []
  if (d.momentum_gainers?.length) {
    sections.push({
      key: 'gainers', label: '势能上扬', items: d.momentum_gainers,
      bgClass: 'bg-green-50 dark:bg-green-900/20', titleClass: 'text-green-700 dark:text-green-300',
    })
  }
  if (d.momentum_losers?.length) {
    sections.push({
      key: 'losers', label: '势能下滑', items: d.momentum_losers,
      bgClass: 'bg-red-50 dark:bg-red-900/20', titleClass: 'text-red-700 dark:text-red-300',
    })
  }
  if (d.structural_shifts?.length) {
    sections.push({
      key: 'shifts', label: '结构性转变', items: d.structural_shifts,
      bgClass: 'bg-purple-50 dark:bg-purple-900/20', titleClass: 'text-purple-700 dark:text-purple-300',
    })
  }
  return sections
})

const roleColor = (r: string) => {
  if (r === 'target') return 'primary' as const
  if (r === 'competitor') return 'error' as const
  return 'neutral' as const
}

const roleLabel = (r: string) => {
  if (r === 'target') return '目标'
  if (r === 'competitor') return '竞品'
  return '背景'
}

const roleBgClass = (r: string) => {
  if (r === 'target') return 'bg-primary-50 dark:bg-primary-900/20'
  if (r === 'competitor') return 'bg-red-50 dark:bg-red-900/20'
  return 'bg-gray-50 dark:bg-gray-800'
}

const sentimentColor = (s: number | string) => {
  if (typeof s === 'number') {
    if (s > 0.6) return 'success' as const
    if (s < 0.4) return 'error' as const
    return 'neutral' as const
  }
  if (s === 'positive') return 'success' as const
  if (s === 'negative') return 'error' as const
  return 'neutral' as const
}

const sentimentLabel = (s: number | string) => {
  if (typeof s === 'number') {
    if (s > 0.6) return '正面'
    if (s < 0.4) return '负面'
    return '中性'
  }
  if (s === 'positive') return '正面'
  if (s === 'negative') return '负面'
  return '中性'
}

const formatPct = (pct: number) => {
  if (pct == null || Number.isNaN(pct)) return '--'
  return `${pct.toFixed(1)}%`
}
</script>
