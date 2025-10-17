<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">爬虫任务</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">管理和监控所有爬虫任务</p>
      </div>

      <div class="flex items-center gap-3">
        <UButton icon="i-heroicons-plus" @click="navigateTo('/crawler-tasks/create')">
          创建任务
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

    <!-- 任务列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-lg font-semibold">任务列表</h2>
          <div class="flex items-center gap-3">
            <USelect
              v-model="filters.platform"
              :items="platformOptions"
              placeholder="全部平台"
              clearable
              class="w-40"
            />
            <USelect
              v-model="filters.status"
              :items="statusOptions"
              placeholder="全部状态"
              clearable
              class="w-40"
            />
            <UInput
              v-model="searchQuery"
              placeholder="搜索任务名称..."
              icon="i-heroicons-magnifying-glass"
              class="w-60"
            />
          </div>
        </div>
      </template>

      <!-- 任务表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载任务列表中...</p>
          </div>
        </template>

        <UTable
          :data="paginatedTasks"
          :columns="columns"
          :loading="loading"
          class="w-full"
        />
      </ClientOnly>

      <!-- 分页 -->
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
import { h, ref, computed, watch, resolveComponent } from 'vue'
import {
  TaskStatus,
  PLATFORM_LABELS,
  TASK_STATUS_LABELS,
  TASK_STATUS_COLORS,
  CRAWLER_TYPE_LABELS,
  type PlatformType,
  type CrawlerTask
} from '../../types'
import { usePlatformOptionsWithAll } from '../../composables/usePlatformOptions'
type TaskCellContext = {
  row: {
    getValue: (accessorKey: string) => unknown
    original: CrawlerTask
  }
}
type TableColumnConfig = {
  accessorKey?: string
  id?: string
  header?: string
  cell?: (ctx: TaskCellContext) => ReturnType<typeof h> | ReturnType<typeof h>[]
}

definePageMeta({
  title: '爬虫任务',
  description: '管理和监控所有爬虫任务'
})

// 常量定义
const DEFAULT_PAGE_SIZE = 20

// 路由和查询参数
const route = useRoute()
const router = useRouter()

// 响应式数据
const searchQuery = ref('')
const refreshing = ref(false)
const filters = reactive({
  platform: undefined as PlatformType | undefined,
  status: undefined as TaskStatus | undefined
})

// 从 URL 查询参数获取当前页码
const currentPage = computed({
  get: () => parseInt(route.query.page as string) || 1,
  set: (value: number) => {
    router.push({
      query: { ...route.query, page: value.toString() }
    })
  }
})

const pageSize = computed(() => parseInt(route.query.pageSize as string) || DEFAULT_PAGE_SIZE)

// API 调用
const crawlerTasksApi = useCrawlerTasksApi()
const { data: userData, pending, refresh } = await crawlerTasksApi.getTasks({
  page: currentPage.value,
  page_size: pageSize.value,
  ...(filters.platform && { platform: filters.platform }),
  ...(filters.status && { status: filters.status })
})

// 计算属性
const loading = computed(() => pending.value || refreshing.value)

// 计算属性 - 从API数据中获取显示内容
const displayTasks = computed(() => {
  const items = userData.value?.items || []

  // 如果有搜索查询，过滤数据
  if (!searchQuery.value) {
    return items
  }

  const query = searchQuery.value.toLowerCase()
  return items.filter((task) =>
    task.name.toLowerCase().includes(query)
  )
})

// 分页相关计算属性
const total = computed(() => userData.value?.total || 0)

// 分页数据
const paginatedTasks = computed(() => {
  // 如果有搜索，使用客户端分页
  if (searchQuery.value) {
    const start = (currentPage.value - 1) * pageSize.value
    const end = start + pageSize.value
    return displayTasks.value.slice(start, end)
  }
  // 否则直接使用服务端分页的数据
  return displayTasks.value
})

// 下拉选项
const platformOptions = usePlatformOptionsWithAll()

const statusOptions = computed(() =>
  Object.entries(TASK_STATUS_LABELS).map(([key, label]) => ({
    value: TaskStatus[key as keyof typeof TaskStatus],
    label
  }))
)

