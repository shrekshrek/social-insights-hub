<script setup lang="ts">
definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = computed(() => Number(route.params.id))

// 智能返回路径：根据来源返回到对应页面
const backPath = computed(() => {
  const from = route.query.from as string
  const projectId = route.query.project_id

  if (from === 'project' && projectId) {
    return `/social-insights/projects/${projectId}`
  }
  return '/social-insights/tasks' // 默认返回任务列表
})

const { getTask, deleteTask } = useTasks()
const { getTaskPosts, getPostWithComments } = usePosts()

// 获取任务详情
const { data: task, pending: _taskLoading, refresh: refreshTask } = getTask(taskId.value)

// 获取任务的原文列表
const postParams = computed(() => ({
  page: 1,
  page_size: 20,
}))

const { data: posts, pending: postsLoading, refresh: refreshPosts } = getTaskPosts(taskId.value, postParams)

const refreshing = ref(false)
const handleRefresh = async () => {
  refreshing.value = true
  await Promise.all([refreshTask(), refreshPosts()])
  refreshing.value = false
}

const handleDelete = async () => {
  if (!task.value) return
  const confirmed = await confirm(`确定要删除任务 "${task.value.name}" 吗？`)
  if (!confirmed) return

  try {
    await deleteTask(task.value.id)
    await navigateTo('/social-insights/tasks')
  } catch (error) {
    console.error('删除任务失败:', error)
  }
}

// 查看评论Modal
const showCommentsModal = ref(false)
const selectedPostId = ref<number | null>(null)
const commentParams = computed(() => ({
  page: 1,
  page_size: 100,
}))

const selectedPostData = computed(() => {
  if (!selectedPostId.value) return null
  return getPostWithComments(selectedPostId.value, commentParams.value)
})

const selectedPost = computed(() => selectedPostData.value?.data.value || null)
const commentsLoading = computed(() => selectedPostData.value?.pending.value || false)

const handleViewComments = (postId: number) => {
  selectedPostId.value = postId
  showCommentsModal.value = true
}

const handleCloseModal = () => {
  showCommentsModal.value = false
  setTimeout(() => {
    selectedPostId.value = null
  }, 300)
}

// 格式化函数
const formatDateTime = (dateStr: string | null) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const formatNumber = (num: number) => {
  if (num >= 10000) {
    return `${(num / 10000).toFixed(1)}万`
  }
  return num.toString()
}

const getStatusColor = (status: string) => {
  const colors: Record<string, string> = { pending: 'gray', running: 'blue', completed: 'green', failed: 'red' }
  return colors[status] || 'gray'
}

const getStatusText = (status: string) => {
  const texts: Record<string, string> = { pending: '待处理', running: '运行中', completed: '已完成', failed: '失败' }
  return texts[status] || status
}

