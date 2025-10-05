<template>
  <div v-if="task" class="space-y-6">
    <!-- 基本信息卡片 -->
    <UCard class="shadow-sm">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-4">
            <div>
              <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{{ task.name }}</h2>
              <div class="mt-2 flex items-center gap-2">
                <UBadge :color="statusColor" variant="subtle">
                  {{ TASK_STATUS_LABELS[task.status] }}
                </UBadge>
                <UBadge color="gray" variant="subtle">
                  {{ PLATFORM_LABELS[task.platform] }}
                </UBadge>
                <UBadge color="gray" variant="subtle">
                  {{ CRAWLER_TYPE_LABELS[task.crawler_type] }}
                </UBadge>
              </div>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <!-- 执行控制按钮 -->
            <UButton
              v-if="canExecute && task.status === 'pending'"
              icon="i-heroicons-play"
              color="green"
              size="sm"
              @click="$emit('start')"
            >
              启动
            </UButton>

            <UButton
              v-if="canExecute && task.status === 'running'"
              icon="i-heroicons-pause"
              color="yellow"
              size="sm"
              @click="$emit('pause')"
            >
              暂停
            </UButton>

            <UButton
              v-if="canExecute && (task.status === 'running' || task.status === 'paused')"
              icon="i-heroicons-stop"
              color="red"
              size="sm"
              @click="$emit('stop')"
            >
              停止
            </UButton>

            <UButton
              v-if="canEdit && task.status === 'pending'"
              icon="i-heroicons-pencil-square"
              variant="outline"
              size="sm"
              color="primary"
              @click="$emit('edit')"
            >
              编辑
            </UButton>

            <UButton
              v-if="canDelete && task.status !== 'running'"
              icon="i-heroicons-trash"
              variant="outline"
              size="sm"
              color="error"
              @click="$emit('delete')"
            >
              删除
            </UButton>

            <UButton
              icon="i-heroicons-arrow-path"
              variant="outline"
              size="sm"
              @click="$emit('refresh')"
            >
              刷新
            </UButton>
          </div>
        </div>
      </template>

      <div class="space-y-6">
        <!-- 基本信息 -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">任务ID</label>
            <p class="text-gray-900 dark:text-gray-100 font-mono text-sm">{{ task.id }}</p>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">状态</label>
            <UBadge :color="statusColor" variant="subtle">
              {{ TASK_STATUS_LABELS[task.status] }}
            </UBadge>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">平台</label>
            <p class="text-gray-900 dark:text-gray-100">{{ PLATFORM_LABELS[task.platform] }}</p>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">爬取模式</label>
            <p class="text-gray-900 dark:text-gray-100">{{ CRAWLER_TYPE_LABELS[task.crawler_type] }}</p>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">进度</label>
            <div class="flex items-center gap-2">
              <p class="text-gray-900 dark:text-gray-100">{{ task.progress }}%</p>
              <div class="flex-1">
                <div class="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-blue-500 transition-all"
                    :style="{ width: `${task.progress}%` }"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">已抓取数量</label>
            <p class="text-gray-900 dark:text-gray-100 font-medium">{{ task.crawled_count }}</p>
          </div>
        </div>

        <!-- 时间信息 -->
        <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div class="space-y-1">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">创建时间</label>
              <p class="text-gray-900 dark:text-gray-100">{{ formatDate(task.created_at) }}</p>
            </div>

            <div class="space-y-1">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">更新时间</label>
              <p class="text-gray-900 dark:text-gray-100">{{ formatDate(task.updated_at) }}</p>
            </div>

            <div v-if="task.started_at" class="space-y-1">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">开始时间</label>
              <p class="text-gray-900 dark:text-gray-100">{{ formatDate(task.started_at) }}</p>
            </div>

            <div v-if="task.completed_at" class="space-y-1">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">完成时间</label>
              <p class="text-gray-900 dark:text-gray-100">{{ formatDate(task.completed_at) }}</p>
            </div>
          </div>
        </div>

        <!-- 错误信息 -->
        <div v-if="task.error_message" class="pt-4 border-t border-gray-200 dark:border-gray-700">
          <div class="space-y-1">
            <label class="block text-sm font-medium text-red-700 dark:text-red-400">错误信息</label>
            <div class="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <p class="text-red-900 dark:text-red-200 text-sm font-mono">{{ task.error_message }}</p>
            </div>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 任务配置卡片 -->
    <UCard class="shadow-sm">
      <template #header>
        <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">任务配置</h3>
      </template>

      <div class="space-y-4">
        <div v-if="task.config.keywords" class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">关键词</label>
          <div class="flex flex-wrap gap-1">
            <UBadge
              v-for="(keyword, index) in task.config.keywords?.split(',')"
              :key="index"
              color="blue"
              variant="subtle"
            >
              {{ keyword.trim() }}
            </UBadge>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">最大抓取数量</label>
            <p class="text-gray-900 dark:text-gray-100">{{ task.config.max_count }}</p>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">抓取评论</label>
            <UBadge :color="task.config.enable_comments ? 'green' : 'gray'" variant="subtle">
              {{ task.config.enable_comments ? '是' : '否' }}
            </UBadge>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">抓取子评论</label>
            <UBadge :color="task.config.enable_sub_comments ? 'green' : 'gray'" variant="subtle">
              {{ task.config.enable_sub_comments ? '是' : '否' }}
            </UBadge>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">使用代理</label>
            <UBadge :color="task.config.proxy_enabled ? 'green' : 'gray'" variant="subtle">
              {{ task.config.proxy_enabled ? '是' : '否' }}
            </UBadge>
          </div>

          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">启用断点续传</label>
            <UBadge :color="task.config.enable_checkpoint ? 'green' : 'gray'" variant="subtle">
              {{ task.config.enable_checkpoint ? '是' : '否' }}
            </UBadge>
          </div>

          <div v-if="task.checkpoint_id" class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">断点ID</label>
            <p class="text-gray-900 dark:text-gray-100 font-mono text-sm">{{ task.checkpoint_id }}</p>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 任务日志卡片 -->
    <UCard class="shadow-sm">
      <template #header>
        <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">任务日志</h3>
      </template>

      <div v-if="task.logs && task.logs.length > 0" class="space-y-2 max-h-96 overflow-y-auto">
        <div
          v-for="log in task.logs"
          :key="log.id"
          class="p-3 rounded-lg"
          :class="getLogColorClass(log.level)"
        >
          <div class="flex items-start gap-2">
            <UBadge :color="getLogBadgeColor(log.level)" variant="subtle" size="xs">
              {{ log.level }}
            </UBadge>
            <div class="flex-1">
              <p class="text-sm">{{ log.message }}</p>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ formatDate(log.created_at) }}</p>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="text-center py-8">
        <p class="text-gray-500 dark:text-gray-400">暂无日志</p>
      </div>
    </UCard>
  </div>

  <UCard v-else>
    <div class="text-center py-8">
      <p class="text-gray-500 dark:text-gray-400">任务信息不存在</p>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { CrawlerTaskDetail, TaskStatus } from '../types'
