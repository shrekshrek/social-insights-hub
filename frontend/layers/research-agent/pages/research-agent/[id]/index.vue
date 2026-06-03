<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <div v-if="loadingTask && !task" class="text-center py-8">
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
                {{ task.title || task.analysis_goal }}
              </h1>
              <UBadge :color="statusColor(task.status)" variant="subtle" size="sm">
                {{ statusLabel(task.status) }}
              </UBadge>
            </div>
            <div class="flex items-center gap-2 mt-1 text-sm text-gray-500">
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
              v-if="canWriteTask"
              variant="outline"
              icon="i-heroicons-arrow-path"
              :loading="rerunning"
              :disabled="task.status === 'pending' || task.status === 'running'"
              @click="handleRerun"
            >
              重新研究
            </UButton>
            <UButton
              v-if="hasPermission(PERMISSIONS.RESEARCH_AGENT_DELETE) || task?.user_id === currentUserId"
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
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">任务信息</h2>
            <ClientOnly>
              <UButton
                v-if="canWriteTask"
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
          <div class="flex gap-3">
            <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">标题</dt>
            <dd class="text-gray-900 dark:text-white font-medium">{{ task.title || '-' }}</dd>
          </div>
          <div class="flex gap-3">
            <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">研究主题</dt>
            <dd class="text-gray-900 dark:text-white font-medium whitespace-pre-line">{{ task.analysis_goal }}</dd>
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
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">类型</dt>
              <dd>
                <UBadge :color="profileColor(task.profile_name)" variant="soft" size="sm">
                  {{ profileLabel(task.profile_name) }}
                </UBadge>
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">状态</dt>
              <dd>
                <UBadge :color="statusColor(task.status)" variant="subtle" size="sm">
                  {{ statusLabel(task.status) }}
                </UBadge>
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">关联策略</dt>
              <dd class="text-gray-900 dark:text-white">
                <UButton
                  v-if="task.strategy_id"
                  variant="link"
                  size="sm"
                  class="p-0"
                  :to="`/strategies/${task.strategy_id}`"
                >
                  策略 #{{ task.strategy_id }}
                </UButton>
                <span v-else class="text-gray-400">独立任务</span>
              </dd>
            </div>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 pt-3 border-t border-gray-100 dark:border-gray-800">
            <div v-if="task.stats" class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">来源数</dt>
              <dd class="text-gray-900 dark:text-white">{{ task.stats.documents_analyzed }} 篇</dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400">创建时间</dt>
              <dd class="text-gray-900 dark:text-white">{{ formatDate(task.created_at) }}</dd>
            </div>
          </div>

          <!-- 创建者 / 参与者（只读 chip 列表） -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 pt-3 border-t border-gray-100 dark:border-gray-800">
            <div class="flex gap-3">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400 pt-0.5">创建者</dt>
              <dd class="text-gray-900 dark:text-white">
                {{ task.owner_username || task.user_id }}
              </dd>
            </div>
            <div class="flex gap-3 sm:col-span-2">
              <dt class="w-20 shrink-0 text-gray-500 dark:text-gray-400 pt-0.5">参与者</dt>
              <dd class="flex-1">
                <ClientOnly fallback="...">
                  <div v-if="task.participant_ids?.length" class="flex flex-wrap gap-1.5">
                    <UBadge
                      v-for="(pid, i) in task.participant_ids"
                      :key="pid"
                      color="neutral"
                      variant="subtle"
                      size="sm"
                    >
                      {{ task.participant_usernames?.[i] || pid }}
                    </UBadge>
                  </div>
                  <span v-else class="text-gray-400">暂无参与者</span>
                </ClientOnly>
              </dd>
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
          <template #header>
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-arrow-path" class="w-4 h-4 text-primary animate-spin" />
              <span class="font-semibold">
                {{ task.status === 'pending' ? '等待执行...' : '研究进行中' }}
              </span>
              <span class="text-xs text-gray-400 font-normal ml-auto">每 3 秒自动刷新</span>
            </div>
          </template>

          <!-- 线性进度日志 -->
          <div v-if="task.progress?.length" class="space-y-0">
            <div
              v-for="(entry, idx) in task.progress"
              :key="idx"
              class="flex items-start gap-3 py-2.5 border-b border-gray-50 dark:border-gray-800 last:border-0"
            >
              <UIcon name="i-heroicons-check-circle" class="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-gray-900 dark:text-white">{{ entry.label }}</span>
                  <UBadge v-if="entry.round > 1" :label="`第 ${entry.round} 轮`" size="sm" variant="subtle" color="neutral" />
                </div>
                <p class="text-xs text-gray-500 mt-0.5 whitespace-pre-line">{{ entry.detail }}</p>
              </div>
              <span class="text-xs text-gray-400 flex-shrink-0">{{ formatTime(entry.ts) }}</span>
            </div>

            <!-- 当前正在执行的下一步 -->
            <div v-if="task.status === 'running'" class="flex items-center gap-3 py-2.5">
              <UIcon name="i-heroicons-arrow-path" class="w-4 h-4 text-primary animate-spin flex-shrink-0" />
              <span class="text-sm text-gray-500">{{ nextStepLabel }}</span>
            </div>
          </div>

          <!-- 尚无进度（pending 或 running 初始阶段） -->
          <div v-else class="flex items-center gap-3 py-6 text-sm text-gray-400">
            <UIcon name="i-heroicons-arrow-path" class="w-4 h-4 animate-spin flex-shrink-0" />
            <span>{{ task.status === 'pending' ? '等待 Celery Worker 接收任务...' : '生成研究计划中...' }}</span>
          </div>
        </UCard>

        <!-- 结果展示 -->
        <template v-if="task.status === 'completed'">
          <!-- 研究过程（折叠） -->
          <UCard v-if="task.progress?.length" :ui="{ body: 'p-0 sm:p-0' }">
            <template #header>
              <button
                class="w-full flex items-center justify-between gap-2 text-left"
                @click="progressExpanded = !progressExpanded"
              >
                <span class="text-lg font-semibold flex items-center gap-2">
                  <UIcon name="i-heroicons-list-bullet" class="w-5 h-5 text-gray-400" />
                  研究过程
                </span>
                <UIcon
                  :name="progressExpanded ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'"
                  class="w-4 h-4 text-gray-400 shrink-0 transition-transform"
                />
              </button>
            </template>
            <div v-if="progressExpanded" class="px-4 sm:px-6 pb-4 sm:pb-6 pt-2">
              <div
                v-for="(entry, idx) in task.progress"
                :key="idx"
                class="flex items-start gap-3 py-2.5 border-b border-gray-50 dark:border-gray-800 last:border-0"
              >
                <UIcon name="i-heroicons-check-circle" class="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-gray-900 dark:text-white">{{ entry.label }}</span>
                    <UBadge v-if="entry.round > 1" :label="`第 ${entry.round} 轮`" size="sm" variant="subtle" color="neutral" />
                  </div>
                  <p class="text-xs text-gray-500 mt-0.5 whitespace-pre-line">{{ entry.detail }}</p>
                </div>
                <span class="text-xs text-gray-400 flex-shrink-0">{{ formatTime(entry.ts) }}</span>
              </div>
            </div>
          </UCard>

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
                    v-for="srcRef in finding.source_refs"
                    :key="srcRef"
                    :href="`#source-${srcRef}`"
                    class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors"
                  >{{ sourceDisplayIndex(srcRef) }}</a>
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
                  <span v-if="source.published_date" class="text-xs text-gray-400 shrink-0">· {{ source.published_date }}</span>
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

    <!-- 编辑研究任务弹窗 -->
    <ClientOnly>
      <UModal
        v-model:open="showEditModal"
        title="编辑研究任务"
        :ui="{ footer: 'justify-end' }"
      >
        <template #body>
          <div class="space-y-4">
            <UFormField label="标题" help="仅标题可修改；研究主题/问题/类型创建后无法修改">
              <UInput v-model="editState.title" placeholder="请输入标题" class="w-full" />
            </UFormField>
            <UFormField label="参与者" help="参与者变更会立即生效，无需点保存">
              <ParticipantsManager
                v-if="task"
                :participants="(task.participant_ids || []).map((id: number, i: number) => ({ id, username: task!.participant_usernames?.[i] || String(id) }))"
                :owner-id="task.user_id"
                :can-manage="true"
                :on-add="handleAddParticipants"
                :on-remove="handleRemoveParticipant"
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
          <UButton :loading="editSubmitting" @click="handleSaveEdit">
            保存
          </UButton>
        </template>
      </UModal>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onUnmounted } from 'vue'
