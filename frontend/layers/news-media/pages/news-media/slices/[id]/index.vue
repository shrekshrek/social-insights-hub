<script setup lang="ts">
import type { NewsNarrative, NewsEntity } from '../../../../types'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const sliceId = Number(route.params.id)

const { getSlice, analyzeSlice, deleteSlice: deleteSliceApi } = useNewsSlices()
const { data: slice, pending: loading, refresh } = getSlice(sliceId)

const analyzing = ref(false)

const handleAnalyze = async () => {
  if (!slice.value) return
  analyzing.value = true
  try {
    await analyzeSlice(sliceId, {
      analysis_goal: slice.value.name,
      subject: slice.value.name,
    })
    await refresh()
  } catch {
    // error already handled
  } finally {
    analyzing.value = false
  }
}

const handleDelete = async () => {
  if (!slice.value) return
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除切片',
    message: `确定要删除切片 "${slice.value.name}" 吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  try {
    await deleteSliceApi(sliceId)
    await navigateTo(`/news-media/monitors/${slice.value.monitor_id}`)
  } catch {
    // error already handled
  }
}

type BadgeColor = 'neutral' | 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error'

const getStatusColor = (status: string): BadgeColor => {
  const map: Record<string, BadgeColor> = {
    pending: 'neutral',
    analyzing: 'info',
    completed: 'success',
    failed: 'error',
  }
  return map[status] || 'neutral'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '待分析',
    analyzing: '分析中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
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

const resultData = computed(() => (slice.value?.result_data || {}) as Record<string, unknown>)
const stats = computed(() => (slice.value?.stats || {}) as Record<string, unknown>)
const narratives = computed(() => (resultData.value.narratives || []) as NewsNarrative[])
const entities = computed(() => (resultData.value.entities || []) as NewsEntity[])
</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="text-center py-8">
      <p class="text-gray-500">加载中...</p>
    </div>

    <template v-else-if="slice">
      <!-- 页面头部 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            :to="`/news-media/monitors/${slice.monitor_id}`"
          />
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            切片详情
          </h1>
        </div>

        <div class="flex items-center gap-3">
          <UButton
            v-if="slice.status === 'completed' || slice.status === 'failed'"
            icon="i-heroicons-sparkles"
            :loading="analyzing"
            @click="handleAnalyze"
          >
            重新分析
          </UButton>
          <UButton
            color="error"
            variant="outline"
            icon="i-heroicons-trash"
            @click="handleDelete"
          >
            删除
          </UButton>
        </div>
      </div>

      <!-- 基本信息 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-semibold">基本信息</h2>
        </template>

        <dl class="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <div>
            <dt class="text-gray-500 dark:text-gray-400">切片名称</dt>
            <dd class="font-medium mt-1">{{ slice.name }}</dd>
          </div>
          <div>
            <dt class="text-gray-500 dark:text-gray-400">状态</dt>
            <dd class="mt-1">
              <UBadge :color="getStatusColor(slice.status)" size="sm" variant="subtle">
                {{ getStatusText(slice.status) }}
              </UBadge>
            </dd>
          </div>
          <div>
            <dt class="text-gray-500 dark:text-gray-400">包含任务</dt>
            <dd class="font-medium mt-1">{{ slice.included_task_ids.length }} 个</dd>
          </div>
          <div>
            <dt class="text-gray-500 dark:text-gray-400">创建时间</dt>
            <dd class="mt-1">{{ formatDate(slice.created_at) }}</dd>
          </div>
        </dl>

        <div v-if="slice.error_message" class="mt-4 p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-600 dark:text-red-400">
          {{ slice.error_message }}
        </div>
      </UCard>

      <!-- 统计摘要 -->
      <UCard v-if="stats.articles_total">
        <template #header>
          <h2 class="text-lg font-semibold">统计摘要</h2>
        </template>

        <ClientOnly>
          <div class="space-y-4">
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">文章总数</span>
                <p class="text-xl font-bold mt-1">{{ stats.articles_total }}</p>
              </div>
              <div v-if="stats.sentiment_overall !== undefined" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">综合情感</span>
                <p class="text-xl font-bold mt-1">
                  {{ stats.sentiment_overall !== null ? Number(stats.sentiment_overall).toFixed(2) : '-' }}
                </p>
              </div>
              <div v-if="stats.sentiment_distribution" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">情感分布</span>
                <p class="font-medium mt-1 text-sm">
                  <span class="text-green-600">{{ (stats.sentiment_distribution as Record<string, number>).positive }}</span> /
                  <span class="text-gray-500">{{ (stats.sentiment_distribution as Record<string, number>).neutral }}</span> /
                  <span class="text-red-600">{{ (stats.sentiment_distribution as Record<string, number>).negative }}</span>
                </p>
              </div>
              <div v-if="stats.source_tier_distribution" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">来源等级</span>
                <p class="font-medium mt-1 text-xs">
                  T1:{{ (stats.source_tier_distribution as Record<string, number>).tier1 }}
                  T2:{{ (stats.source_tier_distribution as Record<string, number>).tier2 }}
                  T3:{{ (stats.source_tier_distribution as Record<string, number>).tier3 }}
                  MP:{{ (stats.source_tier_distribution as Record<string, number>).wechat_mp ?? 0 }}
                </p>
              </div>
            </div>

            <div v-if="(stats.top_entities as Array<{name: string; mention_count: number}> | undefined)?.length">
              <p class="text-sm text-gray-500 mb-2">高频实体</p>
              <div class="flex flex-wrap gap-2">
                <UBadge
                  v-for="ent in (stats.top_entities as Array<{name: string; mention_count: number}>).slice(0, 8)"
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

      <!-- Insight 分析结果 -->
      <UCard v-if="slice.status === 'completed' && resultData">
        <template #header>
          <h2 class="text-lg font-semibold">Insight 分析</h2>
        </template>

        <ClientOnly>
          <div class="space-y-6">
            <!-- 叙事主题 -->
            <div v-if="narratives.length > 0">
              <h3 class="font-semibold text-sm mb-3">叙事主题</h3>
              <div class="space-y-2">
                <div
                  v-for="(n, idx) in narratives"
                  :key="idx"
                  class="p-3 border border-gray-200 dark:border-gray-700 rounded"
                >
                  <div class="flex items-center justify-between mb-1">
                    <span class="font-medium text-sm">{{ n.theme }}</span>
                    <span class="text-xs text-gray-500">{{ n.article_count }} 篇</span>
                  </div>
                  <p class="text-sm text-gray-600 dark:text-gray-400">{{ n.summary }}</p>
                </div>
              </div>
            </div>

            <!-- 关键实体 -->
            <div v-if="entities.length > 0">
              <h3 class="font-semibold text-sm mb-3">关键实体</h3>
              <div class="space-y-2">
                <div
                  v-for="(ent, idx) in entities.slice(0, 10)"
                  :key="idx"
                  class="flex items-center justify-between p-2 border border-gray-200 dark:border-gray-700 rounded text-sm"
                >
                  <div>
                    <span class="font-medium">{{ ent.name }}</span>
                    <span class="text-gray-500 ml-2">{{ ent.role }}</span>
                  </div>
                  <div class="flex items-center gap-3 text-xs text-gray-500">
                    <span>{{ ent.mention_count }} 次提及</span>
                    <span>情感 {{ ent.sentiment?.toFixed(2) ?? '-' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 覆盖度 -->
            <div v-if="resultData.coverage" class="p-3 bg-gray-50 dark:bg-gray-800 rounded text-sm">
              <h3 class="font-semibold mb-2">媒体覆盖</h3>
              <p v-if="(resultData.coverage as Record<string, unknown>).summary" class="text-gray-600 dark:text-gray-400">
                {{ (resultData.coverage as Record<string, unknown>).summary }}
              </p>
            </div>

            <div v-if="!narratives.length && !entities.length && !resultData.coverage" class="text-center py-4 text-gray-400 text-sm">
              分析已完成，暂无详细结果数据
            </div>
          </div>
        </ClientOnly>
      </UCard>

      <!-- 分析中提示 -->
      <UCard v-if="slice.status === 'analyzing'">
        <div class="text-center py-6 text-gray-400 text-sm">
          正在运行 insight 分析...
        </div>
      </UCard>
    </template>

    <div v-else class="text-center py-8">
      <p class="text-gray-500">切片不存在</p>
    </div>
  </div>
</template>
