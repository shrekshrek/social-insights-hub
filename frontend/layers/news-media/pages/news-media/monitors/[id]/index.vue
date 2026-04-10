<script setup lang="ts">
import { h, ref, reactive, computed, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UButton, UBadge } from '#components'
import type { MonitorAggregatedStats } from '../../../../types'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const monitorId = Number(route.params.id)

const { getMonitor, deleteMonitor: deleteMonitorApi, getMonitorAggregated, runMonitorAggregate, addParticipant, removeParticipant, updateMonitor } = useNewsMonitors()
const { getTasks, deleteTask, executeTask } = useNewsTasks()
const { currentUserId } = usePermissions()

const { data: monitor, pending: monitorLoading, refresh: refreshMonitor } = getMonitor(monitorId)

const currentPage = ref(1)
const pageSize = ref(10)
const statusFilter = ref('all')

// phase 筛选：全部 / 探测 / 全量
const phaseFilter = ref<'all' | 'probe' | 'collect'>('all')
const phaseItems = [
  { label: '全部', value: 'all' },
  { label: '探测', value: 'probe' },
  { label: '全量', value: 'collect' },
]
const refreshing = ref(false)

const taskParams = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  ...(statusFilter.value !== 'all' ? { status: statusFilter.value } : {}),
  ...(phaseFilter.value !== 'all' ? { phase: phaseFilter.value } : {}),
}))

const { data: tasksData, pending: tasksLoading, refresh: refreshTasks } = getTasks(monitorId, taskParams)

const tasks = computed(() => tasksData.value?.items || [])
const totalTasks = computed(() => tasksData.value?.total || 0)

const handleRefresh = async () => {
  refreshing.value = true
  await refreshTasks()
  refreshing.value = false
}

// ========== 删除项目 ==========

