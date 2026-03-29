<script setup lang="ts">
import { computed, ref, h, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton } from '#components'
import type { DataTaskWithRelations } from '../../../../tasks/types'
import type { MonitorSlice } from '../../../../types/monitor-slice'
import TaskComparisonSlideover from '../../../../monitors/components/TaskComparisonSlideover.vue'
import QuickTaskForm from '../../../../monitors/components/QuickTaskForm.vue'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const monitorId = computed(() => Number(route.params.id))

const { getMonitor, deleteMonitor, batchCreateTasks } = useMonitors()
const { getTasks, deleteTask } = useTasks()
const { createMonitorSlice, deleteMonitorSlice } = useAnalysis()
const { useApiData } = useApi()

// 获取项目详情（使用顶层 await）
const { data: monitor, pending: _monitorLoading, refresh: refreshMonitor } = await getMonitor(monitorId.value)

// phase 筛选：全部 / 探测 / 全量
const phaseFilter = ref<'all' | 'probe' | 'collect'>('all')
const phaseItems = [
  { label: '全部', value: 'all' },
  { label: '探测', value: 'probe' },
  { label: '全量', value: 'collect' },
]

// 获取项目下的任务列表
const taskParams = computed(() => ({
  monitor_id: monitorId.value,
  page: 1,
  page_size: 100,
  ...(phaseFilter.value !== 'all' ? { phase: phaseFilter.value } : {}),
}))

const { data: tasksData, pending: tasksLoading, refresh: refreshTasks } = await getTasks(taskParams)

const tasks = computed(() => tasksData.value?.items || [])

// ==================== 项目切片（Phase 1）====================

// 已选择的任务（用于生成切片）
const selectedTaskIds = ref<number[]>([])
const setTaskSelected = (taskId: number, checked: boolean) => {
  const s = new Set(selectedTaskIds.value)
  if (checked) s.add(taskId)
  else s.delete(taskId)
  selectedTaskIds.value = Array.from(s)
}
const allTaskIds = computed(() => (tasks.value as DataTaskWithRelations[]).map(t => t.id))
const allSelected = computed(() => allTaskIds.value.length > 0 && allTaskIds.value.every(id => selectedTaskIds.value.includes(id)))
const toggleSelectAll = (checked: boolean) => {
  selectedTaskIds.value = checked ? Array.from(new Set(allTaskIds.value)) : []
}

interface MonitorSliceListResponse {
  items: MonitorSlice[]
}
const { data: slicesData, pending: slicesLoading, refresh: refreshSlices } = useApiData<MonitorSliceListResponse>(
  computed(() => `/social-media/analysis/monitors/${monitorId.value}/slices`),
  { key: computed(() => `monitor-slices-${monitorId.value}`), getCachedData: () => undefined }
)
const slices = computed<MonitorSlice[]>(() => slicesData.value?.items || [])

const handleRefreshSlices = async () => {
  await refreshSlices()
}

const generatingSlice = ref(false)
const sliceNameInput = ref('')
const sliceSubjectInput = ref('')
const sliceCompetitorsInput = ref('')
const sliceWeightsJsonInput = ref('')
const enableCustomPlatformWeights = ref(false)
const showSliceModal = ref(false)

// 任务对比
const showComparisonSlideover = ref(false)

// 检查选中的任务是否来自同一平台
const selectedTasksPlatformCheck = computed(() => {
  if (selectedTaskIds.value.length < 2) {
    return { valid: false, reason: 'not_enough', platformIds: new Set<number>() }
  }
  const selectedSet = new Set(selectedTaskIds.value)
  const platformIds = new Set<number>()
  for (const t of tasks.value as DataTaskWithRelations[]) {
    if (selectedSet.has(t.id) && t.platform_id) {
      platformIds.add(t.platform_id)
    }
  }
  if (platformIds.size > 1) {
    return { valid: false, reason: 'different_platforms', platformIds }
  }
  return { valid: true, reason: null, platformIds }
})

const canCompare = computed(() => selectedTasksPlatformCheck.value.valid)

