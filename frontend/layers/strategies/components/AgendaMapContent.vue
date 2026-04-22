<template>
  <div v-if="result" class="space-y-5">
    <!-- 媒体格局摘要 -->
    <div v-if="result.media_landscape_summary">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">媒体格局摘要</h4>
      <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
        {{ result.media_landscape_summary }}
      </p>
    </div>

    <!-- 叙事地图 -->
    <div v-if="result.narrative_map?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">叙事地图</h4>
      <div class="space-y-2">
        <div
          v-for="(narrative, idx) in sortedNarrativeMap"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <!-- 标题行：排名 + 主题 + 标签 -->
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-xs font-mono text-gray-400 shrink-0">#{{ narrative.heat_rank || idx + 1 }}</span>
              <span class="font-medium text-gray-900 dark:text-white truncate">{{ narrative.theme }}</span>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <UBadge :color="sentimentColor(narrative.sentiment)" variant="subtle" size="sm">
                {{ sentimentLabel(narrative.sentiment) }}
              </UBadge>
              <UBadge :color="credibilityColor(narrative.credibility)" variant="subtle" size="sm">
                {{ narrative.credibility === 'high' ? '高可信' : narrative.credibility === 'medium' ? '中可信' : '低可信' }}
              </UBadge>
              <!-- 来源分布内联 -->
              <span v-if="narrative.supporting_sources" class="text-[10px] text-gray-400 ml-1">
                <template v-for="(count, tier) in narrative.supporting_sources" :key="tier">
                  <span v-if="count" class="mr-1">{{ tierLabel(tier as string) }}×{{ count }}</span>
                </template>
              </span>
            </div>
          </div>
          <!-- 框架（合并到主题下方，更紧凑） -->
          <p v-if="narrative.framing" class="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
            {{ narrative.framing }}
          </p>
          <!-- 代表声音（折叠，只显示第一条，点击展开） -->
          <div v-if="narrative.representative_voices?.length" class="mt-1.5">
            <div
              v-for="(voice, vi) in expandedNarratives.has(idx) ? narrative.representative_voices : narrative.representative_voices.slice(0, 1)"
              :key="vi"
              class="text-xs text-gray-500 dark:text-gray-400 border-l-2 border-gray-200 dark:border-gray-700 pl-2 mt-1"
            >
              <span class="italic">"{{ truncateText(voice.quote, 80) }}"</span>
              <span class="text-gray-400 ml-1">— {{ voice.speaker || voice.source_name || '媒体' }}</span>
            </div>
            <button
              v-if="narrative.representative_voices.length > 1"
              class="mt-1 text-xs text-primary-500 hover:text-primary-600 cursor-pointer"
              @click="toggleNarrative(idx)"
            >
              {{ expandedNarratives.has(idx) ? '收起' : `展开全部 ${narrative.representative_voices.length} 条引用` }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 议程博弈 -->
    <div v-if="result.agenda_battles?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">议程博弈</h4>
      <div class="space-y-2">
        <div
          v-for="(battle, idx) in result.agenda_battles"
          :key="idx"
          class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg"
        >
          <p class="font-medium text-gray-900 dark:text-white text-sm">{{ battle.topic }}</p>
          <div v-if="battle.sides?.length" class="mt-1.5 flex flex-wrap gap-2">
            <div
              v-for="(side, si) in battle.sides"
              :key="si"
              class="text-xs text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-800 px-2 py-1 rounded"
            >
              <span class="font-medium">{{ side.stance }}</span>
              <span class="text-gray-400 ml-1">{{ side.supporters_brief }}</span>
            </div>
          </div>
          <p v-if="battle.dominant_side" class="mt-1 text-xs text-amber-600 dark:text-amber-400">
            主导方：{{ battle.dominant_side }}
          </p>
        </div>
      </div>
    </div>

    <!-- 媒体声量模式 + 注意力缺口：并排两栏 -->
    <div class="grid md:grid-cols-2 gap-4">
      <!-- 媒体声量模式 -->
      <div v-if="hasVoicePatterns">
        <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">媒体声量模式</h4>
        <div class="space-y-2">
          <div
            v-for="(section, sIdx) in voicePatternSections"
            :key="sIdx"
            class="p-2.5 rounded-lg"
            :class="section.bgClass"
          >
            <p class="text-xs font-medium mb-1" :class="section.titleClass">{{ section.label }}</p>
            <ul class="space-y-1">
              <li
                v-for="(item, iIdx) in section.items"
                :key="iIdx"
                class="text-xs text-gray-700 dark:text-gray-300"
              >
                <template v-if="typeof item === 'object'">
                  <span class="font-medium">{{ item.topic }}</span>
                  <span v-if="item.stance" class="text-gray-500 block mt-0.5 pl-2">{{ truncateText(item.stance, 60) }}</span>
                </template>
                <template v-else>{{ item }}</template>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- 注意力缺口 -->
      <div v-if="result.attention_gaps?.length">
        <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">注意力缺口</h4>
        <div class="space-y-2">
          <div
            v-for="(gap, idx) in result.attention_gaps"
            :key="idx"
            class="p-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg"
          >
            <template v-if="typeof gap === 'object'">
              <div class="flex items-start justify-between gap-2">
                <p class="text-xs font-medium text-gray-800 dark:text-gray-200">{{ gap.topic }}</p>
                <UBadge
                  v-if="gap.risk_or_opportunity"
                  :color="gap.risk_or_opportunity === 'risk' ? 'error' : 'success'"
                  variant="subtle"
                  size="sm"
                  class="shrink-0"
                >
                  {{ gap.risk_or_opportunity === 'risk' ? '风险' : '机会' }}
                </UBadge>
              </div>
              <p v-if="gap.why_matters" class="mt-1 text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">
                {{ expandedGaps.has(idx) || gap.why_matters.length <= 120 ? gap.why_matters : truncateText(gap.why_matters, 120) }}
                <button
                  v-if="gap.why_matters.length > 120"
                  class="text-primary-500 hover:text-primary-600 ml-1 cursor-pointer"
                  @click="toggleGap(idx)"
                >
                  {{ expandedGaps.has(idx) ? '收起' : '展开' }}
                </button>
              </p>
            </template>
            <template v-else>
              <p class="text-xs text-gray-700 dark:text-gray-300">{{ gap }}</p>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { AgendaMapResult, VoicePatternEntry } from '../types'
import { UBadge } from '#components'

const props = defineProps<{
  result: AgendaMapResult | null
}>()

// 叙事按 heat_rank 升序排列（#1 在最上面）
const sortedNarrativeMap = computed(() =>
  [...(props.result?.narrative_map || [])].sort((a, b) => (a.heat_rank || 99) - (b.heat_rank || 99)),
)

// 展开状态
const expandedNarratives = ref(new Set<number>())
const expandedGaps = ref(new Set<number>())
const toggleNarrative = (idx: number) => {
  const next = new Set(expandedNarratives.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  expandedNarratives.value = next
}
const toggleGap = (idx: number) => {
  const next = new Set(expandedGaps.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  expandedGaps.value = next
}

const truncateText = (text: string, max: number) => {
  if (!text || text.length <= max) return text
  return text.slice(0, max) + '…'
}

const tierLabel = (tier: string) => {
  const map: Record<string, string> = { tier1: 'T1', tier2: 'T2', tier3: 'T3', wechat_mp: '公众号' }
  return map[tier] || tier
}

const hasVoicePatterns = computed(() => {
  const p = props.result?.media_voice_patterns
  if (!p) return false
  return (p.authoritative_consensus?.length ?? 0) > 0
    || (p.industry_debate?.length ?? 0) > 0
    || (p.emerging_narratives?.length ?? 0) > 0
})

const voicePatternSections = computed(() => {
  const p = props.result?.media_voice_patterns
  if (!p) return []
  const sections: Array<{ label: string; items: VoicePatternEntry[]; bgClass: string; titleClass: string }> = []
  if (p.authoritative_consensus?.length) {
    sections.push({
      label: '权威共识',
      items: p.authoritative_consensus,
      bgClass: 'bg-blue-50 dark:bg-blue-900/20',
      titleClass: 'text-blue-700 dark:text-blue-300',
    })
  }
  if (p.industry_debate?.length) {
    sections.push({
      label: '行业争论',
      items: p.industry_debate,
      bgClass: 'bg-amber-50 dark:bg-amber-900/20',
      titleClass: 'text-amber-700 dark:text-amber-400',
    })
  }
  if (p.emerging_narratives?.length) {
    sections.push({
      label: '新兴叙事',
      items: p.emerging_narratives,
      bgClass: 'bg-purple-50 dark:bg-purple-900/20',
      titleClass: 'text-purple-700 dark:text-purple-300',
    })
  }
  return sections
})

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

const credibilityColor = (c: string) => {
  if (c === 'high') return 'success' as const
  if (c === 'medium') return 'warning' as const
  return 'neutral' as const
}
</script>
