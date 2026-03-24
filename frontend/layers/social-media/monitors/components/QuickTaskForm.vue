<script setup lang="ts">
import { z } from 'zod'

interface QuickTaskState {
  platform_ids: number[]
  task_type: 'search' | 'homefeed'
  data_source: 'remote_crawler' | 'local_upload'
  keywords: string
  max_notes_count: number
  enable_comments: boolean
  per_note_max_comments_count: number
  publish_time_type: number
  sort_type: string
  auto_analyze: boolean
}

const state = defineModel<QuickTaskState>('state', { required: true })

defineProps<{
  disabled?: boolean
}>()

const { getPlatforms } = usePlatforms()
const { data: platforms, pending: platformsLoading } = getPlatforms()

// Zod schema for validation
const quickTaskSchema = z.object({
  platform_ids: z.array(z.number()).min(1, '请至少选择一个平台'),
  task_type: z.enum(['search', 'homefeed'], {
    message: '请选择任务类型'
  }),
  data_source: z.enum(['remote_crawler', 'local_upload'], {
    message: '请选择数据源'
  }),
  keywords: z.string().optional(),
  max_notes_count: z.number().min(1).max(10000).default(100),
  enable_comments: z.boolean().default(true),
  per_note_max_comments_count: z.number().min(0).max(10000).default(20),
  publish_time_type: z.number().default(0),
  sort_type: z.string().default('popularity_descending'),
  auto_analyze: z.boolean().default(true),
}).refine((data) => {
  if (data.task_type === 'search' && !data.keywords?.trim()) {
    return false
  }
  return true
}, {
  message: 'Search任务必须提供关键词',
  path: ['keywords'],
})

// 平台选项
const platformOptions = computed(() => {
  if (!platforms.value) return []
  return platforms.value.map((p) => ({
    label: p.name,
    value: p.id,
    description: p.description,
  }))
})

// 任务类型选项
const taskTypeOptions = [
  { label: '搜索任务', value: 'search', description: '根据关键词搜索内容' },
  { label: '主页任务', value: 'homefeed', description: '采集平台主页推荐内容' },
]

// 数据源选项
const dataSourceOptions = [
  { label: '远程爬虫', value: 'remote_crawler', description: '使用爬虫实时采集数据' },
  { label: '本地上传', value: 'local_upload', description: '上传本地JSON数据文件' },
]

// 是否需要显示关键词输入框
const showKeywordsInput = computed(() => state.value.task_type === 'search')

// 是否显示远程爬虫高级选项
const showCrawlerOptions = computed(() => state.value.data_source === 'remote_crawler')

// 选中的平台代码列表
const selectedPlatformCodes = computed(() => {
  if (!platforms.value) return []
  return platforms.value
    .filter(p => state.value.platform_ids.includes(p.id))
    .map(p => p.code)
})

// 是否显示抖音专属选项
const showDouyinOptions = computed(() => {
  return showCrawlerOptions.value && selectedPlatformCodes.value.includes('dy')
})

// 是否显示小红书专属选项
const showXhsOptions = computed(() => {
  return showCrawlerOptions.value && selectedPlatformCodes.value.includes('xhs')
})

// 抖音发布时间选项
const publishTimeOptions = [
  { label: '不限', value: 0 },
  { label: '一天内', value: 1 },
  { label: '一周内', value: 7 },
  { label: '半年内', value: 182 },
]

// 小红书排序选项
const sortTypeOptions = [
  { label: '综合排序', value: 'general' },
  { label: '最热', value: 'popularity_descending' },
  { label: '最新', value: 'time_descending' },
]

// 任务创建摘要
const taskSummary = computed(() => {
  if (state.value.platform_ids.length === 0) return null

  const platformNames = platformOptions.value
    .filter(p => state.value.platform_ids.includes(p.value))
    .map(p => p.label)

  const taskTypeLabel = taskTypeOptions.find(t => t.value === state.value.task_type)?.label || ''
  const dataSourceLabel = dataSourceOptions.find(d => d.value === state.value.data_source)?.label || ''

  return {
    count: state.value.platform_ids.length,
    platforms: platformNames,
    taskType: taskTypeLabel,
    dataSource: dataSourceLabel,
    keywords: state.value.keywords,
  }
})
</script>

