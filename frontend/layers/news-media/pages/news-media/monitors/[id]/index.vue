<script setup lang="ts">
import { h, ref, reactive, computed, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UButton, UBadge } from '#components'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const monitorId = Number(route.params.id)

const { getMonitor, deleteMonitor: deleteMonitorApi, addParticipant, removeParticipant, updateMonitor } = useNewsMonitors()
const { getTasks, deleteTask, executeTask } = useNewsTasks()
const { getSlices, createSlice, deleteSlice: deleteSliceApi } = useNewsSlices()
const { currentUserId, hasPermission } = usePermissions()

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

// ========== 任务选择（生成切片用） ==========

const selectedTaskIds = ref<number[]>([])

const completedCollectTasks = computed(() =>
  tasks.value.filter(t => t.status === 'completed' && t.phase === 'collect'),
)

const isTaskSelected = (taskId: number) => selectedTaskIds.value.includes(taskId)

const toggleTaskSelection = (taskId: number) => {
  if (isTaskSelected(taskId)) {
    selectedTaskIds.value = selectedTaskIds.value.filter(id => id !== taskId)
  } else {
    selectedTaskIds.value = [...selectedTaskIds.value, taskId]
  }
}

const toggleSelectAll = () => {
  if (selectedTaskIds.value.length === completedCollectTasks.value.length) {
    selectedTaskIds.value = []
  } else {
    selectedTaskIds.value = completedCollectTasks.value.map(t => t.id)
  }
}

// ========== 生成切片弹窗 ==========

const showSliceModal = ref(false)
const sliceNameInput = ref('')
const generatingSlice = ref(false)

const openSliceModal = () => {
  sliceNameInput.value = ''
  showSliceModal.value = true
}

const handleCreateSlice = async () => {
  if (!sliceNameInput.value.trim()) {
    toast.add({ title: '请输入切片名称', color: 'warning' })
    return
  }
  generatingSlice.value = true
  try {
    const created = await createSlice(monitorId, {
      name: sliceNameInput.value.trim(),
      included_task_ids: selectedTaskIds.value,
    })
    showSliceModal.value = false
    selectedTaskIds.value = []
    await navigateTo(`/news-media/slices/${created.id}`)
  } catch {
    // error already handled
  } finally {
    generatingSlice.value = false
  }
}

// ========== 切片列表 ==========

const { data: slicesData, pending: slicesLoading, refresh: refreshSlices } = getSlices(monitorId)
const slices = computed(() => slicesData.value || [])

const handleDeleteSlice = async (slice: NewsSlice) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除切片',
    message: `确定要删除切片 "${slice.name}" 吗？`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  try {
    await deleteSliceApi(slice.id)
    await refreshSlices()
  } catch {
    // error already handled
  }
}

type BadgeColor = 'neutral' | 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error'

const getSliceStatusColor = (status: string): BadgeColor => {
  const map: Record<string, BadgeColor> = {
    pending: 'neutral',
    analyzing: 'info',
    completed: 'success',
    failed: 'error',
  }
  return map[status] || 'neutral'
}

const getSliceStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '待分析',
    analyzing: '分析中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
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
      accessorKey: 'select',
      header: '',
      meta: { class: { th: 'w-10', td: 'w-10' } },
      cell: ({ row }) => {
        const task = row.original
        const selectable = task.status === 'completed' && task.phase === 'collect'
        const disabledReason = !selectable
          ? task.phase === 'probe'
            ? '探测任务数据量小，不可用于生成切片'
            : '仅"已完成"的全量任务可生成切片'
          : ''
        return h('input', {
          type: 'checkbox',
          checked: selectable && isTaskSelected(task.id),
          disabled: !selectable,
          title: disabledReason,
          class: selectable
            ? 'rounded border-gray-300 cursor-pointer'
            : 'rounded border-gray-300 cursor-not-allowed opacity-40',
          onChange: () => selectable && toggleTaskSelection(task.id),
        })
      },
    },
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
        h(Badge, { color: getPhaseColor(row.original.phase), size: 'sm', variant: 'subtle' }, () =>
          getPhaseText(row.original.phase),
        ),
    },
    {
      accessorKey: 'status',
      header: '状态',
      meta: { class: { th: 'w-[80px]', td: 'w-[80px]' } },
      cell: ({ row }) =>
        h(Badge, { color: getStatusColor(row.original.status), size: 'sm', variant: 'solid' }, () =>
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
            v-if="hasPermission(PERMISSIONS.NEWS_MONITOR_DELETE) || monitor?.user_id === currentUserId"
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
                v-if="hasPermission(PERMISSIONS.NEWS_MONITOR_WRITE) || monitor.user_id === currentUserId"
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
                    variant="subtle"
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
                icon="i-heroicons-sparkles"
                :disabled="!selectedTaskIds.length"
                :loading="generatingSlice"
                @click="openSliceModal"
              >
                生成切片
              </UButton>
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

          <!-- 选中提示 -->
          <div
            v-if="selectedTaskIds.length > 0"
            class="mb-3 flex items-center justify-between px-3 py-2 bg-primary-50 dark:bg-primary-900/20 rounded-lg text-sm"
          >
            <span>
              已选 {{ selectedTaskIds.length }} 个任务
              <button class="text-primary-600 dark:text-primary-400 underline ml-2" @click="toggleSelectAll">
                {{ selectedTaskIds.length === completedCollectTasks.length ? '取消全选' : '全选已完成' }}
              </button>
            </span>
          </div>

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

      <!-- 切片列表 -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">分析切片</h2>
            <UButton
              size="sm"
              variant="ghost"
              icon="i-heroicons-arrow-path"
              :loading="slicesLoading"
              @click="refreshSlices()"
            >
              刷新
            </UButton>
          </div>
        </template>

        <ClientOnly>
          <template #fallback>
            <div class="text-center py-6">
              <p class="text-gray-600 dark:text-gray-400">加载切片列表中...</p>
            </div>
          </template>

          <div v-if="slices.length > 0" class="space-y-3">
            <div
              v-for="slice in slices"
              :key="slice.id"
              class="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-medium text-sm truncate">{{ slice.name }}</span>
                  <UBadge
                    :color="getSliceStatusColor(slice.status)"
                    size="sm"
                    variant="subtle"
                  >
                    {{ getSliceStatusText(slice.status) }}
                  </UBadge>
                </div>
                <p class="text-xs text-gray-500">
                  包含 {{ slice.included_task_ids.length }} 个任务 · {{ formatDate(slice.created_at) }}
                </p>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <UButton
                  size="xs"
                  variant="ghost"
                  icon="i-heroicons-eye"
                  :to="`/news-media/slices/${slice.id}`"
                >
                  查看
                </UButton>
                <UButton
                  size="xs"
                  variant="ghost"
                  icon="i-heroicons-trash"
                  color="error"
                  @click="handleDeleteSlice(slice)"
                >
                  删除
                </UButton>
              </div>
            </div>
          </div>

          <div v-else class="text-center py-6 text-gray-400 text-sm">
            暂无分析切片，请在任务列表中勾选已完成任务后点击「生成切片」
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
                :owner-id="monitor?.user_id || 0"
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

      <!-- 生成切片弹窗 -->
      <UModal
        v-model:open="showSliceModal"
        title="生成分析切片"
        :ui="{ footer: 'justify-end' }"
      >
        <template #body>
          <div class="space-y-4">
            <p class="text-sm text-gray-500">
              将基于已选 {{ selectedTaskIds.length }} 个任务（ID: {{ selectedTaskIds.join(', ') }}）生成一份合并分析切片，创建后自动运行 insight 分析。
            </p>
            <UFormField label="切片名称" required>
              <UInput
                v-model="sliceNameInput"
                placeholder="例如：品牌声量总览、竞品对比分析"
                class="w-full"
              />
            </UFormField>
          </div>
        </template>
        <template #footer>
          <UButton
            variant="outline"
            :disabled="generatingSlice"
            @click="showSliceModal = false"
          >
            取消
          </UButton>
          <UButton
            :loading="generatingSlice"
            :disabled="!sliceNameInput.trim()"
            @click="handleCreateSlice"
          >
            开始生成
          </UButton>
        </template>
      </UModal>
    </ClientOnly>

  </div>
</template>
