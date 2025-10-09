<template>
  <UCard>
    <template #header>
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold">
          {{ type === 'account' ? '账号列表' : '代理列表' }} ({{ items.length }})
        </h2>
        <UButton
          icon="i-heroicons-arrow-path"
          variant="ghost"
          :loading="loading"
          @click="emit('refresh')"
        >刷新</UButton>
      </div>
    </template>

    <UTable :rows="items" :columns="columns" :loading="loading">
      <template #status-data="{ row }">
        <UBadge :color="row.is_active ? 'green' : 'gray'">
          {{ row.is_active ? '启用' : '停用' }}
        </UBadge>
      </template>
      <template #failure_count-data="{ row }">
        <span :class="row.failure_count > 0 ? 'text-red-500 font-medium' : 'text-gray-600'">
          {{ row.failure_count }}
        </span>
      </template>
      <template #last_used_at-data="{ row }">
        <span>{{ formatDate(row.last_used_at) }}</span>
      </template>
      <template #actions-data="{ row }">
        <div class="flex items-center gap-2">
          <UButton
            icon="i-heroicons-pencil-square"
            size="xs"
            variant="outline"
            @click="emit('edit', row)"
          />
          <UButton
            :icon="row.is_active ? 'i-heroicons-pause' : 'i-heroicons-play'"
            size="xs"
            variant="ghost"
            color="warning"
            @click="emit('toggle', row)"
          />
        </div>
      </template>
    </UTable>
  </UCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import type { AccountResource, ProxyResource } from '../types'

const props = defineProps({
  type: {
    type: String as PropType<'account' | 'proxy'>,
    required: true,
  },
  items: {
    type: Array as PropType<(AccountResource | ProxyResource)[]>,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits<{
  refresh: []
  edit: [item: AccountResource | ProxyResource]
  toggle: [item: AccountResource | ProxyResource]
}>()

const columns = computed(() => {
  if (props.type === 'account') {
    return [
      { key: 'account_name', id: 'account_name', label: '账号' },
      { key: 'platform', id: 'platform', label: '平台' },
      { key: 'status', id: 'status', label: '状态' },
      { key: 'failure_count', id: 'failure_count', label: '失败次数' },
      { key: 'last_used_at', id: 'last_used_at', label: '最近使用' },
      { key: 'actions', id: 'actions', label: '操作' },
    ]
  }
  return [
    { key: 'label', id: 'label', label: '标识' },
    { key: 'host', id: 'host', label: '地址', sortable: false },
    { key: 'protocol', id: 'protocol', label: '协议' },
    { key: 'status', id: 'status', label: '状态' },
    { key: 'failure_count', id: 'failure_count', label: '失败次数' },
    { key: 'last_used_at', id: 'last_used_at', label: '最近使用' },
    { key: 'actions', id: 'actions', label: '操作' },
  ]
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
