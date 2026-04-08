<script setup lang="ts">
/**
 * 可展开/收起的文本组件
 *
 * 统一处理文本截断逻辑，避免CSS truncate和JS判断不一致的问题
 * 使用纯字符截断而非CSS truncate，确保"+"按钮显示逻辑一致
 *
 * 支持两种模式：
 * 1. 单文本模式：只传 text
 * 2. 标题+内容模式：同时传 title 和 content
 */

const props = withDefaults(defineProps<{
  /** 标题（可选） */
  title?: string
  /** 内容/正文 */
  content?: string
  /** 单文本模式下的文本（向后兼容） */
  text?: string
  /** 最大显示字符数 */
  maxLength?: number
}>(), {
  title: '',
  content: '',
  text: '',
  maxLength: 60,
})

const isExpanded = ref(false)

// 兼容单文本模式
const titleText = computed(() => props.title || '')
const contentText = computed(() => props.content || props.text || '')

const hasLongTitle = computed(() => titleText.value.length > props.maxLength)
const hasLongContent = computed(() => contentText.value.length > props.maxLength)
const needsExpand = computed(() => hasLongTitle.value || hasLongContent.value)

const displayTitle = computed(() => {
  if (!titleText.value) return ''
  if (isExpanded.value || !hasLongTitle.value) return titleText.value
  return titleText.value.substring(0, props.maxLength) + '...'
})

const displayContent = computed(() => {
  if (!contentText.value) return ''
  if (isExpanded.value || !hasLongContent.value) return contentText.value
  return contentText.value.substring(0, props.maxLength) + '...'
})

const toggle = () => {
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <div class="max-w-md">
    <!-- 标题 -->
    <p
      v-if="titleText"
      :class="[
        'font-medium text-sm',
        isExpanded ? 'whitespace-pre-wrap' : ''
      ]"
    >
      {{ displayTitle }}
    </p>
    <!-- 内容 -->
    <p
      v-if="contentText"
      :class="[
        'text-xs text-gray-600 dark:text-gray-400',
        titleText ? 'mt-1' : '',
        isExpanded ? 'whitespace-pre-wrap' : ''
      ]"
    >
      {{ displayContent }}
    </p>
    <!-- 展开/收起按钮 -->
    <button
      v-if="needsExpand"
      class="inline-flex items-center justify-center w-5 h-5 mt-1 text-sm font-bold text-primary-500 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded cursor-pointer transition-colors"
      @click.stop="toggle"
    >
      {{ isExpanded ? '-' : '+' }}
    </button>
  </div>
</template>
