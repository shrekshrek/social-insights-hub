<template>
  <div class="space-y-4">
    <!-- AI 需求理解 -->
    <div
      v-if="understandingSummary"
      class="p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-700 dark:text-blue-300"
    >
      <span class="font-medium">AI 理解：</span>{{ understandingSummary }}
    </div>

    <!-- 研究问题 -->
    <div v-if="researchQuestions.length">
      <h4 class="text-xs font-medium text-gray-500 mb-2">
        研究问题（{{ researchQuestions.length }} 个）
      </h4>
      <div class="space-y-1.5">
        <div
          v-for="rq in researchQuestions"
          :key="rq.id"
          class="flex items-start gap-2 text-sm p-2 bg-gray-50 dark:bg-gray-800 rounded"
        >
          <UBadge
            :color="rq.priority === 'high' ? 'error' : rq.priority === 'medium' ? 'warning' : 'neutral'"
            variant="soft"
            size="xs"
          >
            {{ rq.priority }}
          </UBadge>
          <div class="flex-1 min-w-0">
            <span>{{ rq.question }}</span>
            <span class="text-xs text-gray-400 ml-1">（{{ rq.dimension }}）</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 数据采集方案 -->
    <div v-if="dataPlan.length">
      <h4 class="text-xs font-medium text-gray-500 mb-2">
        数据采集方案（{{ dataPlan.length }} 个维度）
      </h4>
      <div class="space-y-2">
        <div
          v-for="(dp, i) in dataPlan"
          :key="i"
          class="text-sm p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg"
        >
          <!-- 只读模式 -->
          <div v-if="!editing" class="flex items-start gap-2">
            <UIcon name="i-heroicons-chart-bar" class="text-blue-500 mt-0.5 shrink-0" />
            <div class="flex-1 min-w-0">
              <span class="font-medium text-blue-700 dark:text-blue-300">{{ dp.dimension_name }}</span>
              <span v-if="dp.rationale" class="text-gray-500 ml-1">&mdash; {{ dp.rationale }}</span>
              <div class="flex flex-wrap gap-x-3 text-xs text-gray-400 mt-0.5">
                <span v-if="dp.channel === 'news_media'">
                  渠道: 百度 + 搜狗 + DuckDuckGo<span v-if="dp.enable_wechat_mp"> + 微信公众号</span>
                </span>
                <span v-else-if="dp.platforms?.length">
                  平台: {{ dp.platforms.map(p => platformLabel(p)).join('、') }}
                </span>
                <span v-if="dp.keywords?.length">关键词: {{ dp.keywords.join('、') }}</span>
              </div>
            </div>
          </div>
          <!-- 编辑模式 -->
          <div v-else class="space-y-3">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-chart-bar" class="text-blue-500 shrink-0" />
              <UInput
                :model-value="dp.dimension_name"
                size="sm"
                class="flex-1"
                placeholder="维度名称"
                @update:model-value="(v: string) => updateDataPlanField(i, 'dimension_name', v)"
              />
              <UButton
                variant="ghost"
                size="xs"
                color="error"
                icon="i-heroicons-trash"
                @click="removeDataPlanItem(i)"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">关键词（回车添加）</label>
              <div class="flex flex-wrap items-center gap-1.5 p-1.5 border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 min-h-[34px]">
                <span
                  v-for="(kw, ki) in (dp.keywords || [])"
                  :key="ki"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 text-xs"
                >
                  {{ kw }}
                  <button
                    type="button"
                    class="hover:text-red-500 transition-colors"
                    @click="removeKeyword(i, ki)"
                  >
                    <UIcon name="i-heroicons-x-mark" class="text-[10px]" />
                  </button>
                </span>
                <input
                  :ref="(el: any) => { keywordInputRefs[i] = el }"
                  type="text"
                  class="flex-1 min-w-[80px] text-xs border-none outline-none bg-transparent py-0.5 px-1 text-gray-900 dark:text-white placeholder-gray-400"
                  placeholder="输入后回车添加"
                  @keydown.enter.prevent="addKeywordFromInput(i, $event)"
                  @keydown.,="addKeywordFromInput(i, $event)"
                >
              </div>
            </div>
            <!-- 社媒维度：平台选择 -->
            <div v-if="dp.channel !== 'news_media'">
              <label class="text-xs text-gray-500 mb-1 block">平台</label>
              <div class="flex flex-wrap gap-2">
                <label
                  v-for="p in PLATFORM_OPTIONS"
                  :key="p.code"
                  class="flex items-center gap-1.5 px-2 py-1 rounded border text-xs cursor-pointer transition-colors"
                  :class="dp.platforms?.includes(p.code)
                    ? 'border-primary-400 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-500 hover:border-gray-300'"
                >
                  <input
                    type="checkbox"
                    :checked="dp.platforms?.includes(p.code)"
                    class="sr-only"
                    @change="togglePlatform(i, p.code)"
                  >
                  {{ p.label }}
                </label>
              </div>
            </div>
            <!-- 新闻维度：搜索渠道说明 + 公众号开关 -->
            <div v-else>
              <label class="text-xs text-gray-500 mb-1 block">搜索渠道</label>
              <div class="flex flex-wrap items-center gap-2">
                <span
                  v-for="ch in ['百度', '搜狗', 'DuckDuckGo']"
                  :key="ch"
                  class="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 text-xs text-gray-400"
                >{{ ch }}</span>
                <label
                  class="flex items-center gap-1.5 px-2 py-1 rounded border text-xs cursor-pointer transition-colors"
                  :class="dp.enable_wechat_mp
                    ? 'border-primary-400 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-500 hover:border-gray-300'"
                >
                  <input
                    type="checkbox"
                    :checked="dp.enable_wechat_mp"
                    class="sr-only"
                    @change="updateDataPlanField(i, 'enable_wechat_mp', !dp.enable_wechat_mp)"
                  >
                  微信公众号（可选）
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 切片蓝图 -->
    <div v-if="sliceBlueprint.length">
      <h4 class="text-xs font-medium text-gray-500 mb-2">
        切片蓝图（{{ sliceBlueprint.length }} 个切片）
      </h4>
      <div class="space-y-2">
        <div
          v-for="(sb, i) in sliceBlueprint"
          :key="i"
          class="text-sm p-2.5 bg-purple-50 dark:bg-purple-900/20 rounded-lg"
        >
          <div v-if="!editing" class="flex items-start gap-2">
            <UIcon name="i-heroicons-scissors" class="text-purple-500 mt-0.5 shrink-0" />
            <div class="flex-1 min-w-0">
              <span class="font-medium text-purple-700 dark:text-purple-300">{{ sb.name }}</span>
              <span
                class="ml-1.5 text-xs px-1.5 py-0.5 rounded"
                :class="sb.subject ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'"
              >{{ sb.subject ? `聚焦: ${sb.subject}` : '大盘分析' }}</span>
              <div v-if="sb.source_dimensions?.length" class="text-xs text-gray-400 mt-0.5">
                数据来源: {{ sb.source_dimensions.join('、') }}
              </div>
            </div>
          </div>
          <div v-else class="space-y-2">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-scissors" class="text-purple-500 shrink-0" />
              <UInput
                :model-value="sb.name"
                size="sm"
                class="flex-1"
                placeholder="切片名称"
                @update:model-value="(v: string) => updateBlueprintField(i, 'name', v)"
              />
              <UButton
                variant="ghost"
                size="xs"
                color="error"
                icon="i-heroicons-trash"
                @click="removeBlueprintItem(i)"
              />
            </div>
            <UInput
              :model-value="sb.subject || ''"
              size="sm"
              placeholder="分析主体（品牌/产品名，留空则为大盘分析）"
              @update:model-value="(v: string) => updateBlueprintField(i, 'subject', v)"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 产出类型（用户显式选择；决策表见 research_design_chain） -->
    <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-gray-600 dark:text-gray-400">产出路径</span>
        <UBadge
          v-if="outputTypeLocked"
          variant="soft"
          color="warning"
          size="xs"
        >
          当前数据计划仅支持 {{ OUTPUT_TYPE_LABELS[effectiveOutputType] }}
        </UBadge>
      </div>
      <div class="flex flex-col gap-1.5">
        <label
          v-for="opt in OUTPUT_TYPE_OPTIONS"
          :key="opt.value"
          class="flex items-start gap-2 text-sm cursor-pointer"
          :class="{ 'opacity-40 cursor-not-allowed': !isOptionAvailable(opt.value) }"
        >
          <input
            type="radio"
            class="mt-0.5"
            :value="opt.value"
            :checked="effectiveOutputType === opt.value"
            :disabled="!editing || !isOptionAvailable(opt.value)"
            @change="handleOutputTypeChange(opt.value)"
          >
          <div class="flex-1 min-w-0">
            <div class="font-medium">{{ OUTPUT_TYPE_LABELS[opt.value] }}</div>
            <div class="text-xs text-gray-500">{{ opt.hint }}</div>
          </div>
        </label>
      </div>
      <p v-if="outputTypeRationale" class="text-xs text-gray-400">
        AI 建议理由：{{ outputTypeRationale }}
      </p>
    </div>

    <!-- 采集参数 -->
    <div class="flex items-center gap-4 p-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
      <div class="flex items-center gap-2">
        <span class="text-gray-600 dark:text-gray-400 shrink-0">每任务全量:</span>
        <div class="flex">
          <UButton
            v-for="(opt, oi) in NOTES_OPTIONS"
            :key="opt"
            size="xs"
            :variant="notesPerTask === opt ? 'solid' : 'outline'"
            :class="oi === 0 ? 'rounded-r-none' : 'rounded-l-none'"
            @click="$emit('update:notesPerTask', opt)"
          >
            {{ opt }} 条
          </UButton>
        </div>
      </div>
      <span class="text-gray-600 dark:text-gray-400">探测: 20 条（固定）</span>
      <span class="text-gray-400">|</span>
      <span class="text-gray-600 dark:text-gray-400">
        预估: {{ estimatedTaskCount }} 个任务
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DataPlanItem, OutputType, SliceBlueprintItem, ResearchQuestion } from '../types'
import {
  OUTPUT_TYPE_LABELS,
  PLATFORM_OPTIONS,
  platformLabel,
} from '../composables/useStrategyConstants'