import {
  PLATFORM_LABELS,
  CRAWLER_TYPE_LABELS,
  TASK_STATUS_LABELS,
  TASK_STATUS_COLORS
} from '../types'

// Props
interface Props {
  task?: CrawlerTaskDetail | null
  canEdit?: boolean
  canDelete?: boolean
  canExecute?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  task: null,
  canEdit: false,
  canDelete: false,
  canExecute: false
})

// Emits
defineEmits<{
  'start': []
  'pause': []
  'stop': []
  'edit': []
  'delete': []
  'refresh': []
}>()

// 计算属性
const statusColor = computed(() => {
  return props.task ? TASK_STATUS_COLORS[props.task.status as TaskStatus] : 'gray'
})

// 工具函数
const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const getLogBadgeColor = (level: string) => {
  const colorMap: Record<string, string> = {
    ERROR: 'red',
    WARNING: 'yellow',
    INFO: 'blue',
    DEBUG: 'gray'
  }
  return colorMap[level.toUpperCase()] || 'gray'
}

const getLogColorClass = (level: string) => {
  const classMap: Record<string, string> = {
    ERROR: 'bg-red-50 dark:bg-red-900/20',
    WARNING: 'bg-yellow-50 dark:bg-yellow-900/20',
    INFO: 'bg-blue-50 dark:bg-blue-900/20',
    DEBUG: 'bg-gray-50 dark:bg-gray-900/20'
  }
  return classMap[level.toUpperCase()] || 'bg-gray-50 dark:bg-gray-900/20'
}
</script>