<template>
  <UForm
    v-if="state"
    :schema="quickTaskSchema"
    :state="state"
  >
    <div class="space-y-5">
      <!-- 任务类型和数据源 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <UFormField
          label="任务类型"
          name="task_type"
          required
        >
          <USelect
            v-model="state.task_type"
            :items="taskTypeOptions"
            value-key="value"
            placeholder="选择任务类型"
            class="w-full"
            :disabled="disabled"
          />
        </UFormField>

        <UFormField
          label="数据源"
          name="data_source"
          required
        >
          <USelect
            v-model="state.data_source"
            :items="dataSourceOptions"
            value-key="value"
            placeholder="选择数据源"
            class="w-full"
            :disabled="disabled"
          />
        </UFormField>
      </div>

      <!-- 关键词（仅search任务） -->
      <UFormField
        v-if="showKeywordsInput"
        label="搜索关键词"
        name="keywords"
        required
      >
        <UInput
          v-model="state.keywords"
          placeholder="例如：品牌名、产品名、话题标签"
          class="w-full"
          :disabled="disabled"
        />
      </UFormField>

      <!-- 选择平台 -->
      <UFormField
        label="目标平台"
        name="platform_ids"
        required
      >
        <div v-if="platformsLoading" class="text-sm text-gray-500">
          加载中...
        </div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          <label
            v-for="platform in platformOptions"
            :key="platform.value"
            class="relative flex items-start p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
            :class="{
              'ring-2 ring-primary-500 border-primary-500': state.platform_ids.includes(platform.value),
              'opacity-50 pointer-events-none': disabled,
            }"
          >
            <input
              v-model="state.platform_ids"
              type="checkbox"
              :value="platform.value"
              :disabled="disabled"
              class="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            >
            <div class="ml-3 flex-1">
              <div class="font-medium text-sm">
                {{ platform.label }}
              </div>
              <div
                v-if="platform.description"
                class="text-xs text-gray-500 dark:text-gray-400 mt-0.5"
              >
                {{ platform.description }}
              </div>
            </div>
          </label>
        </div>
      </UFormField>

      <!-- 远程爬虫高级选项 -->
      <ClientOnly>
        <template v-if="showCrawlerOptions">
          <USeparator label="爬虫配置" />

          <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
            <UFormField
              label="最大爬取数"
              help="爬取的最大条目数量"
            >
              <UInput
                v-model.number="state.max_notes_count"
                type="number"
                :min="1"
                :max="10000"
                class="w-full"
                :disabled="disabled"
              />
            </UFormField>

            <UFormField
              label="爬取评论"
              help="是否爬取原文的评论"
            >
              <USwitch v-model="state.enable_comments" :disabled="disabled" />
            </UFormField>

            <UFormField
              v-if="state.enable_comments"
              label="单帖最大评论数"
              help="每个原文爬取的最大评论数，0表示不限"
            >
              <UInput
                v-model.number="state.per_note_max_comments_count"
                type="number"
                :min="0"
                :max="10000"
                class="w-full"
                :disabled="disabled"
              />
            </UFormField>
          </div>

          <!-- 抖音专属选项 -->
          <div
            v-if="showDouyinOptions"
            class="grid grid-cols-1 md:grid-cols-2 gap-5"
          >
            <UFormField
              label="发布时间筛选"
              help="按发布时间筛选视频（抖音专属）"
            >
              <USelect
                v-model="state.publish_time_type"
                :items="publishTimeOptions"
                value-key="value"
                class="w-full"
                :disabled="disabled"
              />
            </UFormField>
          </div>

          <!-- 小红书专属选项 -->
          <div
            v-if="showXhsOptions"
            class="grid grid-cols-1 md:grid-cols-2 gap-5"
          >
            <UFormField
              label="排序方式"
              help="搜索结果排序方式（小红书专属）"
            >
              <USelect
                v-model="state.sort_type"
                :items="sortTypeOptions"
                value-key="value"
                class="w-full"
                :disabled="disabled"
              />
            </UFormField>
          </div>

          <!-- 自动分析选项 -->
          <USeparator label="分析配置" />

          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <UFormField
              label="自动分析"
              help="数据采集完成后自动执行全流程分析（初筛→深度→报告）"
            >
              <USwitch v-model="state.auto_analyze" :disabled="disabled" />
            </UFormField>
          </div>
        </template>
      </ClientOnly>
    </div>

    <!-- 任务摘要 -->
    <div
      v-if="taskSummary"
      class="mt-5 pt-5 border-t border-gray-200 dark:border-gray-700"
    >
      <div class="flex items-center gap-2 mb-3">
        <UIcon name="i-lucide-info" class="text-blue-500" />
        <span class="text-sm font-medium">将创建 {{ taskSummary.count }} 个任务</span>
      </div>
      <div class="text-sm text-gray-600 dark:text-gray-400 space-y-1.5">
        <div>{{ taskSummary.taskType }} · {{ taskSummary.dataSource }}</div>
        <div
          v-if="taskSummary.keywords"
          class="text-blue-600 dark:text-blue-400"
        >
          {{ taskSummary.keywords }}
        </div>
        <div class="flex flex-wrap gap-1.5 mt-2">
          <UBadge
            v-for="platform in taskSummary.platforms"
            :key="platform"
            variant="subtle"
            size="sm"
          >
            {{ platform }}
          </UBadge>
        </div>
      </div>
    </div>
  </UForm>
</template>
