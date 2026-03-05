<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  monitorId: number
  taskIds: number[]
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

const isOpen = computed({
  get: () => props.open,
  set: (value) => {
    emit('update:open', value)
    if (!value) emit('close')
  },
})

const { apiRequest } = useApi()

interface ComparisonResult {
  overview: {
    total_posts_raw: number
    unique_posts: number
    overlap_count: number
    overlap_rate: number
  }
  matrix: Array<{
    task_id: number
    task_name: string
    total_posts: number
    unique_posts: number
    overlaps: Array<{
      target_task_id: number
      overlap_count: number
    }>
  }>
  comment_analysis: {
    posts_involved: number
    total_comments_raw: number
    unique_comments: number
    overlap_rate: number
    complementary_rate: number
  }
}

const result = ref<ComparisonResult | null>(null)
const pending = ref(false)
const error = ref<Error | null>(null)

const fetchComparison = async () => {
  if (props.taskIds.length < 2) return

  pending.value = true
  error.value = null
  result.value = null

  try {
    const data = await apiRequest<ComparisonResult>(
      `/social-media/monitors/${props.monitorId}/compare`,
      {
        method: 'POST',
        body: {
          task_ids: props.taskIds,
          compare_type: 'posts',
        },
      }
    )
    result.value = data
  } catch (e) {
    error.value = e as Error
  } finally {
    pending.value = false
  }
}

watch(
  () => props.open,
  (val) => {
    if (val && props.taskIds.length >= 2) {
      fetchComparison()
    }
  }
)

const formatPercent = (val: number) => {
  return (val * 100).toFixed(1) + '%'
}
</script>

<template>
  <USlideover v-model:open="isOpen" :ui="{ width: 'w-screen max-w-2xl' }">
    <template #title>
      <div class="flex items-center gap-2">
        <span class="text-gray-900 dark:text-white font-medium">任务数据对比分析</span>
        <UBadge color="neutral" variant="subtle" size="xs">
          {{ props.taskIds.length }} 个任务
        </UBadge>
      </div>
    </template>

    <template #description>
      <span class="sr-only">对比所选任务的数据重合度</span>
    </template>

    <template #body>
      <div v-if="pending" class="flex items-center justify-center py-12">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-primary-500" />
        <span class="ml-2 text-gray-500">分析计算中...</span>
      </div>

      <div v-else-if="error" class="text-center py-12 text-red-500">
        分析失败：{{ error.message || '未知错误' }}
      </div>

      <div v-else-if="result" class="space-y-8 pb-8">
        <!-- 1. 总体概览 -->
        <section>
          <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-4">
            总体概览
          </h4>
          <div class="grid grid-cols-4 gap-3">
            <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <div class="text-xs text-gray-500 mb-1 whitespace-nowrap">原始总数</div>
              <div class="text-xl font-semibold">{{ result.overview.total_posts_raw }}</div>
            </div>
            <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <div class="text-xs text-gray-500 mb-1 whitespace-nowrap">去重后</div>
              <div class="text-xl font-semibold text-primary-600">{{ result.overview.unique_posts }}</div>
            </div>
            <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <div class="text-xs text-gray-500 mb-1 whitespace-nowrap">重合数</div>
              <div class="text-xl font-semibold">{{ result.overview.overlap_count }}</div>
            </div>
            <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <div class="text-xs text-gray-500 mb-1 whitespace-nowrap">重合率</div>
              <div class="text-xl font-semibold">{{ formatPercent(result.overview.overlap_rate) }}</div>
            </div>
          </div>
        </section>

        <!-- 2. 两两重合矩阵 -->
        <section>
          <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-4">
            交叉重合矩阵
          </h4>
          <div class="overflow-x-auto border rounded-lg border-gray-200 dark:border-gray-700">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
              <thead class="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th
                    scope="col"
                    class="px-3 py-2 text-left font-medium text-gray-500"
                  >
                    基准任务 \ 对比任务
                  </th>
                  <th
                    v-for="(col, idx) in result.matrix"
                    :key="col.task_id"
                    scope="col"
                    class="px-3 py-2 text-right font-medium text-gray-500"
                  >
                    #{{ idx + 1 }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-900">
                <tr v-for="(row, idx) in result.matrix" :key="row.task_id">
                  <td class="px-3 py-2 whitespace-nowrap text-gray-900 dark:text-white font-medium">
                    #{{ idx + 1 }} {{ row.task_name }}
                    <div class="text-xs text-gray-400 font-normal mt-0.5">
                      独有 {{ row.unique_posts }} / 总 {{ row.total_posts }}
                    </div>
                  </td>
                  <td
                    v-for="col in result.matrix"
                    :key="col.task_id"
                    class="px-3 py-2 text-right whitespace-nowrap"
                  >
                    <span v-if="col.task_id === row.task_id" class="text-gray-300">-</span>
                    <span v-else class="text-gray-600 dark:text-gray-300 font-mono">
                      {{ row.overlaps.find(o => o.target_task_id === col.task_id)?.overlap_count || 0 }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="mt-2 text-xs text-gray-500">
            * 表格展示了基准任务（行）与对比任务（列）之间的重合帖子数量。
            <br>例如：行#1 与 列#2 的交叉点数字表示这两个任务共有多少篇相同的帖子。
          </p>
        </section>

        <!-- 3. 评论互补分析 -->
        <section>
          <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            评论互补性分析
            <UBadge size="xs" color="primary" variant="subtle">
              针对重合帖子
            </UBadge>
          </h4>

          <div
            v-if="result.comment_analysis.posts_involved === 0"
            class="text-sm text-gray-500 text-center py-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg"
          >
            未发现重合帖子，无法进行评论互补分析。
          </div>

          <div
            v-else
            class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4"
          >
            <div class="flex items-start gap-4 mb-6">
              <div class="flex-1">
                <div class="text-sm text-gray-900 dark:text-white mb-1">
                  在 {{ result.comment_analysis.posts_involved }} 篇重合帖子中：
                </div>
                <ul class="list-disc list-inside text-xs text-gray-600 dark:text-gray-400 space-y-1 ml-1">
                  <li>各任务采集评论总和：{{ result.comment_analysis.total_comments_raw }} 条</li>
                  <li>去重后实际评论数：<span class="font-bold text-primary-600">{{ result.comment_analysis.unique_comments }}</span> 条</li>
                </ul>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="p-3 rounded-lg bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800">
                <div class="flex items-baseline justify-between mb-1">
                  <span class="text-sm font-medium text-gray-700 dark:text-gray-300">评论互补率</span>
                  <span class="text-xl font-bold text-primary-600">{{ formatPercent(result.comment_analysis.complementary_rate) }}</span>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400">
                  数值越高，说明合并后新增信息越多
                </p>
              </div>

              <div class="p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
                <div class="flex items-baseline justify-between mb-1">
                  <span class="text-sm font-medium text-gray-700 dark:text-gray-300">评论冗余率</span>
                  <span class="text-xl font-bold text-orange-500">{{ formatPercent(result.comment_analysis.overlap_rate) }}</span>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400">
                  数值越高，说明评论重复度越高
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="text-center py-12 text-gray-400">
        请选择任务后点击对比
      </div>
    </template>
  </USlideover>
</template>