const NOTES_OPTIONS = [50, 100] as const

const OUTPUT_TYPE_OPTIONS: ReadonlyArray<{ value: OutputType; hint: string }> = [
  {
    value: 'brand_strategy',
    hint: '消费者洞察主导：社会张力 → 品牌社会角色 → 大创意（要求研究计划含 social_media 维度）',
  },
  {
    value: 'market_report',
    hint: '媒体视角主导：媒体议程图 → 竞争格局 → 战略简报（要求研究计划含 news_media 维度）',
  },
] as const

const props = defineProps<{
  understandingSummary?: string
  researchQuestions: ResearchQuestion[]
  dataPlan: DataPlanItem[]
  sliceBlueprint: SliceBlueprintItem[]
  outputType?: OutputType
  outputTypeRationale?: string
  editing: boolean
  notesPerTask: number
}>()

const emit = defineEmits<{
  'update:dataPlan': [value: DataPlanItem[]]
  'update:sliceBlueprint': [value: SliceBlueprintItem[]]
  'update:notesPerTask': [value: number]
  'update:outputType': [value: OutputType]
}>()

const channelAvailability = computed(() => {
  const hasSocial = props.dataPlan.some(dp => (dp.channel || 'social_media') === 'social_media')
  const hasNews = props.dataPlan.some(dp => dp.channel === 'news_media')
  return { hasSocial, hasNews }
})

