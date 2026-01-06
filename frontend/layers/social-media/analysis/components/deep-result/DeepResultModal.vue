<script setup lang="ts">
/**
 * 深度分析结果弹窗组件（共用）
 *
 * 用于展示帖子原文深度分析或评论深度分析结果
 */
import type { PostAnalysisWithPostInfo } from '../../types'
import PostDeepAnalysisResult from './PostDeepAnalysisResult.vue'
import CommentDeepAnalysisResult from './CommentDeepAnalysisResult.vue'

const props = defineProps<{
  open: boolean
  postData: PostAnalysisWithPostInfo | null
  type: 'post' | 'comment'
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const title = computed(() =>
  props.type === 'post' ? '原文深度分析结果' : '评论深度分析结果'
)

const handleClose = () => {
  emit('update:open', false)
}
</script>

<template>
  <UModal
    :open="open"
    :title="title"
    description="查看AI深度分析的详细结果"
    :ui="{ content: 'w-[calc(100vw-2rem)] max-w-2xl rounded-lg shadow-lg ring ring-default', footer: 'justify-end' }"
    @update:open="handleClose"
  >
    <template #body>
      <div v-if="postData" class="space-y-4">
        <!-- 帖子标题 -->
        <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
            {{ postData.title || '无标题' }}
          </p>
        </div>

        <!-- 原文深度结果 -->
        <PostDeepAnalysisResult
          v-if="type === 'post' && postData.post_deep_result"
          :data="postData.post_deep_result"
        />

        <!-- 评论深度结果 -->
        <CommentDeepAnalysisResult
          v-else-if="type === 'comment' && postData.comment_deep_result"
          :data="postData.comment_deep_result"
        />

        <div v-else class="text-center text-gray-500 py-4">
          暂无分析结果
        </div>
      </div>
    </template>

    <template #footer>
      <UButton
        label="关闭"
        color="neutral"
        variant="outline"
        @click="handleClose"
      />
    </template>
  </UModal>
</template>
