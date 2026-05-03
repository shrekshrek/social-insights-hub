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
          <!-- 关键论述（key_claims） -->
          <ul v-if="player.key_claims?.length" class="mt-1.5 space-y-0.5">
            <li
              v-for="(claim, ci) in player.key_claims"
              :key="ci"
              class="text-[11px] text-gray-600 dark:text-gray-300 pl-2 relative before:content-['·'] before:absolute before:left-0 before:text-gray-400"
            >
              {{ claim }}
            </li>
          </ul>
          <!-- 引用 -->
          <div v-if="quoteText(player.evidence_quote)" class="mt-1 text-[11px] italic text-gray-400 border-l-2 border-gray-200 dark:border-gray-700 pl-2">
            "{{ truncateText(quoteText(player.evidence_quote), 120) }}"
          </div>
        </div>
      </div>
    </div>

    <!-- 定位图（2D 象限可视化） -->
    <div v-if="result.positioning_map?.positions?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">定位图</h4>
      <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <!-- 轴说明 + 选轴理由 -->
        <div class="text-xs text-gray-600 dark:text-gray-300 mb-3 space-y-1">
          <p>
            <span class="font-medium">X 轴：</span>{{ result.positioning_map.x_axis?.label }}
            <span class="text-gray-400">（{{ result.positioning_map.x_axis?.low }} ↔ {{ result.positioning_map.x_axis?.high }}）</span>
          </p>
          <p>
            <span class="font-medium">Y 轴：</span>{{ result.positioning_map.y_axis?.label }}
            <span class="text-gray-400">（{{ result.positioning_map.y_axis?.low }} ↔ {{ result.positioning_map.y_axis?.high }}）</span>
          </p>
          <p v-if="result.positioning_map.rationale" class="text-gray-500 dark:text-gray-400 italic">
            {{ result.positioning_map.rationale }}
          </p>
        </div>

        <!-- 2D 象限网格 -->
        <div class="relative w-full max-w-md mx-auto aspect-square bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded">
          <!-- 中线 -->
          <div class="absolute inset-x-0 top-1/2 border-t border-dashed border-gray-300 dark:border-gray-600" />
          <div class="absolute inset-y-0 left-1/2 border-l border-dashed border-gray-300 dark:border-gray-600" />

          <!-- 轴端点标签 -->
          <span class="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] text-gray-500 whitespace-nowrap">
            ↑ {{ result.positioning_map.y_axis?.high }}
          </span>
          <span class="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[10px] text-gray-500 whitespace-nowrap">
            ↓ {{ result.positioning_map.y_axis?.low }}
          </span>
          <span class="absolute top-1/2 -left-2 -translate-x-full -translate-y-1/2 text-[10px] text-gray-500 whitespace-nowrap">
            {{ result.positioning_map.x_axis?.low }} ←
          </span>
          <span class="absolute top-1/2 -right-2 translate-x-full -translate-y-1/2 text-[10px] text-gray-500 whitespace-nowrap">
            → {{ result.positioning_map.x_axis?.high }}
          </span>

          <!-- 玩家点位 -->
          <div
            v-for="(pos, idx) in result.positioning_map.positions"
            :key="idx"
            class="absolute -translate-x-1/2 translate-y-1/2"
            :style="{
              left: `${(clampCoord(pos.x) + 1) * 50}%`,
              bottom: `${(clampCoord(pos.y) + 1) * 50}%`,
            }"
          >
            <div class="flex items-center gap-1">
              <div
                class="w-2.5 h-2.5 rounded-full shrink-0"
                :class="pos.player === targetPlayerName ? 'bg-primary-500' : 'bg-gray-500 dark:bg-gray-400'"
              />
              <span class="text-[10px] font-medium text-gray-700 dark:text-gray-200 whitespace-nowrap">
                {{ pos.player }}
              </span>
            </div>
          </div>
        </div>

        <!-- 定位理由列表（点位下方展开） -->
        <ul class="mt-6 space-y-1.5">
          <li
            v-for="(pos, idx) in result.positioning_map.positions"
            :key="idx"
            class="text-xs text-gray-600 dark:text-gray-300"
          >
            <span class="font-medium">{{ pos.player }}</span>
            <span class="text-gray-400 ml-1">(x: {{ formatCoord(pos.x) }} · y: {{ formatCoord(pos.y) }})</span>
            <span v-if="pos.rationale" class="block mt-0.5 pl-3 text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">
              {{ pos.rationale }}
            </span>
          </li>
        </ul>
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
          <p class="font-medium text-sm text-gray-900 dark:text-white">{{ battle.battle }}</p>

          <!-- 双阵营 -->
          <div class="mt-2 grid md:grid-cols-2 gap-2">
            <div v-if="battle.leaders?.length" class="bg-white dark:bg-gray-800 rounded p-2">
              <p class="text-[10px] font-medium text-gray-500 mb-1">主导方</p>
              <ul class="space-y-0.5">
                <li
                  v-for="(camp, ci) in battle.leaders"
                  :key="ci"
                  class="text-[11px] text-gray-700 dark:text-gray-300"
                >
                  <span class="font-medium">{{ camp.player }}</span>
                  <span v-if="camp.stance" class="text-gray-500">：{{ camp.stance }}</span>
                </li>
              </ul>
            </div>
            <div v-if="battle.challengers?.length" class="bg-white dark:bg-gray-800 rounded p-2">
              <p class="text-[10px] font-medium text-gray-500 mb-1">挑战方</p>
              <ul class="space-y-0.5">
                <li
                  v-for="(camp, ci) in battle.challengers"
                  :key="ci"
                  class="text-[11px] text-gray-700 dark:text-gray-300"
                >
                  <span class="font-medium">{{ camp.player }}</span>
                  <span v-if="camp.stance" class="text-gray-500">：{{ camp.stance }}</span>
                </li>
              </ul>
            </div>
          </div>

          <!-- 走向 + 证据 -->
          <p v-if="battle.shift_direction" class="mt-2 text-xs text-amber-700 dark:text-amber-300">
            <span class="font-medium">走向：</span>{{ battle.shift_direction }}
          </p>
          <p v-if="battle.evidence" class="mt-1 text-xs text-gray-600 dark:text-gray-300 leading-relaxed">
            <span class="font-medium">证据：</span>{{ battle.evidence }}
          </p>
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
                <span v-if="item.signal || item.implication" class="text-gray-500 block mt-0.5 pl-2 leading-relaxed">
                  {{ isItemExpanded(section.key, iIdx) || (item.signal || item.implication || '').length <= 100
                    ? (item.signal || item.implication)
                    : truncateText(item.signal || item.implication || '', 100)
                  }}
                  <button
                    v-if="(item.signal || item.implication || '').length > 100"
                    class="text-primary-500 hover:text-primary-600 ml-1 cursor-pointer"
                    @click="toggleItemExpanded(section.key, iIdx)"
                  >
                    {{ isItemExpanded(section.key, iIdx) ? '收起' : '展开' }}
                  </button>
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
import type { LandscapeResult, MarketDynamicEntry, EvidenceQuote } from '../types'
import { sentimentColor, sentimentLabel } from '../composables/useStrategyConstants'
import { UBadge } from '#components'

