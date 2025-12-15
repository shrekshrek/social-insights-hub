<script setup lang="ts">
import { z } from 'zod'
import type { DateValue } from '@internationalized/date'

definePageMeta({
  layout: 'default',
})

const { createProject } = useSocialProjects()
const { getPlatforms } = usePlatforms()

// 获取平台列表
const { data: platforms, pending: platformsLoading } = getPlatforms()

// 路由
const router = useRouter()

// 表单状态
const submitting = ref(false)
const enableQuickTasks = ref(false)

// 返回处理
const handleBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    navigateTo('/social-media/projects')
  }
}

// 表单Schema (基础项目信息)
const projectSchema = z.object({
  name: z.string().min(1, '项目名称不能为空').max(255, '项目名称不能超过255个字符'),
  description: z.string().optional(),
  date_range: z.object({
    start: z.custom<DateValue>().optional(),
    end: z.custom<DateValue>().optional()
  }).optional(),
})

// 快速任务Schema
const quickTaskSchema = z.object({
  platform_ids: z.array(z.number()).min(1, '请至少选择一个平台'),
  task_type: z.enum(['search', 'homefeed'], {
    message: '请选择任务类型'
  }),
  data_source: z.enum(['remote_crawler', 'local_upload'], {
    message: '请选择数据源'
  }),
  keywords: z.string().optional(),
}).refine((data) => {
  // search类型必须提供keywords
  if (data.task_type === 'search' && !data.keywords?.trim()) {
    return false
  }
  return true
}, {
  message: 'Search任务必须提供关键词',
  path: ['keywords'],
})

type ProjectSchema = z.output<typeof projectSchema>
type QuickTaskSchema = z.output<typeof quickTaskSchema>

// 表单初始值
const projectState = reactive<ProjectSchema>({
  name: '',
  description: '',
  date_range: undefined,
})

const quickTaskState = reactive<QuickTaskSchema>({
  platform_ids: [],
  task_type: 'search',
  data_source: 'remote_crawler',
  keywords: '',
})

// 格式化日期为 YYYY-MM-DD
const formatDateToString = (date: DateValue | null | undefined): string | undefined => {
  if (!date) return undefined
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const d = date as any
  return `${d.year}-${String(d.month).padStart(2, '0')}-${String(d.day).padStart(2, '0')}`
}

