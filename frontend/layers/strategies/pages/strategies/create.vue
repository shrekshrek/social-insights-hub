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
            <p class="text-gray-600 dark:text-gray-400">加载监测列表...</p>
          </div>
        </template>

        <div v-if="monitorsPending" class="text-center py-8">
          <p class="text-gray-500">加载中...</p>
        </div>

        <div v-else-if="monitors.length === 0" class="text-center py-8">
          <p class="text-gray-500">暂无监测，请先创建监测项目并生成分析切片</p>
        </div>

        <div v-else class="space-y-4">
          <div
            v-for="monitor in monitors"
            :key="monitor.id"
            class="border border-gray-200 dark:border-gray-700 rounded-lg"
          >
            <!-- 监测标题 (可折叠) -->
            <button
              class="w-full flex items-center justify-between p-3 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-t-lg"
              @click="toggleMonitor(monitor.id)"
            >
              <div class="flex items-center gap-2">
                <UIcon
                  :name="expandedMonitors.has(monitor.id) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                  class="text-gray-400"
                />
                <span class="font-medium">{{ monitor.name }}</span>
              </div>
              <span class="text-sm text-gray-500">
                {{ getMonitorSliceCount(monitor.id) }} 个切片
              </span>
            </button>

            <!-- 切片列表 -->
            <div
              v-if="expandedMonitors.has(monitor.id)"
              class="border-t border-gray-200 dark:border-gray-700 p-3 space-y-2"
            >
              <div
                v-if="!monitorSlicesMap[monitor.id] || monitorSlicesMap[monitor.id]!.length === 0"
                class="text-sm text-gray-400 py-2"
              >
                该监测暂无分析切片
              </div>
              <label
                v-for="slice in (monitorSlicesMap[monitor.id] || [])"
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

interface MonitorSliceItem {
  id: number
  name: string | null
  monitor_id: number
  created_at: string
}

interface MonitorItem {
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
const expandedMonitors = ref(new Set<number>())
const monitorSlicesMap = ref<Record<number, MonitorSliceItem[]>>({})

// 加载项目列表 (不分页，取前100个)
const { data: monitorsData, pending: monitorsPending } = useApiDataFn<{
  items: MonitorItem[]
  total: number
}>('/social-media/monitors?page_size=100', {
  key: 'strategy-create-monitors',
})

const monitors = computed(() => monitorsData.value?.items || [])

const canSubmit = computed(() => {
  return form.value.name.trim().length > 0 && selectedSliceIds.value.length > 0
})

const toggleMonitor = async (monitorId: number) => {
  if (expandedMonitors.value.has(monitorId)) {
    expandedMonitors.value.delete(monitorId)
  } else {
    expandedMonitors.value.add(monitorId)
    // 首次展开时加载切片
    if (!monitorSlicesMap.value[monitorId]) {
      try {
        const result = await apiRequest<{ items: MonitorSliceItem[] }>(
          `/social-media/analysis/monitors/${monitorId}/slices`
        )
        monitorSlicesMap.value = {
          ...monitorSlicesMap.value,
          [monitorId]: result.items,
        }
      } catch {
        monitorSlicesMap.value = {
          ...monitorSlicesMap.value,
          [monitorId]: [],
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

const getMonitorSliceCount = (monitorId: number) => {
  return (monitorSlicesMap.value[monitorId] || []).length
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
