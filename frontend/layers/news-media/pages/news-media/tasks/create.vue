<script setup lang="ts">
import { z } from 'zod'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const { createTask } = useNewsTasks()
const { getMonitors, getMonitor } = useNewsMonitors()

const preselectedMonitorId = route.query.monitor_id ? Number(route.query.monitor_id) : undefined
const isFromMonitorDetail = computed(() => !!preselectedMonitorId)

const { data: preselectedMonitor } = preselectedMonitorId
  ? getMonitor(preselectedMonitorId)
  : { data: ref(null) }

const router = useRouter()
const submitting = ref(false)

const cancelReturnPath = computed(() => {
  if (isFromMonitorDetail.value && preselectedMonitorId) {
    return `/news-media/${preselectedMonitorId}`
  }
  return '/news-media/tasks'
})

const handleBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    navigateTo(cancelReturnPath.value)
  }
}

const schema = z.object({
  name: z.string().min(1, '任务名称不能为空').max(255, '任务名称不能超过255个字符'),
  keywords: z.string().min(1, '关键词不能为空'),
  monitor_id: z.number({ message: '请选择所属项目' }),
  phase: z.enum(['probe', 'collect']).optional(),
})

const state = reactive<{
  name: string
  keywords: string
  monitor_id: number | undefined
  phase: 'probe' | 'collect' | undefined
}>({
  name: '',
  keywords: '',
  monitor_id: preselectedMonitorId,
  phase: 'probe',
})

// ========== 项目搜索 ==========

const monitorSearchQuery = ref('')
const monitorSearchFocused = ref(false)
const selectedMonitorCache = ref<{ id: number; name: string } | null>(null)

const monitorSearchParams = computed(() => ({
  page: 1,
  page_size: 50,
  ...(monitorSearchQuery.value.trim() ? { search: monitorSearchQuery.value.trim() } : {}),
}))

const { data: monitorsData, pending: monitorsPending } = getMonitors(monitorSearchParams)

const monitorOptions = computed(() =>
  (monitorsData.value?.items || []).map((m) => ({ label: m.name, value: m.id })),
)

const selectedMonitorName = computed(() => {
  if (!state.monitor_id) return ''
  const fromResults = monitorOptions.value.find((m) => m.value === state.monitor_id)
  if (fromResults) return fromResults.label
  if (selectedMonitorCache.value?.id === state.monitor_id) return selectedMonitorCache.value.name
  return ''
})

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

const handleSearchInput = (value: string) => {
  monitorSearchQuery.value = value
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {}, 300)
}

const selectMonitor = (id: number, name: string) => {
  state.monitor_id = id
  selectedMonitorCache.value = { id, name }
  monitorSearchQuery.value = ''
  monitorSearchFocused.value = false
}

const handleMonitorInputFocus = () => {
  monitorSearchFocused.value = true
  monitorSearchQuery.value = ''
}

const handleMonitorInputBlur = () => {
  setTimeout(() => {
    monitorSearchFocused.value = false
    monitorSearchQuery.value = ''
  }, 200)
}

// ========== 提交 ==========

const handleSubmit = async () => {
  submitting.value = true
  try {
    const result = await createTask(state.monitor_id!, {
      name: state.name,
      keywords: state.keywords,
      phase: state.phase || null,
    })
    await navigateTo(`/news-media/tasks/${result.id}`)
  } catch {
    // error handled by apiRequest
  } finally {
    submitting.value = false
  }
}

const phaseOptions = [
  { label: '探测 (快速，百度 10 条)', value: 'probe' },
  { label: '全量 (双渠道，各 50 条)', value: 'collect' },
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="handleBack"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            新建新闻采集任务
          </h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">
            创建一个新的新闻搜索采集任务
          </p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          variant="outline"
          :disabled="submitting"
          :to="cancelReturnPath"
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

    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">
          任务信息
        </h2>
      </template>

      <UForm
        :schema="schema"
        :state="state"
        @submit="handleSubmit"
      >
        <div class="space-y-5">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 任务名称 -->
            <UFormField
              label="任务名称"
              name="name"
              required
            >
              <UInput
                v-model="state.name"
                placeholder="请输入任务名称"
                class="w-full"
              />
            </UFormField>

            <!-- 所属项目（预选时只读） -->
            <UFormField
              v-if="isFromMonitorDetail"
              label="所属项目"
            >
              <UInput
                :model-value="preselectedMonitor?.name || '加载中...'"
                disabled
                class="w-full"
              />
            </UFormField>

            <!-- 所属项目（搜索选择） -->
            <UFormField
              v-else
              label="所属项目"
              name="monitor_id"
              required
            >
              <div class="relative">
                <UInput
                  :model-value="monitorSearchFocused ? monitorSearchQuery : selectedMonitorName"
                  placeholder="输入项目名称搜索..."
                  icon="i-lucide-search"
                  :loading="monitorsPending"
                  class="w-full"
                  @update:model-value="handleSearchInput"
                  @focus="handleMonitorInputFocus"
                  @blur="handleMonitorInputBlur"
                />

                <div
                  v-if="monitorSearchFocused && !monitorsPending"
                  class="absolute z-10 mt-1 w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-60 overflow-auto"
                >
                  <template v-if="monitorOptions.length > 0">
                    <button
                      v-for="monitor in monitorOptions"
                      :key="monitor.value"
                      type="button"
                      class="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 text-sm"
                      :class="{
                        'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400':
                          state.monitor_id === monitor.value,
                      }"
                      @click="selectMonitor(monitor.value, monitor.label)"
                    >
                      {{ monitor.label }}
                    </button>
                  </template>
                  <div
                    v-else
                    class="px-3 py-2 text-sm text-gray-500"
                  >
                    {{ monitorSearchQuery ? '未找到匹配的项目' : '开始输入以搜索项目' }}
                  </div>
                </div>

                <div
                  v-if="monitorSearchFocused && monitorsPending"
                  class="absolute z-10 mt-1 w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg px-3 py-2"
                >
                  <div class="flex items-center gap-2 text-sm text-gray-500">
                    <UIcon name="i-lucide-loader-2" class="animate-spin" />
                    <span>搜索中...</span>
                  </div>
                </div>
              </div>
            </UFormField>
          </div>

          <!-- 关键词 -->
          <UFormField
            label="搜索关键词"
            name="keywords"
            help="输入新闻搜索关键词，多个词用空格或逗号分隔"
            required
          >
            <UInput
              v-model="state.keywords"
              placeholder="例如：新能源汽车 市场份额"
              class="w-full"
            />
          </UFormField>

          <!-- 采集阶段 -->
          <UFormField
            label="采集阶段"
            name="phase"
            help="探测阶段用于快速验证关键词效果，全量阶段采集完整数据"
          >
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label
                v-for="opt in phaseOptions"
                :key="opt.value"
                class="relative flex items-start p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                :class="{
                  'ring-2 ring-primary-500 border-primary-500': state.phase === opt.value,
                }"
              >
                <input
                  v-model="state.phase"
                  type="radio"
                  :value="opt.value"
                  class="mt-0.5 h-4 w-4 rounded-full border-gray-300 text-primary-600 focus:ring-primary-500"
                >
                <div class="ml-3 flex-1 text-sm">
                  {{ opt.label }}
                </div>
              </label>
            </div>
          </UFormField>
        </div>
      </UForm>
    </UCard>
  </div>
</template>
