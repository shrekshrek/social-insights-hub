<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { DataTaskWithRelations } from '~/layers/social-insights/types'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const projectId = computed(() => Number(route.params.id))

const { getProject, deleteProject } = useSocialProjects()
const { getTasks } = useTasks()

// 获取项目详情
const { data: project, pending: _projectLoading, refresh: refreshProject } = getProject(projectId.value)

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

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除项目',
    message: `确定要删除项目 "${project.value.name}" 吗？此操作不可恢复，所有相关任务和数据也将被删除。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })

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
    pending: 'neutral',
    running: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
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

// 表格列定义
const columns: TableColumn<DataTaskWithRelations>[] = [
  {
    accessorKey: 'name',
    header: '任务名称',
    cell: ({ row }) => h('span', { class: 'font-medium' }, row.original.name),
  },
  {
    accessorKey: 'platform_name',
    header: '平台',
    cell: ({ row }) => {
      const UBadge = resolveComponent('UBadge')
      return h(UBadge, { variant: 'subtle', size: 'xs' }, () => row.original.platform_name || '-')
    },
  },
  {
    accessorKey: 'task_type',
    header: '类型',
    cell: ({ row }) => h('span', { class: 'text-sm' }, row.original.task_type),
  },
  {
    accessorKey: 'status',
    header: '状态',
    cell: ({ row }) => {
      const UBadge = resolveComponent('UBadge')
      return h(UBadge, {
        color: getStatusColor(row.original.status),
        variant: 'solid',
        size: 'xs'
      }, () => getStatusText(row.original.status))
    },
  },
  {
    accessorKey: 'stats',
    header: '数据统计',
    cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' },
      `${row.original.posts_count} 原文 / ${row.original.comments_count} 评论`
    ),
  },
  {
    accessorKey: 'created_at',
    header: '创建时间',
    cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, formatDateTime(row.original.created_at)),
  },
  {
    accessorKey: 'actions',
    header: '操作',
    cell: ({ row }) => {
      const UButton = resolveComponent('UButton')
      return h('div', { class: 'flex items-center gap-2' }, [
        h(UButton, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-eye',
          onClick: () => navigateTo(`/social-insights/tasks/${row.original.id}?from=project&project_id=${projectId.value}`),
        }, () => '查看'),
        row.original.status === 'pending' && row.original.data_source === 'local_upload'
          ? h(UButton, {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-arrow-up-tray',
              color: 'info',
              onClick: () => navigateTo(`/social-insights/tasks/${row.original.id}/upload`),
            }, () => '上传')
          : null,
      ].filter(Boolean))
    },
  },
]
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
          color="error"
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

      <div class="space-y-4">
        <!-- 第一行：项目名称和描述 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              项目名称
            </h3>
            <p class="mt-1 text-sm text-gray-900 dark:text-white">
              {{ project.name }}
            </p>
          </div>

          <div v-if="project.description">
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              项目描述
            </h3>
            <p
              class="mt-1 text-sm text-gray-900 dark:text-white line-clamp-2"
              :title="project.description"
            >
              {{ project.description }}
            </p>
          </div>
        </div>

        <!-- 第二行：其他信息（自适应2-4列） -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              创建者
            </h3>
            <p class="mt-1 text-sm text-gray-900 dark:text-white">
              {{ project.owner_username || '-' }}
            </p>
          </div>

          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              参与者
            </h3>
            <p
              class="mt-1 text-sm text-gray-900 dark:text-white truncate"
              :title="project.participant_usernames?.join(', ') || '无'"
            >
              {{ project.participant_usernames?.length ? project.participant_usernames.join(', ') : '无' }}
            </p>
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

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载任务列表中...
            </p>
          </div>
        </template>

        <div v-if="tasks.length === 0" class="text-center py-8">
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

        <UTable
          v-else
          :data="tasks"
          :columns="columns"
          :loading="tasksLoading"
          class="w-full"
        />
      </ClientOnly>
    </UCard>
  </div>
</template>
