<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <div v-if="loadingTask" class="text-center py-8">
      <p class="text-gray-500">加载中...</p>
    </div>

    <template v-else-if="task">
      <!-- 页面头部 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <UButton variant="ghost" icon="i-heroicons-arrow-left" to="/research-agent" />
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ task.query }}
              </h1>
              <UBadge :color="statusColor(task.status)" variant="subtle" size="sm">
                {{ statusLabel(task.status) }}
              </UBadge>
            </div>
            <div class="flex items-center gap-2 mt-1 text-sm text-gray-500">
              <span v-if="researchTypeLabel">{{ researchTypeLabel }}</span>
              <span v-if="researchTypeLabel">|</span>
              <span>{{ formatDate(task.created_at) }}</span>
              <template v-if="task.stats">
                <span>|</span>
                <span>{{ task.stats.documents_analyzed }} 篇来源 · {{ task.stats.candidates_total }} 候选</span>
              </template>
            </div>
          </div>
        </div>

        <ClientOnly>
          <div class="flex items-center gap-2">
            <UButton
              variant="ghost"
              icon="i-heroicons-arrow-path"
              :loading="refreshingAll"
              @click="handleRefreshAll"
            >
              刷新
            </UButton>
            <UButton
              variant="outline"
              icon="i-heroicons-arrow-path"
              :loading="rerunning"
              @click="handleRerun"
            >
              重新研究
            </UButton>
            <UButton
              variant="outline"
              color="error"
              icon="i-heroicons-trash"
              @click="handleDelete"
            >
              删除
            </UButton>
          </div>
        </ClientOnly>
      </div>

      <!-- 任务信息卡片 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-semibold">任务信息</h2>
        </template>
        <dl class="space-y-2 text-sm">
          <div class="flex gap-3">
            <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">研究主题</dt>
            <dd class="text-gray-900 dark:text-white font-medium">{{ task.query }}</dd>
          </div>
          <div v-if="researchTypeLabel" class="flex gap-3">
            <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">研究类型</dt>
            <dd>
              <UBadge variant="subtle" size="sm">{{ researchTypeLabel }}</UBadge>
            </dd>
          </div>
          <div v-if="task.research_questions?.length" class="flex gap-3">
            <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">研究问题</dt>
            <dd class="text-gray-900 dark:text-white">
              <ul class="list-disc list-inside space-y-1">
                <li v-for="(q, idx) in task.research_questions" :key="idx">{{ q }}</li>
              </ul>
            </dd>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 pt-3 border-t border-gray-100 dark:border-gray-800">
            <div class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">状态</dt>
              <dd>
                <UBadge :color="statusColor(task.status)" variant="subtle" size="sm">
                  {{ statusLabel(task.status) }}
                </UBadge>
              </dd>
            </div>
            <div v-if="task.stats" class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">来源数</dt>
              <dd class="text-gray-900 dark:text-white">{{ task.stats.documents_analyzed }} 篇</dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">创建时间</dt>
              <dd class="text-gray-900 dark:text-white">{{ formatDate(task.created_at) }}</dd>
            </div>
          </div>
        </dl>

        <!-- 错误信息 -->
        <UAlert
          v-if="task.status === 'failed' && task.error_message"
          color="error"
          variant="soft"
          title="研究执行失败"
          :description="task.error_message"
          icon="i-heroicons-exclamation-triangle"
          class="mt-4"
        />
      </UCard>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-12 text-gray-500">加载中...</div>
        </template>

        <!-- 运行中状态 -->
        <UCard v-if="task.status === 'pending' || task.status === 'running'">
          <div class="text-center py-12">
            <UIcon name="i-heroicons-arrow-path" class="w-10 h-10 text-primary mx-auto mb-3 animate-spin" />
            <p class="text-lg font-medium text-gray-900 dark:text-white">
              {{ task.status === 'pending' ? '等待执行...' : '正在研究中...' }}
            </p>
            <p class="text-sm text-gray-500 mt-2">
              AI 正在搜索相关资料并分析，通常需要 2-5 分钟
            </p>
            <p class="text-xs text-gray-400 mt-1">
              每 10 秒自动刷新
            </p>
          </div>
        </UCard>

        <!-- 结果展示 -->
        <template v-if="task.status === 'completed'">
          <!-- 覆盖度概览 -->
          <UCard v-if="result?.coverage">
            <template #header>
              <h2 class="text-lg font-semibold flex items-center gap-2">
                <UIcon name="i-heroicons-chart-bar" class="w-5 h-5" />
                研究概览
              </h2>
            </template>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div class="text-center">
                <p class="text-2xl font-bold text-primary">{{ result.coverage.questions_covered }}/{{ result.coverage.questions_total }}</p>
                <p class="text-sm text-gray-500">问题覆盖</p>
              </div>
              <div class="text-center">
                <p class="text-2xl font-bold text-green-600">{{ result.coverage.high_confidence_count }}</p>
                <p class="text-sm text-gray-500">高置信度</p>
              </div>
              <div class="text-center">
                <p class="text-2xl font-bold text-blue-600">{{ result?.sources?.length || 0 }}</p>
                <p class="text-sm text-gray-500">引用来源</p>
              </div>
              <div class="text-center">
                <p class="text-2xl font-bold text-gray-700 dark:text-gray-300">
                  {{ tierCount('tier1') }}
                </p>
                <p class="text-sm text-gray-500">权威来源</p>
              </div>
            </div>
          </UCard>

          <!-- 按研究问题展示发现 -->
          <UCard v-if="result?.findings_by_question">
            <template #header>
              <h2 class="text-lg font-semibold flex items-center gap-2">
                <UIcon name="i-heroicons-light-bulb" class="w-5 h-5" />
                研究发现
              </h2>
            </template>
            <div class="space-y-6">
              <div
                v-for="(finding, question) in result.findings_by_question"
                :key="question"
                class="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
              >
                <div class="flex items-start justify-between gap-2 mb-3">
                  <h3 class="font-medium text-gray-900 dark:text-white">{{ question }}</h3>
                  <UBadge
                    :color="confidenceColor(finding.confidence)"
                    variant="subtle"
                    size="sm"
                  >
                    {{ confidenceLabel(finding.confidence) }}置信度
                  </UBadge>
                </div>

                <p class="text-gray-700 dark:text-gray-300 mb-3">{{ finding.answer_summary }}</p>

                <!-- 数据点 -->
                <div v-if="finding.data_points?.length" class="mb-3">
                  <p class="text-sm font-medium text-gray-500 mb-2">关键数据</p>
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div
                      v-for="(dp, idx) in finding.data_points"
                      :key="idx"
                      class="bg-gray-50 dark:bg-gray-800 rounded px-3 py-2 text-sm"
                    >
                      <span class="text-gray-600 dark:text-gray-400">{{ dp.metric }}：</span>
                      <span class="font-medium text-gray-900 dark:text-white">{{ dp.value }}</span>
                      <span v-if="dp.period" class="text-gray-400 ml-1">({{ dp.period }})</span>
                      <span v-if="dp.source" class="text-gray-400 ml-1">- {{ dp.source }}</span>
                    </div>
                  </div>
                </div>

                <!-- 来源引用 -->
                <div v-if="finding.source_refs?.length" class="flex items-center gap-1.5 text-sm text-gray-500">
                  <span>来源：</span>
                  <a
                    v-for="ref in finding.source_refs"
                    :key="ref"
                    :href="`#source-${ref}`"
                    class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors"
                  >{{ sourceDisplayIndex(ref) }}</a>
                </div>
              </div>
            </div>
          </UCard>

          <!-- 综合报告 -->
          <UCard v-if="result?.synthesis">
            <template #header>
              <h2 class="text-lg font-semibold flex items-center gap-2">
                <UIcon name="i-heroicons-document-text" class="w-5 h-5" />
                综合报告
              </h2>
            </template>
            <MarkdownRenderer :content="synthesisWithRefs" />
          </UCard>

          <!-- 来源列表 -->
          <UCard v-if="result?.sources?.length">
            <template #header>
              <h2 class="text-lg font-semibold flex items-center gap-2">
                <UIcon name="i-heroicons-link" class="w-5 h-5" />
                来源 ({{ result.sources.length }})
              </h2>
            </template>
            <div class="divide-y divide-gray-100 dark:divide-gray-800">
              <div
                v-for="source in result.sources"
                :id="`source-${source.id}`"
                :key="source.id"
                class="py-2 flex items-center justify-between gap-3 scroll-mt-20"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-medium shrink-0">{{ sourceDisplayIndex(source.id) }}</span>
                  <UBadge :color="tierColor(source.source_tier)" variant="subtle" size="sm" class="shrink-0">
                    {{ tierLabel(source.source_tier) }}
                  </UBadge>
                  <span class="text-sm font-medium text-gray-900 dark:text-white truncate">{{ source.title }}</span>
                  <span class="text-xs text-gray-400 shrink-0">{{ source.source }}</span>
                </div>
                <a
                  :href="source.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="shrink-0"
                >
                  <UButton variant="ghost" icon="i-heroicons-arrow-top-right-on-square" size="xs" />
                </a>
              </div>
            </div>
          </UCard>

          <!-- 信息缺口 -->
          <UCard v-if="result?.information_gaps?.length">
            <template #header>
              <h2 class="text-lg font-semibold flex items-center gap-2">
                <UIcon name="i-heroicons-exclamation-circle" class="w-5 h-5 text-amber-500" />
                信息缺口
              </h2>
            </template>
            <ul class="space-y-2">
              <li
                v-for="(gap, idx) in result.information_gaps"
                :key="idx"
                class="flex items-start gap-2 text-gray-700 dark:text-gray-300"
              >
                <UIcon name="i-heroicons-minus" class="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                <span>{{ gap }}</span>
              </li>
            </ul>
          </UCard>
        </template>
      </ClientOnly>
    </template>

    <!-- 不存在 -->
    <div v-else class="text-center py-12">
      <p class="text-gray-500">研究任务不存在</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onUnmounted } from 'vue'
