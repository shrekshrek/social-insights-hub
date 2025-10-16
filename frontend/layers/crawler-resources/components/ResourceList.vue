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
        <template #actions-data="{ row }">
          <div class="flex items-center gap-2">
            <UButton
              icon="i-heroicons-pencil-square"
              size="xs"
              variant="outline"
              @click="emit('edit', row.__raw)"
            />
            <UButton
              v-if="props.type === 'account'"
              :icon="row.is_active ? 'i-heroicons-pause' : 'i-heroicons-play'"
              size="xs"
              variant="ghost"
              color="warning"
              @click="emit('toggle', row.__raw)"
            />
            <template v-else>
              <UButton
                :icon="row.is_active ? 'i-heroicons-pause' : 'i-heroicons-play'"
                size="xs"
                variant="ghost"
                color="warning"
                @click="emit('toggle', row.__raw)"
              />
              <UButton
                icon="i-heroicons-arrow-path"
                size="xs"
                variant="ghost"
                @click="emit('refresh', row.__raw)"
              />
            </template>
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
      { key: 'account_name', id: 'account_name', label: '账号' },
      { key: 'platform', id: 'platform', label: '平台' },
      { key: 'status_text', id: 'status', label: '状态' },
      { key: 'failure_count', id: 'failure_count', label: '失败次数' },
      { key: 'last_used_display', id: 'last_used_at', label: '最近使用' },
      { key: 'actions', id: 'actions', label: '操作' },
    ]
  }
  return [
    { key: 'name', id: 'name', label: '名称' },
    { key: 'provider_type', id: 'provider_type', label: '类型' },
    { key: 'pool_size', id: 'pool_size', label: '池容量' },
    { key: 'status_text', id: 'status', label: '状态' },
    { key: 'last_synced_display', id: 'last_synced_at', label: '最近同步' },
    { key: 'actions', id: 'actions', label: '操作' },
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
        __raw: account,
        status_text: account.is_active ? '启用' : '停用',
        last_used_display: formatDate(account.last_used_at),
      }
    }
    const provider = item as ProxyProvider
    return {
      ...provider,
      __raw: provider,
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