const openComparisonSlideover = () => {
  const check = selectedTasksPlatformCheck.value
  if (selectedTaskIds.value.length < 2) {
    toast.add({
      title: '至少选择 2 个任务',
      description: '请勾选至少两个任务进行对比',
      color: 'warning',
    })
    return
  }
  if (check.reason === 'different_platforms') {
    toast.add({
      title: '无法对比不同平台的任务',
      description: '请选择同一平台的任务进行对比，当前选择了多个平台',
      color: 'error',
    })
    return
  }
  showComparisonSlideover.value = true
}

// ==================== 批量创建任务 ====================

const showBatchTaskModal = ref(false)
const batchTaskSubmitting = ref(false)

const batchTaskState = reactive({
  platform_ids: [] as number[],
  task_type: 'search' as 'search' | 'homefeed',
  data_source: 'remote_crawler' as 'remote_crawler' | 'local_upload',
  keywords: '',
  max_notes_count: 100,
  enable_comments: true,
  per_note_max_comments_count: 20,
  publish_time_type: 0,
  sort_type: 'popularity_descending',
  auto_analyze: true,
})

const resetBatchTaskState = () => {
  batchTaskState.platform_ids = []
  batchTaskState.task_type = 'search'
  batchTaskState.data_source = 'remote_crawler'
  batchTaskState.keywords = ''
  batchTaskState.max_notes_count = 100
  batchTaskState.enable_comments = true
  batchTaskState.per_note_max_comments_count = 20
  batchTaskState.publish_time_type = 0
  batchTaskState.sort_type = 'popularity_descending'
  batchTaskState.auto_analyze = true
}

const openBatchTaskModal = () => {
  resetBatchTaskState()
  showBatchTaskModal.value = true
}

const handleBatchCreateTasks = async () => {
  if (batchTaskState.platform_ids.length === 0) {
    toast.add({ title: '请至少选择一个平台', color: 'warning' })
    return
  }
  if (batchTaskState.task_type === 'search' && !batchTaskState.keywords?.trim()) {
    toast.add({ title: '搜索任务必须提供关键词', color: 'warning' })
    return
  }

  batchTaskSubmitting.value = true
  try {
    await batchCreateTasks(monitorId.value, {
      platform_ids: batchTaskState.platform_ids,
      task_type: batchTaskState.task_type,
      data_source: batchTaskState.data_source,
      keywords: batchTaskState.keywords || undefined,
      max_notes_count: batchTaskState.max_notes_count,
      enable_comments: batchTaskState.enable_comments,
      per_note_max_comments_count: batchTaskState.per_note_max_comments_count,
      publish_time_type: batchTaskState.publish_time_type,
      sort_type: batchTaskState.sort_type,
      auto_analyze: batchTaskState.auto_analyze,
    })
    showBatchTaskModal.value = false
    await refreshTasks()
  } catch {
    // apiRequest 已处理错误 toast
  } finally {
    batchTaskSubmitting.value = false
  }
}

const openSliceModal = () => {
  if (!selectedTaskIds.value.length) return
  sliceNameInput.value = ''
  sliceSubjectInput.value = ''
  sliceCompetitorsInput.value = ''
  sliceWeightsJsonInput.value = ''
  enableCustomPlatformWeights.value = false
  showSliceModal.value = true
}

const toast = useToast()

const parseCompetitors = (raw: string): string[] => {
  const items = (raw || '')
    .split(/[\n,，]/g)
    .map(s => s.trim())
    .filter(Boolean)
  return Array.from(new Set(items)).slice(0, 30)
}

const parseKeywords = (raw: string | null | undefined): string[] => {
  const items = (raw || '')
    .split(/[\n,，;；]/g)
    .map(s => s.trim())
    .filter(Boolean)
  return Array.from(new Set(items))
}

