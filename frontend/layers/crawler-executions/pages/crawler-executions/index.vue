<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold">任务执行监控</h1>
      <p class="text-gray-500">查看任务进度、执行结果与日志摘要。</p>
    </div>

    <div class="grid gap-6 md:grid-cols-3">
      <div class="space-y-3">
        <h2 class="text-lg font-medium">任务列表</h2>
        <UCard
          v-for="task in tasks"
          :key="task.id"
          :ui="{ body: 'space-y-2 cursor-pointer' }"
          :class="[
            'transition-colors',
            selectedTask && selectedTask.id === task.id ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : ''
          ]"
          @click="selectTask(task)"
        >
          <div class="flex items-center justify-between">
            <span class="font-medium">{{ task.name }}</span>
            <UBadge :color="statusColor(task.status)">{{ statusLabel(task.status) }}</UBadge>
          </div>
          <div class="text-sm text-gray-500 flex flex-col gap-1">
            <span>平台：{{ task.platform }}</span>
            <span>模式：{{ task.crawler_type }}</span>
            <span>进度：{{ task.progress }}%</span>
          </div>
        </UCard>
        <UAlert
          v-if="tasks.length === 0 && !loadingTasks"
          color="warning"
          title="暂无任务"
          description="创建一个爬虫任务后即可在此查看执行情况。"
        />
        <USkeleton v-if="loadingTasks" :ui="{ rounded: 'rounded-lg' }" class="h-24" />
      </div>

      <div class="md:col-span-2 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-medium">执行结果</h2>
            <p v-if="selectedTask" class="text-gray-500 text-sm">
              任务：{{ selectedTask.name }} · 已获取 {{ results.length }} 条记录
            </p>
          </div>
          <UButton
            v-if="selectedTask"
            size="sm"
            :loading="loadingResults"
            icon="i-heroicons-arrow-path"
            variant="ghost"
            @click="refreshResults"
          >刷新</UButton>
        </div>

        <div v-if="loadingResults" class="space-y-2">
          <USkeleton v-for="i in 3" :key="i" :ui="{ rounded: 'rounded-lg' }" class="h-12" />
        </div>

        <div v-else-if="results.length === 0">
          <UAlert
            color="info"
            title="暂无结果"
            description="任务尚未生成可展示的结果，稍后再试或检查日志。"
          />
        </div>

        <UTable
          v-else
          :rows="results"
          :columns="columns"
          :ui="{ td: { base: 'whitespace-normal align-top' } }"
        >
          <template #title-data="{ row }">
            <span class="font-medium">{{ row.title }}</span>
          </template>
          <template #keyword-data="{ row }">
            <UBadge v-if="row.keyword" color="primary">{{ row.keyword }}</UBadge>
            <span v-else class="text-gray-400">—</span>
          </template>
          <template #created_at-data="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </UTable>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import type { CrawlerTaskResponse } from '~/layers/crawler-tasks/types'
import { useApi } from '~/app/composables/useApi'

defineOptions({ name: 'CrawlerExecutionsPage' })

interface NoteResult {
  id: number
  note_id: string
  title: string
  keyword?: string | null
  created_at: string
  raw_data?: Record<string, unknown> | null
}

const { apiRequest } = useApi()
const tasks = ref<CrawlerTaskResponse[]>([])
const results = ref<NoteResult[]>([])
const selectedTask = ref<CrawlerTaskResponse | null>(null)
const loadingTasks = ref(false)
const loadingResults = ref(false)

const columns = computed(() => [
  { key: 'note_id', label: '笔记ID' },
  { key: 'title', label: '标题' },
  { key: 'keyword', label: '关键词' },
  { key: 'created_at', label: '采集时间' },
])

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] ?? status
}

function statusColor(status: string) {
  const map: Record<string, string> = {
    pending: 'gray',
    running: 'primary',
    paused: 'warning',
    completed: 'success',
    failed: 'error',
    cancelled: 'secondary',
  }
  return map[status] ?? 'gray'
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) {
    return value
  }
  return date.toLocaleString()
}

async function fetchTasks() {
  loadingTasks.value = true
  try {
    const res = await apiRequest<PaginatedResponse<CrawlerTaskResponse>>('/crawler-tasks')
    tasks.value = res.items ?? []
    if (tasks.value.length > 0) {
      const firstTask = tasks.value[0]
      if (firstTask) {
        await selectTask(firstTask)
      }
    }
  } finally {
    loadingTasks.value = false
  }
}

async function selectTask(task: CrawlerTaskResponse) {
  selectedTask.value = task
  await loadResults(task.id)
}

async function loadResults(taskId: number) {
  loadingResults.value = true
  try {
    results.value = await apiRequest<NoteResult[]>(`/crawler-tasks/${taskId}/results`)
  } finally {
    loadingResults.value = false
  }
}

async function refreshResults() {
  if (selectedTask.value) {
    await loadResults(selectedTask.value.id)
  }
}

onMounted(fetchTasks)
</script>
