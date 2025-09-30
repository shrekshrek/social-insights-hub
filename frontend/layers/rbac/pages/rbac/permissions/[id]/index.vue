<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">权限详情</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">查看权限详细信息</p>
      </div>
      
      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo('/rbac/permissions')"
      >
        返回列表
      </UButton>
    </div>

    <!-- 加载状态 -->
    <UCard v-if="pending">
      <div class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载权限信息中...</p>
      </div>
    </UCard>

    <!-- 错误状态 -->
    <UCard v-else-if="error">
      <div class="text-center py-8">
        <p class="text-red-500 mb-4">{{ error.message || '加载权限信息失败' }}</p>
        <UButton size="sm" @click="refresh()">重试</UButton>
      </div>
    </UCard>
    
    <!-- 权限详情 -->
    <PermissionDetail
      v-else-if="data"
      :permission="data"
    />
  </div>
</template>

<script setup lang="ts">
// 页面元数据
definePageMeta({
  title: "权限详情",
  description: "查看权限详细信息",
});

// 路由参数
const route = useRoute();
const permissionId = computed(() => Number(route.params.id));

// API 调用
const rbacApi = useRbacApi();
const { data, pending, error, refresh } = await rbacApi.getPermission(permissionId.value);

// 权限详情为只读模式，所有权限通过代码管理

// 监听路由变化
watch(() => route.params.id, async (newId) => {
  if (newId) {
    await refresh();
  }
});
</script> 