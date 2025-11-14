<script setup lang="ts">
import type { DataTaskWithRelations } from '../../../types'

definePageMeta({
  middleware: 'auth',
  layout: 'default',
})

const { getTasks, deleteTask } = useTasks()
const { getProjects } = useSocialProjects()
const { getPlatforms } = usePlatforms()

// 获取项目和平台列表用于过滤
const { data: projectsData } = getProjects({ page: 1, page_size: 100 })
const { data: platforms } = getPlatforms()

// 分页和过滤
const currentPage = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')
const selectedProjectId = ref<number | undefined>()
const selectedPlatformId = ref<number | undefined>()
const selectedStatus = ref<string | undefined>()
const selectedDataSource = ref<string | undefined>()
const refreshing = ref(false)

// 获取任务列表
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
  project_id: selectedProjectId.value,
  platform_id: selectedPlatformId.value,
  status: selectedStatus.value,
  data_source: selectedDataSource.value,
}))

const { data: tasksData, pending: loading, refresh } = getTasks(params)

const tasks = computed(() => tasksData.value?.items || [])
const total = computed(() => tasksData.value?.total || 0)

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

// 删除任务
const handleDelete = async (task: DataTaskWithRelations) => {
  const confirmed = await confirm(`确定要删除任务 "${task.name}" 吗？此操作不可恢复。`)
  if (!confirmed) return

  try {
    await deleteTask(task.id)
    await handleRefresh()
  } catch (error) {
    console.error('删除任务失败:', error)
  }
}

// 表格列定义
const columns = [
  { key: 'name', label: '任务名称' },
  { key: 'project', label: '所属项目' },
  { key: 'platform', label: '平台' },
  { key: 'status', label: '状态' },
  { key: 'stats', label: '数据统计' },
  { key: 'created_at', label: '创建时间' },
  { key: 'actions', label: '操作' },
]

// 格式化日期
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

// 过滤选项
const statusOptions = [
  { label: '全部', value: undefined },
  { label: '待处理', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]

const dataSourceOptions = [
  { label: '全部', value: undefined },
  { label: '本地上传', value: 'local_upload' },
  { label: '远程爬虫', value: 'remote_crawler' },
]
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          数据采集任务
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理您的社交媒体数据采集任务
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          @click="navigateTo('/social-insights/tasks/create')"
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
      </div>
    </div>

    <!-- 过滤器 -->
    <UCard>
      <div class="grid grid-cols-4 gap-4">
        <UFormGroup label="搜索">
          <UInput
            v-model="searchQuery"
            placeholder="搜索任务名称或关键词..."
            icon="i-heroicons-magnifying-glass"
          />
        </UFormGroup>

        <UFormGroup label="所属项目">
          <USelectMenu
            v-model="selectedProjectId"
            :options="[
              { label: '全部项目', value: undefined },
              ...(projectsData?.items.map(p => ({ label: p.name, value: p.id })) || [])
            ]"
            placeholder="选择项目"
          />
        </UFormGroup>

        <UFormGroup label="平台">
          <USelectMenu
            v-model="selectedPlatformId"
            :options="[
              { label: '全部平台', value: undefined },
              ...(platforms?.map(p => ({ label: p.name, value: p.id })) || [])
            ]"
            placeholder="选择平台"
          />
        </UFormGroup>

        <UFormGroup label="状态">
          <USelectMenu
            v-model="selectedStatus"
            :options="statusOptions"
            placeholder="选择状态"
          />
        </UFormGroup>
      </div>
    </UCard>

    <!-- 任务列表卡片 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">
          任务列表
        </h2>
      </template>

      <!-- 任务表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载任务列表中...
            </p>
          </div>
        </template>

        <UTable
          :data="tasks"
          :columns="columns"
          :loading="loading"
          class="w-full"
        >
          <template #project-data="{ row }">
            <span class="text-sm text-gray-900 dark:text-white">
              {{ row.project_name || '-' }}
            </span>
          </template>

          <template #platform-data="{ row }">
            <UBadge variant="subtle">
              {{ row.platform_name }}
            </UBadge>
          </template>

          <template #status-data="{ row }">
            <UBadge :color="getStatusColor(row.status)">
              {{ getStatusText(row.status) }}
            </UBadge>
          </template>

          <template #stats-data="{ row }">
            <div class="text-xs text-gray-600 dark:text-gray-400">
              <div>原文: {{ row.posts_count }}</div>
              <div>评论: {{ row.comments_count }}</div>
            </div>
          </template>

          <template #created_at-data="{ row }">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              {{ formatDateTime(row.created_at) }}
            </span>
          </template>

          <template #actions-data="{ row }">
            <div class="flex items-center gap-2">
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-eye"
                @click="navigateTo(`/social-insights/tasks/${row.id}`)"
              >
                查看
              </UButton>
              <UButton
                v-if="row.status === 'pending' && row.data_source === 'local_upload'"
                size="xs"
                variant="ghost"
                icon="i-heroicons-arrow-up-tray"
                @click="navigateTo(`/social-insights/tasks/${row.id}/upload`)"
              >
                上传
              </UButton>
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-trash"
                color="red"
                @click="handleDelete(row)"
              >
                删除
              </UButton>
            </div>
          </template>
        </UTable>
      </ClientOnly>

      <!-- 分页 -->
      <template #footer>
        <ClientOnly>
          <div class="flex justify-between items-center">
            <div class="text-sm text-gray-500 dark:text-gray-400">
              显示 {{ (currentPage - 1) * pageSize + 1 }} 到
              {{ Math.min(currentPage * pageSize, total) }} 共
              {{ total }} 条记录
            </div>
            <UPagination
              v-model:page="currentPage"
              :total="total"
              :items-per-page="pageSize"
              :sibling-count="2"
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>
