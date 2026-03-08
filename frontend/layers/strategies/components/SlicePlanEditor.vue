<template>
  <div class="space-y-2">
    <div
      v-for="(item, i) in modelValue"
      :key="i"
      class="text-sm p-2.5 bg-purple-50 dark:bg-purple-900/20 rounded-lg"
    >
      <!-- 只读模式 -->
      <div v-if="!editing" class="flex items-start gap-2">
        <UIcon name="i-heroicons-scissors" class="text-purple-500 mt-0.5 shrink-0" />
        <div class="flex-1 min-w-0">
          <span class="font-medium text-purple-700 dark:text-purple-300">{{ item.name }}</span>
          <span
            class="ml-1.5 text-xs px-1.5 py-0.5 rounded"
            :class="item.subject ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'"
          >{{ item.subject ? `聚焦: ${item.subject}` : '大盘分析' }}</span>
          <span v-if="item.purpose" class="text-gray-500 ml-1">&mdash; {{ item.purpose }}</span>
          <div v-if="item.expected_sources?.length" class="text-xs text-gray-400 mt-0.5">
            数据来源: {{ item.expected_sources.join('、') }}
          </div>
        </div>
      </div>
      <!-- 编辑模式 -->
      <div v-else class="space-y-2">
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-scissors" class="text-purple-500 shrink-0" />
          <UInput
            :model-value="item.name"
            size="sm"
            class="flex-1"
            placeholder="切片名称"
            @update:model-value="(v: string) => updateField(i, 'name', v)"
          />
          <UButton
            variant="ghost"
            size="xs"
            color="error"
            icon="i-heroicons-trash"
            @click="removeItem(i)"
          />
        </div>
        <UInput
          :model-value="item.subject || ''"
          size="sm"
          placeholder="分析主体（品牌/产品名，留空则为大盘分析）"
          @update:model-value="(v: string) => updateField(i, 'subject', v)"
        />
        <UInput
          :model-value="item.purpose"
          size="sm"
          placeholder="分析目的"
          @update:model-value="(v: string) => updateField(i, 'purpose', v)"
        />
        <div>
          <label class="text-xs text-gray-500 mb-1 block">数据来源（回车添加）</label>
          <div class="flex flex-wrap items-center gap-1.5 p-1.5 border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 min-h-[34px]">
            <span
              v-for="(src, si) in (item.expected_sources || [])"
              :key="si"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 text-xs"
            >
              {{ src }}
              <button
                type="button"
                class="hover:text-red-500 transition-colors"
                @click="removeSource(i, si)"
              >
                <UIcon name="i-heroicons-x-mark" class="text-[10px]" />
              </button>
            </span>
            <input
              :ref="(el: any) => { sourceInputRefs[i] = el }"
              type="text"
              class="flex-1 min-w-[80px] text-xs border-none outline-none bg-transparent py-0.5 px-1 text-gray-900 dark:text-white placeholder-gray-400"
              placeholder="输入后回车添加"
              @keydown.enter.prevent="addSourceFromInput(i)"
            >
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑模式下的添加按钮 -->
    <UButton
      v-if="editing"
      variant="ghost"
      size="xs"
      icon="i-heroicons-plus"
      @click="addItem"
    >
      添加切片建议
    </UButton>
  </div>
</template>

<script setup lang="ts">
import type { SlicePlanItem } from '../types'

const props = defineProps<{
  modelValue: SlicePlanItem[]
  editing: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SlicePlanItem[]]
}>()

const sourceInputRefs = ref<Record<number, HTMLInputElement | null>>({})

const updateField = (index: number, field: string, value: string) => {
  emit('update:modelValue', props.modelValue.map((item, i) =>
    i === index ? { ...item, [field]: value } : item,
  ))
}

const removeItem = (index: number) => {
  emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))
}

const addItem = () => {
  emit('update:modelValue', [...props.modelValue, { name: '', subject: '', purpose: '' }])
}

const removeSource = (itemIndex: number, sourceIndex: number) => {
  emit('update:modelValue', props.modelValue.map((item, i) => {
    if (i !== itemIndex) return item
    return { ...item, expected_sources: (item.expected_sources || []).filter((_, si) => si !== sourceIndex) }
  }))
}

const addSourceFromInput = (itemIndex: number) => {
  const input = sourceInputRefs.value[itemIndex]
  if (!input) return
  const value = input.value.trim()
  if (!value) return
  emit('update:modelValue', props.modelValue.map((item, i) => {
    if (i !== itemIndex) return item
    const existing = item.expected_sources || []
    if (existing.includes(value)) return item
    return { ...item, expected_sources: [...existing, value] }
  }))
  input.value = ''
}
</script>
