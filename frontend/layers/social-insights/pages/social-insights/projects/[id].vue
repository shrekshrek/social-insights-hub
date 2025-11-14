<script setup lang="ts">
definePageMeta({
  middleware: 'auth',
  layout: 'default',
})

const route = useRoute()
const projectId = computed(() => Number(route.params.id))

const { getProject, deleteProject } = useSocialProjects()
const { getTasks } = useTasks()

// 获取项目详情
const { data: project, pending: projectLoading, refresh: refreshProject } = getProject(projectId.value)

// 获取项目下的任务列表
const taskParams = computed(() => ({
  project_id: projectId.value,
  page: 1,
  page_size: 100,
}))

const { data: tasksData, pending: tasksLoading, refresh: refreshTasks } = getTasks(taskParams)

const tasks = computed(() => tasksData.value?.items || [])

// 刷新所有数据
const refreshing = ref(false)
const handleRefresh = async () => {
  refreshing.value = true
  await Promise.all([refreshProject(), refreshTasks()])
  refreshing.value = false
}

// 删除项目
const handleDelete = async () => {
  if (!project.value) return

  const confirmed = await confirm(
    `确定要删除项目 "${project.value.name}" 吗？此操作不可恢复，所有相关任务和数据也将被删除。`
  )
  if (!confirmed) return

  try {
    await deleteProject(project.value.id)
    await navigateTo('/social-insights/projects')
  } catch (error) {
    console.error('删除项目失败:', error)
  }
}

// 格式化日期
const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

const formatDateTime = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 任务状态颜色
const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'gray',
    running: 'blue',
    completed: 'green',
    failed: 'red',
  }
  return colors[status] || 'gray'
}

// 任务状态文本
const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    pending: '待处理',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }
  return texts[status] || status
}
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            @click="navigateTo('/social-insights/projects')"
          />
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ project?.name || '加载中...' }}
            </h1>
            <p class="text-gray-600 dark:text-gray-400 mt-1">
              项目详情
            </p>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          @click="navigateTo(`/social-insights/tasks/create?project_id=${projectId}`)"
        >
          新建任务
        </UButton>
        <UButton
          variant="outline"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
        <UButton
          variant="outline"
          icon="i-heroicons-trash"
          color="red"
          @click="handleDelete"
        >
          删除项目
        </UButton>
      </div>
    </div>

    <!-- 项目信息卡片 -->
    <UCard v-if="project">
      <template #header>
        <h2 class="text-lg font-semibold">
          项目信息
        </h2>
      </template>

      <div class="grid grid-cols-2 gap-6">
        <div>
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            项目名称
          </h3>
          <p class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ project.name }}
          </p>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            创建者
          </h3>
          <p class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ project.owner_username || '-' }}
          </p>
        </div>

        <div class="col-span-2">
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            项目描述
          </h3>
          <p class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ project.description || '无描述' }}
          </p>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            关键词
          </h3>
          <p class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ project.keywords || '-' }}
          </p>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            目标平台
          </h3>
          <div class="mt-1 flex flex-wrap gap-2">
            <UBadge
              v-for="platform in project.platforms"
              :key="platform.id"
              variant="subtle"
            >
              {{ platform.name }}
            </UBadge>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            项目时间
          </h3>
          <p class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ formatDate(project.project_start_date) }} - {{ formatDate(project.project_end_date) }}
          </p>
        </div>

        <div>
          <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
            创建时间
          </h3>
          <p class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ formatDateTime(project.created_at) }}
          </p>
        </div>
      </div>
    </UCard>

    <!-- 任务列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            任务列表 ({{ tasks.length }})
          </h2>
        </div>
      </template>

      <div v-if="tasksLoading" class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">
          加载任务列表中...
        </p>
      </div>

      <div v-else-if="tasks.length === 0" class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">
          暂无任务
        </p>
        <UButton
          class="mt-4"
          @click="navigateTo(`/social-insights/tasks/create?project_id=${projectId}`)"
        >
          创建第一个任务
        </UButton>
      </div>

      <div v-else class="space-y-4">
        <div
          v-for="task in tasks"
          :key="task.id"
          class="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
          @click="navigateTo(`/social-insights/tasks/${task.id}`)"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center gap-3">
                <h3 class="text-base font-medium text-gray-900 dark:text-white">
                  {{ task.name }}
                </h3>
                <UBadge :color="getStatusColor(task.status)">
                  {{ getStatusText(task.status) }}
                </UBadge>
                <UBadge variant="subtle">
                  {{ task.platform_name }}
                </UBadge>
              </div>
              <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
                {{ task.description || '无描述' }}
              </p>
              <div class="mt-2 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                <span>类型: {{ task.task_type }}</span>
                <span>数据源: {{ task.data_source === 'local_upload' ? '本地上传' : '远程爬虫' }}</span>
                <span>原文: {{ task.posts_count }}</span>
                <span>评论: {{ task.comments_count }}</span>
                <span>创建: {{ formatDateTime(task.created_at) }}</span>
              </div>
            </div>
            <UButton
              size="xs"
              variant="ghost"
              icon="i-heroicons-arrow-right"
            />
          </div>
        </div>
      </div>
    </UCard>
  </div>
</template>
