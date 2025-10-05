<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">创建爬虫任务</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">添加新的爬虫任务</p>
      </div>

      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo('/crawler-tasks')"
      >
        返回列表
      </UButton>
    </div>

    <!-- 创建表单 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">任务信息</h2>
      </template>

      <TaskForm
        :loading="loading"
        @submit="handleSubmit"
        @cancel="handleCancel"
      />
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { TaskCreateRequest } from '../../types'

// 页面元数据
definePageMeta({
  title: '创建爬虫任务'
})

// 状态
const loading = ref(false)

// API
const crawlerTasksApi = useCrawlerTasksApi()

// 处理表单提交
const handleSubmit = async (data: TaskCreateRequest) => {
  loading.value = true
  try {
    await crawlerTasksApi.createTask(data)

    // 显示成功消息
    const toast = useToast()
    toast.add({
      title: '创建成功',
      description: `任务 "${data.name}" 已创建`,
      color: 'success'
    })

    navigateTo('/crawler-tasks')
  } catch (error) {
    console.error('创建任务失败:', error)

    // 显示错误消息
    const toast = useToast()
    toast.add({
      title: '创建失败',
      description: '无法创建任务，请稍后重试',
      color: 'error'
    })
  } finally {
    loading.value = false
  }
}

// 处理取消
const handleCancel = () => {
  navigateTo('/crawler-tasks')
}
</script>
