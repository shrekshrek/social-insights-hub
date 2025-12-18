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
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

interface ProjectOverviewData {
  total_volume?: number
  global_sentiment?: number
  platform_volume?: Record<string, number>
  keyword_volume?: Record<string, number>
}

interface ProjectTopicAspectItem {
  category: string
  heat: number
  sentiment: number
  mention_count?: number
  top_keywords?: string[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

interface ProjectDetailsData {
  top_entities?: ProjectTopicOrEntity[]
  top_topics?: ProjectTopicOrEntity[]
}

interface ProjectSnapshotResultData {
  meta?: {
    project_id: number
    generated_at: string
    scope?: {
      mode: string
      included_task_ids: number[]
    }
    task_diagnostics?: Array<{
      task_id: number
      platform: string
      keyword: string
      data_volume_total: number
      nsr?: number
      entities_count: number
      opinions_count: number
      has_entities: boolean
      has_opinions: boolean
      raw_aggregated_opinions_count?: number
      raw_insights_top_topics_count?: number
      used_opinions_source?: string
      opinions_sample?: string[]
      raw_aggregated_entities_count?: number
      raw_insights_top_entities_count?: number
      used_entities_source?: string
      entities_sample?: string[]
    }>
  }
  overview?: ProjectOverviewData
  topic_aspects?: ProjectTopicAspectItem[]
  details?: ProjectDetailsData
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
  {
    key: computed(() => `project-snapshot-detail-${projectId.value}-${snapshotId.value}`),
    silent404: true,
    // snapshot_id 未指定时不应触发请求（否则会请求到 /api/v1/ 并在控制台报 404）
    // 同时保持 SSR/CSR 行为一致，避免 hydration mismatch
    immediate: computed(() => Boolean(snapshotId.value)),
    getCachedData: () => undefined,
  }
)

const handleRefresh = async () => {
  if (!snapshotId.value) return
  await refreshSnapshot()
}

// 展示数据
const snapshotResult = computed<ProjectSnapshotResultData | null>(() => snapshot.value?.result_data || null)
// 新结构优先：details / topic_aspects / overview
const overview = computed<ProjectOverviewData | null>(() => snapshotResult.value?.overview || null)
const topicAspects = computed<ProjectTopicAspectItem[]>(() => snapshotResult.value?.topic_aspects || [])
const detailsTopEntities = computed<ProjectTopicOrEntity[]>(() => snapshotResult.value?.details?.top_entities || [])
const detailsTopTopics = computed<ProjectTopicOrEntity[]>(() => snapshotResult.value?.details?.top_topics || [])

// 旧结构兜底：insights.project_top_*
const projectTopTopics = computed<ProjectTopicOrEntity[]>(() => {
  return detailsTopTopics.value.length
    ? detailsTopTopics.value
    : (snapshotResult.value?.insights?.project_top_topics || [])
})
const projectTopEntities = computed<ProjectTopicOrEntity[]>(() => {
  return detailsTopEntities.value.length
    ? detailsTopEntities.value
    : (snapshotResult.value?.insights?.project_top_entities || [])
})
const negativeTopics = computed(() => projectTopTopics.value.filter(t => (t.sentiment ?? 0) < 0))
const positiveTopics = computed(() => projectTopTopics.value.filter(t => (t.sentiment ?? 0) > 0))

const sortedPlatformVolume = computed(() => {
  const m = overview.value?.platform_volume || {}
  return Object.entries(m).sort((a, b) => (b[1] || 0) - (a[1] || 0))
})
const sortedKeywordVolume = computed(() => {
  const m = overview.value?.keyword_volume || {}
  return Object.entries(m).sort((a, b) => (b[1] || 0) - (a[1] || 0))
})

const taskDiagnostics = computed(() => snapshotResult.value?.meta?.task_diagnostics || [])
const tasksMissingOpinions = computed(() => taskDiagnostics.value.filter(t => !t.has_opinions))
const tasksMissingEntities = computed(() => taskDiagnostics.value.filter(t => !t.has_entities))
const showDiagnostics = ref(false)

const formatDist = (dist?: Record<string, number>) => {
  if (!dist) return '-'
  const entries = Object.entries(dist).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 4)
  return entries.map(([k, v]) => `${k}:${v}`).join('，')
}

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
          <ClientOnly>
            <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ snapshot?.name || `快照 ${snapshotId}` }}
            </h1>
            <template #fallback>
              <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
                {{ `快照 ${snapshotId}` }}
              </h1>
            </template>
          </ClientOnly>
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
        <!-- 新版板块 1：项目全景（Overview） -->
        <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">🌍 项目全景</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <div class="text-gray-500 dark:text-gray-400">总声量</div>
              <div class="text-gray-900 dark:text-white font-mono text-lg">
                {{ overview?.total_volume ?? '-' }}
              </div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">全局情感</div>
              <div class="text-gray-900 dark:text-white font-mono text-lg">
                {{ typeof overview?.global_sentiment === 'number' ? overview.global_sentiment.toFixed(2) : '-' }}
              </div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">平台/关键词构成</div>
              <div class="text-gray-900 dark:text-white text-xs mt-1">
                <div>平台：{{ sortedPlatformVolume.length ? sortedPlatformVolume.slice(0, 6).map(([k, v]) => `${k}:${v}`).join('，') : '-' }}</div>
                <div class="mt-1">关键词：{{ sortedKeywordVolume.length ? sortedKeywordVolume.slice(0, 6).map(([k, v]) => `${k}:${v}`).join('，') : '-' }}</div>
              </div>
            </div>
          </div>
          <div v-if="!overview" class="text-xs text-gray-400 mt-3">
            当前快照未包含 overview（可能是旧快照）。建议重新生成一次快照以获得完整三板块数据。
          </div>
          <div v-else class="text-xs text-gray-500 dark:text-gray-400 mt-3">
            <div v-if="tasksMissingOpinions.length">
              诊断：有 {{ tasksMissingOpinions.length }} 个任务未产出观点（aggregated_opinions 为空），因此“全域观点/类目对比”可能偏弱。
            </div>
            <div v-if="tasksMissingEntities.length" class="mt-1">
              诊断：有 {{ tasksMissingEntities.length }} 个任务未产出实体（aggregated_entities 为空）。
            </div>
            <div v-if="taskDiagnostics.length" class="mt-2">
              <button
                class="text-primary-600 dark:text-primary-400 hover:underline"
                @click="showDiagnostics = !showDiagnostics"
              >
                {{ showDiagnostics ? '收起' : '展开' }} 任务诊断明细
              </button>
              <div v-if="showDiagnostics" class="mt-2 overflow-x-auto">
                <table class="min-w-full text-xs">
                  <thead>
                    <tr class="text-left text-gray-500 dark:text-gray-400">
                      <th class="py-1 pr-3">task_id</th>
                      <th class="py-1 pr-3">平台</th>
                      <th class="py-1 pr-3">关键词</th>
                      <th class="py-1 pr-3">声量</th>
                      <th class="py-1 pr-3">实体数</th>
                      <th class="py-1 pr-3">观点数</th>
                      <th class="py-1 pr-3">观点来源</th>
                      <th class="py-1 pr-3">观点样例</th>
                      <th class="py-1 pr-3">NSR</th>
                    </tr>
                  </thead>
                  <tbody class="text-gray-700 dark:text-gray-300">
                    <tr
                      v-for="t in taskDiagnostics"
                      :key="t.task_id"
                      class="border-t border-gray-100 dark:border-gray-800"
                    >
                      <td class="py-1 pr-3 font-mono">{{ t.task_id }}</td>
                      <td class="py-1 pr-3">{{ t.platform }}</td>
                      <td class="py-1 pr-3">{{ t.keyword || '-' }}</td>
                      <td class="py-1 pr-3 font-mono">{{ t.data_volume_total }}</td>
                      <td class="py-1 pr-3 font-mono" :class="t.has_entities ? '' : 'text-red-500'">{{ t.entities_count }}</td>
                      <td class="py-1 pr-3 font-mono" :class="t.has_opinions ? '' : 'text-red-500'">{{ t.opinions_count }}</td>
                      <td class="py-1 pr-3 font-mono text-gray-500 dark:text-gray-400">
                        {{ t.used_opinions_source || '-' }}
                        <span v-if="typeof t.raw_aggregated_opinions_count === 'number'">
                          (agg:{{ t.raw_aggregated_opinions_count }}, ins:{{ t.raw_insights_top_topics_count ?? '-' }})
                        </span>
                      </td>
                      <td class="py-1 pr-3">
                        {{ (t.opinions_sample || []).filter(Boolean).slice(0, 3).join('、') || '-' }}
                      </td>
                      <td class="py-1 pr-3 font-mono">{{ typeof t.nsr === 'number' ? t.nsr.toFixed(2) : '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- 新版板块 2：全域实体/观点排行（Global Ranking） -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">🏷️ 全域实体排行</h3>
            <div v-if="projectTopEntities.length" class="space-y-2">
              <div
                v-for="(e, idx) in projectTopEntities.slice(0, 20)"
                :key="`global-entity-${idx}`"
                class="p-3 rounded bg-gray-50 dark:bg-gray-800"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      <span class="text-gray-900 dark:text-white font-medium">{{ e.name }}</span>
                      <UBadge v-if="e.role" color="neutral" variant="subtle" size="xs">{{ e.role }}</UBadge>
                      <UBadge v-if="e.type" color="info" variant="subtle" size="xs">{{ e.type }}</UBadge>
                    </div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      平台：{{ formatDist(e.platform_distribution) }}
                    </div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      关键词：{{ formatDist(e.keyword_distribution) }}
                    </div>
                  </div>
                  <div class="text-right shrink-0">
                    <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(e.score || 0).toFixed(2) }}</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ e.mentions }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 py-4">暂无实体数据</div>
          </div>

          <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">💬 全域观点排行</h3>
            <div v-if="projectTopTopics.length" class="space-y-2">
              <div
                v-for="(t, idx) in projectTopTopics.slice(0, 20)"
                :key="`global-topic-${idx}`"
                class="p-3 rounded bg-gray-50 dark:bg-gray-800"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      <span class="text-gray-900 dark:text-white font-medium">{{ t.name }}</span>
                      <UBadge v-if="t.category" color="neutral" variant="subtle" size="xs">{{ t.category }}</UBadge>
                      <UBadge v-if="(t.sentiment ?? 0) < 0" color="error" variant="subtle" size="xs">负面</UBadge>
                      <UBadge v-else-if="(t.sentiment ?? 0) > 0" color="success" variant="subtle" size="xs">正面</UBadge>
                      <UBadge v-else color="neutral" variant="subtle" size="xs">中性</UBadge>
                    </div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      平台：{{ formatDist(t.platform_distribution) }}
                    </div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      关键词：{{ formatDist(t.keyword_distribution) }}
                    </div>
                  </div>
                  <div class="text-right shrink-0">
                    <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(t.score || 0).toFixed(2) }}</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ t.mentions }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-gray-400 py-4">暂无观点数据</div>
          </div>
        </div>

        <!-- 新版板块 3：多维对比分析（按类目聚合） -->
        <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">📊 多维对比分析（类目）</h3>
          <div v-if="topicAspects.length" class="space-y-2">
            <div
              v-for="(a, idx) in topicAspects.slice(0, 20)"
              :key="`aspect-${idx}`"
              class="p-3 rounded bg-gray-50 dark:bg-gray-800"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-gray-900 dark:text-white font-medium">{{ a.category }}</span>
                    <UBadge v-if="a.sentiment < 0" color="error" variant="subtle" size="xs">整体偏负</UBadge>
                    <UBadge v-else-if="a.sentiment > 0" color="success" variant="subtle" size="xs">整体偏正</UBadge>
                    <UBadge v-else color="neutral" variant="subtle" size="xs">整体中性</UBadge>
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    代表词：{{ (a.top_keywords || []).slice(0, 6).join('、') || '-' }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    平台：{{ formatDist(a.platform_distribution) }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    关键词：{{ formatDist(a.keyword_distribution) }}
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(a.heat || 0).toFixed(1) }}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">热度</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    情感 {{ Number(a.sentiment || 0).toFixed(2) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="text-sm text-gray-400 py-4">
            暂无类目对比数据（旧快照可能没有 topic_aspects）。建议重新生成一次快照。
          </div>
        </div>

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
