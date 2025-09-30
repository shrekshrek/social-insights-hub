<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
    <div class="max-w-md w-full mx-auto text-center">
      <div class="mb-8">
        <UIcon 
          name="i-heroicons-lock-closed" 
          class="w-24 h-24 mx-auto text-gray-400 dark:text-gray-600 mb-4"
        />
        <h1 class="text-6xl font-bold text-gray-900 dark:text-white mb-2">
          401
        </h1>
        <p class="text-xl text-gray-600 dark:text-gray-400 mb-8">
          登录已过期
        </p>
        <p class="text-gray-500 dark:text-gray-400 mb-8">
          您的登录状态已过期，请重新登录以继续使用
        </p>
      </div>
      
      <div class="space-y-4">
        <UButton 
          size="lg" 
          color="primary" 
          class="w-full"
          @click="goToLogin"
        >
          重新登录
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
  title: '登录已过期 - 401',
  meta: [
    { name: 'description', content: '您的登录状态已过期，请重新登录' }
  ]
})

// 跳转到登录页
const goToLogin = () => {
  navigateTo('/login')
}

// 返回首页
const goHome = () => {
  navigateTo('/')
}
</script> 