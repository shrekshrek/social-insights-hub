<template>
  <!-- toaster=null 禁止 UApp 在 SSR/hydration 阶段渲染内联 Toaster
       避免 reka-ui 的 ToastPortal(Transition+Teleport) 触发 classList 报错 -->
  <UApp :toaster="null">
    <ClientOnly>
      <UToaster />
    </ClientOnly>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>

<script setup lang="ts">
// 认证状态管理已移至 plugins/auth-init.client.ts 统一处理
</script>