// 当搜索查询或筛选变化时，重置到第一页
watch([searchQuery, () => filters.platform, () => filters.status], () => {
  if (currentPage.value !== 1) {
    currentPage.value = 1
  }
  refresh()
})

// 刷新数据
const handleRefresh = async () => {
  refreshing.value = true
  try {
    await refresh()
  } finally {
    refreshing.value = false
  }
}

// 工具函数
const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 表格列配置
const columns: TableColumnConfig[] = [
  {
    accessorKey: 'name',
    header: '任务名称',
    cell: ({ row }: TaskCellContext) => {
      const name = row.getValue('name') as string
      const task = row.original
      const UBadge = resolveComponent('UBadge')

      return h('div', { class: 'flex flex-col space-y-2' }, [
        h('div', { class: 'flex items-center gap-2' }, [
          h('span', { class: 'font-medium text-gray-900 dark:text-white' }, name),
          h(UBadge, {
            color: TASK_STATUS_COLORS[task.status],
            variant: 'subtle',
            size: 'xs'
          }, () => TASK_STATUS_LABELS[task.status])
        ]),
        h('div', { class: 'flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400' }, [
          h('span', {}, PLATFORM_LABELS[task.platform]),
          h('span', {}, '·'),
          h('span', {}, CRAWLER_TYPE_LABELS[task.crawler_type])
        ])
      ])
    }
  },
  {
    accessorKey: 'progress',
    header: '进度',
    cell: ({ row }: TaskCellContext) => {
      const progress = row.getValue('progress') as number
      const crawledCount = row.original.crawled_count

      return h('div', { class: 'flex flex-col space-y-1 w-32' }, [
        h('div', { class: 'flex items-center justify-between text-sm' }, [
          h('span', { class: 'text-gray-600 dark:text-gray-400' }, `${progress}%`),
          h('span', { class: 'text-gray-500 dark:text-gray-500' }, `${crawledCount}条`)
        ]),
        h('div', { class: 'h-1.5 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden' }, [
          h('div', {
            class: 'h-full bg-blue-500 transition-all',
            style: { width: `${progress}%` }
          })
        ])
      ])
    }
  },
  {
    accessorKey: 'created_at',
    header: '创建时间',
    cell: ({ row }: TaskCellContext) => {
      return h(
        'span',
        { class: 'text-sm text-gray-500 dark:text-gray-400' },
        formatDate(row.getValue('created_at') as string)
      )
    }
  },
  {
    id: 'actions',
    header: '操作',
    cell: ({ row }: TaskCellContext) => {
      const UButton = resolveComponent('UButton')
      const task = row.original

      const buttons = []

      // 根据任务状态显示不同按钮
      if (task.status === 'pending' || task.status === 'paused') {
        buttons.push(
          h(UButton, {
            color: 'green',
            variant: 'ghost',
            size: 'sm',
            icon: 'i-heroicons-play',
            onClick: async () => {
              await crawlerTasksApi.startTask(task.id)
              await refresh()
            }
          })
        )
      }

      if (task.status === 'running') {
        buttons.push(
          h(UButton, {
            color: 'yellow',
            variant: 'ghost',
            size: 'sm',
            icon: 'i-heroicons-pause',
            onClick: async () => {
              await crawlerTasksApi.pauseTask(task.id)
              await refresh()
            }
          })
        )
      }

      if (task.status === 'running' || task.status === 'paused') {
        buttons.push(
          h(UButton, {
            color: 'error',
            variant: 'ghost',
            size: 'sm',
            icon: 'i-heroicons-stop',
            onClick: async () => {
              const { $confirm } = useNuxtApp()
              const confirmed = await $confirm(`确定要停止任务 "${task.name}" 吗？`)
              if (!confirmed) return

              await crawlerTasksApi.stopTask(task.id)
              await refresh()
            }
          })
        )
      }

      // 查看按钮
      buttons.push(
        h(UButton, {
          color: 'neutral',
          variant: 'ghost',
          size: 'sm',
          icon: 'i-heroicons-eye',
          onClick: () => navigateTo(`/crawler-tasks/${task.id}`)
        })
      )

      return h('div', { class: 'flex items-center gap-1' }, buttons)
    }
  }
]
</script>
