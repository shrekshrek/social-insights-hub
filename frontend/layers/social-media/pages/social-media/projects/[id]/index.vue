<script setup lang="ts">
import { computed, ref, h, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton } from '#components'
import type { DataTaskWithRelations } from '../../../../tasks/types'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const projectId = computed(() => Number(route.params.id))

const { getProject, deleteProject } = useSocialProjects()
const { getTasks } = useTasks()
const { createProjectSnapshot, deleteProjectSnapshot } = useAnalysis()
const { useApiData } = useApi()

// 获取项目详情（使用顶层 await）
const { data: project, pending: _projectLoading, refresh: refreshProject } = await getProject(projectId.value)

// 获取项目下的任务列表
const taskParams = computed(() => ({
  project_id: projectId.value,
  page: 1,
  page_size: 100,
}))

const { data: tasksData, pending: tasksLoading, refresh: refreshTasks } = await getTasks(taskParams)

const tasks = computed(() => tasksData.value?.items || [])

// ==================== 项目快照（Phase 1）====================

// 已选择的任务（用于生成快照）
const selectedTaskIds = ref<number[]>([])
const setTaskSelected = (taskId: number, checked: boolean) => {
  const s = new Set(selectedTaskIds.value)
  if (checked) s.add(taskId)
  else s.delete(taskId)
  selectedTaskIds.value = Array.from(s)
}
const allTaskIds = computed(() => (tasks.value as DataTaskWithRelations[]).map(t => t.id))
const allSelected = computed(() => allTaskIds.value.length > 0 && allTaskIds.value.every(id => selectedTaskIds.value.includes(id)))
const toggleSelectAll = (checked: boolean) => {
  selectedTaskIds.value = checked ? Array.from(new Set(allTaskIds.value)) : []
}

// 快照列表
interface ProjectSnapshot {
  id: number
  name: string | null
  project_id: number
  user_id: number
  included_task_ids: number[]
  result_data: Record<string, unknown>
  created_at: string
  updated_at: string
}
interface ProjectSnapshotListResponse {
  items: ProjectSnapshot[]
}
const { data: snapshotsData, pending: snapshotsLoading, refresh: refreshSnapshots } = useApiData<ProjectSnapshotListResponse>(
  computed(() => `/social-media/analysis/projects/${projectId.value}/snapshots`),
  { key: computed(() => `project-snapshots-${projectId.value}`), getCachedData: () => undefined }
)
const snapshots = computed<ProjectSnapshot[]>(() => snapshotsData.value?.items || [])

const handleRefreshSnapshots = async () => {
  await refreshSnapshots()
}

const generatingSnapshot = ref(false)
const snapshotNameInput = ref('')
const showSnapshotModal = ref(false)

const openSnapshotModal = () => {
  if (!selectedTaskIds.value.length) return
  snapshotNameInput.value = ''
  showSnapshotModal.value = true
}

const handleGenerateSnapshot = async () => {
  showSnapshotModal.value = false

  generatingSnapshot.value = true
  try {
    const name = snapshotNameInput.value.trim() || undefined
    await createProjectSnapshot(projectId.value, selectedTaskIds.value, name)
    selectedTaskIds.value = []
    snapshotNameInput.value = ''
    await refreshSnapshots()
    await navigateTo(`/social-media/projects/${projectId.value}/analysis`)
  } finally {
    generatingSnapshot.value = false
  }
}

