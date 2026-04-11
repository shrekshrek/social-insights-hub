<template>
  <div v-if="result" class="space-y-6">
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
      <div class="space-y-3">
        <div
          v-for="(narrative, idx) in result.narrative_map"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-start justify-between gap-2 flex-wrap">
            <p class="font-medium text-gray-900 dark:text-white">
              {{ narrative.heat_rank || idx + 1 }}. {{ narrative.theme }}
            </p>
            <div class="flex items-center gap-1.5">
              <UBadge
                :color="sentimentColor(narrative.sentiment)"
                variant="subtle"
                size="xs"
              >
                {{ sentimentLabel(narrative.sentiment) }}
              </UBadge>
              <UBadge
                :color="credibilityColor(narrative.credibility)"
                variant="subtle"
                size="xs"
              >
                {{ credibilityLabel(narrative.credibility) }}
              </UBadge>
            </div>
          </div>
          <p v-if="narrative.framing" class="mt-1 text-sm text-gray-600 dark:text-gray-300">
            <span class="font-medium">框架：</span>{{ narrative.framing }}
          </p>
          <div
            v-if="narrative.supporting_sources"
            class="mt-1.5 text-xs text-gray-500 flex flex-wrap gap-2"
          >
            <span v-if="narrative.supporting_sources.tier1">Tier1 {{ narrative.supporting_sources.tier1 }}</span>
            <span v-if="narrative.supporting_sources.tier2">Tier2 {{ narrative.supporting_sources.tier2 }}</span>
            <span v-if="narrative.supporting_sources.tier3">Tier3 {{ narrative.supporting_sources.tier3 }}</span>
            <span v-if="narrative.supporting_sources.wechat_mp">公众号 {{ narrative.supporting_sources.wechat_mp }}</span>
          </div>
          <div v-if="narrative.representative_voices?.length" class="mt-2 space-y-1">
            <div
              v-for="(voice, vi) in narrative.representative_voices"
              :key="vi"
              class="text-xs text-gray-600 dark:text-gray-400 border-l-2 border-gray-300 dark:border-gray-600 pl-2"
            >
              <span class="font-medium">{{ voice.source_name }}</span>
              <span class="text-gray-400 mx-1">·</span>
              <span class="text-gray-400">{{ voice.tier }}</span>
              <p class="italic mt-0.5">"{{ voice.quote }}"</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 议程博弈 -->
    <div v-if="result.agenda_battles?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">议程博弈</h4>
      <div class="space-y-3">
        <div
          v-for="(battle, idx) in result.agenda_battles"
          :key="idx"
          class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg"
        >
          <p class="font-medium text-gray-900 dark:text-white">{{ idx + 1 }}. {{ battle.topic }}</p>
          <div v-if="battle.sides?.length" class="mt-2 space-y-1.5">
            <div
              v-for="(side, si) in battle.sides"
              :key="si"
              class="text-sm text-gray-700 dark:text-gray-300"
            >
              <span class="font-medium">{{ side.stance }}：</span>{{ side.supporters_brief }}
            </div>
          </div>
          <p v-if="battle.dominant_side" class="mt-1 text-xs text-amber-700 dark:text-amber-400">
            主导方：{{ battle.dominant_side }}
          </p>
          <p v-if="battle.note" class="mt-1 text-xs text-gray-500">{{ battle.note }}</p>
        </div>
      </div>
    </div>

    <!-- 媒体声量模式 -->
    <div v-if="hasVoicePatterns">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">媒体声量模式</h4>
      <div class="grid md:grid-cols-3 gap-3">
        <div
          v-if="result.media_voice_patterns?.authoritative_consensus?.length"
          class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg"
        >
          <p class="text-xs font-medium text-blue-700 dark:text-blue-300 mb-1.5">权威共识</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(item, idx) in result.media_voice_patterns.authoritative_consensus"
              :key="idx"
            >
              · {{ item }}
            </li>
          </ul>
        </div>
        <div
          v-if="result.media_voice_patterns?.industry_debate?.length"
          class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg"
        >
          <p class="text-xs font-medium text-amber-700 dark:text-amber-400 mb-1.5">行业争论</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(item, idx) in result.media_voice_patterns.industry_debate"
              :key="idx"
            >
              · {{ item }}
            </li>
          </ul>
        </div>
        <div
          v-if="result.media_voice_patterns?.emerging_narratives?.length"
          class="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg"
        >
          <p class="text-xs font-medium text-purple-700 dark:text-purple-300 mb-1.5">新兴叙事</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(item, idx) in result.media_voice_patterns.emerging_narratives"
              :key="idx"
            >
              · {{ item }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 注意力空白 -->
    <div v-if="result.attention_gaps?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">注意力空白</h4>
      <ul class="space-y-1.5">
        <li
          v-for="(gap, idx) in result.attention_gaps"
          :key="idx"
          class="text-sm text-gray-700 dark:text-gray-300 p-2 bg-gray-50 dark:bg-gray-800 rounded"
        >
          · {{ gap }}
        </li>
      </ul>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { AgendaMapResult } from '../types'
import { UBadge } from '#components'

const props = defineProps<{
  result: AgendaMapResult | null
}>()

const hasVoicePatterns = computed(() => {
  const p = props.result?.media_voice_patterns
  if (!p) return false
  return (p.authoritative_consensus?.length ?? 0) > 0
    || (p.industry_debate?.length ?? 0) > 0
    || (p.emerging_narratives?.length ?? 0) > 0
})

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

const credibilityColor = (c: string) => {
  if (c === 'high') return 'success' as const
  if (c === 'medium') return 'warning' as const
  return 'neutral' as const
}

const credibilityLabel = (c: string) => {
  if (c === 'high') return '可信度高'
  if (c === 'medium') return '可信度中'
  return '可信度低'
}
</script>
