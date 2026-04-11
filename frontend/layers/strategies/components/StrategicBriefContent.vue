<template>
  <div v-if="result" class="space-y-6">
    <!-- 决策层摘要 -->
    <div v-if="result.executive_summary">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-2">决策层摘要</h4>
      <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed p-3 bg-primary-50 dark:bg-primary-900/20 rounded-lg">
        {{ result.executive_summary }}
      </p>
    </div>

    <!-- 战略优先级 -->
    <div v-if="result.strategic_priorities?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">战略优先级</h4>
      <div class="space-y-3">
        <div
          v-for="(priority, idx) in result.strategic_priorities"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-start gap-2">
            <UBadge color="primary" variant="solid" size="xs">{{ idx + 1 }}</UBadge>
            <div class="flex-1 min-w-0">
              <p class="font-medium text-gray-900 dark:text-white">{{ priority.priority }}</p>
              <p v-if="priority.rationale" class="mt-1 text-sm text-gray-600 dark:text-gray-300">
                {{ priority.rationale }}
              </p>
              <div v-if="priority.answers_questions?.length" class="mt-1.5 flex flex-wrap gap-1">
                <UBadge
                  v-for="qid in priority.answers_questions"
                  :key="qid"
                  color="info"
                  variant="subtle"
                  size="xs"
                >
                  {{ qid }}
                </UBadge>
              </div>
              <div v-if="priority.actions?.length" class="mt-2">
                <p class="text-xs font-medium text-gray-500 mb-1">具体动作：</p>
                <ul class="space-y-0.5 text-sm text-gray-700 dark:text-gray-300">
                  <li v-for="(action, ai) in priority.actions" :key="ai">
                    · {{ action }}
                  </li>
                </ul>
              </div>
              <p v-if="priority.success_metric" class="mt-2 text-xs text-gray-500">
                <span class="font-medium">成功指标：</span>{{ priority.success_metric }}
              </p>
              <p v-if="priority.evidence_refs?.length" class="mt-1 text-xs text-gray-400">
                证据：{{ priority.evidence_refs.join(' · ') }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 市场机会 -->
    <div v-if="result.market_opportunities?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">市场机会</h4>
      <div class="space-y-3">
        <div
          v-for="(opp, idx) in result.market_opportunities"
          :key="idx"
          class="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg"
        >
          <p class="font-medium text-gray-900 dark:text-white">{{ idx + 1 }}. {{ opp.opportunity }}</p>
          <p v-if="opp.why_now" class="mt-1 text-sm text-gray-700 dark:text-gray-300">
            <span class="font-medium">为何此刻：</span>{{ opp.why_now }}
          </p>
          <p v-if="opp.entry_path" class="mt-1 text-sm text-gray-700 dark:text-gray-300">
            <span class="font-medium">切入路径：</span>{{ opp.entry_path }}
          </p>
          <p v-if="opp.evidence_refs?.length" class="mt-1 text-xs text-gray-400">
            证据：{{ opp.evidence_refs.join(' · ') }}
          </p>
        </div>
      </div>
    </div>

    <!-- 风险与威胁 -->
    <div v-if="result.risks_and_threats?.length">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">风险与威胁</h4>
      <div class="space-y-3">
        <div
          v-for="(risk, idx) in result.risks_and_threats"
          :key="idx"
          class="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg"
        >
          <div class="flex items-start justify-between gap-2">
            <p class="font-medium text-gray-900 dark:text-white">{{ idx + 1 }}. {{ risk.risk }}</p>
            <UBadge :color="likelihoodColor(risk.likelihood)" variant="subtle" size="xs">
              {{ likelihoodLabel(risk.likelihood) }}
            </UBadge>
          </div>
          <p v-if="risk.mitigation" class="mt-1 text-sm text-gray-700 dark:text-gray-300">
            <span class="font-medium">缓解思路：</span>{{ risk.mitigation }}
          </p>
          <p v-if="risk.source" class="mt-1 text-xs text-gray-400">来源：{{ risk.source }}</p>
        </div>
      </div>
    </div>

    <!-- 推荐定位 -->
    <div v-if="result.recommended_positioning?.statement">
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">推荐定位</h4>
      <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
        <p class="font-medium text-gray-900 dark:text-white">
          {{ result.recommended_positioning.statement }}
        </p>
        <div
          v-if="result.recommended_positioning.target_position"
          class="mt-2 text-xs text-gray-500"
        >
          <span>X: {{ result.recommended_positioning.target_position.x_axis }}</span>
          <span class="mx-2">·</span>
          <span>Y: {{ result.recommended_positioning.target_position.y_axis }}</span>
          <span class="mx-2">·</span>
          <span>方向: {{ result.recommended_positioning.target_position.direction }}</span>
        </div>
        <p
          v-if="result.recommended_positioning.differentiation_logic"
          class="mt-2 text-sm text-gray-700 dark:text-gray-300"
        >
          <span class="font-medium">差异化逻辑：</span>{{ result.recommended_positioning.differentiation_logic }}
        </p>
        <div v-if="result.recommended_positioning.proof_points?.length" class="mt-2">
          <p class="text-xs font-medium text-gray-500 mb-1">支撑论点：</p>
          <ul class="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <li
              v-for="(pp, idx) in result.recommended_positioning.proof_points"
              :key="idx"
            >
              · {{ pp.claim }}
              <span
                v-if="pp.agenda_map_narrative_ref"
                class="text-xs text-gray-400 ml-1"
              >（Agenda Map 叙事：{{ pp.agenda_map_narrative_ref }}）</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-gray-400 text-center py-4">暂无数据</div>
</template>

<script setup lang="ts">
import type { StrategicBriefResult } from '../types'
import { UBadge } from '#components'

defineProps<{
  result: StrategicBriefResult | null
}>()

const likelihoodColor = (l: string) => {
  if (l === 'high') return 'error' as const
  if (l === 'medium') return 'warning' as const
  return 'neutral' as const
}

const likelihoodLabel = (l: string) => {
  if (l === 'high') return '高'
  if (l === 'medium') return '中'
  return '低'
}
</script>
