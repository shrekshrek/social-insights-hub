<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
    <div class="max-w-md w-full mx-auto text-center">
      <div class="mb-8">
        <UIcon 
          :name="errorIcon" 
          class="w-24 h-24 mx-auto text-gray-400 dark:text-gray-600 mb-4"
        />
        <h1 class="text-6xl font-bold text-gray-900 dark:text-white mb-2">
          {{ error.statusCode }}
        </h1>
        <p class="text-xl text-gray-600 dark:text-gray-400 mb-8">
          {{ errorMessage }}
        </p>
      </div>
      
      <div class="space-y-4">
        <UButton 
          size="lg" 
          color="primary" 
          class="w-full"
          @click="handleError"
        >
          {{ buttonText }}
        </UButton>
        
        <UButton 
          variant="ghost" 
          size="lg" 
          class="w-full"
          @click="goHome"
        >
          返回首页
        </UButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { NuxtError } from '#app'

// 定义props
const props = defineProps<{
  error: NuxtError
}>()

// 计算错误信息
const errorMessage = computed(() => {
  switch (props.error.statusCode) {
    case 404:
      return '页面未找到'
    case 500:
      return '服务器内部错误'
    case 403:
      return '访问被拒绝'
    default:
      return props.error.statusMessage || '发生了未知错误'
  }
})

// 计算错误图标
const errorIcon = computed(() => {
  switch (props.error.statusCode) {
    case 404:
      return 'i-heroicons-document-magnifying-glass'
    case 500:
      return 'i-heroicons-exclamation-triangle'
    case 403:
      return 'i-heroicons-lock-closed'
    default:
      return 'i-heroicons-x-circle'
  }
})

// 计算按钮文本
const buttonText = computed(() => {
  switch (props.error.statusCode) {
    case 404:
      return '刷新页面'
    default:
      return '重试'
  }
})

// 处理错误
const handleError = () => {
  clearError({ redirect: '/' })
}

// 返回首页
const goHome = () => {
  clearError({ redirect: '/' })
}

// 设置页面标题
useHead({
  title: `错误 ${props.error.statusCode}`,
  meta: [
    { name: 'description', content: errorMessage.value }
  ]
})
</script> 