const deletingSnapshotId = ref<number | null>(null)
const handleDeleteSnapshot = async (snapshotId: number) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除快照',
    message: `确定要删除快照 ${snapshotId} 吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  deletingSnapshotId.value = snapshotId
  try {
    await deleteProjectSnapshot(projectId.value, snapshotId)
    await refreshSnapshots()
  } finally {
    deletingSnapshotId.value = null
  }
}

// 刷新所有数据
const refreshing = ref(false)
const handleRefresh = async () => {
  refreshing.value = true
  await Promise.all([refreshProject(), refreshTasks(), refreshSnapshots()])
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
    await navigateTo('/social-media/projects')
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

// 表格列定义 - 使用 computed 以避免 SSR 水合问题
const columns = computed<TableColumn<DataTaskWithRelations>[]>(() => {
  const Badge = UBadge as Component
  const Button = UButton as Component

  return [
    {
      id: 'select',
      header: () => h('input', {
        type: 'checkbox',
        checked: allSelected.value,
        onChange: (e: Event) => toggleSelectAll((e.target as HTMLInputElement).checked),
        title: '全选',
      }),
      cell: ({ row }) => h('input', {
        type: 'checkbox',
        checked: selectedTaskIds.value.includes(row.original.id),
        onChange: (e: Event) => setTaskSelected(row.original.id, (e.target as HTMLInputElement).checked),
      }),
    },
    {
      accessorKey: 'id',
      header: 'ID',
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'name',
      header: '任务名称',
      cell: ({ row }) => h('span', { class: 'font-medium' }, row.original.name),
    },
    {
      accessorKey: 'platform_name',
      header: '平台',
      cell: ({ row }) => h(Badge, { variant: 'subtle', size: 'xs' }, () => row.original.platform_name || '-'),
    },
    {
      accessorKey: 'task_type',
      header: '类型',
      cell: ({ row }) => h('span', { class: 'text-sm' }, row.original.task_type),
    },
    {
      accessorKey: 'status',
      header: '状态',
      cell: ({ row }) => h(Badge, {
        color: getStatusColor(row.original.status),
        variant: 'solid',
        size: 'xs'
      }, () => getStatusText(row.original.status)),
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
      cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
        h(Button, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-eye',
          onClick: () => navigateTo(`/social-media/tasks/${row.original.id}?from=project&project_id=${projectId.value}`),
        }, () => '查看'),
        row.original.status === 'pending' && row.original.data_source === 'local_upload'
          ? h(Button, {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-arrow-up-tray',
              color: 'info',
              onClick: () => navigateTo(`/social-media/tasks/${row.original.id}/upload`),
            }, () => '上传')
          : null,
      ].filter(Boolean)),
    },
  ]
})
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
            to="/social-media/projects"
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

      <ClientOnly>
        <div v-if="project" class="flex items-center gap-3">
          <UButton
            icon="i-heroicons-plus"
            :to="`/social-media/tasks/create?project_id=${projectId}`"
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
            删除
          </UButton>
        </div>
      </ClientOnly>
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
          <ClientOnly>
            <div class="flex items-center gap-2">
              <div class="text-xs text-gray-500 dark:text-gray-400">
                已选 {{ selectedTaskIds.length }} 个
              </div>
              <UButton
                size="sm"
                icon="i-heroicons-sparkles"
                :disabled="!selectedTaskIds.length"
                :loading="generatingSnapshot"
                @click="openSnapshotModal"
              >
                生成快照
              </UButton>
            </div>
          </ClientOnly>
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
            :to="`/social-media/tasks/create?project_id=${projectId}`"
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

    <!-- 项目快照列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            项目快照 (<ClientOnly fallback="...">{{ snapshots.length }}</ClientOnly>)
          </h2>
          <ClientOnly>
            <UButton
              size="sm"
              variant="ghost"
              icon="i-heroicons-arrow-path"
              :loading="snapshotsLoading"
              @click="handleRefreshSnapshots"
            >
              刷新
            </UButton>
          </ClientOnly>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载快照中...
            </p>
          </div>
        </template>

        <div v-if="snapshotsLoading" class="text-sm text-gray-400">
          加载中...
        </div>
        <div v-else-if="!snapshots.length" class="text-sm text-gray-400">
          暂无快照（可在上方勾选任务后生成）
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="s in snapshots"
            :key="s.id"
            class="p-4 rounded border border-gray-200 dark:border-gray-800"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ s.name || `快照 ${s.id}` }}
                  <span class="ml-1 text-xs text-gray-400 font-normal">#{{ s.id }}</span>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {{ new Date(s.created_at).toLocaleString('zh-CN') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  包含任务 ({{ (s.included_task_ids || []).length }})：
                  <span class="font-mono">{{ (s.included_task_ids || []).join(', ') || '-' }}</span>
                </div>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <UButton
                  size="xs"
                  variant="ghost"
                  icon="i-heroicons-eye"
                  :to="`/social-media/projects/${projectId}/analysis?snapshot_id=${s.id}`"
                >
                  查看
                </UButton>
                <UButton
                  size="xs"
                  variant="ghost"
                  color="error"
                  icon="i-heroicons-trash"
                  :loading="deletingSnapshotId === s.id"
                  @click="handleDeleteSnapshot(s.id)"
                >
                  删除
                </UButton>
              </div>
            </div>
          </div>
        </div>
      </ClientOnly>
    </UCard>

    <!-- 生成快照弹窗 -->
    <UModal v-model:open="showSnapshotModal">
      <template #content>
        <div class="p-6 space-y-4">
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
            生成项目快照
          </h3>
          <p class="text-sm text-gray-600 dark:text-gray-400">
            将基于已选 {{ selectedTaskIds.length }} 个任务（ID: {{ selectedTaskIds.join(', ') }}）生成一份项目级合并分析快照。
          </p>
          <UFormField label="快照名称（可选）">
            <UInput
              v-model="snapshotNameInput"
              placeholder="输入快照名称"
              class="w-full"
            />
          </UFormField>
          <div class="flex justify-end gap-3 pt-2">
            <UButton
              variant="outline"
              @click="showSnapshotModal = false"
            >
              取消
            </UButton>
            <UButton
              :loading="generatingSnapshot"
              @click="handleGenerateSnapshot"
            >
              开始生成
            </UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>
