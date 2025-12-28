<script setup lang="ts">
/**
 * 通用 Tab 切换组件
 * 用于图表组件中的模式/视图切换
 */

interface TabOption {
  value: string
  label: string
}

const props = defineProps<{
  modelValue: string
  options: TabOption[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const isActive = (value: string) => props.modelValue === value

const handleClick = (value: string) => {
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400">
    <button
      v-for="option in options"
      :key="option.value"
      class="px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800 transition-colors"
      :class="isActive(option.value)
        ? 'bg-gray-50 dark:bg-gray-800/60 text-gray-800 dark:text-gray-200'
        : 'bg-transparent hover:bg-gray-50/50 dark:hover:bg-gray-800/30'"
      @click="handleClick(option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

