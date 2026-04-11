<template>
  <div v-if="result" class="space-y-6">
    <!-- 竞争格局摘要 -->
    <div v-if="result.competitive_summary">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">竞争格局摘要</h4>
      <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        {{ result.competitive_summary }}
      </p>
    </div>

    <!-- 玩家列表 -->
    <div v-if="result.players?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">玩家阵营</h4>
      <div class="space-y-3">
        <div
          v-for="(player, idx) in result.players"
          :key="idx"
          class="p-3 rounded-lg"
          :class="roleBgClass(player.role)"
        >
          <div class="flex items-start justify-between gap-2 flex-wrap">
            <div class="flex items-center gap-2">
              <p class="font-medium text-gray-900 dark:text-white">{{ player.name }}</p>
              <UBadge :color="roleColor(player.role)" variant="subtle" size="xs">
                {{ roleLabel(player.role) }}
              </UBadge>
            </div>
            <div class="flex items-center gap-2 text-xs text-gray-500">
              <span>SoV {{ formatPct(player.media_sov_pct) }}</span>
              <UBadge :color="sentimentColor(player.media_sentiment)" variant="subtle" size="xs">
                {{ sentimentLabel(player.media_sentiment) }}
              </UBadge>
              <span>{{ player.source_count }} 源</span>
            </div>
          </div>
          <p v-if="player.narrative_position" class="mt-1.5 text-sm text-gray-700 dark:text-gray-300">
            <span class="font-medium">叙事定位：</span>{{ player.narrative_position }}
          </p>
          <p
            v-if="player.evidence_quote"
            class="mt-1.5 text-xs italic text-gray-500 dark:text-gray-400 border-l-2 border-gray-300 dark:border-gray-600 pl-2"
          >
            "{{ player.evidence_quote }}"
          </p>
        </div>
      </div>
    </div>

    <!-- 定位图 -->
    <div v-if="result.positioning_map?.placements?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">定位图</h4>
      <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div class="text-xs text-gray-500 mb-2">
          <span>X 轴：{{ result.positioning_map.x_axis }}</span>
          <span class="mx-2">·</span>
          <span>Y 轴：{{ result.positioning_map.y_axis }}</span>
        </div>
        <p v-if="result.positioning_map.rationale" class="text-xs text-gray-500 mb-2">
          {{ result.positioning_map.rationale }}
        </p>
        <div class="grid md:grid-cols-2 gap-2">
          <div
            v-for="(placement, idx) in result.positioning_map.placements"
            :key="idx"
            class="p-2 bg-white dark:bg-gray-900 rounded text-sm"
          >
            <span class="font-medium">{{ placement.name }}</span>
            <span class="text-gray-400 mx-1">·</span>
            <span class="text-xs text-gray-500">X: {{ placement.x }} / Y: {{ placement.y }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 话语权博弈 -->
    <div v-if="result.discourse_battles?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">话语权博弈</h4>
      <div class="space-y-3">
        <div
          v-for="(battle, idx) in result.discourse_battles"
          :key="idx"
          class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg"
        >
          <p class="font-medium text-gray-900 dark:text-white">{{ idx + 1 }}. {{ battle.topic }}</p>
          <p v-if="battle.players_involved?.length" class="mt-1 text-sm text-gray-700 dark:text-gray-300">
            <span class="font-medium">参与者：</span>{{ battle.players_involved.join('、') }}
          </p>
          <p v-if="battle.winner" class="mt-1 text-xs text-amber-700 dark:text-amber-400">
            胜方：{{ battle.winner }}
          </p>
          <p v-if="battle.agenda_map_battle_ref" class="mt-1 text-xs text-gray-500">
            关联 Agenda Map 议程：{{ battle.agenda_map_battle_ref }}
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
          v-if="result.market_dynamics?.momentum_gainers?.length"
          class="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg"
        >
          <p class="text-xs font-medium text-green-700 dark:text-green-300 mb-1.5">势能上扬</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(item, idx) in result.market_dynamics.momentum_gainers"
              :key="idx"
            >
              · {{ item }}
            </li>
          </ul>
        </div>
        <div
          v-if="result.market_dynamics?.momentum_losers?.length"
          class="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg"
        >
          <p class="text-xs font-medium text-red-700 dark:text-red-300 mb-1.5">势能下滑</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(item, idx) in result.market_dynamics.momentum_losers"
              :key="idx"
            >
              · {{ item }}
            </li>
          </ul>
        </div>
        <div
          v-if="result.market_dynamics?.structural_shifts?.length"
          class="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg"
        >
          <p class="text-xs font-medium text-purple-700 dark:text-purple-300 mb-1.5">结构性转变</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(item, idx) in result.market_dynamics.structural_shifts"
              :key="idx"
            >
              · {{ item }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { LandscapeResult } from '../types'
import { UBadge } from '#components'

const props = defineProps<{
  result: LandscapeResult | null
}>()

const hasMarketDynamics = computed(() => {
  const d = props.result?.market_dynamics
  if (!d) return false
  return (d.momentum_gainers?.length ?? 0) > 0
    || (d.momentum_losers?.length ?? 0) > 0
    || (d.structural_shifts?.length ?? 0) > 0
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

const sentimentColor = (s: string) => {
  if (s === 'positive') return 'success' as const
  if (s === 'negative') return 'error' as const
  return 'neutral' as const
}

const sentimentLabel = (s: string) => {
  if (s === 'positive') return '正面'
  if (s === 'negative') return '负面'
  return '中性'
}

const formatPct = (pct: number) => {
  if (pct == null || Number.isNaN(pct)) return '--'
  return `${pct.toFixed(1)}%`
}
</script>
