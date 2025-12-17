<script setup lang="ts">
import { computed, ref } from 'vue'

definePageMeta({
  layout: 'default',
})

// 类型定义
interface OriginalTerm {
  text: string
  count: number
}

interface SourceTask {
  task_id: number
  mentions: number
}

interface ProjectTopicOrEntity {
  name: string
  category?: string
  sentiment?: number
  role?: string
  type?: string
  heat: number
  mentions: number
  score: number
  original_terms?: OriginalTerm[]
  source_tasks?: SourceTask[]
  post_ids_sample?: { task_id: number; post_id: number }[]
}

interface ProjectSnapshotResultData {
  meta?: {
    project_id: number
    generated_at: string
    scope?: {
      mode: string
      included_task_ids: number[]
    }
  }
  insights?: {
    project_top_entities?: ProjectTopicOrEntity[]
    project_top_topics?: ProjectTopicOrEntity[]
  }
}

interface ProjectSnapshot {
  id: number
  name: string | null
  project_id: number
  user_id: number
  included_task_ids: number[]
  result_data: ProjectSnapshotResultData
  created_at: string
  updated_at: string
}

const route = useRoute()
const projectId = computed(() => Number(route.params.id))
const snapshotId = computed(() => route.query.snapshot_id ? Number(route.query.snapshot_id) : null)

const { useApiData } = useApi()

// 直接获取指定快照详情
const { data: snapshot, pending: snapshotLoading, refresh: refreshSnapshot } = useApiData<ProjectSnapshot>(
  computed(() => snapshotId.value ? `/social-media/analysis/projects/${projectId.value}/snapshots/${snapshotId.value}` : ''),
  { key: computed(() => `project-snapshot-detail-${projectId.value}-${snapshotId.value}`), silent404: true, getCachedData: () => undefined }
)

const handleRefresh = async () => {
  await refreshSnapshot()
}

// 展示数据
const snapshotResult = computed<ProjectSnapshotResultData | null>(() => snapshot.value?.result_data || null)
const projectTopTopics = computed<ProjectTopicOrEntity[]>(() => snapshotResult.value?.insights?.project_top_topics || [])
const projectTopEntities = computed<ProjectTopicOrEntity[]>(() => snapshotResult.value?.insights?.project_top_entities || [])
const negativeTopics = computed(() => projectTopTopics.value.filter(t => (t.sentiment ?? 0) < 0))
const positiveTopics = computed(() => projectTopTopics.value.filter(t => (t.sentiment ?? 0) > 0))

// 汇总统计
const stats = computed(() => {
  const taskCount = snapshot.value?.included_task_ids?.length || 0
  const entityCount = projectTopEntities.value.length
  const topicCount = projectTopTopics.value.length
  const totalMentions = projectTopEntities.value.reduce((sum, e) => sum + (e.mentions || 0), 0)
    + projectTopTopics.value.reduce((sum, t) => sum + (t.mentions || 0), 0)
  return { taskCount, entityCount, topicCount, totalMentions }
})

