<script setup lang="ts">
import { marked } from 'marked'

const props = defineProps<{
  content: string
}>()

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

const html = computed(() => {
  if (!props.content) return ''
  return marked.parse(props.content) as string
})
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- 内容来自 LLM 生成的可信报告，非用户输入 -->
  <div class="markdown-body" v-html="html" />
</template>

<style scoped>
.markdown-body {
  color: #1f2937; /* gray-800 */
  line-height: 1.7;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-weight: 600;
  color: #111827; /* gray-900 */
  margin-top: 1.25em;
  margin-bottom: 0.5em;
}

.markdown-body :deep(h1) { font-size: 1.25rem; }
.markdown-body :deep(h2) { font-size: 1.125rem; }
.markdown-body :deep(h3) { font-size: 1rem; }

.markdown-body :deep(p) {
  margin-bottom: 0.75em;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: #111827;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 0.75em;
}

.markdown-body :deep(li) {
  margin-bottom: 0.25em;
}

/* 深色模式 */
:global(.dark) .markdown-body {
  color: #e5e7eb; /* gray-200 */
}

:global(.dark) .markdown-body :deep(h1),
:global(.dark) .markdown-body :deep(h2),
:global(.dark) .markdown-body :deep(h3),
:global(.dark) .markdown-body :deep(strong) {
  color: #fff;
}
</style>

