<!-- eslint-disable vue/multi-word-component-names -->
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
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">新建策略</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">基于已有切片数据创建品牌策略</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton variant="outline" :disabled="submitting" @click="handleBack">
          取消
        </UButton>
        <UButton :loading="submitting" :disabled="!canSubmit" @click="handleSubmit">
          创建
        </UButton>
      </div>
    </div>

    <!-- 表单 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">基本信息</h2>
      </template>

      <div class="space-y-4">
        <UFormField label="策略名称" required>
          <UInput
            v-model="form.name"
            placeholder="请输入策略名称"
            class="w-full"
          />
        </UFormField>

        <UFormField label="品牌名称">
          <UInput
            v-model="brief.brand"
            placeholder="例如: 美赞臣"
            class="w-full"
          />
        </UFormField>

        <UFormField label="品类">
          <UInput
            v-model="brief.category"
            placeholder="例如: 婴幼儿奶粉"
            class="w-full"
          />
        </UFormField>

        <UFormField label="目标人群">
          <UInput
            v-model="brief.target_audience"
            placeholder="例如: 25-35岁新手妈妈"
            class="w-full"
          />
        </UFormField>

        <UFormField label="品牌定位">
          <UInput
            v-model="brief.positioning"
            placeholder="例如: 科学营养，值得信赖"
            class="w-full"
          />
        </UFormField>

        <UFormField label="补充说明">
          <UTextarea
            v-model="brief.notes"
            placeholder="其他需要 AI 参考的背景信息（可选）"
            :rows="2"
            class="w-full"
          />
        </UFormField>
      </div>
    </UCard>

    <!-- 切片选择 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">选择分析切片</h2>
          <span class="text-sm text-gray-500">已选 {{ selectedSliceIds.length }} 个切片</span>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载项目列表...</p>
          </div>
        </template>

        <div v-if="projectsPending" class="text-center py-8">
          <p class="text-gray-500">加载中...</p>
        </div>

        <div v-else-if="projects.length === 0" class="text-center py-8">
          <p class="text-gray-500">暂无项目，请先创建监控项目并生成分析切片</p>
        </div>

        <div v-else class="space-y-4">
          <div
            v-for="project in projects"
            :key="project.id"
            class="border border-gray-200 dark:border-gray-700 rounded-lg"
          >
            <!-- 项目标题 (可折叠) -->
            <button
              class="w-full flex items-center justify-between p-3 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-t-lg"
              @click="toggleProject(project.id)"
            >
              <div class="flex items-center gap-2">
                <UIcon
                  :name="expandedProjects.has(project.id) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                  class="text-gray-400"
                />
                <span class="font-medium">{{ project.name }}</span>
              </div>
              <span class="text-sm text-gray-500">
                {{ getProjectSliceCount(project.id) }} 个切片
              </span>
            </button>

            <!-- 切片列表 -->
            <div
              v-if="expandedProjects.has(project.id)"
              class="border-t border-gray-200 dark:border-gray-700 p-3 space-y-2"
            >
              <div
                v-if="!projectSlicesMap[project.id] || projectSlicesMap[project.id]!.length === 0"
                class="text-sm text-gray-400 py-2"
              >
                该项目暂无分析切片
              </div>
              <label
                v-for="slice in (projectSlicesMap[project.id] || [])"
                :key="slice.id"
                class="flex items-center gap-3 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
              >
                <input
                  type="checkbox"
                  :checked="selectedSliceIds.includes(slice.id)"
                  class="rounded border-gray-300"
                  @change="toggleSlice(slice.id)"
                >
                <div class="flex-1 min-w-0">
                  <span class="text-sm font-medium">{{ slice.name || `切片 #${slice.id}` }}</span>
                  <span class="text-xs text-gray-400 ml-2">
                    {{ formatDate(slice.created_at) }}
                  </span>
                </div>
              </label>
            </div>
          </div>
        </div>
      </ClientOnly>
    </UCard>
  </div>
</template>

<script setup lang="ts">
definePageMeta({
  title: '新建策略',
})

interface ProjectSliceItem {
  id: number
  name: string | null
  project_id: number
  created_at: string
}

interface ProjectItem {
  id: number
  name: string
}

const router = useRouter()
const strategiesApi = useStrategies()
const { apiRequest, useApiData: useApiDataFn } = useApi()

const submitting = ref(false)
const form = ref({ name: '' })
const brief = ref({
  brand: '',
  category: '',
  target_audience: '',
  positioning: '',
  notes: '',
})
const selectedSliceIds = ref<number[]>([])
const expandedProjects = ref(new Set<number>())
const projectSlicesMap = ref<Record<number, ProjectSliceItem[]>>({})

// 加载项目列表 (不分页，取前100个)
const { data: projectsData, pending: projectsPending } = useApiDataFn<{
  items: ProjectItem[]
  total: number
}>('/social-media/projects?page_size=100', {
  key: 'strategy-create-projects',
})

const projects = computed(() => projectsData.value?.items || [])

const canSubmit = computed(() => {
  return form.value.name.trim().length > 0 && selectedSliceIds.value.length > 0
})

const toggleProject = async (projectId: number) => {
  if (expandedProjects.value.has(projectId)) {
    expandedProjects.value.delete(projectId)
  } else {
    expandedProjects.value.add(projectId)
    // 首次展开时加载切片
    if (!projectSlicesMap.value[projectId]) {
      try {
        const result = await apiRequest<{ items: ProjectSliceItem[] }>(
          `/social-media/analysis/projects/${projectId}/slices`
        )
        projectSlicesMap.value = {
          ...projectSlicesMap.value,
          [projectId]: result.items,
        }
      } catch {
        projectSlicesMap.value = {
          ...projectSlicesMap.value,
          [projectId]: [],
        }
      }
    }
  }
}

const toggleSlice = (sliceId: number) => {
  const idx = selectedSliceIds.value.indexOf(sliceId)
  if (idx >= 0) {
    selectedSliceIds.value = selectedSliceIds.value.filter(id => id !== sliceId)
  } else {
    selectedSliceIds.value = [...selectedSliceIds.value, sliceId]
  }
}

const getProjectSliceCount = (projectId: number) => {
  return (projectSlicesMap.value[projectId] || []).length
}

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

const handleBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    navigateTo('/strategies')
  }
}

const handleSubmit = async () => {
  if (!canSubmit.value) return

  submitting.value = true
  try {
    // 过滤空字段，全空则不传
    const briefEntries = Object.entries(brief.value).filter(([, v]) => v.trim())
    const brandBrief = briefEntries.length > 0
      ? Object.fromEntries(briefEntries)
      : null

    const result = await strategiesApi.createStrategy({
      name: form.value.name.trim(),
      slice_ids: selectedSliceIds.value,
      brand_brief: brandBrief,
    })
    navigateTo(`/strategies/${result.id}`)
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    submitting.value = false
  }
}
</script>