// 展开/收起 original_terms
const expandedItems = ref<Set<string>>(new Set())
const toggleExpand = (key: string) => {
  if (expandedItems.value.has(key)) {
    expandedItems.value.delete(key)
  } else {
    expandedItems.value.add(key)
  }
}
const isExpanded = (key: string) => expandedItems.value.has(key)
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          :to="`/social-media/projects/${projectId}`"
        />
        <div>
          <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
            {{ snapshot?.name || `快照 ${snapshotId}` }}
          </h1>
          <p class="text-sm text-gray-500 dark:text-gray-400">
            项目级合并分析快照详情
          </p>
        </div>
      </div>
      <ClientOnly>
        <UButton
          icon="i-heroicons-arrow-path"
          variant="ghost"
          :loading="snapshotLoading"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </ClientOnly>
    </div>

    <ClientOnly>
      <template #fallback>
        <div class="text-center py-12 text-gray-400">加载中...</div>
      </template>

      <div v-if="snapshotLoading" class="text-center py-12 text-gray-400">加载中...</div>
      <div v-else-if="!snapshotId" class="text-center py-12 text-gray-400">
        未指定快照 ID，请从项目详情页选择一个快照查看
      </div>
      <div v-else-if="!snapshot" class="text-center py-12 text-gray-400">快照不存在或已删除</div>

      <div v-else class="space-y-6">
        <!-- 汇总统计卡片 -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.taskCount }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">包含任务数</div>
          </div>
          <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.entityCount }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">热门实体</div>
          </div>
          <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.topicCount }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">热门话题</div>
          </div>
          <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.totalMentions }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">总提及数</div>
          </div>
        </div>

        <!-- 元信息 -->
        <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <span class="text-gray-500 dark:text-gray-400">快照 ID：</span>
              <span class="text-gray-900 dark:text-white font-mono">{{ snapshot.id }}</span>
            </div>
            <div>
              <span class="text-gray-500 dark:text-gray-400">生成时间：</span>
              <span class="text-gray-900 dark:text-white">{{ snapshotResult?.meta?.generated_at ? new Date(snapshotResult.meta.generated_at).toLocaleString('zh-CN') : new Date(snapshot.created_at).toLocaleString('zh-CN') }}</span>
            </div>
            <div>
              <span class="text-gray-500 dark:text-gray-400">包含任务 ID：</span>
              <span class="text-gray-900 dark:text-white font-mono">{{ snapshot.included_task_ids?.join(', ') || '-' }}</span>
            </div>
          </div>
        </div>

        <!-- 热门实体 -->
        <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">🏷️ 热门实体 ({{ projectTopEntities.length }})</h3>
          <div v-if="projectTopEntities.length" class="space-y-3">
            <div
              v-for="(e, idx) in projectTopEntities"
              :key="`entity-${idx}`"
              class="p-4 rounded-lg bg-gray-50 dark:bg-gray-800"
            >
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-gray-900 dark:text-white font-medium text-base">{{ e.name }}</span>
                    <UBadge v-if="e.role" color="neutral" variant="subtle" size="xs">{{ e.role }}</UBadge>
                    <UBadge v-if="e.type" color="info" variant="subtle" size="xs">{{ e.type }}</UBadge>
                  </div>
                  <!-- 来源任务 -->
                  <div v-if="e.source_tasks?.length" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    来源任务：
                    <span v-for="(st, stIdx) in e.source_tasks" :key="st.task_id">
                      {{ stIdx > 0 ? ', ' : '' }}任务{{ st.task_id }}({{ st.mentions }}次)
                    </span>
                  </div>
                  <!-- 原始观点（可展开） -->
                  <div v-if="e.original_terms?.length" class="mt-2">
                    <button
                      class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                      @click="toggleExpand(`entity-${idx}`)"
                    >
                      {{ isExpanded(`entity-${idx}`) ? '收起' : '展开' }} {{ e.original_terms.length }} 个原始观点
                    </button>
                    <div v-if="isExpanded(`entity-${idx}`)" class="mt-2 pl-3 border-l-2 border-gray-200 dark:border-gray-700">
                      <div
                        v-for="(term, tIdx) in e.original_terms.slice(0, 20)"
                        :key="tIdx"
                        class="text-xs text-gray-600 dark:text-gray-400 py-0.5"
                      >
                        • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
                      </div>
                      <div v-if="e.original_terms.length > 20" class="text-xs text-gray-400 py-0.5">
                        ... 等共 {{ e.original_terms.length }} 个
                      </div>
                    </div>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <div class="text-lg font-bold font-mono text-gray-900 dark:text-white">{{ Number(e.score || 0).toFixed(2) }}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ e.mentions }}</div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="text-sm text-gray-400 py-4">暂无实体数据</div>
        </div>

        <!-- 热门话题（负面） -->
        <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">🔴 热门话题 - 负面 ({{ negativeTopics.length }})</h3>
          <div v-if="negativeTopics.length" class="space-y-3">
            <div
              v-for="(t, idx) in negativeTopics"
              :key="`neg-${idx}`"
              class="p-4 rounded-lg bg-red-50 dark:bg-red-900/10"
            >
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-gray-900 dark:text-white font-medium text-base">{{ t.name }}</span>
                    <UBadge v-if="t.category" color="neutral" variant="subtle" size="xs">{{ t.category }}</UBadge>
                  </div>
                  <div v-if="t.source_tasks?.length" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    来源任务：
                    <span v-for="(st, stIdx) in t.source_tasks" :key="st.task_id">
                      {{ stIdx > 0 ? ', ' : '' }}任务{{ st.task_id }}({{ st.mentions }}次)
                    </span>
                  </div>
                  <div v-if="t.original_terms?.length" class="mt-2">
                    <button
                      class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                      @click="toggleExpand(`neg-${idx}`)"
                    >
                      {{ isExpanded(`neg-${idx}`) ? '收起' : '展开' }} {{ t.original_terms.length }} 个原始观点
                    </button>
                    <div v-if="isExpanded(`neg-${idx}`)" class="mt-2 pl-3 border-l-2 border-red-200 dark:border-red-800">
                      <div
                        v-for="(term, tIdx) in t.original_terms.slice(0, 20)"
                        :key="tIdx"
                        class="text-xs text-gray-600 dark:text-gray-400 py-0.5"
                      >
                        • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
                      </div>
                      <div v-if="t.original_terms.length > 20" class="text-xs text-gray-400 py-0.5">
                        ... 等共 {{ t.original_terms.length }} 个
                      </div>
                    </div>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <div class="text-lg font-bold font-mono text-gray-900 dark:text-white">{{ Number(t.score || 0).toFixed(2) }}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ t.mentions }}</div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="text-sm text-gray-400 py-4">暂无负面话题</div>
        </div>

        <!-- 热门话题（正面） -->
        <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">🟢 热门话题 - 正面 ({{ positiveTopics.length }})</h3>
          <div v-if="positiveTopics.length" class="space-y-3">
            <div
              v-for="(t, idx) in positiveTopics"
              :key="`pos-${idx}`"
              class="p-4 rounded-lg bg-green-50 dark:bg-green-900/10"
            >
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-gray-900 dark:text-white font-medium text-base">{{ t.name }}</span>
                    <UBadge v-if="t.category" color="neutral" variant="subtle" size="xs">{{ t.category }}</UBadge>
                  </div>
                  <div v-if="t.source_tasks?.length" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    来源任务：
                    <span v-for="(st, stIdx) in t.source_tasks" :key="st.task_id">
                      {{ stIdx > 0 ? ', ' : '' }}任务{{ st.task_id }}({{ st.mentions }}次)
                    </span>
                  </div>
                  <div v-if="t.original_terms?.length" class="mt-2">
                    <button
                      class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                      @click="toggleExpand(`pos-${idx}`)"
                    >
                      {{ isExpanded(`pos-${idx}`) ? '收起' : '展开' }} {{ t.original_terms.length }} 个原始观点
                    </button>
                    <div v-if="isExpanded(`pos-${idx}`)" class="mt-2 pl-3 border-l-2 border-green-200 dark:border-green-800">
                      <div
                        v-for="(term, tIdx) in t.original_terms.slice(0, 20)"
                        :key="tIdx"
                        class="text-xs text-gray-600 dark:text-gray-400 py-0.5"
                      >
                        • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
                      </div>
                      <div v-if="t.original_terms.length > 20" class="text-xs text-gray-400 py-0.5">
                        ... 等共 {{ t.original_terms.length }} 个
                      </div>
                    </div>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <div class="text-lg font-bold font-mono text-gray-900 dark:text-white">{{ Number(t.score || 0).toFixed(2) }}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ t.mentions }}</div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="text-sm text-gray-400 py-4">暂无正面话题</div>
        </div>
      </div>
    </ClientOnly>
  </div>
</template>
