<script setup lang="ts">
/**
 * 帖子列表弹窗组件
 *
 * 用于显示指定帖子ID列表对应的帖子详情
 */
import type { PostAnalysisWithPostInfo } from '../types'

const props = defineProps<{
  open: boolean
  taskId: number
  postIds: number[]
  title?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { getTaskPostAnalyses } = useAnalysis()

const page = ref(1)
const pageSize = ref(20)
const postIdsRef = computed(() => props.postIds)

const {
  data: postData,
  pending: loading,
  refresh,
} = getTaskPostAnalyses(props.taskId, {
  page,
  pageSize,
  filterAnalyzed: false,
  postIds: postIdsRef,
})

const posts = computed(() => postData.value?.items || [])
const total = computed(() => postData.value?.total || 0)

// 当弹窗打开或 postIds 变化时刷新数据
watch(() => [props.open, props.postIds], ([isOpen]) => {
  if (isOpen && props.postIds.length > 0) {
    page.value = 1
    refresh()
  }
})

const formatNumber = (num?: number | null) => {
  if (num == null) return '-'
  if (num >= 10000) return `${(num / 10000).toFixed(1)}万`
  return num.toLocaleString()
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  return isNaN(date.getTime()) ? '-' : date.toLocaleDateString('zh-CN')
}

const getSentimentLabel = (sentiment: number | null) => {
  if (sentiment === null) return '-'
  if (sentiment > 0) return '正面'
  if (sentiment < 0) return '负面'
  return '中性'
}

const getSentimentColor = (sentiment: number | null) => {
  if (sentiment === null) return 'neutral'
  if (sentiment > 0) return 'success'
  if (sentiment < 0) return 'error'
  return 'neutral'
}

const handleClose = () => {
  emit('update:open', false)
}
</script>

<template>
  <UModal
    :open="open"
    :title="title || `相关帖子 (${postIds.length})`"
    :ui="{ width: 'sm:max-w-4xl', footer: 'justify-end' }"
    @update:open="handleClose"
  >
    <template #body>
      <div v-if="loading" class="flex items-center justify-center py-12">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-gray-400" />
      </div>

      <div v-else-if="posts.length === 0" class="text-center py-12 text-gray-500">
        <UIcon name="i-heroicons-inbox" class="w-10 h-10 mx-auto mb-2 opacity-60" />
        <p class="text-sm">暂无帖子数据</p>
      </div>

      <div v-else class="space-y-2 max-h-[60vh] overflow-y-auto">
        <div
          v-for="post in posts"
          :key="post.post_id"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <!-- 标题和内容 -->
          <div class="mb-2">
            <h4 v-if="post.title" class="font-medium text-gray-900 dark:text-gray-100 line-clamp-1">
              {{ post.title }}
            </h4>
            <p class="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mt-1">
              {{ post.content || '无内容' }}
            </p>
          </div>

          <!-- 底部信息栏 -->
          <div class="flex items-center justify-between text-xs text-gray-500">
            <div class="flex items-center gap-3">
              <!-- 作者 -->
              <span v-if="post.author_name">
                <UIcon name="i-heroicons-user" class="w-3 h-3 inline mr-0.5" />
                {{ post.author_name }}
              </span>
              <!-- 互动数据 -->
              <span>
                <UIcon name="i-heroicons-heart" class="w-3 h-3 inline mr-0.5" />
                {{ formatNumber(post.likes_count) }}
              </span>
              <span>
                <UIcon name="i-heroicons-chat-bubble-left" class="w-3 h-3 inline mr-0.5" />
                {{ formatNumber(post.comments_count) }}
              </span>
              <!-- 情感 -->
              <UBadge
                v-if="post.sentiment !== null"
                :color="getSentimentColor(post.sentiment)"
                variant="subtle"
                size="xs"
              >
                {{ getSentimentLabel(post.sentiment) }}
              </UBadge>
              <!-- CII -->
              <span v-if="post.cii !== null" class="font-mono">
                CII {{ post.cii.toFixed(1) }}
              </span>
            </div>
            <!-- 发布时间 -->
            <span>{{ formatDateTime(post.published_at) }}</span>
          </div>

          <!-- 链接 -->
          <a
            v-if="post.url"
            :href="post.url"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 mt-2 text-xs text-primary-600 hover:text-primary-700"
          >
            <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-3 h-3" />
            查看原文
          </a>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="total > pageSize" class="flex justify-between items-center mt-4 pt-4 border-t">
        <span class="text-xs text-gray-500">
          共 {{ total }} 条
        </span>
        <UPagination
          v-model:page="page"
          :total="total"
          :items-per-page="pageSize"
          size="xs"
        />
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
