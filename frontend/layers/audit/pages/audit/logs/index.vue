<script setup lang="ts">
import { h, computed, ref, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge } from '#components'
import type { AuditLog, AuditAction, AuditResource } from '../../../types'

definePageMeta({
  layout: 'default',
})

const { getAuditLogs } = useAuditApi()

// 分页与筛选
const currentPage = ref(1)
const pageSize = ref(20)
const filterUserId = ref<number | undefined>()
const filterAction = ref<AuditAction | 'all'>('all')
const filterResource = ref<AuditResource | 'all'>('all')
const filterStartTime = ref<string | undefined>()
const filterEndTime = ref<string | undefined>()
const refreshing = ref(false)

const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  user_id: filterUserId.value,
  action: filterAction.value === 'all' ? undefined : filterAction.value,
  resource: filterResource.value === 'all' ? undefined : filterResource.value,
  start_time: filterStartTime.value,
  end_time: filterEndTime.value,
}))

const {
  data: logsData,
  pending: loading,
  refresh,
} = getAuditLogs(params)

const logs = computed(() => logsData.value?.items || [])
const total = computed(() => logsData.value?.total || 0)

const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

// 操作类型选项
const actionOptions = [
  { label: '全部类型', value: 'all' },
  { label: '登录成功', value: 'LOGIN' },
  { label: '登录失败', value: 'LOGIN_FAILED' },
  { label: '创建', value: 'CREATE' },
  { label: '更新', value: 'UPDATE' },
  { label: '删除', value: 'DELETE' },
  { label: '触发', value: 'TRIGGER' },
]

// 资源类型选项
const resourceOptions = [
  { label: '全部资源', value: 'all' },
  { label: '用户', value: 'user' },
  { label: '角色', value: 'role' },
  { label: '权限', value: 'permission' },
  { label: '社媒监测', value: 'social_monitor' },
  { label: '社媒采集', value: 'social_task' },
  { label: '社媒切片', value: 'social_slice' },
  { label: '新闻监测', value: 'news_monitor' },
  { label: '新闻采集', value: 'news_task' },
  { label: '新闻切片', value: 'news_slice' },
  { label: '策略研究', value: 'strategy' },
  { label: 'AI 分析', value: 'analysis_job' },
  { label: '知识库文档', value: 'kb_document' },
  { label: '专题研究', value: 'research_task' },
]