import { PERMISSIONS } from '~/config/permissions'


definePageMeta({ layout: 'default' })

const route = useRoute()
const router = useRouter()
const toast = useToast()
const taskId = Number(route.params.id)
const { currentUserId, hasPermission } = usePermissions()

const {
  getTask,
  getTaskResult,
  updateTask,
  rerunTask,
  deleteTask,
  addParticipants,
  removeParticipant,
  statusLabel,
  statusColor,
  confidenceLabel,
  confidenceColor,
  tierLabel,
  tierColor,
  profileLabel,
  profileColor,
} = useResearchAgentApi()

const { data: task, pending: loadingTask, refresh: refreshTask } = getTask(taskId)
const { data: result, refresh: refreshResult } = getTaskResult(taskId)

useHead({
  title: computed(() => {
    const displayTitle = task.value?.title || task.value?.analysis_goal
    return displayTitle ? `${displayTitle} - 专题研究` : '研究详情'
  }),
})



// 进度：下一步预测标签
// 顺序必须与后端 graph.py 一致：plan → search → filter → fetch → analyze → evaluate → synthesize
const NODE_SEQUENCE = ['plan', 'search', 'filter', 'fetch', 'analyze', 'evaluate', 'synthesize']
const NODE_LABELS: Record<string, string> = {
  plan: '生成研究计划', search: '搜索报告资料', fetch: '抓取全文',
  filter: '筛选相关内容', analyze: '分析文档', evaluate: '评估覆盖度', synthesize: '综合分析报告',
}

