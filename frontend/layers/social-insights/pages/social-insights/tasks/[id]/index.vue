<script setup lang="ts">
definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = computed(() => Number(route.params.id))

const { getTask, deleteTask } = useTasks()
const { getTaskPosts } = usePosts()

// 获取任务详情
const { data: task, pending: taskLoading, refresh: refreshTask } = getTask(taskId.value)

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

const formatDateTime = (dateStr: string | null) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const getStatusColor = (status: string) => {
  const colors: Record<string, string> = { pending: 'gray', running: 'blue', completed: 'green', failed: 'red' }
  return colors[status] || 'gray'
}

const getStatusText = (status: string) => {
  const texts: Record<string, string> = { pending: '待处理', running: '运行中', completed: '已完成', failed: '失败' }
  return texts[status] || status
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" @click="navigateTo('/social-insights/tasks')" />
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
        <div><h3 class="text-sm font-medium text-gray-500">任务名称</h3><p class="mt-1 text-sm">{{ task.name }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">状态</h3><UBadge class="mt-1" :color="getStatusColor(task.status)">{{ getStatusText(task.status) }}</UBadge></div>
        <div><h3 class="text-sm font-medium text-gray-500">任务类型</h3><p class="mt-1 text-sm">{{ task.task_type }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">数据源</h3><p class="mt-1 text-sm">{{ task.data_source === 'local_upload' ? '本地上传' : '远程爬虫' }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">原文数量</h3><p class="mt-1 text-sm">{{ task.posts_count }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">评论数量</h3><p class="mt-1 text-sm">{{ task.comments_count }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">创建时间</h3><p class="mt-1 text-sm">{{ formatDateTime(task.created_at) }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">开始时间</h3><p class="mt-1 text-sm">{{ formatDateTime(task.started_at) }}</p></div>
        <div><h3 class="text-sm font-medium text-gray-500">完成时间</h3><p class="mt-1 text-sm">{{ formatDateTime(task.completed_at) }}</p></div>
      </div>
    </UCard>

    <UCard>
      <template #header><h2 class="text-lg font-semibold">原文列表 ({{ posts?.length || 0 }})</h2></template>
      <div v-if="postsLoading" class="text-center py-8"><p class="text-gray-600">加载中...</p></div>
      <div v-else-if="!posts || posts.length === 0" class="text-center py-8"><p class="text-gray-600">暂无数据</p></div>
      <div v-else class="space-y-4">
        <div v-for="post in posts" :key="post.id" class="border rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer" @click="navigateTo(`/social-insights/posts/${post.id}`)">
          <h3 class="font-medium">{{ post.title || post.content?.substring(0, 50) }}</h3>
          <div class="mt-2 flex gap-4 text-xs text-gray-500">
            <span>👍 {{ post.likes_count }}</span>
            <span>💬 {{ post.comments_count }}</span>
            <span>🔄 {{ post.shares_count }}</span>
            <span>👀 {{ post.views_count }}</span>
            <span class="ml-auto">{{ formatDateTime(post.collected_at) }}</span>
          </div>
        </div>
      </div>
    </UCard>
  </div>
</template>