// 格式化函数
const formatDateTime = (value: string) => {
  const date = new Date(value)
  return isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const ACTION_LABELS: Record<string, string> = {
  LOGIN: '登录',
  LOGIN_FAILED: '登录失败',
  CREATE: '创建',
  UPDATE: '更新',
  DELETE: '删除',
  TRIGGER: '触发',
}

const ACTION_COLORS: Record<string, string> = {
  LOGIN: 'success',
  LOGIN_FAILED: 'error',
  CREATE: 'info',
  UPDATE: 'warning',
  DELETE: 'error',
  TRIGGER: 'primary',
}

const RESOURCE_LABELS: Record<string, string> = {
  user: '用户',
  role: '角色',
  permission: '权限',
  social_monitor: '社媒监测',
  social_task: '社媒采集',
  social_slice: '社媒切片',
  news_monitor: '新闻监测',
  news_task: '新闻采集',
  news_slice: '新闻切片',
  strategy: '策略',
  analysis_job: 'AI 分析',
  kb_document: '知识库',
  research_task: '专题研究',
}

// 组合展示名：优先 operation（route.summary），否则回退到 action + resource
const getDisplayOperation = (log: AuditLog): string => {
  if (log.operation) return log.operation
  const actionLabel = ACTION_LABELS[log.action] || log.action
  if (log.resource) {
    const resourceLabel = RESOURCE_LABELS[log.resource] || log.resource
    return `${actionLabel}${resourceLabel}`
  }
  return actionLabel
}

// 表格列定义
const columns = computed<TableColumn<AuditLog>[]>(() => {
  const Badge = UBadge as Component

  return [
    {
      accessorKey: 'created_at',
      header: '时间',
      cell: ({ row }) => h('span', {
        class: 'text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap font-mono',
      }, formatDateTime(row.original.created_at)),
    },
    {
      accessorKey: 'username',
      header: '操作用户',
      cell: ({ row }) => {
        const log = row.original
        return h('div', { class: 'text-sm' }, [
          h('span', { class: 'font-medium' }, log.username || '-'),
          log.user_id
            ? h('span', { class: 'text-xs text-gray-400 ml-1 font-mono' }, `#${log.user_id}`)
            : null,
        ])
      },
    },
    {
      accessorKey: 'action',
      header: '类型',
      meta: { class: { th: 'w-[80px]', td: 'w-[80px]' } },
      cell: ({ row }) => h(Badge, {
        color: ACTION_COLORS[row.original.action] || 'neutral',
        variant: 'subtle',
        size: 'sm',
      }, () => ACTION_LABELS[row.original.action] || row.original.action),
    },
    {
      accessorKey: 'operation',
      header: '操作',
      cell: ({ row }) => {
        const log = row.original
        return h('div', { class: 'text-sm' }, [
          h('span', { class: 'font-medium' }, getDisplayOperation(log)),
          log.resource_id
            ? h('span', { class: 'text-xs text-gray-400 ml-1 font-mono' }, `#${log.resource_id}`)
            : null,
        ])
      },
    },
    {
      accessorKey: 'status_code',
      header: '状态',
      meta: { class: { th: 'w-[64px]', td: 'w-[64px]' } },
      cell: ({ row }) => {
        const code = row.original.status_code
        if (!code) return h('span', { class: 'text-gray-400' }, '-')
        const isError = code >= 400
        return h(Badge, {
          color: isError ? 'error' : 'success',
          variant: 'outline',
          size: 'sm',
        }, () => String(code))
      },
    },
    {
      accessorKey: 'ip_address',
      header: 'IP',
      cell: ({ row }) => h('span', {
        class: 'text-xs text-gray-500 font-mono',
      }, row.original.ip_address || '-'),
    },
    {
      accessorKey: 'request_path',
      header: '请求路径',
      meta: { class: { th: 'w-[260px]', td: 'w-[260px]' } },
      cell: ({ row }) => h('span', {
        class: 'text-xs text-gray-500 font-mono truncate block max-w-[260px]',
        title: row.original.request_path || '',
      }, row.original.request_path || '-'),
    },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          操作日志
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          记录所有用户的写操作和认证事件
        </p>
      </div>

      <UButton
        variant="ghost"
        icon="i-heroicons-arrow-path"
        :loading="refreshing"
        @click="handleRefresh"
      >
        刷新
      </UButton>
    </div>

    <!-- 日志列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-4 flex-wrap">
          <h2 class="text-lg font-semibold">
            审计记录
          </h2>

          <div class="flex items-center gap-3 flex-wrap">
            <UInput
              v-model.number="filterUserId"
              type="number"
              placeholder="用户ID"
              class="w-24"
            />

            <USelect
              v-model="filterAction"
              :items="actionOptions"
              value-key="value"
              class="w-32"
            />

            <USelect
              v-model="filterResource"
              :items="resourceOptions"
              value-key="value"
              class="w-32"
            />

            <UInput
              v-model="filterStartTime"
              type="datetime-local"
              placeholder="开始时间"
              class="w-44"
            />

            <UInput
              v-model="filterEndTime"
              type="datetime-local"
              placeholder="结束时间"
              class="w-44"
            />
          </div>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8 text-gray-600 dark:text-gray-400">
            加载中...
          </div>
        </template>

        <UTable
          :data="logs"
          :columns="columns"
          :loading="loading"
          class="w-full"
        >
          <template #empty-state>
            <div class="text-center py-10 text-gray-500">
              <UIcon name="i-heroicons-clipboard-document-list" class="w-10 h-10 mx-auto mb-2 opacity-60" />
              <p class="text-sm">暂无操作记录</p>
            </div>
          </template>
        </UTable>
      </ClientOnly>

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
              show-first
              show-last
              show-edges
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>
