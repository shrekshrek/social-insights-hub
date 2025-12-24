<script setup lang="ts">
/**
 * 帖子列表弹窗组件
 *
 * 用于显示指定帖子ID列表对应的帖子详情，使用表格格式展示
 * 使用共用的 usePostAnalysisColumns composable 和 DeepResultModal 组件
 */
import { usePostAnalysisColumns } from '../composables/usePostAnalysisColumns'
import DeepResultModal from './DeepResultModal.vue'

const props = defineProps<{
  open: boolean
  taskId?: number
  postIds?: number[]
  /** 多任务样本：用于项目快照等跨任务场景 */
  groups?: Array<{ taskId: number; postIds: number[]; label?: string; platform?: string }>
  title?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { getTaskPostAnalyses } = useAnalysis()

const page = ref(1)
const pageSize = ref(20)

const groups = computed(() => (Array.isArray(props.groups) ? props.groups : []))
const hasGroups = computed(() => groups.value.length > 0)
const selectedTaskId = ref<number | undefined>(undefined)

watch(
  () => [props.open, groups.value.length],
  ([isOpen]) => {
    if (!isOpen) return
    if (hasGroups.value) {
      selectedTaskId.value = groups.value[0]?.taskId
    } else {
      selectedTaskId.value = props.taskId
    }
  }
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
})

const posts = computed(() => postData.value?.items || [])
const total = computed(() => postData.value?.total || 0)

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

// 当弹窗打开或 postIds 变化时刷新数据
watch(() => [props.open, postIdsRef.value, safeTaskId.value], ([isOpen]) => {
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
    :title="title || `相关帖子（样本）(${postIdsRef.length})`"
    :description="`共 ${total} 条帖子`"
    :ui="{ content: 'w-[calc(100vw-2rem)] max-w-6xl rounded-lg shadow-lg ring ring-default', footer: 'justify-end' }"
    @update:open="handleClose"
  >
    <template #body>
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
        <p class="text-sm">暂无帖子数据</p>
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
