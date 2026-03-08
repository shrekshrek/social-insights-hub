<template>
  <div>
    <div class="space-y-2 mb-4">
      <div
        v-for="(s, i) in modelValue"
        :key="i"
        class="text-sm p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg"
      >
        <!-- Read-only mode -->
        <div v-if="!editing" class="flex items-start gap-2">
          <UIcon name="i-heroicons-chart-bar" class="text-blue-500 mt-0.5 shrink-0" />
          <div class="flex-1 min-w-0">
            <span class="font-medium text-blue-700 dark:text-blue-300">{{ s.name }}</span>
            <span v-if="s.rationale" class="text-gray-500 ml-1">&mdash; {{ s.rationale }}</span>
            <div class="flex flex-wrap gap-x-3 text-xs text-gray-400 mt-0.5">
              <span v-if="s.platforms?.length">
                平台: {{ s.platforms.map(p => platformLabel(p)).join('、') }}
              </span>
              <span v-if="s.keywords?.length">关键词: {{ s.keywords.join('、') }}</span>
            </div>
          </div>
        </div>
        <!-- Edit mode -->
        <div v-else class="space-y-3">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-chart-bar" class="text-blue-500 shrink-0" />
            <UInput
              :model-value="s.name"
              size="sm"
              class="flex-1"
              placeholder="监测名称"
              @update:model-value="(v: string) => updateField(i, 'name', v)"
            />
            <UButton
              variant="ghost"
              size="xs"
              color="error"
              icon="i-heroicons-trash"
              @click="removeSuggestion(i)"
            />
          </div>
          <div>
            <label class="text-xs text-gray-500 mb-1 block">关键词（每个关键词独立采集）</label>
            <div class="flex flex-wrap items-center gap-1.5 p-1.5 border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 min-h-[34px]">
              <span
                v-for="(kw, ki) in (s.keywords || [])"
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
                :key="p.llmCode"
                class="flex items-center gap-1.5 px-2 py-1 rounded border text-xs cursor-pointer transition-colors"
                :class="s.platforms?.includes(p.llmCode)
                  ? 'border-primary-400 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                  : 'border-gray-200 dark:border-gray-700 text-gray-500 hover:border-gray-300'"
              >
                <input
                  type="checkbox"
                  :checked="s.platforms?.includes(p.llmCode)"
                  class="sr-only"
                  @change="togglePlatform(i, p.llmCode)"
                >
                {{ p.label }}
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Notes per task + estimate -->
    <div class="flex items-center gap-4 mb-4 p-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
      <div class="flex items-center gap-2">
        <span class="text-gray-600 dark:text-gray-400 shrink-0">每任务采集:</span>
        <div class="flex">
          <UButton
            size="xs"
            :variant="notesPerTask === 50 ? 'solid' : 'outline'"
            class="rounded-r-none"
            @click="$emit('update:notesPerTask', 50)"
          >
            50 条
          </UButton>
          <UButton
            size="xs"
            :variant="notesPerTask === 100 ? 'solid' : 'outline'"
            class="rounded-l-none"
            @click="$emit('update:notesPerTask', 100)"
          >
            100 条
          </UButton>
        </div>
      </div>
      <span class="text-gray-400">|</span>
      <span class="text-gray-600 dark:text-gray-400">
        预估: {{ estimatedTaskCount }} 个任务 × {{ notesPerTask }} 条 =
        <span class="font-medium text-gray-900 dark:text-white">{{ estimatedTaskCount * notesPerTask }} 条</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { MonitorSuggestion } from '../types'

const PLATFORM_OPTIONS = [
  { llmCode: 'douyin', label: '抖音' },
  { llmCode: 'xiaohongshu', label: '小红书' },
  { llmCode: 'weibo', label: '微博' },
  { llmCode: 'bilibili', label: 'B站' },
  { llmCode: 'kuaishou', label: '快手' },
  { llmCode: 'zhihu', label: '知乎' },
  { llmCode: 'tieba', label: '贴吧' },
] as const

const PLATFORM_LABEL_MAP: Record<string, string> = Object.fromEntries(
  PLATFORM_OPTIONS.map(p => [p.llmCode, p.label]),
)
const platformLabel = (code: string) => PLATFORM_LABEL_MAP[code] || code

const props = defineProps<{
  modelValue: MonitorSuggestion[]
  notesPerTask: number
  editing: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: MonitorSuggestion[]]
  'update:notesPerTask': [value: number]
}>()

const keywordInputRefs = ref<Record<number, HTMLInputElement | null>>({})

const estimatedTaskCount = computed(() => {
  return props.modelValue.reduce((total, s) => {
    const keywords = s.keywords?.length || 1
    const platforms = s.platforms?.length || 1
    return total + keywords * platforms
  }, 0)
})

const updateField = (index: number, field: string, value: string) => {
  emit('update:modelValue', props.modelValue.map((s, i) =>
    i === index ? { ...s, [field]: value } : s,
  ))
}

const removeKeyword = (suggestionIndex: number, keywordIndex: number) => {
  emit('update:modelValue', props.modelValue.map((s, i) => {
    if (i !== suggestionIndex) return s
    return { ...s, keywords: (s.keywords || []).filter((_, ki) => ki !== keywordIndex) }
  }))
}

const addKeywordFromInput = (suggestionIndex: number, event: Event) => {
  const input = keywordInputRefs.value[suggestionIndex]
  if (!input) return
  event.preventDefault()
  const value = input.value.trim().replace(/[,，、]$/, '').trim()
  if (!value) return
  emit('update:modelValue', props.modelValue.map((s, i) => {
    if (i !== suggestionIndex) return s
    const existing = s.keywords || []
    if (existing.includes(value)) return s
    return { ...s, keywords: [...existing, value] }
  }))
  input.value = ''
}

const togglePlatform = (index: number, platformCode: string) => {
  emit('update:modelValue', props.modelValue.map((s, i) => {
    if (i !== index) return s
    const current = s.platforms || []
    const platforms = current.includes(platformCode)
      ? current.filter(p => p !== platformCode)
      : [...current, platformCode]
    return { ...s, platforms }
  }))
}

const removeSuggestion = (index: number) => {
  emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))
}
</script>
