<script setup lang="ts">
/**
 * 原文列表弹窗组件
 *
 * 用于显示指定原文ID列表对应的原文详情，使用表格格式展示
 * 使用共用的 usePostAnalysisColumns composable 和 DeepResultModal 组件
 */
import { usePostAnalysisColumns } from '../../composables/usePostAnalysisColumns'
import DeepResultModal from '../deep-result/DeepResultModal.vue'

const props = defineProps<{
  open: boolean
  taskId?: number
  postIds?: number[]
  /** 多任务样本：用于项目切片等跨任务场景 */
  groups?: Array<{ taskId: number; postIds: number[]; label?: string; platform?: string }>
  title?: string
  /** 是否显示推广/有机分组 tab */
  hasSpamData?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { getTaskPostAnalyses } = useAnalysis()

const page = ref(1)
const pageSize = ref(20)
const spamGroup = ref<'high' | 'low' | undefined>(undefined)

const spamTabs = [
  { value: undefined, label: '全部' },
  { value: 'high' as const, label: '推广' },
  { value: 'low' as const, label: '有机' },
]

// 懒记录各 tab 的 total，访问一次后就显示数量，无需额外请求
const tabTotals = reactive<Partial<Record<string, number>>>({})

const groups = computed(() => (Array.isArray(props.groups) ? props.groups : []))
const hasGroups = computed(() => groups.value.length > 0)
const selectedTaskId = ref<number | undefined>(undefined)

// selectedTaskId 始终保持有效值（默认第一个 group），不等 modal open。
// 这样 USelect 初次渲染就能显示 "任务 #X" label，避免"下拉空但内容是第一个 task"
// 的 UI/数据错位（用户会误以为"空 = 全部样本合并"，实际并非如此）。
watch(
  () => [groups.value.length, groups.value[0]?.taskId, props.taskId],
  () => {
    if (hasGroups.value) {
      // 当前选中的 task 不在新的 groups 列表里，重置到第一个
      const exists = selectedTaskId.value
        && groups.value.some(g => g.taskId === selectedTaskId.value)
      if (!exists) {
        selectedTaskId.value = groups.value[0]?.taskId
      }
    } else if (!selectedTaskId.value) {
      selectedTaskId.value = props.taskId
    }
  },
  { immediate: true },
)

// modal open 时重置 spam tab + tabTotals 缓存（与 selectedTaskId 解耦）
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    spamGroup.value = undefined
    for (const k of Object.keys(tabTotals)) {
      tabTotals[k] = undefined
    }
  },
)

const selectedGroup = computed(() => {
  if (!hasGroups.value) return null
  const tid = selectedTaskId.value
  if (!tid) return groups.value[0] ?? null
  return groups.value.find(g => g.taskId === tid) ?? groups.value[0] ?? null
})

const effectiveTaskId = computed(() => {
  if (hasGroups.value) return selectedGroup.value?.taskId ?? null
  return props.taskId ?? null
})
const postIdsRef = computed(() => {
  if (hasGroups.value) return selectedGroup.value?.postIds ?? []
  return props.postIds ?? []
})

const safeTaskId = computed(() => (effectiveTaskId.value && effectiveTaskId.value > 0 ? effectiveTaskId.value : 0))

const {
  data: postData,
  pending: loading,
  refresh,
} = getTaskPostAnalyses(safeTaskId, {
  page,
  pageSize,
  filterAnalyzed: false,
  postIds: postIdsRef,
  spamGroup,
})

const posts = computed(() => postData.value?.items || [])
const total = computed(() => postData.value?.total || 0)

// 每次请求完成后记录当前 tab 的 total
watch([total, loading], ([newTotal, isLoading]) => {
  if (!isLoading && newTotal !== undefined) {
    tabTotals[String(spamGroup.value)] = newTotal
  }
})

// 深度分析结果弹窗状态
const deepResultModalOpen = ref(false)
const deepResultModalType = ref<'post' | 'comment'>('post')
const deepResultModalPostId = ref<number | null>(null)