// 格式化日期范围为显示文本
const dateRangeText = computed(() => {
  if (!projectState.date_range) return ''
  const { start, end } = projectState.date_range
  if (!start && !end) return ''

  const startStr = start ? formatDateToString(start as DateValue) : ''
  const endStr = end ? formatDateToString(end as DateValue) : ''

  if (startStr && endStr) {
    return `${startStr} - ${endStr}`
  } else if (startStr) {
    return startStr
  } else if (endStr) {
    return endStr
  }
  return ''
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
const showKeywordsInput = computed(() => {
  return quickTaskState.task_type === 'search'
})

// 任务创建摘要
const taskSummary = computed(() => {
  if (!enableQuickTasks.value || quickTaskState.platform_ids.length === 0) {
    return null
  }

  const platformNames = platformOptions.value
    .filter(p => quickTaskState.platform_ids.includes(p.value))
    .map(p => p.label)

  const taskTypeLabel = taskTypeOptions.find(t => t.value === quickTaskState.task_type)?.label || ''
  const dataSourceLabel = dataSourceOptions.find(d => d.value === quickTaskState.data_source)?.label || ''

  return {
    count: quickTaskState.platform_ids.length,
    platforms: platformNames,
    taskType: taskTypeLabel,
    dataSource: dataSourceLabel,
    keywords: quickTaskState.keywords
  }
})

// 提交表单
const handleSubmit = async () => {
  submitting.value = true
  try {
    const projectData: SocialProjectCreate = {
      name: projectState.name,
      description: projectState.description || undefined,
      project_start_date: formatDateToString(projectState.date_range?.start as DateValue),
      project_end_date: formatDateToString(projectState.date_range?.end as DateValue),
    }

    // 如果启用了快速任务创建
    if (enableQuickTasks.value) {
      const quickTasks: QuickTaskCreate = {
        platform_ids: quickTaskState.platform_ids,
        task_type: quickTaskState.task_type,
        data_source: quickTaskState.data_source,
        keywords: quickTaskState.keywords || undefined,
      }
      projectData.quick_tasks = quickTasks
    }

    const result = await createProject(projectData)

    // 显示成功消息
    const toast = useToast()
    if (result.created_tasks && result.created_tasks.length > 0) {
      toast.add({
        title: '项目创建成功',
        description: `已创建项目并自动创建${result.created_tasks.length}个任务`,
        color: 'success',
      })
    } else {
      toast.add({
        title: '项目创建成功',
        color: 'success',
      })
    }

    // 跳转到项目详情页
    await navigateTo(`/social-media/projects/${result.project.id}`)
  } catch (error) {
    console.error('创建项目失败:', error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="handleBack"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            新建项目
          </h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">
            创建一个新的社交媒体数据采集项目
          </p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          variant="outline"
          :disabled="submitting"
          to="/social-media/projects"
        >
          取消
        </UButton>
        <UButton
          :loading="submitting"
          @click="handleSubmit"
        >
          创建
        </UButton>
      </div>
    </div>

    <!-- 项目基本信息卡片 -->
    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">
          项目信息
        </h2>
      </template>

      <UForm
        :schema="projectSchema"
        :state="projectState"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
          <!-- 项目名称 -->
          <UFormField
            label="项目名称"
            name="name"
            required
          >
            <UInput
              v-model="projectState.name"
              placeholder="请输入项目名称"
              class="w-full"
            />
          </UFormField>

          <!-- 项目时间范围 -->
          <UFormField
            label="项目时间"
            name="date_range"
          >
            <UPopover class="w-full">
              <UInput
                :model-value="dateRangeText"
                readonly
                placeholder="选择日期范围"
                icon="i-lucide-calendar"
                class="w-full"
              />

              <template #content>
                <UCalendar
                  v-model="projectState.date_range"
                  class="p-2"
                  :number-of-months="2"
                  range
                />
              </template>
            </UPopover>
          </UFormField>

          <!-- 项目描述 - 占据整行 -->
          <UFormField
            label="项目描述"
            name="description"
            class="md:col-span-2"
          >
            <UTextarea
              v-model="projectState.description"
              placeholder="请输入项目描述"
              :rows="3"
              class="w-full"
            />
          </UFormField>
        </div>
      </UForm>
    </UCard>

    <!-- 快速创建任务卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-base font-semibold">
            批量创建任务
          </h2>
          <USwitch
            v-model="enableQuickTasks"
          />
        </div>
      </template>

      <div v-if="enableQuickTasks">
        <UForm
          :schema="quickTaskSchema"
          :state="quickTaskState"
        >
          <div class="space-y-5">
            <!-- 任务类型和数据源 - 两列并排 -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
              <!-- 任务类型 -->
              <UFormField
                label="任务类型"
                name="task_type"
                required
              >
                <USelect
                  v-model="quickTaskState.task_type"
                  :items="taskTypeOptions"
                  value-key="value"
                  placeholder="选择任务类型"
                  class="w-full"
                />
              </UFormField>

              <!-- 数据源 -->
              <UFormField
                label="数据源"
                name="data_source"
                required
              >
                <USelect
                  v-model="quickTaskState.data_source"
                  :items="dataSourceOptions"
                  value-key="value"
                  placeholder="选择数据源"
                  class="w-full"
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
                v-model="quickTaskState.keywords"
                placeholder="例如：品牌名、产品名、话题标签"
                class="w-full"
              />
            </UFormField>

            <!-- 选择平台 - 占据整行 -->
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
                    'ring-2 ring-primary-500 border-primary-500': quickTaskState.platform_ids.includes(platform.value)
                  }"
                >
                  <input
                    v-model="quickTaskState.platform_ids"
                    type="checkbox"
                    :value="platform.value"
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
      </div>

      <div v-else class="text-sm text-gray-500 py-8 text-center">
        <p>稍后可在项目详情页创建任务</p>
      </div>
    </UCard>

  </div>
</template>
