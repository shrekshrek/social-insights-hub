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
          <p class="text-gray-600 dark:text-gray-400 mt-1">填写品牌 Brief，AI 将协助规划监测方案</p>
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

    <!-- 基本信息 + Brand Brief -->
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

        <UFormField label="品牌名称" required>
          <UInput
            v-model="brief.brand_name"
            placeholder="例如: 美赞臣"
            class="w-full"
          />
        </UFormField>

        <UFormField label="分析目标" required>
          <UTextarea
            v-model="brief.analysis_goal"
            placeholder="例如: 分析竞品口碑，找到品牌差异化机会"
            :rows="2"
            class="w-full"
          />
        </UFormField>

        <UFormField label="行业 / 品类">
          <UInput
            v-model="brief.industry"
            placeholder="例如: 婴幼儿奶粉"
            class="w-full"
          />
        </UFormField>

        <UFormField label="主要竞品">
          <UInput
            v-model="competitorsRaw"
            placeholder="多个竞品用逗号分隔，例如: 飞鹤, 惠氏, 雅培"
            class="w-full"
          />
        </UFormField>

        <UFormField label="关注维度">
          <UInput
            v-model="focusAreasRaw"
            placeholder="多个维度用逗号分隔，例如: 口碑, 竞品, 趋势"
            class="w-full"
          />
        </UFormField>

        <UFormField label="时间范围">
          <UInput
            v-model="brief.time_range"
            placeholder="例如: 近6个月"
            class="w-full"
          />
        </UFormField>

        <UFormField label="补充说明">
          <UTextarea
            v-model="brief.constraints"
            placeholder="其他需要 AI 参考的背景信息（可选）"
            :rows="2"
            class="w-full"
          />
        </UFormField>
      </div>
    </UCard>

    <!-- 快速路径：可选切片选择 -->
    <UCard>
      <template #header>
        <button
          class="w-full flex items-center justify-between"
          @click="showSlices = !showSlices"
        >
          <div>
            <h2 class="text-lg font-semibold text-left">快速路径：直接关联切片（可选）</h2>
            <p class="text-sm text-gray-500 text-left mt-0.5">
              若已有分析切片，可跳过 AI 咨询流程直接关联
            </p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <span v-if="selectedSliceIds.length > 0" class="text-sm text-primary-600 font-medium">
              已选 {{ selectedSliceIds.length }} 个
            </span>
            <UIcon
              :name="showSlices ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'"
              class="text-gray-400"
            />
          </div>
        </button>
      </template>

      <ClientOnly v-if="showSlices">
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

      <div v-else class="py-2 text-sm text-gray-400">
        点击展开选择切片
      </div>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { BrandBrief } from '../../types'

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
const showSlices = ref(false)
const form = ref({ name: '' })
const brief = ref<Partial<BrandBrief>>({
  brand_name: '',
  analysis_goal: '',
  industry: '',
  time_range: '',
  constraints: '',
})
const competitorsRaw = ref('')
const focusAreasRaw = ref('')
const selectedSliceIds = ref<number[]>([])
const expandedMonitors = ref(new Set<number>())
const monitorSlicesMap = ref<Record<number, MonitorSliceItem[]>>({})

const { data: monitorsData, pending: monitorsPending } = useApiDataFn<{
  items: MonitorItem[]
  total: number
}>('/social-media/monitors?page_size=100', {
  key: 'strategy-create-monitors',
})

const monitors = computed(() => monitorsData.value?.items || [])

const canSubmit = computed(() => {
  return (
    form.value.name.trim().length > 0
    && (brief.value.brand_name?.trim().length ?? 0) > 0
    && (brief.value.analysis_goal?.trim().length ?? 0) > 0
  )
})

const toggleMonitor = async (monitorId: number) => {
  if (expandedMonitors.value.has(monitorId)) {
    expandedMonitors.value.delete(monitorId)
  } else {
    expandedMonitors.value.add(monitorId)
    if (!monitorSlicesMap.value[monitorId]) {
      try {
        const result = await apiRequest<{ items: MonitorSliceItem[] }>(
          `/social-media/analysis/monitors/${monitorId}/slices`
        )
        monitorSlicesMap.value = { ...monitorSlicesMap.value, [monitorId]: result.items }
      } catch {
        monitorSlicesMap.value = { ...monitorSlicesMap.value, [monitorId]: [] }
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
    const competitors = competitorsRaw.value
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
    const focusAreas = focusAreasRaw.value
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)

    const brandBrief: BrandBrief = {
      brand_name: brief.value.brand_name!.trim(),
      analysis_goal: brief.value.analysis_goal!.trim(),
      ...(brief.value.industry?.trim() && { industry: brief.value.industry.trim() }),
      ...(competitors.length > 0 && { competitors }),
      ...(focusAreas.length > 0 && { focus_areas: focusAreas }),
      ...(brief.value.time_range?.trim() && { time_range: brief.value.time_range.trim() }),
      ...(brief.value.constraints?.trim() && { constraints: brief.value.constraints.trim() }),
    }

    const result = await strategiesApi.createStrategy({
      name: form.value.name.trim(),
      brand_brief: brandBrief,
      ...(selectedSliceIds.value.length > 0 && { slice_ids: selectedSliceIds.value }),
    })
    navigateTo(`/strategies/${result.id}`)
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    submitting.value = false
  }
}
</script>
