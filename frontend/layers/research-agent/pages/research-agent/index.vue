<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          专题研究
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          Agentic 搜索分析，自动搜集行业报告并生成结构化研究结论
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton icon="i-heroicons-plus" to="/research-agent/create">
          新建研究
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

    <!-- 任务列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-lg font-semibold">研究任务</h2>
          <div class="flex items-center gap-3">
            <UInput
              v-model="searchQuery"
              placeholder="搜索研究主题..."
              icon="i-heroicons-magnifying-glass"
              class="w-60"
            />
            <USelect
              v-model="selectedStatus"
              :items="statusOptions"
              value-key="value"
              placeholder="状态"
              class="w-32"
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
              共 {{ total }} 条记录
            </div>
            <UPagination
              v-model:page="currentPage"
              :total="total"
              :items-per-page="PAGE_SIZE"
              :sibling-count="2"
              show-first
              show-last
              show-edges
              :disabled="total === 0"
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { h, ref, computed, watch, type Component } from 'vue'
import type { ResearchTask } from '../../types'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton } from '#components'

definePageMeta({ layout: 'default' })
useHead({ title: '专题研究' })

const PAGE_SIZE = 10

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { getTasks, rerunTask, deleteTask, statusLabel, statusColor } = useResearchAgent()

const searchQuery = ref('')
const selectedStatus = ref('all')
const refreshing = ref(false)

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '等待中', value: 'pending' },
  { label: '研究中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]

const currentPage = computed({
  get: () => parseInt(route.query.page as string) || 1,
  set: (value: number) => {
    router.push({ query: { ...route.query, page: value.toString() } })
  },
})

const apiParams = computed(() => ({
  page: currentPage.value,
  page_size: PAGE_SIZE,
  status: selectedStatus.value === 'all' ? undefined : selectedStatus.value,
  search: searchQuery.value || undefined,
}))

const { data: listData, pending, refresh } = getTasks(apiParams)

const loading = computed(() => pending.value || refreshing.value)
const tasks = computed(() => listData.value?.items ?? [])
const total = computed(() => listData.value?.total ?? 0)

watch(searchQuery, () => {
  if (currentPage.value !== 1) currentPage.value = 1
})

watch(selectedStatus, () => {
  if (currentPage.value !== 1) currentPage.value = 1
})

const handleRefresh = async () => {
  refreshing.value = true
  try {
    await refresh()
  } finally {
    refreshing.value = false
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const columns: TableColumn<ResearchTask>[] = [
  {
    id: 'title',
    header: '研究主题',
    meta: { class: { th: 'w-[300px]', td: 'w-[300px] whitespace-normal' } },
    cell: ({ row }) => {
      const displayTitle = row.original.title || row.original.analysis_goal
      return h(
        UButton as Component,
        {
          variant: 'link',
          to: `/research-agent/${row.original.id}`,
          class: 'p-0 font-medium text-left whitespace-normal leading-snug line-clamp-2',
        },
        () => displayTitle,
      )
    },
  },
  {
    accessorKey: 'status',
    header: '状态',
    meta: { class: { th: 'w-[80px]', td: 'w-[80px]' } },
    cell: ({ row }) => {
      const status = row.getValue('status') as string
      return h(
        UBadge as Component,
        { color: statusColor(status), variant: 'subtle', size: 'sm' },
        () => statusLabel(status),
      )
    },
  },
  {
    id: 'stats',
    header: '来源',
    meta: { class: { th: 'w-[80px]', td: 'w-[80px]' } },
    cell: ({ row }) => {
      const stats = row.original.stats
      if (!stats) return h('span', { class: 'text-sm text-gray-400' }, '-')
      return h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, `${stats.documents_analyzed} 篇`)
    },
  },
  {
    accessorKey: 'created_at',
    header: '创建时间',
    meta: { class: { th: 'w-[120px]', td: 'w-[120px] whitespace-nowrap' } },
    cell: ({ row }) => {
      return h('span', { class: 'text-sm text-gray-500 dark:text-gray-400' }, formatDate(row.getValue('created_at')))
    },
  },
  {
    id: 'actions',
    header: '操作',
    meta: { class: { th: 'w-[140px]', td: 'w-[140px]' } },
    cell: ({ row }) => {
      return h('div', { class: 'flex items-center gap-2' }, [
        h(UButton as Component, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-eye',
          to: `/research-agent/${row.original.id}`,
        }, () => '查看'),
        h(UButton as Component, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-arrow-path',
          disabled: row.original.status === 'pending' || row.original.status === 'running',
          onClick: () => handleRerun(row.original),
        }, () => '重跑'),
        h(UButton as Component, {
          size: 'xs',
          variant: 'ghost',
          color: 'error',
          icon: 'i-heroicons-trash',
          onClick: () => handleDelete(row.original),
        }, () => '删除'),
      ])
    },
  },
]

async function handleRerun(task: ResearchTask) {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '确认重新研究',
    message: `将清空当前结果并重新执行研究，此操作不可撤销。确定继续？`,
    confirmText: '重新研究',
    type: 'warning',
  })
  if (!confirmed) return
  try {
    await rerunTask(task.id)
    toast.add({ title: '已重新发起研究，请等待执行完成', color: 'success' })
    await refresh()
  } catch {
    // 错误已由 apiRequest 统一处理
  }
}

async function handleDelete(task: ResearchTask) {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '确认删除',
    message: `确定要删除研究任务「${task.title || task.analysis_goal}」吗？此操作不可撤销。`,
    confirmText: '删除',
    type: 'error',
  })
  if (!confirmed) return
  try {
    await deleteTask(task.id)
    toast.add({ title: '删除成功', color: 'success' })
    await refresh()
  } catch {
    // 错误已由 apiRequest 统一处理
  }
}
</script>