// 表格列定义
const columns = [
  { key: 'title', label: '标题/内容', class: 'min-w-[300px]' },
  { key: 'author_name', label: '作者', class: 'min-w-[120px]' },
  { key: 'likes_count', label: '点赞', class: 'text-right' },
  { key: 'comments_count', label: '评论', class: 'text-right' },
  { key: 'shares_count', label: '转发', class: 'text-right' },
  { key: 'views_count', label: '浏览', class: 'text-right' },
  { key: 'collected_at', label: '采集时间', class: 'min-w-[160px]' },
  { key: 'actions', label: '操作', class: 'text-right' },
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" @click="navigateTo(backPath)" />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ task?.name || '加载中...' }}</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">任务详情</p>
        </div>
      </div>
      <div class="flex gap-3">
        <UButton v-if="task?.status === 'pending' && task?.data_source === 'local_upload'" icon="i-heroicons-arrow-up-tray" @click="navigateTo(`/social-insights/tasks/${taskId}/upload`)">上传数据</UButton>
        <UButton variant="outline" icon="i-heroicons-arrow-path" :loading="refreshing" @click="handleRefresh">刷新</UButton>
        <UButton variant="outline" icon="i-heroicons-trash" color="red" @click="handleDelete">删除</UButton>
      </div>
    </div>

    <UCard v-if="task">
      <template #header><h2 class="text-lg font-semibold">任务信息</h2></template>
      <div class="grid grid-cols-3 gap-6">
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">任务名称</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.name }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">状态</h3><UBadge class="mt-1" :color="getStatusColor(task.status)">{{ getStatusText(task.status) }}</UBadge></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">平台</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.platform_name || '-' }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">任务类型</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.task_type }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">数据源</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.data_source === 'local_upload' ? '本地上传' : '远程爬虫' }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">所属项目</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.project_name || '-' }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">原文数量</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.posts_count }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">评论数量</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.comments_count }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">创建者</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ task.creator_username || '-' }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">创建时间</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ formatDateTime(task.created_at) }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">开始时间</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ formatDateTime(task.started_at) }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">完成时间</h3><p class="mt-1 text-sm text-gray-900 dark:text-white">{{ formatDateTime(task.completed_at) }}</p></div>
      </div>
    </UCard>

    <UCard>
      <template #header><h2 class="text-lg font-semibold">原文列表 ({{ posts?.length || 0 }})</h2></template>

      <UTable
        v-if="!postsLoading && posts && posts.length > 0"
        :rows="posts"
        :columns="columns"
        :loading="postsLoading"
      >
        <template #title-data="{ row }">
          <div class="max-w-md">
            <p class="font-medium text-sm truncate">{{ row.title || '无标题' }}</p>
            <p class="text-xs text-gray-600 dark:text-gray-400 truncate mt-1">
              {{ row.content?.substring(0, 80) || '无内容' }}
            </p>
          </div>
        </template>

        <template #author_name-data="{ row }">
          <span class="text-sm">{{ row.author_name || '-' }}</span>
        </template>

        <template #likes_count-data="{ row }">
          <span class="text-sm text-right block">{{ formatNumber(row.likes_count) }}</span>
        </template>

        <template #comments_count-data="{ row }">
          <span class="text-sm text-right block">{{ formatNumber(row.comments_count) }}</span>
        </template>

        <template #shares_count-data="{ row }">
          <span class="text-sm text-right block">{{ formatNumber(row.shares_count) }}</span>
        </template>

        <template #views_count-data="{ row }">
          <span class="text-sm text-right block">{{ formatNumber(row.views_count) }}</span>
        </template>

        <template #collected_at-data="{ row }">
          <span class="text-xs">{{ formatDateTime(row.collected_at) }}</span>
        </template>

        <template #actions-data="{ row }">
          <div class="flex justify-end">
            <UButton
              size="xs"
              variant="ghost"
              icon="i-heroicons-chat-bubble-left-right"
              @click="handleViewComments(row.id)"
            >
              查看评论
            </UButton>
          </div>
        </template>
      </UTable>

      <div v-else-if="postsLoading" class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载中...</p>
      </div>

      <div v-else class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">暂无数据</p>
      </div>
    </UCard>

    <!-- 评论Modal -->
    <UModal v-model="showCommentsModal" :ui="{ width: 'sm:max-w-4xl' }">
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold">帖子详情与评论</h3>
            <UButton
              variant="ghost"
              icon="i-heroicons-x-mark"
              @click="handleCloseModal"
            />
          </div>
        </template>

        <div v-if="commentsLoading" class="text-center py-8">
          <p class="text-gray-600 dark:text-gray-400">加载中...</p>
        </div>

        <div v-else-if="selectedPost" class="space-y-6">
          <!-- 帖子信息 -->
          <div class="border-b border-gray-200 dark:border-gray-700 pb-4">
            <h4 class="font-medium text-base mb-2">{{ selectedPost.title || '无标题' }}</h4>
            <p class="text-sm text-gray-700 dark:text-gray-300 mb-3 whitespace-pre-wrap">
              {{ selectedPost.content || '无内容' }}
            </p>
            <div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
              <span>作者: {{ selectedPost.author_name || '-' }}</span>
              <span>👍 {{ formatNumber(selectedPost.likes_count) }}</span>
              <span>💬 {{ formatNumber(selectedPost.comments_count) }}</span>
              <span>🔄 {{ formatNumber(selectedPost.shares_count) }}</span>
              <span>👀 {{ formatNumber(selectedPost.views_count) }}</span>
              <span>{{ formatDateTime(selectedPost.collected_at) }}</span>
            </div>
          </div>

          <!-- 评论列表 -->
          <div>
            <h4 class="font-medium text-sm mb-3">
              评论列表 ({{ selectedPost.comments?.length || 0 }})
            </h4>

            <div v-if="!selectedPost.comments || selectedPost.comments.length === 0" class="text-center py-4 text-gray-500">
              暂无评论
            </div>

            <div v-else class="space-y-3 max-h-[400px] overflow-y-auto">
              <div
                v-for="comment in selectedPost.comments"
                :key="comment.id"
                class="border border-gray-200 dark:border-gray-700 rounded-lg p-3"
              >
                <div class="flex items-start gap-3">
                  <div class="flex-1">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="font-medium text-sm">{{ comment.author_name || '匿名用户' }}</span>
                      <span class="text-xs text-gray-500">{{ formatDateTime(comment.collected_at) }}</span>
                    </div>
                    <p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                      {{ comment.content || '无内容' }}
                    </p>
                    <div class="flex items-center gap-3 mt-2 text-xs text-gray-500">
                      <span>👍 {{ comment.likes_count }}</span>
                      <span v-if="comment.sub_comments_count > 0">💬 {{ comment.sub_comments_count }} 条回复</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </UCard>
    </UModal>
  </div>
</template>
