<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          策略研究
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          基于社交洞察数据的品牌策略生成
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton icon="i-heroicons-plus" to="/strategies/create">
          新建策略
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

    <!-- 策略列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">策略列表</h2>
          <UInput
            v-model="searchQuery"
            placeholder="搜索策略名称..."
            icon="i-heroicons-magnifying-glass"
            class="w-64"
          />
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载策略列表中...</p>
          </div>
        </template>

        <UTable
          :data="displayItems"
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
import { h, ref, computed, watch, type Component } from 'vue'
import type { StrategyListItem, StrategyStatus } from '../../types'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton } from '#components'
import { STATUS_MAP, formatDate } from '../../composables/useStrategyConstants'

definePageMeta({
  title: '策略管理',
  description: '品牌策略生成与管理',
})

const DEFAULT_PAGE_SIZE = 10

const route = useRoute()
const router = useRouter()

const searchQuery = ref('')
const refreshing = ref(false)

const currentPage = computed({
  get: () => parseInt(route.query.page as string) || 1,
  set: (value: number) => {
    router.push({
      query: { ...route.query, page: value.toString() },
    })
  },
})

const pageSize = ref(DEFAULT_PAGE_SIZE)

const strategiesApi = useStrategies()

const apiParams = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
}))

const {
  data: listData,
  pending,
  refresh,
} = strategiesApi.getStrategies(apiParams)

const loading = computed(() => pending.value || refreshing.value)
const displayItems = computed(() => listData.value?.items || [])
const total = computed(() => listData.value?.total || 0)

watch(searchQuery, () => {
  if (currentPage.value !== 1) {
    currentPage.value = 1
  }
})

const handleRefresh = async () => {
  refreshing.value = true
  try {
    await refresh()
  } finally {
    refreshing.value = false
  }
}


const columns: TableColumn<StrategyListItem>[] = [
  {
    accessorKey: 'name',
    header: '策略名称',
    cell: ({ row }) => {
      return h(
        UButton as Component,
        {
          variant: 'link',
          to: `/strategies/${row.original.id}`,
          class: 'font-medium',
        },
        () => row.getValue('name')
      )
    },
  },
  {
    accessorKey: 'status',
    header: '状态',
    cell: ({ row }) => {
      const status = row.getValue('status') as StrategyStatus
      const info = STATUS_MAP[status] || { label: status, color: 'neutral' as const }
      return h(
        UBadge as Component,
        { color: info.color, variant: 'soft', size: 'sm' },
        () => info.label
      )
    },
  },
  {
    accessorKey: 'slice_count',
    header: '关联切片',
    cell: ({ row }) => {
      return h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, `${row.getValue('slice_count')} 个`)
    },
  },
  {
    accessorKey: 'creator_name',
    header: '创建人',
  },
  {
    accessorKey: 'created_at',
    header: '创建时间',
    cell: ({ row }) => {
      return h(
        'span',
        { class: 'text-sm text-gray-500 dark:text-gray-400' },
        formatDate(row.getValue('created_at'))
      )
    },
  },
  {
    id: 'actions',
    header: '操作',
    cell: ({ row }) => {
      return h('div', { class: 'flex items-center gap-2' }, [
        h(UButton as Component, {
          color: 'neutral',
          variant: 'ghost',
          size: 'sm',
          icon: 'i-heroicons-eye',
          to: `/strategies/${row.original.id}`,
        }),
        h(UButton as Component, {
          color: 'error',
          variant: 'ghost',
          size: 'sm',
          icon: 'i-heroicons-trash',
          onClick: () => confirmDelete(row.original),
        }),
      ])
    },
  },
]

const confirmDelete = async (item: StrategyListItem) => {
  try {
    const { $confirm } = useNuxtApp()
    const confirmed = await $confirm(`确定要删除策略「${item.name}」吗？`)
    if (!confirmed) return

    await strategiesApi.deleteStrategy(item.id)
    await handleRefresh()
  } catch {
    // 错误已由 useApi 自动处理
  }
}
</script>