import { RESEARCH_TYPE_OPTIONS } from '../../../composables/useResearchAgent'

definePageMeta({ layout: 'default' })

const route = useRoute()
const router = useRouter()
const toast = useToast()
const taskId = Number(route.params.id)

const {
  getTask,
  getTaskResult,
  rerunTask,
  deleteTask,
  statusLabel,
  statusColor,
  confidenceLabel,
  confidenceColor,
  tierLabel,
  tierColor,
} = useResearchAgent()

const { data: task, pending: loadingTask, refresh: refreshTask } = getTask(taskId)
const { data: result, refresh: refreshResult } = getTaskResult(taskId)

useHead({
  title: computed(() => task.value?.query ? `${task.value.query} - 研究分析` : '研究详情'),
})

// 研究类型标签
const researchTypeLabel = computed(() => {
  const rt = (task.value?.search_config as Record<string, unknown>)?.research_type as string | undefined
  if (!rt) return null
  return RESEARCH_TYPE_OPTIONS.find(opt => opt.value === rt)?.label ?? null
})

// 自动轮询：pending/running 状态每 10 秒刷新
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

function startPolling() {
  stopPolling()
  pollTimer.value = setInterval(async () => {
    await refreshTask()
    await refreshResult()
    // 状态已完成或失败时停止轮询
    if (task.value && task.value.status !== 'pending' && task.value.status !== 'running') {
      stopPolling()
    }
  }, 10000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

// 监听任务状态，自动启停轮询
watch(
  () => task.value?.status,
  (status) => {
    if (status === 'pending' || status === 'running') {
      startPolling()
    } else {
      stopPolling()
    }
  },
  { immediate: true },
)

onUnmounted(() => stopPolling())

// 来源 ID → 显示序号映射 (src_0 → 1, src_1 → 2, ...)
const sourceIndexMap = computed(() => {
  const map: Record<string, number> = {}
  result.value?.sources?.forEach((s, i) => {
    map[s.id] = i + 1
  })
  return map
})

function sourceDisplayIndex(srcId: string): number {
  return sourceIndexMap.value[srcId] ?? 0
}

// 综合报告中 src_X 替换为带锚链接的上标数字
const synthesisWithRefs = computed(() => {
  const raw = result.value?.synthesis
  if (!raw) return ''
  const map = sourceIndexMap.value
  return raw.replace(/[(\[（【]*\s*\bsrc_\d+\b\s*[)\]）】]*/g, (match) => {
    const srcId = match.match(/src_\d+/)?.[0]
    if (!srcId) return match
    const idx = map[srcId]
    if (!idx) return match
    return `<a href="#source-${srcId}" class="source-ref">${idx}</a>`
  })
})

function tierCount(tier: string): number {
  return result.value?.coverage?.source_quality?.[tier] ?? 0
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const refreshingAll = ref(false)

async function handleRefreshAll() {
  refreshingAll.value = true
  try {
    await Promise.all([refreshTask(), refreshResult()])
  } finally {
    refreshingAll.value = false
  }
}

const rerunning = ref(false)

async function handleRerun() {
  rerunning.value = true
  try {
    const newTask = await rerunTask(taskId)
    toast.add({ title: `已创建新研究任务 #${newTask.id}`, color: 'success' })
    router.push(`/research-agent/${newTask.id}`)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    rerunning.value = false
  }
}

async function handleDelete() {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '确认删除',
    message: `确定要删除研究任务「${task.value?.query}」吗？此操作不可撤销。`,
    confirmText: '删除',
    type: 'error',
  })
  if (!confirmed) return
  try {
    await deleteTask(taskId)
    toast.add({ title: '删除成功', color: 'success' })
    router.push('/research-agent')
  } catch {
    // 错误已由 apiRequest 统一处理
  }
}
</script>

<style scoped>
:deep(.source-ref) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 9999px;
  background-color: color-mix(in srgb, var(--ui-primary) 10%, transparent);
  color: var(--ui-primary);
  font-size: 0.75rem;
  font-weight: 500;
  text-decoration: none;
  vertical-align: middle;
  cursor: pointer;
  transition: background-color 0.15s;
}

:deep(.source-ref:hover) {
  background-color: color-mix(in srgb, var(--ui-primary) 20%, transparent);
}
</style>