// 基于“已选任务”的 keywords 给出候选项（低风险、可解释）
const keywordCandidates = computed(() => {
  const selected = new Set(selectedTaskIds.value)
  const counts = new Map<string, number>()
  for (const t of tasks.value as DataTaskWithRelations[]) {
    if (!selected.has(t.id)) continue
    for (const kw of parseKeywords(t.keywords)) {
      counts.set(kw, (counts.get(kw) || 0) + 1)
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => (b[1] || 0) - (a[1] || 0))
    .slice(0, 24)
    .map(([kw]) => kw)
})

const addCompetitor = (kw: string) => {
  const cur = parseCompetitors(sliceCompetitorsInput.value)
  if (!cur.includes(kw)) cur.push(kw)
  sliceCompetitorsInput.value = cur.join('，')
}

const parsePlatformWeights = (raw: string): Record<string, number> | undefined => {
  const s = (raw || '').trim()
  if (!s) return undefined
  const obj = JSON.parse(s) as unknown
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    throw new Error('platform_weights 必须是 JSON 对象，例如 {"bilibili":1.5}')
  }
  const weights: Record<string, number> = {}
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const key = String(k || '').trim()
    if (!key) continue
    const n = typeof v === 'number' ? v : Number(v)
    if (!Number.isFinite(n) || n <= 0) {
      throw new Error(`平台权重必须是 >0 的数字：${key}`)
    }
    weights[key] = n
  }
  return Object.keys(weights).length ? weights : undefined
}

const handleGenerateSlice = async () => {
  // 先校验配置，避免关闭弹窗后报错找不到入口
  let platformWeights: Record<string, number> | undefined
  if (enableCustomPlatformWeights.value) {
    try {
      platformWeights = parsePlatformWeights(sliceWeightsJsonInput.value)
    } catch (e) {
      toast.add({
        title: '平台权重配置有误',
        description: (e as Error).message || '请检查 JSON 格式与数值',
        color: 'error',
      })
      return
    }
  }

  showSliceModal.value = false

  generatingSlice.value = true
  try {
    const name = sliceNameInput.value.trim() || undefined
    const subject = sliceSubjectInput.value.trim() || undefined
    const competitors = parseCompetitors(sliceCompetitorsInput.value)
    const created = await createMonitorSlice(monitorId.value, selectedTaskIds.value, name, {
      subject: subject || null,
      competitors: competitors.length ? competitors : null,
      platform_weights: platformWeights || null,
    })
    selectedTaskIds.value = []
    sliceNameInput.value = ''
    sliceSubjectInput.value = ''
    sliceCompetitorsInput.value = ''
    sliceWeightsJsonInput.value = ''
    enableCustomPlatformWeights.value = false
    await refreshSlices()
    // 生成后直接跳转到该切片详情页，避免 slice_id 丢失导致页面显示"切片 null"
    await navigateTo(`/social-media/monitors/${monitorId.value}/analysis?slice_id=${created.id}`)
  } catch {
    // apiRequest 已在 onResponseError 中显示了错误 toast，这里不需要重复显示
    // 只需要捕获错误防止 unhandled rejection
  } finally {
    generatingSlice.value = false
  }
}

const deletingTaskId = ref<number | null>(null)
const handleDeleteTask = async (task: DataTaskWithRelations) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除任务',
    message: `确定要删除任务 "${task.name}" 吗？此操作不可恢复，将同时删除所有相关的原文和评论数据。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  deletingTaskId.value = task.id
  try {
    await deleteTask(task.id)
    await refreshTasks()
  } finally {
    deletingTaskId.value = null
  }
}

const deletingSliceId = ref<number | null>(null)
const handleDeleteSlice = async (sliceId: number) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除切片',
    message: `确定要删除切片 ${sliceId} 吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  deletingSliceId.value = sliceId
  try {
    await deleteMonitorSlice(monitorId.value, sliceId)
    await refreshSlices()
  } finally {
    deletingSliceId.value = null
  }
}

// 刷新所有数据
const refreshing = ref(false)
const handleRefresh = async () => {
  refreshing.value = true
  await Promise.all([refreshMonitor(), refreshTasks(), refreshSlices()])
  refreshing.value = false
}