const selectedPostForDeepResult = computed(() => {
  if (!deepResultModalPostId.value) return null
  return posts.value.find(p => p.post_id === deepResultModalPostId.value) || null
})

const openDeepResultModal = (postId: number, type: 'post' | 'comment') => {
  deepResultModalPostId.value = postId
  deepResultModalType.value = type
  deepResultModalOpen.value = true
}

// 使用共用的表格列定义
const { columns } = usePostAnalysisColumns({
  onOpenDeepResult: openDeepResultModal,
  contentColumnSize: 160,
})

// 当弹窗打开或 postIds / spamGroup 变化时重置分页并刷新
watch(() => [props.open, postIdsRef.value, safeTaskId.value, spamGroup.value], ([isOpen]) => {
  if (isOpen && safeTaskId.value > 0 && postIdsRef.value.length > 0) {
    page.value = 1
    refresh()
  }
})

const handleClose = () => {
  emit('update:open', false)
}
</script>

<template>
  <UModal
    :open="open"
    :title="title || `相关原文（样本）(${postIdsRef.length})`"
    :ui="{ content: 'w-[calc(100vw-2rem)] max-w-6xl rounded-lg shadow-lg ring ring-default', footer: 'justify-end' }"
    @update:open="handleClose"
  >
    <template #body>
      <!-- 副标题：原文数 + 推广/有机分组切换 -->
      <div class="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-3">
        <span>共 {{ total }} 条原文</span>
        <div v-if="hasSpamData" class="flex items-center gap-1 text-[11px]">
          <button
            v-for="tab in spamTabs"
            :key="String(tab.value)"
            class="px-2 py-0.5 rounded border transition-colors"
            :class="spamGroup === tab.value
              ? 'bg-primary-500 text-white border-primary-500'
              : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="spamGroup = tab.value"
          >
            {{ tab.label }}{{ tabTotals[String(tab.value)] !== undefined ? ` ${tabTotals[String(tab.value)]}` : '' }}
          </button>
        </div>
      </div>

      <div v-if="hasGroups" class="mb-3 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <span class="shrink-0">任务：</span>
        <USelect
          v-model="selectedTaskId"
          :items="groups.map(g => ({ label: g.label || `任务 #${g.taskId}（${g.postIds.length}条样本）`, value: g.taskId }))"
          value-key="value"
          size="xs"
          class="min-w-64"
        />
        <span class="hidden sm:inline">
          · 仅展示样本帖（每个维度最多 50 条），用于快速核验趋势与原话
        </span>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-12">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-gray-400" />
      </div>

      <div v-else-if="posts.length === 0" class="text-center py-12 text-gray-500">
        <UIcon name="i-heroicons-inbox" class="w-10 h-10 mx-auto mb-2 opacity-60" />
        <p class="text-sm">暂无原文数据</p>
      </div>

      <div v-else>
        <UTable
          sticky
          :data="posts"
          :columns="columns"
          class="max-h-[60vh]"
        >
          <template #empty-state>
            <div class="text-center py-10 text-gray-500">
              <UIcon name="i-heroicons-inbox" class="w-10 h-10 mx-auto mb-2 opacity-60" />
              <p class="text-sm">暂无数据</p>
            </div>
          </template>
        </UTable>

        <!-- 分页 -->
        <div v-if="total > pageSize" class="flex justify-between items-center mt-4 pt-4">
          <span class="text-xs text-gray-500">
            显示 {{ (page - 1) * pageSize + 1 }} 到 {{ Math.min(page * pageSize, total) }} 共 {{ total }} 条
          </span>
          <UPagination
            v-model:page="page"
            :total="total"
            :items-per-page="pageSize"
            size="xs"
          />
        </div>
      </div>
    </template>

    <template #footer>
      <UButton
        label="关闭"
        color="neutral"
        variant="outline"
        @click="handleClose"
      />
    </template>
  </UModal>

  <!-- 深度分析结果弹窗（使用共用组件） -->
  <DeepResultModal
    v-model:open="deepResultModalOpen"
    :post-data="selectedPostForDeepResult"
    :type="deepResultModalType"
  />
</template>
