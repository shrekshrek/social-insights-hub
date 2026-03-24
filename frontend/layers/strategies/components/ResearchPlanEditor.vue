<template>
  <div class="space-y-4">
    <!-- 课题适配度评估 -->
    <div
      v-if="feasibility && feasibility.recommendation !== 'proceed'"
      class="p-3 rounded-lg border"
      :class="feasibility.recommendation === 'not_recommended'
        ? 'border-red-200 bg-red-50 dark:bg-red-900/20'
        : 'border-amber-200 bg-amber-50 dark:bg-amber-900/20'"
    >
      <div class="flex items-center gap-2 mb-2">
        <UIcon
          :name="feasibility.recommendation === 'not_recommended' ? 'i-heroicons-x-circle' : 'i-heroicons-exclamation-triangle'"
          :class="feasibility.recommendation === 'not_recommended' ? 'text-red-500' : 'text-amber-500'"
        />
        <span
          class="font-medium text-sm"
          :class="feasibility.recommendation === 'not_recommended' ? 'text-red-700 dark:text-red-300' : 'text-amber-700 dark:text-amber-300'"
        >
          {{ feasibility.recommendation === 'not_recommended' ? '该课题不适合社媒数据调研' : '研究范围已收窄' }}
          <span class="text-xs font-normal opacity-70 ml-1">适配度 {{ Math.round(feasibility.fit_score * 100) }}%</span>
        </span>
      </div>
      <p class="text-sm text-gray-600 dark:text-gray-400 mb-2">{{ feasibility.rationale }}</p>
      <div class="grid grid-cols-2 gap-3 text-xs">
        <div v-if="feasibility.social_can_tell?.length">
          <span class="font-medium text-green-600 dark:text-green-400">社媒数据能回答：</span>
          <ul class="mt-1 space-y-0.5 text-gray-600 dark:text-gray-400">
            <li v-for="(item, i) in feasibility.social_can_tell" :key="i">· {{ item }}</li>
          </ul>
        </div>
        <div v-if="feasibility.social_cannot_tell?.length">
          <span class="font-medium text-red-600 dark:text-red-400">社媒数据无法回答：</span>
          <ul class="mt-1 space-y-0.5 text-gray-600 dark:text-gray-400">
            <li v-for="(item, i) in feasibility.social_cannot_tell" :key="i">· {{ item }}</li>
          </ul>
        </div>
      </div>
      <div v-if="feasibility.complementary_methods?.length" class="mt-2 text-xs">
        <span class="font-medium text-gray-500">建议补充方法：</span>
        <span class="text-gray-600 dark:text-gray-400">{{ feasibility.complementary_methods.join('、') }}</span>
      </div>
    </div>

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
                <span v-if="dp.platforms?.length">
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
            <div>
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

    <!-- 产出类型 -->
    <div v-if="outputType" class="text-sm text-gray-500">
      <span class="font-medium">产出类型：</span>{{ outputType }}
      <span v-if="outputTypeRationale" class="text-gray-400 ml-1">— {{ outputTypeRationale }}</span>
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
      <div class="flex items-center gap-2">
        <span class="text-gray-600 dark:text-gray-400 shrink-0">探测:</span>
        <div class="flex">
          <UButton
            v-for="(opt, oi) in PROBE_OPTIONS"
            :key="opt"
            size="xs"
            :variant="probeNotes === opt ? 'solid' : 'outline'"
            :class="oi === 0 ? 'rounded-r-none' : 'rounded-l-none'"
            @click="$emit('update:probeNotes', opt)"
          >
            {{ opt }} 条
          </UButton>
        </div>
      </div>
      <span class="text-gray-400">|</span>
      <span class="text-gray-600 dark:text-gray-400">
        预估: {{ estimatedTaskCount }} 个任务
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DataPlanItem, SliceBlueprintItem, ResearchQuestion, FeasibilityAssessment } from '../types'
import { PLATFORM_OPTIONS, platformLabel } from '../composables/useStrategyConstants'

const NOTES_OPTIONS = [50, 100] as const
const PROBE_OPTIONS = [15, 30] as const

const props = defineProps<{
  feasibility?: FeasibilityAssessment
  understandingSummary?: string
  researchQuestions: ResearchQuestion[]
  dataPlan: DataPlanItem[]
  sliceBlueprint: SliceBlueprintItem[]
  outputType?: string
  outputTypeRationale?: string
  editing: boolean
  notesPerTask: number
  probeNotes: number
}>()

const emit = defineEmits<{
  'update:dataPlan': [value: DataPlanItem[]]
  'update:sliceBlueprint': [value: SliceBlueprintItem[]]
  'update:notesPerTask': [value: number]
  'update:probeNotes': [value: number]
}>()

const keywordInputRefs = ref<Record<number, HTMLInputElement | null>>({})

const estimatedTaskCount = computed(() => {
  return props.dataPlan.reduce((total, dp) => {
    const platforms = dp.platforms?.length || 1
    return total + platforms
  }, 0)
})

// data_plan 编辑
const updateDataPlanField = (index: number, field: string, value: string) => {
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
