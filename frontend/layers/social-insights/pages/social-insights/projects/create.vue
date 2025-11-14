<script setup lang="ts">
import type { SocialProjectCreate } from '../../../types'
import { z } from 'zod'

definePageMeta({
  middleware: 'auth',
  layout: 'default',
})

const { createProject } = useSocialProjects()
const { getPlatforms } = usePlatforms()

// 获取平台列表
const { data: platforms, pending: platformsLoading } = getPlatforms()

// 表单状态
const submitting = ref(false)

// 表单Schema
const schema = z.object({
  name: z.string().min(1, '项目名称不能为空').max(255, '项目名称不能超过255个字符'),
  description: z.string().optional(),
  keywords: z.string().optional(),
  project_start_date: z.string().optional(),
  project_end_date: z.string().optional(),
  platform_ids: z.array(z.number()).min(1, '请至少选择一个平台'),
})

type Schema = z.output<typeof schema>

// 表单初始值
const state = reactive<Schema>({
  name: '',
  description: '',
  keywords: '',
  project_start_date: undefined,
  project_end_date: undefined,
  platform_ids: [],
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

// 提交表单
const handleSubmit = async () => {
  submitting.value = true
  try {
    const projectData: SocialProjectCreate = {
      name: state.name,
      description: state.description || undefined,
      keywords: state.keywords || undefined,
      project_start_date: state.project_start_date || undefined,
      project_end_date: state.project_end_date || undefined,
      platform_ids: state.platform_ids,
    }

    const result = await createProject(projectData)

    // 跳转到项目详情页
    await navigateTo(`/social-insights/projects/${result.id}`)
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
        创建一个新的社交媒体数据采集项目
      </p>
    </div>

    <!-- 表单卡片 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">
          项目信息
        </h2>
      </template>

      <UForm
        :schema="schema"
        :state="state"
        class="space-y-6"
        @submit="handleSubmit"
      >
        <!-- 项目名称 -->
        <UFormGroup
          label="项目名称"
          name="name"
          required
        >
          <UInput
            v-model="state.name"
            placeholder="请输入项目名称"
          />
        </UFormGroup>

        <!-- 项目描述 -->
        <UFormGroup
          label="项目描述"
          name="description"
        >
          <UTextarea
            v-model="state.description"
            placeholder="请输入项目描述"
            :rows="4"
          />
        </UFormGroup>

        <!-- 关键词 -->
        <UFormGroup
          label="关键词"
          name="keywords"
          help="多个关键词请用逗号分隔"
        >
          <UInput
            v-model="state.keywords"
            placeholder="例如：品牌名,产品名,话题标签"
          />
        </UFormGroup>

        <!-- 项目时间范围 -->
        <div class="grid grid-cols-2 gap-4">
          <UFormGroup
            label="开始日期"
            name="project_start_date"
          >
            <UInput
              v-model="state.project_start_date"
              type="date"
            />
          </UFormGroup>

          <UFormGroup
            label="结束日期"
            name="project_end_date"
          >
            <UInput
              v-model="state.project_end_date"
              type="date"
            />
          </UFormGroup>
        </div>

        <!-- 选择平台 -->
        <UFormGroup
          label="目标平台"
          name="platform_ids"
          required
          help="请选择要采集数据的社交媒体平台"
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
                v-model="state.platform_ids"
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

        <!-- 操作按钮 -->
        <div class="flex items-center gap-3 pt-4">
          <UButton
            type="submit"
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
      </UForm>
    </UCard>
  </div>
</template>