// 删除项目
const handleDelete = async () => {
  if (!monitor.value) return

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除项目',
    message: `确定要删除项目 "${monitor.value.name}" 吗？此操作不可恢复，所有相关任务和数据也将被删除。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })

  if (!confirmed) return

  try {
    await deleteMonitor(monitor.value.id)
    await navigateTo('/social-media/monitors')
  } catch (error) {
    console.error('删除项目失败:', error)
  }
}

// 格式化日期
const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

const formatDateTime = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatCompactNumber = (n: unknown): string => {
  const v = typeof n === 'number' ? n : Number(n)
  if (!Number.isFinite(v)) return '-'
  const abs = Math.abs(v)
  if (abs >= 10000) return `${(v / 10000).toFixed(abs >= 100000 ? 0 : 1)}万`
  if (abs >= 1000) return `${(v / 1000).toFixed(abs >= 10000 ? 0 : 1)}k`
  return `${Math.round(v)}`
}

// 任务状态颜色
const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'neutral',
    accepted: 'neutral',
    running: 'info',
    probe_ready: 'warning',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

// 任务状态文本
const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    pending: '待处理',
    accepted: '已接单',
    running: '运行中',
    probe_ready: '探测完成',
    completed: '已完成',
    failed: '失败',
  }
  return texts[status] || status
}

// 分析状态颜色
const getAnalysisColor = (status: string | null) => {
  if (!status) return 'neutral'
  const colors: Record<string, string> = {
    pending: 'neutral',
    processing: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

// 分析状态文本
const getAnalysisText = (status: string | null) => {
  if (!status) return '-'
  const texts: Record<string, string> = {
    pending: '待分析',
    processing: '分析中',
    completed: '分析完成',
    failed: '分析失败',
  }
  return texts[status] || status
}

const getSliceStageColor = (status?: string) => {
  const colors: Record<string, string> = {
    pending: 'neutral',
    processing: 'info',
    completed: 'success',
    failed: 'error',
    skipped: 'warning',
  }
  if (!status) return 'neutral'
  return colors[status] || 'neutral'
}

const getSliceStageText = (status?: string) => {
  const texts: Record<string, string> = {
    pending: '未开始',
    processing: '进行中',
    completed: '已完成',
    failed: '失败',
    skipped: '跳过',
  }
  if (!status) return '未知'
  return texts[status] || status
}

const formatCompetitors = (items?: unknown): string => {
  if (!Array.isArray(items)) return '-'
  const arr = items.map(x => String(x || '').trim()).filter(Boolean)
  if (!arr.length) return '-'
  const head = arr.slice(0, 3).join('、')
  const rest = arr.length - 3
  return rest > 0 ? `${head} 等${rest + 3}个` : head
}

const formatTaskIdsPreview = (ids?: number[]): string => {
  const arr = Array.isArray(ids) ? ids : []
  if (!arr.length) return '-'
  const head = arr.slice(0, 6).join(', ')
  return arr.length > 6 ? `${head} …` : head
}

const sliceColumns = computed<TableColumn<MonitorSlice>[]>(() => {
  const Badge = UBadge as Component
  const Button = UButton as Component

  return [
    {
      accessorKey: 'name',
      header: '切片',
      meta: { class: { th: 'w-[240px]', td: 'w-[240px] whitespace-normal' } },
      cell: ({ row }) => {
        const s = row.original
        const subject = s.result_data?.meta?.subject || null
        const competitors = formatCompetitors(s.result_data?.meta?.competitors)
        const hasFocus = Boolean(subject)
        return h('div', {}, [
          h('div', { class: 'flex items-center gap-1.5 flex-wrap' }, [
            h('span', { class: 'font-medium text-gray-900 dark:text-white leading-snug line-clamp-2' }, s.name || `切片 ${s.id}`),
            h('span', { class: 'text-xs text-gray-400 font-normal shrink-0' }, `#${s.id}`),
            hasFocus
              ? h(Badge, { size: 'xs', variant: 'subtle', color: 'primary' }, () => 'Focus')
              : h(Badge, { size: 'xs', variant: 'subtle', color: 'neutral' }, () => '无 Focus'),
          ]),
          h('div', { class: 'mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate' },
            `主体：${subject ? String(subject) : '-'} · 竞品：${competitors}`
          ),
        ])
      },
    },
    {
      accessorKey: 'created_at',
      header: '创建时间',
      meta: { class: { th: 'w-[90px]', td: 'w-[90px] whitespace-nowrap' } },
      cell: ({ row }) => h('span', { class: 'text-gray-600 dark:text-gray-400' }, formatDateTime(row.original.created_at)),
    },
    {
      accessorKey: 'included_task_ids',
      header: '任务',
      meta: { class: { th: 'w-[100px]', td: 'w-[100px] whitespace-normal' } },
      cell: ({ row }) => {
        const ids = row.original.included_task_ids || []
        return h('div', { class: 'text-xs text-gray-600 dark:text-gray-400' }, [
          h('div', { class: 'font-medium text-gray-900 dark:text-white' }, `${ids.length} 个`),
          h('div', { class: 'mt-0.5 font-mono whitespace-normal' }, formatTaskIdsPreview(ids)),
        ])
      },
    },
    {
      accessorKey: 'status',
      header: '进度',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px] whitespace-nowrap' } },
      cell: ({ row }) => {
        const s = row.original
        const stage2 = s.result_data?.pipeline?.stage2?.status
        const stage3 = s.result_data?.pipeline?.stage3?.status
        return h('div', { class: 'flex flex-col gap-1 items-start' }, [
          h(Badge, { size: 'xs', variant: 'solid', color: getSliceStageColor(stage2) }, () => `归一化：${getSliceStageText(stage2)}`),
          h(Badge, { size: 'xs', variant: 'solid', color: getSliceStageColor(stage3) }, () => `报告：${getSliceStageText(stage3)}`),
        ])
      },
    },
    {
      accessorKey: 'metrics',
      header: '关键指标',
      meta: { class: { th: 'w-[90px]', td: 'w-[90px]' } },
      cell: ({ row }) => {
        const s = row.original
        const totalVolume = s.result_data?.layers?.landscape?.overview?.total_volume
        const globalSentiment = s.result_data?.layers?.landscape?.overview?.global_nsr
        const entityCount = s.result_data?.foundation?.aligned_entities?.length ?? null
        const topicCount = s.result_data?.foundation?.aligned_topics?.length ?? null
        const sentimentText = typeof globalSentiment === 'number' && Number.isFinite(globalSentiment)
          ? globalSentiment.toFixed(2)
          : '-'
        return h('div', { class: 'text-xs text-gray-600 dark:text-gray-400' }, [
          h('div', { class: 'text-gray-900 dark:text-white font-medium' },
            `总声量 ${formatCompactNumber(totalVolume)} · 情绪 ${sentimentText}`
          ),
          h('div', { class: 'mt-0.5' },
            `实体 ${entityCount ?? '-'} · 话题 ${topicCount ?? '-'}`
          ),
        ])
      },
    },
    {
      accessorKey: 'actions',
      header: '操作',
      meta: { class: { th: 'w-[90px]', td: 'w-[90px] whitespace-nowrap' } },
      cell: ({ row }) => {
        const s = row.original
        return h('div', { class: 'flex items-center gap-2' }, [
          h(Button, {
            size: 'xs',
            variant: 'ghost',
            icon: 'i-heroicons-eye',
            to: `/social-media/monitors/${monitorId.value}/analysis?slice_id=${s.id}`,
          }, () => '查看'),
          h(Button, {
            size: 'xs',
            variant: 'ghost',
            color: 'error',
            icon: 'i-heroicons-trash',
            loading: deletingSliceId.value === s.id,
            onClick: () => handleDeleteSlice(s.id),
          }, () => '删除'),
        ])
      },
    },
  ]
})

