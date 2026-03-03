<script setup lang="ts">
import { z } from 'zod'
import type { DateValue } from '@internationalized/date'
import QuickTaskForm from '../../../projects/components/QuickTaskForm.vue'

definePageMeta({
  layout: 'default',
})

const { createProject } = useSocialProjects()

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

type ProjectSchema = z.output<typeof projectSchema>

// 表单初始值
const projectState = reactive<ProjectSchema>({
  name: '',
  description: '',
  date_range: undefined,
})

const quickTaskState = reactive({
  platform_ids: [] as number[],
  task_type: 'search' as 'search' | 'homefeed',
  data_source: 'remote_crawler' as 'remote_crawler' | 'local_upload',
  keywords: '',
  max_notes_count: 100,
  enable_comments: true,
  per_note_max_comments_count: 20,
  publish_time_type: 0,
  sort_type: 'popularity_descending',
  auto_analyze: true,
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
        max_notes_count: quickTaskState.max_notes_count,
        enable_comments: quickTaskState.enable_comments,
        per_note_max_comments_count: quickTaskState.per_note_max_comments_count,
        publish_time_type: quickTaskState.publish_time_type,
        sort_type: quickTaskState.sort_type,
        auto_analyze: quickTaskState.auto_analyze,
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

      <QuickTaskForm
        v-if="enableQuickTasks"
        v-model:state="quickTaskState"
      />

      <div v-else class="text-sm text-gray-500 py-8 text-center">
        <p>稍后可在项目详情页创建任务</p>
      </div>
    </UCard>

  </div>
</template>