const handleDeleteMonitor = async () => {
  if (!monitor.value) return
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除监测项目',
    message: `确定要删除 "${monitor.value.name}" 吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  try {
    await deleteMonitorApi(monitorId)
    await navigateTo('/news-media/monitors')
  } catch {
    // error already handled
  }
}

// ========== 编辑项目 ==========

const toast = useToast()
const showEditModal = ref(false)
const editSubmitting = ref(false)
const editState = reactive({
  name: '',
  description: '',
})

const openEditModal = () => {
  if (!monitor.value) return
  editState.name = monitor.value.name || ''
  editState.description = monitor.value.description || ''
  showEditModal.value = true
}

const handleUpdateMonitor = async () => {
  if (!editState.name.trim()) {
    toast.add({ title: '项目名称不能为空', color: 'warning' })
    return
  }
  editSubmitting.value = true
  try {
    await updateMonitor(monitorId, {
      name: editState.name.trim(),
      description: editState.description || null,
    })
    showEditModal.value = false
    await refreshMonitor()
  } catch {
    // error already handled
  } finally {
    editSubmitting.value = false
  }
}

// ========== 任务操作 ==========

const handleDeleteTask = async (task: NewsTaskWithRelations) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除任务',
    message: `确定要删除任务 "${task.name}" 吗？`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  try {
    await deleteTask(task.id)
    await handleRefresh()
  } catch {
    // error already handled
  }
}

const handleExecuteTask = async (task: NewsTaskWithRelations) => {
  try {
    await executeTask(task.id)
    await handleRefresh()
  } catch {
    // error already handled
  }
}

// ========== 统计聚合 ==========

const aggregatedStats = ref<MonitorAggregatedStats | null>(null)
const aggregatedLoading = ref(false)

const loadAggregated = async () => {
  aggregatedLoading.value = true
  try {
    aggregatedStats.value = await getMonitorAggregated(monitorId)
  } catch {
    // 无数据时静默失败
  } finally {
    aggregatedLoading.value = false
  }
}

onMounted(loadAggregated)

// ========== 叙事聚合 ==========

const narrativeResult = ref<Record<string, unknown> | null>(
  (monitor.value?.aggregated_result as Record<string, unknown> | undefined) ?? null
)
const narrativeLoading = ref(false)
const showNarrativePanel = ref(!!narrativeResult.value)

const handleRunNarrative = async () => {
  narrativeLoading.value = true
  try {
    const result = await runMonitorAggregate(monitorId, {
      analysis_goal: monitor.value?.name || '',
      subject: monitor.value?.name || '',
    })
    narrativeResult.value = result as Record<string, unknown>
    showNarrativePanel.value = true
  } catch {
    // error already handled
  } finally {
    narrativeLoading.value = false
  }
}

// ========== 辅助函数 ==========

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

// ========== 表格列 ==========

const taskColumns = computed<TableColumn<NewsTaskWithRelations>[]>(() => {
  const Button = UButton as Component
  const Badge = UBadge as Component

  return [
    {
      accessorKey: 'id',
      header: 'ID',
      meta: { class: { th: 'w-14', td: 'w-14' } },
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'name',
      header: '任务名称',
      meta: { class: { th: 'w-[160px]', td: 'w-[160px] whitespace-normal' } },
      cell: ({ row }) =>
        h('div', { class: 'font-medium leading-snug line-clamp-2', title: row.original.name }, row.original.name),
    },
    {
      accessorKey: 'keywords',
      header: '关键词',
      meta: { class: { th: 'w-[180px]', td: 'w-[180px] whitespace-normal' } },
      cell: ({ row }) =>
        h(
          'div',
          { class: 'text-sm text-gray-600 dark:text-gray-400 leading-snug line-clamp-2', title: row.original.keywords || '' },
          row.original.keywords || '-',
        ),
    },
    {
      accessorKey: 'phase',
      header: '阶段',
      meta: { class: { th: 'w-[70px]', td: 'w-[70px]' } },
      cell: ({ row }) =>
        h(Badge, { color: getPhaseColor(row.original.phase), size: 'xs', variant: 'subtle' }, () =>
          getPhaseText(row.original.phase),
        ),
    },
    {
      accessorKey: 'status',
      header: '状态',
      meta: { class: { th: 'w-[80px]', td: 'w-[80px]' } },
      cell: ({ row }) =>
        h(Badge, { color: getStatusColor(row.original.status), size: 'xs', variant: 'solid' }, () =>
          getStatusText(row.original.status),
        ),
    },
    {
      accessorKey: 'articles_count',
      header: '采集量',
      meta: { class: { th: 'w-[70px]', td: 'w-[70px]' } },
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, `${row.original.articles_count} 文章`),
    },
    {
      accessorKey: 'created_at',
      header: '创建时间',
      meta: { class: { th: 'w-[112px]', td: 'w-[112px]' } },
      cell: ({ row }) =>
        h(
          'span',
          { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' },
          formatDate(row.original.created_at),
        ),
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
              to: `/news-media/tasks/${row.original.id}?from=monitor&monitor_id=${monitorId}`,
            },
            () => '查看',
          ),
          row.original.status === 'pending'
            ? h(
                Button,
                {
                  size: 'xs',
                  variant: 'ghost',
                  icon: 'i-heroicons-play',
                  onClick: () => handleExecuteTask(row.original),
                },
                () => '执行',
              )
            : null,
          h(
            Button,
            {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-trash',
              color: 'error',
              onClick: () => handleDeleteTask(row.original),
            },
            () => '删除',
          ),
        ]),
    },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <div v-if="monitorLoading" class="text-center py-8">
      <p class="text-gray-500">加载中...</p>
    </div>

    <template v-else-if="monitor">
      <!-- 页面头部 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            to="/news-media/monitors"
          />
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            项目详情
          </h1>
        </div>

        <div class="flex items-center gap-3">
          <UButton
            color="error"
            variant="outline"
            icon="i-heroicons-trash"
            @click="handleDeleteMonitor"
          >
            删除项目
          </UButton>
        </div>
      </div>

      <!-- 项目信息 -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              项目信息
            </h2>
            <ClientOnly>
              <UButton
                v-if="monitor.owner_id === currentUserId"
                size="sm"
                variant="outline"
                icon="i-heroicons-pencil-square"
                @click="openEditModal"
              >
                编辑
              </UButton>
            </ClientOnly>
          </div>
        </template>

        <dl class="space-y-2 text-sm">
          <!-- 名称 -->
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
              项目名称
            </dt>
            <dd class="text-gray-900 dark:text-white font-medium">
              {{ monitor.name }}
            </dd>
          </div>

          <!-- 描述 -->
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
              项目描述
            </dt>
            <dd
              class="text-gray-900 dark:text-white line-clamp-2 flex-1"
              :title="monitor.description || undefined"
            >
              {{ monitor.description || '-' }}
            </dd>
          </div>

          <!-- 元信息（3 列） -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 pt-3 border-t border-gray-100 dark:border-gray-800">
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                创建者
              </dt>
              <dd class="text-gray-900 dark:text-white">
                {{ monitor.owner_username || '-' }}
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                创建时间
              </dt>
              <dd class="text-gray-900 dark:text-white">
                {{ formatDate(monitor.created_at) }}
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                任务数
              </dt>
              <dd class="text-gray-900 dark:text-white">
                {{ totalTasks }}
              </dd>
            </div>
          </div>

          <!-- 参与者（只读 chip 列表） -->
          <div class="flex gap-3 pt-3 border-t border-gray-100 dark:border-gray-800">
            <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400 pt-0.5">
              参与者
            </dt>
            <dd class="flex-1">
              <ClientOnly fallback="...">
                <div v-if="monitor.participant_ids?.length" class="flex flex-wrap gap-1.5">
                  <UBadge
                    v-for="(pid, i) in monitor.participant_ids"
                    :key="pid"
                    color="neutral"
                    variant="soft"
                    size="sm"
                  >
                    {{ monitor.participant_usernames?.[i] || pid }}
                  </UBadge>
                </div>
                <span v-else class="text-gray-400">暂无参与者</span>
              </ClientOnly>
            </dd>
          </div>
        </dl>
      </UCard>

      <!-- 任务列表 -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <h2 class="text-lg font-semibold">任务列表</h2>
              <ClientOnly>
                <div class="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
                  <button
                    v-for="item in phaseItems"
                    :key="item.value"
                    class="px-2.5 py-1 text-xs rounded-md transition-colors"
                    :class="phaseFilter === item.value
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm font-medium'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'"
                    @click="phaseFilter = item.value as 'all' | 'probe' | 'collect'"
                  >
                    {{ item.label }}
                  </button>
                </div>
              </ClientOnly>
            </div>
            <div class="flex items-center gap-3">
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
                placeholder="全部状态"
                class="w-28"
              />
              <UButton
                size="sm"
                icon="i-heroicons-plus"
                :to="`/news-media/tasks/create?monitor_id=${monitorId}`"
              >
                创建任务
              </UButton>
              <UButton
                size="sm"
                variant="ghost"
                icon="i-heroicons-arrow-path"
                :loading="refreshing"
                @click="handleRefresh"
              >
                刷新
              </UButton>
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
            :columns="taskColumns"
            :loading="tasksLoading"
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
                共 {{ totalTasks }} 个任务
              </div>
              <UPagination
                v-model:page="currentPage"
                :total="totalTasks"
                :items-per-page="pageSize"
                :sibling-count="2"
              />
            </div>
          </ClientOnly>
        </template>
      </UCard>

      <!-- 统计聚合摘要 -->
      <UCard v-if="aggregatedStats && aggregatedStats.articles_total > 0">
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">聚合摘要</h2>
            <UButton
              variant="ghost"
              size="sm"
              icon="i-heroicons-arrow-path"
              :loading="aggregatedLoading"
              @click="loadAggregated"
            >
              刷新
            </UButton>
          </div>
        </template>

        <ClientOnly>
          <div class="space-y-4">
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">文章总数</span>
                <p class="text-xl font-bold mt-1">{{ aggregatedStats.articles_total }}</p>
              </div>
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">相关文章</span>
                <p class="text-xl font-bold mt-1">{{ aggregatedStats.articles_relevant }}</p>
              </div>
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">综合情感</span>
                <p class="text-xl font-bold mt-1">
                  {{ aggregatedStats.sentiment_overall !== null ? aggregatedStats.sentiment_overall?.toFixed(2) : '-' }}
                </p>
              </div>
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">情感分布（正/中/负）</span>
                <p class="font-medium mt-1 text-sm">
                  <span class="text-green-600">{{ aggregatedStats.sentiment_distribution.positive }}</span> /
                  <span class="text-gray-500">{{ aggregatedStats.sentiment_distribution.neutral }}</span> /
                  <span class="text-red-600">{{ aggregatedStats.sentiment_distribution.negative }}</span>
                </p>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3 text-sm">
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">来源等级分布</span>
                <p class="font-medium mt-1">
                  权威 {{ aggregatedStats.source_tier_distribution.tier1 }} /
                  行业 {{ aggregatedStats.source_tier_distribution.tier2 }} /
                  其他 {{ aggregatedStats.source_tier_distribution.tier3 }}
                </p>
              </div>
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">搜索渠道分布</span>
                <p class="font-medium mt-1">
                  百度 {{ aggregatedStats.search_source_distribution.baidu }} /
                  DuckDuckGo {{ aggregatedStats.search_source_distribution.duckduckgo }}
                </p>
              </div>
            </div>

            <div v-if="aggregatedStats.top_entities.length > 0">
              <p class="text-sm text-gray-500 mb-2">高频实体 Top{{ Math.min(aggregatedStats.top_entities.length, 5) }}</p>
              <div class="flex flex-wrap gap-2">
                <UBadge
                  v-for="ent in aggregatedStats.top_entities.slice(0, 5)"
                  :key="ent.name"
                  variant="subtle"
                >
                  {{ ent.name }} · {{ ent.mention_count }}次
                </UBadge>
              </div>
            </div>
          </div>
        </ClientOnly>
      </UCard>

      <!-- 叙事聚合报告 -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">叙事聚合报告</h2>
            <UButton
              icon="i-heroicons-sparkles"
              :loading="narrativeLoading"
              @click="handleRunNarrative"
            >
              生成聚合报告
            </UButton>
          </div>
        </template>

        <ClientOnly>
          <div v-if="narrativeResult && showNarrativePanel" class="space-y-4 text-sm">
            <div v-if="(narrativeResult.narratives as NewsNarrative[] | undefined)?.length">
              <h3 class="font-semibold mb-2">叙事主题</h3>
              <div class="space-y-2">
                <div
                  v-for="(n, idx) in (narrativeResult.narratives as NewsNarrative[])"
                  :key="idx"
                  class="p-3 border border-gray-200 dark:border-gray-700 rounded"
                >
                  <div class="flex items-center justify-between mb-1">
                    <span class="font-medium">{{ n.theme }}</span>
                    <span class="text-xs text-gray-500">{{ n.article_count }} 篇</span>
                  </div>
                  <p class="text-gray-600 dark:text-gray-400">{{ n.summary }}</p>
                </div>
              </div>
            </div>
            <p v-else class="text-gray-500 text-center py-4">报告生成完成，暂无叙事主题数据</p>
          </div>

          <div v-else class="text-center py-6 text-gray-400 text-sm">
            点击「生成聚合报告」分析该项目下所有全量采集任务的叙事主题
          </div>
        </ClientOnly>
      </UCard>
    </template>

    <div v-else class="text-center py-8">
      <p class="text-gray-500">监测项目不存在</p>
    </div>

    <!-- 编辑项目弹窗 -->
    <ClientOnly>
      <UModal
        v-model:open="showEditModal"
        title="编辑项目"
        :ui="{ footer: 'justify-end' }"
      >
        <template #body>
          <div class="space-y-4">
            <UFormField label="项目名称" required>
              <UInput
                v-model="editState.name"
                placeholder="请输入项目名称"
                class="w-full"
              />
            </UFormField>
            <UFormField label="项目描述">
              <UTextarea
                v-model="editState.description"
                :rows="3"
                placeholder="请输入项目描述"
                class="w-full"
              />
            </UFormField>
            <UFormField
              label="参与者"
              help="参与者变更会立即生效，无需点保存"
            >
              <ParticipantsManager
                :participants="(monitor?.participant_ids || []).map((id: number, i: number) => ({ id, username: monitor?.participant_usernames?.[i] || String(id) }))"
                :owner-id="monitor?.owner_id || 0"
                :can-manage="true"
                :on-add="async (ids: number[]) => { await addParticipant(monitorId, ids); await refreshMonitor() }"
                :on-remove="async (uid: number) => { await removeParticipant(monitorId, uid); await refreshMonitor() }"
              />
            </UFormField>
          </div>
        </template>
        <template #footer>
          <UButton
            variant="outline"
            :disabled="editSubmitting"
            @click="showEditModal = false"
          >
            取消
          </UButton>
          <UButton
            :loading="editSubmitting"
            @click="handleUpdateMonitor"
          >
            保存
          </UButton>
        </template>
      </UModal>
    </ClientOnly>

  </div>
</template>
