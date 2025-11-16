<script setup lang="ts">
import type { DataTaskCreate, TaskType, DataSource } from '../../../types'
import { z } from 'zod'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const { createTask } = useTasks()
const { getProjects } = useSocialProjects()
const { getPlatforms } = usePlatforms()

// 从URL获取project_id（如果有的话）
const preselectedProjectId = route.query.project_id ? Number(route.query.project_id) : undefined

// 获取项目和平台列表
const { data: projectsData } = getProjects({ page: 1, page_size: 100 })
const { data: platforms } = getPlatforms()

// 表单状态
const submitting = ref(false)

// 表单Schema
const schema = z.object({
  name: z.string().min(1, '任务名称不能为空').max(255, '任务名称不能超过255个字符'),
  description: z.string().optional(),
  project_id: z.number({ message: '请选择项目' }),
  platform_id: z.number({ message: '请选择平台' }),
  task_type: z.enum(['search', 'detail', 'creator', 'homefeed'], { message: '请选择任务类型' }),
  data_source: z.enum(['local_upload', 'remote_crawler'], { message: '请选择数据源' }),
  keywords: z.string().optional(),
})

// 表单初始值
const state = reactive({
  name: '',
  description: '',
  project_id: preselectedProjectId,
  platform_id: undefined as number | undefined,
  task_type: 'search' as const,
  data_source: 'local_upload' as const,
  keywords: '',
})

// 项目选项
const projectOptions = computed(() => {
  if (!projectsData.value) return []
  return projectsData.value.items.map((p) => ({
    label: p.name,
    value: p.id,
  }))
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
const taskTypeOptions: Array<{ label: string; value: TaskType; description: string }> = [
  { label: '搜索任务', value: 'search', description: '通过关键词搜索帖子' },
  { label: '详情任务', value: 'detail', description: '获取特定帖子的详细信息' },
  { label: '作者任务', value: 'creator', description: '获取特定作者的帖子列表' },
  { label: '首页动态', value: 'homefeed', description: '获取首页推荐动态' },
]

// 数据源选项
const dataSourceOptions: Array<{ label: string; value: DataSource; description: string }> = [
  { label: '本地上传', value: 'local_upload', description: '上传本地JSON数据文件' },
  { label: '远程爬虫', value: 'remote_crawler', description: '通过WebSocket与爬虫平台通信（即将支持）' },
]

// 提交表单
const handleSubmit = async () => {
  submitting.value = true
  try {
    const taskData: DataTaskCreate = {
      name: state.name,
      description: state.description || undefined,
      project_id: state.project_id!,
      platform_id: state.platform_id!,
      task_type: state.task_type,
      data_source: state.data_source,
      keywords: state.keywords || undefined,
    }

    const result = await createTask(taskData)

    // 如果是本地上传，直接跳转到上传页面
    if (result.data_source === 'local_upload') {
      await navigateTo(`/social-insights/tasks/${result.id}/upload`)
    } else {
      // 否则跳转到任务详情页
      await navigateTo(`/social-insights/tasks/${result.id}`)
    }
  } catch (error) {
    console.error('创建任务失败:', error)
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
        新建任务
      </h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">
        创建一个新的数据采集任务
      </p>
    </div>

    <!-- 表单卡片 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">
          任务信息
        </h2>
      </template>

      <UForm
        :schema="schema"
        :state="state"
        class="space-y-6"
        @submit="handleSubmit"
      >
        <!-- 任务名称 -->
        <UFormGroup
          label="任务名称"
          name="name"
          required
        >
          <UInput
            v-model="state.name"
            placeholder="请输入任务名称"
          />
        </UFormGroup>

        <!-- 任务描述 -->
        <UFormGroup
          label="任务描述"
          name="description"
        >
          <UTextarea
            v-model="state.description"
            placeholder="请输入任务描述"
            :rows="3"
          />
        </UFormGroup>

        <!-- 所属项目 -->
        <UFormGroup
          label="所属项目"
          name="project_id"
          required
        >
          <USelectMenu
            v-model="state.project_id"
            :options="projectOptions"
            placeholder="选择项目"
          />
        </UFormGroup>

        <!-- 目标平台 -->
        <UFormGroup
          label="目标平台"
          name="platform_id"
          required
        >
          <USelectMenu
            v-model="state.platform_id"
            :options="platformOptions"
            placeholder="选择平台"
          />
        </UFormGroup>

        <!-- 任务类型 -->
        <UFormGroup
          label="任务类型"
          name="task_type"
          required
        >
          <div class="space-y-2">
            <div
              v-for="option in taskTypeOptions"
              :key="option.value"
              class="flex items-center"
            >
              <URadio
                v-model="state.task_type"
                :value="option.value"
                :label="option.label"
              />
              <span class="ml-2 text-xs text-gray-500">
                {{ option.description }}
              </span>
            </div>
          </div>
        </UFormGroup>

        <!-- 关键词（仅search类型） -->
        <UFormGroup
          v-if="state.task_type === 'search'"
          label="搜索关键词"
          name="keywords"
          help="多个关键词请用逗号分隔"
        >
          <UInput
            v-model="state.keywords"
            placeholder="例如：热点话题,品牌名,产品名"
          />
        </UFormGroup>

        <!-- 数据源 -->
        <UFormGroup
          label="数据源"
          name="data_source"
          required
        >
          <div class="space-y-2">
            <div
              v-for="option in dataSourceOptions"
              :key="option.value"
              class="flex items-center"
            >
              <URadio
                v-model="state.data_source"
                :value="option.value"
                :label="option.label"
                :disabled="option.value === 'remote_crawler'"
              />
              <span class="ml-2 text-xs text-gray-500">
                {{ option.description }}
              </span>
            </div>
          </div>
        </UFormGroup>

        <!-- 操作按钮 -->
        <div class="flex items-center gap-3 pt-4">
          <UButton
            type="submit"
            :loading="submitting"
          >
            创建任务
          </UButton>
          <UButton
            variant="outline"
            @click="navigateTo('/social-insights/tasks')"
          >
            取消
          </UButton>
        </div>
      </UForm>
    </UCard>
  </div>
</template>
