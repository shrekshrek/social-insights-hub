<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
    <div class="max-w-md w-full mx-auto text-center">
      <div class="mb-8">
        <UIcon 
          name="i-heroicons-shield-exclamation" 
          class="w-24 h-24 mx-auto text-red-400 dark:text-red-500 mb-4"
        />
        <h1 class="text-6xl font-bold text-gray-900 dark:text-white mb-2">
          403
        </h1>
        <p class="text-xl text-gray-600 dark:text-gray-400 mb-8">
          访问被拒绝
        </p>
        <p class="text-gray-500 dark:text-gray-400 mb-8">
          您没有权限访问此页面，请联系管理员获取相应权限
        </p>
      </div>
      
      <div class="space-y-4">
        <UButton 
          size="lg" 
          color="primary" 
          class="w-full"
          @click="goBack"
        >
          返回上一页
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
// 页面元数据
definePageMeta({
  layout: false, // 不使用默认布局
})

// 设置页面标题
useHead({
  title: '访问被拒绝 - 403',
  meta: [
    { name: 'description', content: '您没有权限访问此页面' }
  ]
})

// 返回上一页
const goBack = () => {
  // 如果有历史记录，返回上一页，否则返回首页
  if (history.length > 1) {
    history.back()
  } else {
    navigateTo('/')
  }
}

// 返回首页
const goHome = () => {
  navigateTo('/')
}
</script> 