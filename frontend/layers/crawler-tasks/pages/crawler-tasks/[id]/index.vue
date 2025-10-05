<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">任务详情</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">查看和管理爬虫任务</p>
      </div>

      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo('/crawler-tasks')"
      >
        返回列表
      </UButton>
    </div>

    <!-- 加载状态 -->
    <UCard v-if="pending">
      <div class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载任务信息中...</p>
      </div>
    </UCard>

    <!-- 错误状态 -->
    <UCard v-else-if="error">
      <div class="text-center py-8">
        <p class="text-red-500 mb-4">{{ error.message || '加载任务信息失败' }}</p>
        <UButton size="sm" @click="refresh()">重试</UButton>
      </div>
    </UCard>

    <!-- 任务详情 -->
    <TaskDetail
      v-else-if="data"
      :task="data"
      :can-edit="canEdit"
      :can-delete="canDelete"
      :can-execute="canExecute"
      @start="handleStart"
      @pause="handlePause"
      @stop="handleStop"
      @edit="handleEdit"
      @delete="handleDelete"
      @refresh="refresh"
    />
  </div>
</template>

<script setup lang="ts">
// 页面元数据
definePageMeta({
  title: '任务详情'
})

// 路由参数
const route = useRoute()
const taskId = computed(() => Number(route.params.id))

// API 调用
const crawlerTasksApi = useCrawlerTasksApi()
const { data, pending, error, refresh } = await crawlerTasksApi.getTaskDetail(taskId.value)

// 权限检查
const { hasPermission } = usePermissions()

const canEdit = computed(() => {
  return hasPermission({ target: 'crawler_tasks', action: 'write' })
})

const canDelete = computed(() => {
  return hasPermission({ target: 'crawler_tasks', action: 'delete' })
})

const canExecute = computed(() => {
  return hasPermission({ target: 'crawler_tasks', action: 'execute' })
})

// 事件处理
const handleEdit = () => {
  navigateTo(`/crawler-tasks/${taskId.value}/edit`)
}

const handleStart = async () => {
  if (!data.value) return

  try {
    await crawlerTasksApi.startTask(data.value.id)
    await refresh()
  } catch {
    // Error already handled in API
  }
}

const handlePause = async () => {
  if (!data.value) return

  try {
    await crawlerTasksApi.pauseTask(data.value.id)
    await refresh()
  } catch {
    // Error already handled in API
  }
}

const handleStop = async () => {
  if (!data.value) return

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm(`确定要停止任务 "${data.value.name}" 吗？`)
  if (!confirmed) return

  try {
    await crawlerTasksApi.stopTask(data.value.id)
    await refresh()
  } catch {
    // Error already handled in API
  }
}

const handleDelete = async () => {
  if (!data.value) return

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm(`确定要删除任务 "${data.value.name}" 吗？此操作不可恢复。`)
  if (!confirmed) return

  try {
    await crawlerTasksApi.deleteTask(data.value.id)

    const toast = useToast()
    toast.add({
      title: '删除成功',
      description: `任务 "${data.value.name}" 已被删除`,
      color: 'success'
    })

    navigateTo('/crawler-tasks')
  } catch {
    const toast = useToast()
    toast.add({
      title: '删除失败',
      description: '无法删除任务，请稍后重试',
      color: 'error'
    })
  }
}

// 监听路由变化
watch(() => route.params.id, async (newId) => {
  if (newId) {
    await refresh()
  }
})
</script>
