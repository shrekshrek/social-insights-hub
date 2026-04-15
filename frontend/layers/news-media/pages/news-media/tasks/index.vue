<script setup lang="ts">
import { h, ref, computed, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UButton, UBadge } from '#components'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: 'default',
})

const { getAllTasks, deleteTask } = useNewsTasks()
const { currentUserId, hasPermission } = usePermissions()

const currentPage = ref(1)
const pageSize = ref(10)
const searchQuery = ref('')
const statusFilter = ref('all')
const phaseFilter = ref('all')
const refreshing = ref(false)

const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
  ...(statusFilter.value !== 'all' ? { status: statusFilter.value } : {}),
  ...(phaseFilter.value !== 'all' ? { phase: phaseFilter.value } : {}),
}))

const { data: tasksData, pending: loading, refresh } = getAllTasks(params)

const tasks = computed(() => tasksData.value?.items || [])
const total = computed(() => tasksData.value?.total || 0)

const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

const handleDelete = async (task: NewsTaskWithRelations) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除任务',
    message: `确定要删除任务 "${task.name}" 吗？所有相关文章数据也将被删除。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  try {
    await deleteTask(task.id)
    await handleRefresh()
  } catch {
    // error handled by apiRequest
  }
}

const getStatusColor = (status: string) => {
  const map: Record<string, string> = {
    pending: 'neutral',
    running: 'info',
    completed: 'success',
    failed: 'error',
  }
  return map[status] || 'neutral'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

const getPhaseText = (phase: string | null) => {
  const map: Record<string, string> = { probe: '探测', collect: '全量' }
  return map[phase || ''] || phase || '-'
}

const getPhaseColor = (phase: string | null) => {
  const map: Record<string, string> = { probe: 'info', collect: 'warning' }
  return map[phase || ''] || 'neutral'
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const columns = computed<TableColumn<NewsTaskWithRelations>[]>(() => {
  const Button = UButton as Component
  const Badge = UBadge as Component

  return [
    {
      accessorKey: 'id',
      header: 'ID',
      meta: { class: { th: 'w-12', td: 'w-12' } },
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'name',
      header: '任务名称',
      meta: { class: { th: 'w-[130px]', td: 'w-[130px] whitespace-normal' } },
      cell: ({ row }) =>
        h('div', { class: 'font-medium leading-snug line-clamp-2', title: row.original.name }, row.original.name),
    },
    {
      accessorKey: 'keywords',
      header: '关键词',
      meta: { class: { th: 'w-[130px]', td: 'w-[130px] whitespace-normal' } },
      cell: ({ row }) =>
        h('div', { class: 'text-sm text-gray-600 dark:text-gray-400 leading-snug line-clamp-2', title: row.original.keywords || '' }, row.original.keywords || '-'),
    },
    {
      accessorKey: 'monitor_name',
      header: '所属项目',
      meta: { class: { th: 'w-[130px]', td: 'w-[130px] whitespace-normal' } },
      cell: ({ row }) => {
        if (!row.original.monitor_name || !row.original.monitor_id) {
          return h('span', { class: 'text-gray-400' }, '-')
        }
        return h(
          Button,
          {
            variant: 'link',
            size: 'xs',
            class: 'p-0 font-normal w-full text-left whitespace-normal leading-snug line-clamp-2',
            title: row.original.monitor_name,
            to: `/news-media/monitors/${row.original.monitor_id}`,
          },
          () => row.original.monitor_name,
        )
      },
    },
    {
      accessorKey: 'phase',
      header: '阶段',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) =>
        h(Badge, { color: getPhaseColor(row.original.phase), size: 'xs', variant: 'subtle' }, () =>
          getPhaseText(row.original.phase),
        ),
    },
    {
      accessorKey: 'status',
      header: '状态',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) =>
        h(Badge, { color: getStatusColor(row.original.status), size: 'xs', variant: 'solid' }, () =>
          getStatusText(row.original.status),
        ),
    },
    {
      accessorKey: 'articles_count',
      header: '采集量',
      meta: { class: { th: 'w-[70px]', td: 'w-[70px]' } },
      cell: ({ row }) =>
        h('span', { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' }, `${row.original.articles_count} 文章`),
    },
    {
      accessorKey: 'created_at',
      header: '创建时间',
      meta: { class: { th: 'w-[112px]', td: 'w-[112px]' } },
      cell: ({ row }) =>
        h('span', { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' }, formatDate(row.original.created_at)),
    },
    {
      accessorKey: 'actions',
      header: '操作',
      meta: { class: { th: 'w-[120px]', td: 'w-[120px]' } },
      cell: ({ row }) =>
        h('div', { class: 'flex items-center gap-1' }, [
          h(
            Button,
            {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-eye',
              to: `/news-media/tasks/${row.original.id}`,
            },
            () => '查看',
          ),
          (hasPermission(PERMISSIONS.NEWS_TASK_DELETE) || row.original.user_id === currentUserId.value)
            ? h(Button, {
                size: 'xs',
                variant: 'ghost',
                icon: 'i-heroicons-trash',
                color: 'error',
                onClick: () => handleDelete(row.original),
              }, () => '删除')
            : null,
        ]),
    },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          新闻采集
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理所有新闻数据采集任务
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          to="/news-media/tasks/create"
        >
          新建任务
        </UButton>
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </div>
    </div>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">任务列表</h2>
          <div class="flex items-center gap-3">
            <UInput
              v-model="searchQuery"
              placeholder="搜索任务名称..."
              icon="i-heroicons-magnifying-glass"
              class="w-60"
            />
            <USelect
              v-model="phaseFilter"
              :items="[
                { label: '全部阶段', value: 'all' },
                { label: '探测', value: 'probe' },
                { label: '全量', value: 'collect' },
              ]"
              value-key="value"
              class="w-28"
            />
            <USelect
              v-model="statusFilter"
              :items="[
                { label: '全部状态', value: 'all' },
                { label: '等待中', value: 'pending' },
                { label: '运行中', value: 'running' },
                { label: '已完成', value: 'completed' },
                { label: '失败', value: 'failed' },
              ]"
              value-key="value"
              class="w-28"
            />
          </div>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载任务列表中...</p>
          </div>
        </template>

        <UTable
          :data="tasks"
          :columns="columns"
          :loading="loading"
          class="w-full"
          :ui="{ base: 'w-full table-fixed' }"
        />
      </ClientOnly>

      <template #footer>
        <ClientOnly>
          <template #fallback>
            <div class="flex justify-between items-center">
              <div class="h-4 bg-gray-200 rounded w-32 animate-pulse" />
              <div class="h-8 bg-gray-200 rounded w-64 animate-pulse" />
            </div>
          </template>

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
