<script setup lang="ts">
/**
 * 可点击的次数组件
 *
 * 用于显示提及次数，如果有关联原文则可点击查看
 */
const props = withDefaults(defineProps<{
  count: number
  postIds?: number[]
  label?: string  // 用于弹窗标题，如 "福建舰"
  size?: 'default' | 'xs'  // 样式大小
}>(), {
  postIds: () => [],
  label: '',
  size: 'default',
})

const emit = defineEmits<{
  click: [title: string, postIds: number[]]
}>()

const hasPostIds = computed(() => props.postIds && props.postIds.length > 0)

const handleClick = () => {
  if (hasPostIds.value) {
    const title = props.label ? `${props.label} 相关原文` : '相关原文'
    emit('click', title, props.postIds)
  }
}

// 根据 size 确定样式
const buttonClass = computed(() =>
  props.size === 'xs'
    ? 'text-xs text-gray-400 dark:text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 cursor-pointer'
    : 'text-gray-500 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 cursor-pointer'
)

const textClass = computed(() =>
  props.size === 'xs'
    ? 'underline'
    : 'text-gray-700 dark:text-gray-300 underline'
)

const staticClass = computed(() =>
  props.size === 'xs'
    ? 'text-xs text-gray-400 dark:text-gray-500'
    : 'text-gray-500 dark:text-gray-400'
)

const staticTextClass = computed(() =>
  props.size === 'xs'
    ? ''
    : 'text-gray-700 dark:text-gray-300'
)
</script>

<template>
  <button
    v-if="hasPostIds"
    :class="buttonClass"
    @click="handleClick"
  >
    <span :class="textClass">{{ count }}次</span>
  </button>
  <span v-else :class="staticClass">
    <span :class="staticTextClass">{{ count }}次</span>
  </span>
</template>