const nextStepLabel = computed(() => {
  const progress = task.value?.progress
  if (!progress?.length) return '生成研究计划中...'
  const lastStep = progress[progress.length - 1]?.step ?? ''
  if (lastStep === 'evaluate') return '判断是否补充搜索...'
  const nextIdx = NODE_SEQUENCE.indexOf(lastStep) + 1
  const nextNode = NODE_SEQUENCE[nextIdx]
  return nextNode ? `${NODE_LABELS[nextNode]}中...` : '完成中...'
})

function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// 自动轮询：pending/running 状态每 10 秒刷新
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

function startPolling() {
  stopPolling()
  pollTimer.value = setInterval(async () => {
    await refreshTask()
    // 任务完成后拉取结果并停止轮询
    if (task.value && task.value.status !== 'pending' && task.value.status !== 'running') {
      if (task.value.status === 'completed') {
        await refreshResult()
      }
      stopPolling()
    }
  }, 3000)
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
  return raw.replace(/[([（【]*\s*\bsrc_\d+\b\s*[)\]）】]*/g, (match) => {
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

const progressExpanded = ref(false)
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
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '确认重新研究',
    message: `将清空当前结果并重新执行研究，此操作不可撤销。确定继续？`,
    confirmText: '重新研究',
    type: 'warning',
  })
  if (!confirmed) return
  rerunning.value = true
  try {
    await rerunTask(taskId)
    toast.add({ title: '已重新发起研究，请等待执行完成', color: 'success' })
    await refreshTask()
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
    message: `确定要删除研究任务「${task.value?.title || task.value?.analysis_goal}」吗？此操作不可撤销。`,
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

// 编辑：仅 owner 或 admin 可管
const showEditModal = ref(false)
const editSubmitting = ref(false)
const editState = reactive({ title: '' })

// 写操作权限（重新研究 / 编辑 / 管理参与者）：owner 或具备 RESEARCH_AGENT_WRITE
const canWriteTask = computed(() => {
  if (!task.value) return false
  return task.value.user_id === currentUserId.value || hasPermission(PERMISSIONS.RESEARCH_AGENT_WRITE)
})

function openEditModal() {
  editState.title = task.value?.title || ''
  showEditModal.value = true
}

async function handleSaveEdit() {
  if (!task.value) return
  const newTitle = editState.title.trim()
  // 如果未变更则不发请求
  if (newTitle === (task.value.title || '')) {
    showEditModal.value = false
    return
  }
  editSubmitting.value = true
  try {
    await updateTask(taskId, { title: newTitle || undefined })
    toast.add({ title: '已保存', color: 'success' })
    await refreshTask()
    showEditModal.value = false
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    editSubmitting.value = false
  }
}

async function handleAddParticipants(userIds: number[]) {
  await addParticipants(taskId, userIds)
  await refreshTask()
}

async function handleRemoveParticipant(userId: number) {
  await removeParticipant(taskId, userId)
  await refreshTask()
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
