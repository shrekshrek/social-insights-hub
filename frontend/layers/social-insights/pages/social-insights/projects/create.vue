<script setup lang="ts">
import type { SocialProjectCreate, QuickTaskCreate } from '../../../types'
import { z } from 'zod'

definePageMeta({
  layout: 'default',
})

const { createProject } = useSocialProjects()
const { getPlatforms } = usePlatforms()

// 获取平台列表
const { data: platforms, pending: platformsLoading } = getPlatforms()

// 表单状态
const submitting = ref(false)
const enableQuickTasks = ref(false)

// 表单Schema (基础项目信息)
const projectSchema = z.object({
  name: z.string().min(1, '项目名称不能为空').max(255, '项目名称不能超过255个字符'),
  description: z.string().optional(),
  date_range: z.object({
    start: z.date().optional(),
    end: z.date().optional()
  }).optional(),
})

// 快速任务Schema
const quickTaskSchema = z.object({
  platform_ids: z.array(z.number()).min(1, '请至少选择一个平台'),
  task_type: z.enum(['search', 'homefeed'], {
    required_error: '请选择任务类型'
  }),
  data_source: z.enum(['remote_crawler', 'local_upload'], {
    required_error: '请选择数据源'
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

// 提交表单
const handleSubmit = async () => {
  submitting.value = true
  try {
    const projectData: SocialProjectCreate = {
      name: projectState.name,
      description: projectState.description || undefined,
      project_start_date: projectState.date_range?.start?.toISOString().split('T')[0] || undefined,
      project_end_date: projectState.date_range?.end?.toISOString().split('T')[0] || undefined,
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
        color: 'green',
      })
    } else {
      toast.add({
        title: '项目创建成功',
        color: 'green',
      })
    }

    // 跳转到项目详情页
    await navigateTo(`/social-insights/projects/${result.project.id}`)
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
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        新建项目
      </h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">
        创建一个新的社交媒体数据采集项目，可选择同时批量创建任务
      </p>
    </div>

    <!-- 项目基本信息卡片 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">
          项目基本信息
        </h2>
      </template>

      <UForm
        :schema="projectSchema"
        :state="projectState"
        class="space-y-6"
      >
        <!-- 项目名称 -->
        <UFormGroup
          label="项目名称"
          name="name"
          required
        >
          <UInput
            v-model="projectState.name"
            placeholder="请输入项目名称"
          />
        </UFormGroup>

        <!-- 项目描述 -->
        <UFormGroup
          label="项目描述"
          name="description"
        >
          <UTextarea
            v-model="projectState.description"
            placeholder="请输入项目描述"
            :rows="4"
          />
        </UFormGroup>

        <!-- 项目时间范围 -->
        <UFormGroup
          label="项目时间范围"
          name="date_range"
          help="选择项目的开始和结束日期（可选）"
        >
          <UInputDate
            v-model="projectState.date_range"
            mode="range"
            placeholder="选择日期范围"
          />
        </UFormGroup>
      </UForm>
    </UCard>

    <!-- 快速创建任务卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            快速创建任务（可选）
          </h2>
          <UToggle
            v-model="enableQuickTasks"
            label="启用"
          />
        </div>
      </template>

      <div v-if="enableQuickTasks">
        <UForm
          :schema="quickTaskSchema"
          :state="quickTaskState"
          class="space-y-6"
        >
          <!-- 任务类型 -->
          <UFormGroup
            label="任务类型"
            name="task_type"
            required
            help="仅支持批量创建搜索任务和主页任务"
          >
            <USelectMenu
              v-model="quickTaskState.task_type"
              :options="taskTypeOptions"
              value-attribute="value"
              option-attribute="label"
            >
              <template #option="{ option }">
                <div>
                  <div class="font-medium">
                    {{ option.label }}
                  </div>
                  <div class="text-xs text-gray-500">
                    {{ option.description }}
                  </div>
                </div>
              </template>
            </USelectMenu>
          </UFormGroup>

          <!-- 数据源 -->
          <UFormGroup
            label="数据源"
            name="data_source"
            required
          >
            <USelectMenu
              v-model="quickTaskState.data_source"
              :options="dataSourceOptions"
              value-attribute="value"
              option-attribute="label"
            >
              <template #option="{ option }">
                <div>
                  <div class="font-medium">
                    {{ option.label }}
                  </div>
                  <div class="text-xs text-gray-500">
                    {{ option.description }}
                  </div>
                </div>
              </template>
            </USelectMenu>
          </UFormGroup>

          <!-- 关键词（仅search任务） -->
          <UFormGroup
            v-if="showKeywordsInput"
            label="搜索关键词"
            name="keywords"
            required
            help="将为每个平台创建使用此关键词的搜索任务"
          >
            <UInput
              v-model="quickTaskState.keywords"
              placeholder="例如：品牌名、产品名、话题标签"
            />
          </UFormGroup>

          <!-- 选择平台 -->
          <UFormGroup
            label="目标平台"
            name="platform_ids"
            required
            help="将为每个选中的平台创建一个任务"
          >
            <div v-if="platformsLoading" class="text-sm text-gray-500">
              加载平台列表中...
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="platform in platformOptions"
                :key="platform.value"
                class="flex items-center"
              >
                <UCheckbox
                  v-model="quickTaskState.platform_ids"
                  :value="platform.value"
                  :label="platform.label"
                />
                <span
                  v-if="platform.description"
                  class="ml-2 text-xs text-gray-500"
                >
                  {{ platform.description }}
                </span>
              </div>
            </div>
          </UFormGroup>
        </UForm>
      </div>

      <div v-else class="text-sm text-gray-500">
        <p>您可以稍后在项目详情页面创建任务</p>
      </div>
    </UCard>

    <!-- 操作按钮 -->
    <div class="flex items-center gap-3">
      <UButton
        @click="handleSubmit"
        :loading="submitting"
      >
        创建项目
      </UButton>
      <UButton
        variant="outline"
        @click="navigateTo('/social-insights/projects')"
      >
        取消
      </UButton>
    </div>
  </div>
</template>