const isOptionAvailable = (opt: OutputType): boolean => {
  const { hasSocial, hasNews } = channelAvailability.value
  if (opt === 'brand_strategy') return hasSocial
  if (opt === 'market_report') return hasNews
  return false
}

// 当仅一种路径可选时锁定；优先 brand_strategy（若两者都可选则尊重 props.outputType）
const effectiveOutputType = computed<OutputType>(() => {
  const brandOk = isOptionAvailable('brand_strategy')
  const marketOk = isOptionAvailable('market_report')
  if (brandOk && !marketOk) return 'brand_strategy'
  if (!brandOk && marketOk) return 'market_report'
  return props.outputType ?? 'brand_strategy'
})

const outputTypeLocked = computed(() => {
  const brandOk = isOptionAvailable('brand_strategy')
  const marketOk = isOptionAvailable('market_report')
  return brandOk !== marketOk
})

// 当锁定或 data_plan 变化时同步回父组件
watch(effectiveOutputType, (next, prev) => {
  if (next !== prev && next !== props.outputType) {
    emit('update:outputType', next)
  }
}, { immediate: true })

const handleOutputTypeChange = (value: OutputType) => {
  if (!isOptionAvailable(value)) return
  emit('update:outputType', value)
}

const keywordInputRefs = ref<Record<number, HTMLInputElement | null>>({})

