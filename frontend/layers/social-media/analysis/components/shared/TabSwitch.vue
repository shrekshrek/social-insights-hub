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
  <div class="flex items-center gap-1 text-[11px]">
    <button
      v-for="option in options"
      :key="option.value"
      class="px-2 py-0.5 rounded border transition-colors"
      :class="isActive(option.value)
        ? 'bg-primary-500 text-white border-primary-500'
        : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
      @click="handleClick(option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

