<template>
  <div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center p-4">
    <div class="w-full max-w-sm">
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-2">全栈项目脚手架</h1>
        <p class="text-gray-600 dark:text-gray-400">现代化的全栈开发解决方案</p>
      </div>
      
      <UCard class="shadow-xl">
        <slot />
      </UCard>
      
      <div class="text-center mt-6">
        <p class="text-sm text-gray-500 dark:text-gray-400">
          © 2024 全栈项目脚手架. 保留所有权利。
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script> 