const estimatedTaskCount = computed(() => {
  return props.dataPlan.reduce((total, dp) => {
    const keywords = dp.keywords?.length || 1
    if (dp.channel === 'news_media') {
      // 新闻维度：每个关键词一个任务（无平台维度）
      return total + keywords
    }
    const platforms = dp.platforms?.length || 1
    return total + keywords * platforms
  }, 0)
})

// data_plan 编辑
const updateDataPlanField = (index: number, field: string, value: string | boolean) => {
  emit('update:dataPlan', props.dataPlan.map((dp, i) =>
    i === index ? { ...dp, [field]: value } : dp,
  ))
}

const removeDataPlanItem = (index: number) => {
  emit('update:dataPlan', props.dataPlan.filter((_, i) => i !== index))
}

const removeKeyword = (dpIndex: number, kwIndex: number) => {
  emit('update:dataPlan', props.dataPlan.map((dp, i) => {
    if (i !== dpIndex) return dp
    return { ...dp, keywords: (dp.keywords || []).filter((_, ki) => ki !== kwIndex) }
  }))
}

const addKeywordFromInput = (dpIndex: number, event: Event) => {
  const input = keywordInputRefs.value[dpIndex]
  if (!input) return
  event.preventDefault()
  const value = input.value.trim().replace(/[,，、]$/, '').trim()
  if (!value) return
  emit('update:dataPlan', props.dataPlan.map((dp, i) => {
    if (i !== dpIndex) return dp
    const existing = dp.keywords || []
    if (existing.includes(value)) return dp
    return { ...dp, keywords: [...existing, value] }
  }))
  input.value = ''
}

const togglePlatform = (index: number, platformCode: string) => {
  emit('update:dataPlan', props.dataPlan.map((dp, i) => {
    if (i !== index) return dp
    const current = dp.platforms || []
    const platforms = current.includes(platformCode)
      ? current.filter(p => p !== platformCode)
      : [...current, platformCode]
    return { ...dp, platforms }
  }))
}

// slice_blueprint 编辑
const updateBlueprintField = (index: number, field: string, value: string) => {
  emit('update:sliceBlueprint', props.sliceBlueprint.map((sb, i) =>
    i === index ? { ...sb, [field]: value } : sb,
  ))
}

const removeBlueprintItem = (index: number) => {
  emit('update:sliceBlueprint', props.sliceBlueprint.filter((_, i) => i !== index))
}
</script>
