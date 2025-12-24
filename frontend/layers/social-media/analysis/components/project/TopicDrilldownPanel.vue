<script setup lang="ts">
import { computed } from 'vue'

interface OriginalTerm {
  text: string
  count: number
}

interface TopicItem {
  name: string
  category?: string
  heat: number
  sentiment?: number
  mentions: number
  original_terms?: OriginalTerm[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
  post_ids_sample?: Array<{ task_id: number; post_id: number }>
}

const props = defineProps<{
  item: TopicItem | null
  type?: 'pain' | 'gain' | 'controversy' | 'unmet' | null
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update:open', value: boolean): void
  (e: 'open-posts', item: TopicItem, type: 'pain' | 'gain' | 'controversy' | 'unmet'): void
}>()

// 使用 computed 避免直接修改 props
const isOpen = computed({
  get: () => props.open,
  set: (value) => {
    if (!value) emit('close')
    emit('update:open', value)
  },
})

const handleOpenPosts = () => {
  if (!props.item || !props.type) return
  if (!props.item.post_ids_sample?.length) return
  emit('open-posts', props.item, props.type)
}

// 类型标签配置
const typeConfig = computed(() => {
  switch (props.type) {
    case 'pain':
      return { label: '痛点', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-100 dark:bg-red-900/30' }
    case 'gain':
      return { label: '爽点', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-900/30' }
    case 'controversy':
      return { label: '争议点', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-100 dark:bg-amber-900/30' }
    case 'unmet':
      return { label: '未被满足需求', color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-100 dark:bg-purple-900/30' }
    default:
      return { label: '话题', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800' }
  }
})

// 无障碍描述
const dialogDescription = computed(() => props.item?.category ? `查看${props.item.category}分类下的话题详细信息` : '查看话题详细信息')

// 格式化分布数据
const formatDistribution = (dist?: Record<string, number>) => {
  if (!dist) return []
  return Object.entries(dist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
}

// 情感颜色
const getSentimentColor = (s?: number) => {
  if (s === undefined) return 'text-gray-600 dark:text-gray-400'
  if (s >= 0.2) return 'text-emerald-600 dark:text-emerald-400'
  if (s <= -0.2) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-400'
}
</script>

<template>
  <USlideover v-model:open="isOpen">
    <template #title>
      <div v-if="item" class="flex items-center gap-2">
        <span
          class="px-2 py-0.5 rounded text-xs font-medium"
          :class="[typeConfig.color, typeConfig.bg]"
        >
          {{ typeConfig.label }}
        </span>
        <span class="text-gray-900 dark:text-white font-medium truncate">{{ item.name }}</span>
      </div>
      <span v-else class="text-gray-500">话题详情</span>
    </template>

    <template #description>
      <span class="sr-only">{{ dialogDescription }}</span>
    </template>

    <template #body>
      <div v-if="item" class="space-y-6">
        <!-- 基础信息 -->
        <div class="grid grid-cols-3 gap-4">
          <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
            <div class="text-xs text-gray-500 dark:text-gray-400">热度</div>
            <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
              {{ item.heat.toFixed(0) }}
            </div>
          </div>
          <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
            <div class="text-xs text-gray-500 dark:text-gray-400">提及数</div>
            <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
              {{ item.mentions }}
            </div>
          </div>
          <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
            <div class="text-xs text-gray-500 dark:text-gray-400">情感值</div>
            <div
              class="text-lg font-mono font-semibold mt-1"
              :class="getSentimentColor(item.sentiment)"
            >
              {{ item.sentiment !== undefined ? (item.sentiment >= 0 ? '+' : '') + item.sentiment.toFixed(2) : '-' }}
            </div>
          </div>
        </div>

        <!-- 分类 -->
        <div v-if="item.category" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">所属分类</div>
          <div class="text-sm text-gray-900 dark:text-white">{{ item.category }}</div>
        </div>

        <!-- 平台分布 -->
        <div v-if="item.platform_distribution" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">平台分布</div>
          <div class="flex flex-wrap gap-2">
            <div
              v-for="[platform, count] in formatDistribution(item.platform_distribution)"
              :key="platform"
              class="px-2 py-1 rounded bg-white dark:bg-gray-700 text-xs"
            >
              <span class="text-gray-600 dark:text-gray-300">{{ platform }}</span>
              <span class="ml-1 font-mono text-gray-900 dark:text-white">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 关键词分布 -->
        <div v-if="item.keyword_distribution" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">关键词分布</div>
          <div class="flex flex-wrap gap-2">
            <div
              v-for="[keyword, count] in formatDistribution(item.keyword_distribution)"
              :key="keyword"
              class="px-2 py-1 rounded bg-white dark:bg-gray-700 text-xs"
            >
              <span class="text-gray-600 dark:text-gray-300">{{ keyword }}</span>
              <span class="ml-1 font-mono text-gray-900 dark:text-white">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 原话摘要 -->
        <div v-if="item.original_terms?.length" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
            用户原话 ({{ item.original_terms.length }})
          </div>
          <div class="space-y-2 max-h-64 overflow-y-auto">
            <div
              v-for="(term, idx) in item.original_terms.slice(0, 20)"
              :key="idx"
              class="p-2 rounded bg-white dark:bg-gray-700 text-sm"
            >
              <div class="text-gray-800 dark:text-gray-200">{{ term.text }}</div>
              <div class="text-xs text-gray-400 mt-1">出现 {{ term.count }} 次</div>
            </div>
          </div>
        </div>

        <!-- 帖子样本入口（统一交互：先看原话，再按需打开样本帖） -->
        <div class="flex items-center justify-end">
          <UButton
            size="xs"
            color="neutral"
            variant="outline"
            :disabled="!item.post_ids_sample?.length"
            :label="item.post_ids_sample?.length ? `查看帖子样本（${item.post_ids_sample.length}）` : '暂无帖子样本'"
            @click="handleOpenPosts"
          />
        </div>

        <!-- 洞察提示 -->
        <div
          v-if="type === 'unmet'"
          class="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800"
        >
          <div class="flex items-start gap-2">
            <UIcon name="i-heroicons-light-bulb" class="w-5 h-5 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5" />
            <div>
              <div class="text-sm font-medium text-purple-900 dark:text-purple-100">产品机会洞察</div>
              <div class="text-xs text-purple-700 dark:text-purple-300 mt-1">
                这是一个跨平台/跨关键词的行业共性痛点。如果您能解决这个问题，将形成差异化竞争优势。
              </div>
            </div>
          </div>
        </div>

        <div
          v-else-if="type === 'pain'"
          class="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800"
        >
          <div class="flex items-start gap-2">
            <UIcon name="i-heroicons-exclamation-triangle" class="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <div>
              <div class="text-sm font-medium text-red-900 dark:text-red-100">风险提示</div>
              <div class="text-xs text-red-700 dark:text-red-300 mt-1">
                用户对此话题存在明显负面情绪，建议关注并制定改进计划。
              </div>
            </div>
          </div>
        </div>

        <div
          v-else-if="type === 'gain'"
          class="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800"
        >
          <div class="flex items-start gap-2">
            <UIcon name="i-heroicons-trophy" class="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div class="text-sm font-medium text-emerald-900 dark:text-emerald-100">优势亮点</div>
              <div class="text-xs text-emerald-700 dark:text-emerald-300 mt-1">
                用户对此话题评价积极，可作为营销卖点进行放大宣传。
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="py-12 text-center text-gray-400">
        请选择一个话题查看详情
      </div>
    </template>
  </USlideover>
</template>

