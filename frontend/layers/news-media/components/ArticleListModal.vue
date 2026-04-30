<script setup lang="ts">
/**
 * 新闻文章列表弹窗。
 *
 * 用于切片详情页里各处下钻：事件聚类 / 实体全景 / 竞争层。
 * 输入 article_ids，从后端 GET /news-media/slices/{id}/articles?ids=... 拿详情。
 * 后端会按 slice.included_task_ids 过滤越权 ids。
 */
import { computed, ref, watch } from 'vue'
import type { NewsArticle } from '../types'

const props = defineProps<{
  open: boolean
  sliceId: number
  articleIds: number[]
  title?: string
  /** 副标题，例如事件名 / 实体名 */
  subtitle?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { getSliceArticlesByIds } = useNewsSlices()

const articles = ref<NewsArticle[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const handleClose = (val: boolean) => {
  emit('update:open', val)
}

const fetchArticles = async () => {
  if (props.articleIds.length === 0) {
    articles.value = []
    return
  }
  loading.value = true
  error.value = null
  try {
    const result = await getSliceArticlesByIds(props.sliceId, props.articleIds)
    // 后端不保证顺序，按入参 ids 顺序排
    const orderMap = new Map(props.articleIds.map((id, idx) => [id, idx]))
    articles.value = [...result].sort(
      (a, b) => (orderMap.get(a.id) ?? 999) - (orderMap.get(b.id) ?? 999),
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
    articles.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.sliceId, props.articleIds],
  ([isOpen]) => {
    if (isOpen) fetchArticles()
  },
  { immediate: true, deep: true },
)

// ========== Display helpers ==========

type BadgeColor = 'neutral' | 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error'

const tierLabel = (t: string) => ({
  tier1: '权威', tier2: '行业', tier3: '其他', wechat_mp: '公众号',
} as Record<string, string>)[t] || t

const tierColor = (t: string): BadgeColor => ({
  tier1: 'error', tier2: 'warning', tier3: 'neutral', wechat_mp: 'success',
} as Record<string, BadgeColor>)[t] || 'neutral'

const relevanceLabel = (r: string | null) => ({
  high: '高', medium: '中', low: '低',
} as Record<string, string>)[r ?? ''] || '-'

const relevanceColor = (r: string | null): BadgeColor => ({
  high: 'success', medium: 'warning', low: 'neutral',
} as Record<string, BadgeColor>)[r ?? ''] || 'neutral'

const articleTypeLabel = (t: string | null) => ({
  report: '报道', opinion: '评论', pr: '公关稿', analysis: '分析',
} as Record<string, string>)[t ?? ''] || (t ?? '-')

const formatSent = (s: number | null) => {
  if (s === null) return '-'
  return s > 0 ? `+${s.toFixed(1)}` : s.toFixed(1)
}

const sentimentClass = (s: number | null) => {
  if (s === null) return 'text-gray-400'
  if (s > 0) return 'text-green-600 dark:text-green-400'
  if (s < 0) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-300'
}

const dateOnly = (iso: string | null) => {
  if (!iso) return '-'
  return iso.slice(0, 10)
}

const headerTitle = computed(() => props.title || `文章列表（${props.articleIds.length} 篇）`)
</script>

<template>
  <UModal
    :open="open"
    :title="headerTitle"
    :description="subtitle"
    :ui="{
      content: 'w-[calc(100vw-2rem)] max-w-4xl rounded-lg shadow-lg ring ring-default',
      footer: 'justify-end',
    }"
    @update:open="handleClose"
  >
    <template #body>
      <div v-if="loading" class="text-center py-8 text-gray-500">加载中...</div>

      <div v-else-if="error" class="text-center py-8 text-red-500">
        {{ error }}
      </div>

      <div v-else-if="articles.length === 0" class="text-center py-8 text-gray-400 text-sm">
        无文章数据
      </div>

      <div v-else class="space-y-3 max-h-[70vh] overflow-y-auto">
        <div
          v-for="a in articles"
          :key="a.id"
          class="p-3 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div class="flex items-start gap-3">
            <a
              :href="a.url"
              target="_blank"
              rel="noopener"
              class="flex-1 text-blue-600 hover:underline font-medium text-sm leading-snug"
            >
              {{ a.title }}
            </a>
            <UButton
              :to="a.url"
              external
              target="_blank"
              icon="i-heroicons-arrow-top-right-on-square"
              size="xs"
              variant="ghost"
              color="neutral"
              class="shrink-0"
              :title="'打开原文'"
            />
          </div>

          <div class="flex items-center gap-3 mt-1.5 text-xs text-gray-500 flex-wrap">
            <span>{{ a.source_name }}</span>
            <UBadge :color="tierColor(a.source_tier)" size="sm" variant="subtle">
              {{ tierLabel(a.source_tier) }}
            </UBadge>
            <UBadge v-if="a.relevance" :color="relevanceColor(a.relevance)" size="sm" variant="subtle">
              相关性 {{ relevanceLabel(a.relevance) }}
            </UBadge>
            <span v-if="a.article_type" class="text-gray-500">
              {{ articleTypeLabel(a.article_type) }}
            </span>
            <span v-if="a.sentiment !== null" :class="sentimentClass(a.sentiment)">
              情感 {{ formatSent(a.sentiment) }}
            </span>
            <span class="ml-auto">{{ dateOnly(a.published_at) }}</span>
          </div>

          <p v-if="a.summary" class="text-xs text-gray-600 dark:text-gray-400 mt-2 leading-relaxed">
            {{ a.summary }}
          </p>
        </div>
      </div>
    </template>

    <template #footer>
      <UButton color="neutral" variant="outline" @click="handleClose(false)">
        关闭
      </UButton>
    </template>
  </UModal>
</template>
