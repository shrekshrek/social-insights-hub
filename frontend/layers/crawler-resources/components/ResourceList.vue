<template>
  <div class="space-y-4">
    <ClientOnly>
      <template #fallback>
        <div class="space-y-2">
          <div class="h-10 rounded bg-gray-100 animate-pulse" />
          <div class="flex justify-between">
            <div class="h-4 w-32 rounded bg-gray-100 animate-pulse" />
            <div class="h-8 w-48 rounded bg-gray-100 animate-pulse" />
          </div>
        </div>
      </template>

      <UTable :data="tableRows" :columns="columns" :loading="loading">
        <template #actions-cell="{ row }">
          <div v-if="props.type === 'account'" class="flex items-center gap-1">
            <UTooltip text="编辑">
              <UButton
                icon="i-heroicons-pencil-square"
                size="xs"
                variant="outline"
                @click="emit('edit', row.original)"
              />
            </UTooltip>
            <UTooltip :text="row.original.is_active ? '禁用' : '启用'">
              <UButton
                :icon="row.original.is_active ? 'i-heroicons-pause' : 'i-heroicons-play'"
                size="xs"
                variant="ghost"
                color="warning"
                @click="emit('toggle', row.original)"
              />
            </UTooltip>
          </div>
          <div v-else class="flex items-center gap-1">
            <UTooltip text="编辑">
              <UButton
                icon="i-heroicons-pencil-square"
                size="xs"
                variant="outline"
                @click="emit('edit', row.original)"
              />
            </UTooltip>
            <UTooltip :text="row.original.is_active ? '禁用' : '启用'">
              <UButton
                :icon="row.original.is_active ? 'i-heroicons-pause' : 'i-heroicons-play'"
                size="xs"
                variant="ghost"
                color="warning"
                @click="emit('toggle', row.original)"
              />
            </UTooltip>
            <UTooltip text="刷新代理池">
              <UButton
                icon="i-heroicons-arrow-path"
                size="xs"
                variant="outline"
                color="primary"
                @click="emit('refresh', row.original)"
              />
            </UTooltip>
          </div>
        </template>
      </UTable>

      <slot name="footer" :meta="props.meta" :total="total" :range-start="rangeStart" :range-end="rangeEnd">
        <div class="flex flex-wrap items-center justify-between gap-3 text-sm text-gray-500 mt-3">
          <span>
            <template v-if="total > 0">
              显示 {{ rangeStart }}-{{ rangeEnd }} 共 {{ total }} 条记录
            </template>
            <template v-else>
              暂无数据
            </template>
          </span>
          <UPagination
            v-model:page="page"
            :total="total"
            :items-per-page="pageSize"
            :disabled="total === 0"
            :sibling-count="1"
            show-first
            show-last
            show-edges
          />
        </div>
      </slot>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PropType } from 'vue'
import type { AccountResource, ProxyProvider } from '../types'

const props = defineProps({
  type: {
    type: String as PropType<'account' | 'provider'>,
    required: true,
  },
  meta: {
    type: Array as PropType<Array<Record<string, unknown>>>,
    default: () => [],
  },
  items: {
    type: Array as PropType<(AccountResource | ProxyProvider)[]>,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  pageSize: {
    type: Number,
    default: 10,
  },
})

const emit = defineEmits<{
  edit: [item: AccountResource | ProxyProvider]
  toggle: [item: AccountResource | ProxyProvider]
  refresh: [item: ProxyProvider]
}>()

const page = ref(1)

watch(
  () => props.items,
  () => {
    page.value = 1
  },
  { deep: true },
)

watch(
  () => props.items.length,
  (length) => {
    if (length === 0) {
      page.value = 1
      return
    }
    const maxPage = Math.max(1, Math.ceil(length / props.pageSize))
    if (page.value > maxPage) {
      page.value = maxPage
    }
  },
)

const columns = computed(() => {
  if (props.type === 'account') {
    return [
      { accessorKey: 'account_name', header: '账号' },
      { accessorKey: 'platform', header: '平台' },
      { accessorKey: 'status_text', header: '状态' },
      { accessorKey: 'failure_count', header: '失败次数' },
      { accessorKey: 'last_used_display', header: '最近使用' },
      { id: 'actions', header: '操作', cell: () => '' },
    ]
  }
  return [
    { accessorKey: 'name', header: '名称' },
    { accessorKey: 'provider_type', header: '类型' },
    { accessorKey: 'pool_size', header: '池容量' },
    { accessorKey: 'status_text', header: '状态' },
    { accessorKey: 'last_synced_display', header: '最近同步' },
    { id: 'actions', header: '操作', cell: () => '' },
  ]
})

const total = computed(() => props.items.length)

const paginatedItems = computed(() => {
  const start = (page.value - 1) * props.pageSize
  return props.items.slice(start, start + props.pageSize)
})

const tableRows = computed(() =>
  paginatedItems.value.map((item) => {
    if (props.type === 'account') {
      const account = item as AccountResource
      return {
        ...account,
        status_text: account.is_active ? '启用' : '停用',
        last_used_display: formatDate(account.last_used_at),
      }
    }
    const provider = item as ProxyProvider
    return {
      ...provider,
      status_text: provider.is_active ? '启用' : '禁用',
      last_synced_display: formatDate(provider.last_synced_at),
    }
  }),
)

const rangeStart = computed(() => {
  if (total.value === 0) {
    return 0
  }
  return (page.value - 1) * props.pageSize + 1
})

const rangeEnd = computed(() => {
  if (total.value === 0) {
    return 0
  }
  return Math.min(page.value * props.pageSize, total.value)
})

const formatDate = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) {
    return value
  }
  return date.toLocaleString()
}
</script>