const props = defineProps<{
  result: LandscapeResult | null
}>()

const truncateText = (text: string, max: number) => {
  if (!text || text.length <= max) return text
  return text.slice(0, max) + '…'
}

/** evidence_quote 兼容字符串 / 对象两种返回 */
const quoteText = (q: string | EvidenceQuote | undefined | null): string => {
  if (!q) return ''
  if (typeof q === 'string') return q
  return q.quote ?? ''
}

/** 把 [-1,1] 范围的坐标限制在 [-1,1]，避免 LLM 偶尔输出越界值导致点位飞出网格 */
const clampCoord = (n: number) => Math.max(-1, Math.min(1, n ?? 0))

const formatCoord = (n: number) => {
  if (n == null || Number.isNaN(n)) return '--'
  return n.toFixed(2)
}

/** target 玩家在定位图中高亮（与 player.role 对齐） */
const targetPlayerName = computed(() => {
  return props.result?.players?.find(p => p.role === 'target')?.name ?? ''
})

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

// 市场动态条目展开状态：key=`${sectionKey}:${itemIdx}`
const expandedItems = ref(new Set<string>())
const isItemExpanded = (sectionKey: string, idx: number) =>
  expandedItems.value.has(`${sectionKey}:${idx}`)
const toggleItemExpanded = (sectionKey: string, idx: number) => {
  const key = `${sectionKey}:${idx}`
  const next = new Set(expandedItems.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedItems.value = next
}

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

const formatPct = (pct: number) => {
  if (pct == null || Number.isNaN(pct)) return '--'
  return `${pct.toFixed(1)}%`
}
</script>