// 表格列定义 - 使用 computed 以避免 SSR 水合问题
const columns = computed<TableColumn<DataTaskWithRelations>[]>(() => {
  const Badge = UBadge as Component
  const Button = UButton as Component

  return [
    {
      id: 'select',
      meta: { class: { th: 'w-8', td: 'w-8' } },
      header: () => h('input', {
        type: 'checkbox',
        checked: allSelected.value,
        onChange: (e: Event) => toggleSelectAll((e.target as HTMLInputElement).checked),
        title: '全选',
      }),
      cell: ({ row }) => h('input', {
        type: 'checkbox',
        checked: selectedTaskIds.value.includes(row.original.id),
        onChange: (e: Event) => setTaskSelected(row.original.id, (e.target as HTMLInputElement).checked),
      }),
    },
    {
      accessorKey: 'id',
      meta: { class: { th: 'w-14', td: 'w-14' } },
      header: 'ID',
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'name',
      header: '任务名称',
      meta: { class: { th: 'w-[200px]', td: 'w-[200px] whitespace-normal' } },
      cell: ({ row }) => h('div', { class: 'font-medium leading-snug line-clamp-2', title: row.original.name }, row.original.name),
    },
    {
      accessorKey: 'platform_name',
      meta: { class: { th: 'w-20', td: 'w-20 whitespace-nowrap' } },
      header: '平台',
      cell: ({ row }) => h(Badge, { variant: 'subtle', size: 'xs' }, () => row.original.platform_name || '-'),
    },
    {
      accessorKey: 'task_type',
      meta: { class: { th: 'w-20', td: 'w-20 whitespace-nowrap' } },
      header: '类型',
      cell: ({ row }) => h('span', { class: 'text-sm' }, row.original.task_type),
    },
    {
      accessorKey: 'phase',
      meta: { class: { th: 'w-16', td: 'w-16 whitespace-nowrap' } },
      header: '阶段',
      cell: ({ row }) => {
        const phase = row.original.phase
        if (!phase) return h('span', { class: 'text-xs text-gray-400' }, '-')
        return h(Badge, {
          size: 'xs',
          variant: 'subtle',
          color: phase === 'probe' ? 'warning' : 'primary',
        }, () => phase === 'probe' ? '探测' : '全量')
      },
    },
    {
      accessorKey: 'status',
      meta: { class: { th: 'w-[96px]', td: 'w-[96px] whitespace-nowrap' } },
      header: '状态',
      cell: ({ row }) => {
        const collectBadge = h(Badge, {
          color: getStatusColor(row.original.status),
          variant: 'solid',
          size: 'xs',
        }, () => getStatusText(row.original.status))

        const s = row.original.aggregation_status
        if (!s) return collectBadge

        const analysisBadge = h(Badge, {
          color: getAnalysisColor(s),
          variant: 'subtle',
          size: 'xs',
        }, () => getAnalysisText(s))

        return h('div', { class: 'flex flex-wrap items-center gap-1' }, [collectBadge, analysisBadge])
      },
    },
    {
      accessorKey: 'stats',
      meta: { class: { th: 'w-[140px]', td: 'w-[140px] whitespace-nowrap overflow-hidden' } },
      header: '数据统计',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' },
        `${row.original.posts_count} 原文 / ${row.original.comments_count} 评论`
      ),
    },
    {
      accessorKey: 'created_at',
      meta: { class: { th: 'w-[112px]', td: 'w-[112px] whitespace-nowrap' } },
      header: '创建时间',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, formatDateTime(row.original.created_at)),
    },
    {
      accessorKey: 'actions',
      meta: { class: { th: 'w-[128px]', td: 'w-[128px] whitespace-nowrap' } },
      header: '操作',
      cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
        h(Button, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-eye',
          to: `/social-media/tasks/${row.original.id}?from=monitor&monitor_id=${monitorId.value}`,
        }, () => '查看'),
        row.original.status === 'pending' && row.original.data_source === 'local_upload'
          ? h(Button, {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-arrow-up-tray',
              color: 'info',
              to: `/social-media/tasks/${row.original.id}/upload`,
            }, () => '上传')
          : null,
        h(Button, {
          size: 'xs',
          variant: 'ghost',
          color: 'error',
          icon: 'i-heroicons-trash',
          loading: deletingTaskId.value === row.original.id,
          onClick: () => handleDeleteTask(row.original),
        }, () => '删除'),
      ].filter(Boolean)),
    },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            to="/social-media/monitors"
          />
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ monitor?.name || '加载中...' }}
            </h1>
            <p class="text-gray-600 dark:text-gray-400 mt-1">
              项目详情
            </p>
          </div>
        </div>
      </div>

      <ClientOnly>
        <div v-if="monitor" class="flex items-center gap-3">
          <UButton
            icon="i-heroicons-plus"
            :to="`/social-media/tasks/create?monitor_id=${monitorId}`"
          >
            新建任务
          </UButton>
          <UButton
            variant="outline"
            icon="i-heroicons-squares-plus"
            @click="openBatchTaskModal"
          >
            批量创建
          </UButton>
          <UButton
            variant="outline"
            icon="i-heroicons-arrow-path"
            :loading="refreshing"
            @click="handleRefresh"
          >
            刷新
          </UButton>
          <UButton
            variant="outline"
            icon="i-heroicons-trash"
            color="error"
            @click="handleDelete"
          >
            删除
          </UButton>
        </div>
      </ClientOnly>
    </div>

    <!-- 项目信息卡片 -->
    <UCard v-if="monitor">
      <template #header>
        <h2 class="text-lg font-semibold">
          项目信息
        </h2>
      </template>

      <div class="space-y-4">
        <!-- 第一行：项目名称和描述 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              项目名称
            </h3>
            <p class="mt-1 text-sm text-gray-900 dark:text-white">
              {{ monitor.name }}
            </p>
          </div>

          <div v-if="monitor.description">
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              项目描述
            </h3>
            <p
              class="mt-1 text-sm text-gray-900 dark:text-white line-clamp-2"
              :title="monitor.description"
            >
              {{ monitor.description }}
            </p>
          </div>
        </div>

        <!-- 第二行：其他信息（自适应2-4列） -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              创建者
            </h3>
            <p class="mt-1 text-sm text-gray-900 dark:text-white">
              {{ monitor.owner_username || '-' }}
            </p>
          </div>

          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              参与者
            </h3>
            <p
              class="mt-1 text-sm text-gray-900 dark:text-white truncate"
              :title="monitor.participant_usernames?.join(', ') || '无'"
            >
              {{ monitor.participant_usernames?.length ? monitor.participant_usernames.join(', ') : '无' }}
            </p>
          </div>

          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              项目时间
            </h3>
            <p class="mt-1 text-sm text-gray-900 dark:text-white">
              {{ formatDate(monitor.start_date) }} - {{ formatDate(monitor.end_date) }}
            </p>
          </div>

          <div>
            <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
              创建时间
            </h3>
            <p class="mt-1 text-sm text-gray-900 dark:text-white">
              {{ formatDateTime(monitor.created_at) }}
            </p>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 任务列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <h2 class="text-lg font-semibold">
              任务列表 ({{ tasks.length }})
            </h2>
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
          <ClientOnly>
            <div class="flex items-center gap-2">
              <div class="text-xs text-gray-500 dark:text-gray-400">
                已选 {{ selectedTaskIds.length }} 个
              </div>
              <UButton
                size="sm"
                variant="outline"
                icon="i-heroicons-scale"
                :disabled="!canCompare"
                :title="selectedTasksPlatformCheck.reason === 'different_platforms' ? '请选择同一平台的任务' : selectedTaskIds.length < 2 ? '至少选择2个任务' : ''"
                @click="openComparisonSlideover"
              >
                对比任务
              </UButton>
              <UButton
                size="sm"
                icon="i-heroicons-sparkles"
                :disabled="!selectedTaskIds.length"
                :loading="generatingSlice"
                @click="openSliceModal"
              >
                生成切片
              </UButton>
            </div>
          </ClientOnly>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载任务列表中...
            </p>
          </div>
        </template>

        <div v-if="tasks.length === 0" class="text-center py-8">
          <p class="text-gray-600 dark:text-gray-400">
            暂无任务
          </p>
          <UButton
            class="mt-4"
            :to="`/social-media/tasks/create?monitor_id=${monitorId}`"
          >
            创建第一个任务
          </UButton>
        </div>

        <div v-else class="overflow-x-auto">
          <UTable
            :data="tasks"
            :columns="columns"
            :loading="tasksLoading"
            class="w-full"
            :ui="{ base: 'w-full table-fixed' }"
          />
        </div>
      </ClientOnly>
    </UCard>

    <!-- 项目切片列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            切片列表 (<ClientOnly fallback="...">{{ slices.length }}</ClientOnly>)
          </h2>
          <ClientOnly>
            <UButton
              size="sm"
              variant="ghost"
              icon="i-heroicons-arrow-path"
              :loading="slicesLoading"
              @click="handleRefreshSlices"
            >
              刷新
            </UButton>
          </ClientOnly>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载切片中...
            </p>
          </div>
        </template>

        <div v-if="slicesLoading" class="text-sm text-gray-400">
          加载中...
        </div>
        <div v-else-if="!slices.length" class="text-sm text-gray-400">
          暂无切片（可在上方勾选任务后生成）
        </div>

        <UTable
          v-else
          :data="slices"
          :columns="sliceColumns"
          :loading="slicesLoading"
          class="w-full"
          :ui="{ base: 'w-full table-fixed' }"
        />
      </ClientOnly>
    </UCard>

    <!-- 生成切片弹窗 -->
    <ClientOnly>
      <UModal
        v-model:open="showSliceModal"
        title="生成项目切片"
        :description="`将基于已选 ${selectedTaskIds.length} 个任务（ID: ${selectedTaskIds.join(', ')}）生成一份项目级合并分析切片。`"
        :ui="{ footer: 'justify-end' }"
      >
        <template #body>
          <div class="space-y-4">
            <UFormField label="切片名称（可选）">
              <UInput
                v-model="sliceNameInput"
                placeholder="输入切片名称"
                class="w-full"
              />
            </UFormField>
            <UFormField label="主体（可选，用于 Focus / 战略诊断）" help="例如：产品名/品牌名。为空则不生成 Focus 报告。">
              <UInput
                v-model="sliceSubjectInput"
                placeholder="输入主体，例如：iPhone 16"
                class="w-full"
              />
            </UFormField>
            <div v-if="keywordCandidates.length" class="px-1">
              <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                基于已选任务关键词的候选（点击快速填入，不保证完全准确）
              </div>
              <div class="flex flex-wrap gap-2">
                <UButton
                  v-for="kw in keywordCandidates"
                  :key="`kwcand-${kw}`"
                  size="xs"
                  variant="soft"
                  color="primary"
                  @click="sliceSubjectInput = kw"
                >
                  设为主体：{{ kw }}
                </UButton>
                <UButton
                  v-for="kw in keywordCandidates"
                  :key="`kwcand-comp-${kw}`"
                  size="xs"
                  variant="soft"
                  color="neutral"
                  @click="addCompetitor(kw)"
                >
                  加为竞品：{{ kw }}
                </UButton>
              </div>
            </div>
            <UFormField label="竞品列表（可选）" help="用逗号或换行分隔。用于 Role 仲裁与 Focus 对比。">
              <UTextarea
                v-model="sliceCompetitorsInput"
                :rows="3"
                placeholder="例如：华为 Mate 60，小米 15\n或每行一个"
                class="w-full"
              />
            </UFormField>
            <div class="p-3 rounded border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 space-y-3">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  高级：自定义平台权重（可选）
                </div>
                <USwitch v-model="enableCustomPlatformWeights" />
              </div>
              <div class="text-xs text-gray-600 dark:text-gray-400">
                一般用户无需调整。系统会使用默认权重做“平台公平”归一化；仅在你非常确定不同平台的热度口径需要校正时才开启。
              </div>
              <UFormField
                v-if="enableCustomPlatformWeights"
                label="平台权重 JSON"
                help='JSON 对象，例如：{"bilibili":1.5,"weibo":0.8}。key 使用平台 slug（后端平台标识），value 必须 > 0。'
              >
                <UTextarea
                  v-model="sliceWeightsJsonInput"
                  :rows="4"
                  placeholder='{"bilibili": 1.5}'
                  class="w-full font-mono"
                />
              </UFormField>
            </div>
          </div>
        </template>
        <template #footer>
          <UButton
            variant="outline"
            @click="showSliceModal = false"
          >
            取消
          </UButton>
          <UButton
            :loading="generatingSlice"
            @click="handleGenerateSlice"
          >
            开始生成
          </UButton>
        </template>
      </UModal>
    </ClientOnly>

    <!-- 批量创建任务弹窗 -->
    <ClientOnly>
      <UModal
        v-model:open="showBatchTaskModal"
        title="批量创建任务"
        description="为多个平台批量创建相同配置的任务"
        :ui="{ footer: 'justify-end' }"
      >
        <template #body>
          <QuickTaskForm
            v-model:state="batchTaskState"
            :disabled="batchTaskSubmitting"
          />
        </template>
        <template #footer>
          <UButton
            variant="outline"
            :disabled="batchTaskSubmitting"
            @click="showBatchTaskModal = false"
          >
            取消
          </UButton>
          <UButton
            :loading="batchTaskSubmitting"
            @click="handleBatchCreateTasks"
          >
            创建
          </UButton>
        </template>
      </UModal>
    </ClientOnly>

    <!-- 任务对比侧边栏 -->
    <ClientOnly>
      <TaskComparisonSlideover
        v-model:open="showComparisonSlideover"
        :monitor-id="monitorId"
        :task-ids="selectedTaskIds"
      />
    </ClientOnly>
  </div>
</template>
