<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">编辑用户</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">修改用户信息</p>
      </div>
      
      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo(`/users/${userId}`)"
      >
        返回详情
      </UButton>
    </div>

    <!-- 加载状态 -->
    <UCard v-if="pending">
      <div class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载用户信息中...</p>
      </div>
    </UCard>

    <!-- 错误状态 -->
    <UCard v-else-if="error">
      <div class="text-center py-8">
        <p class="text-red-500 mb-4">{{ error.message || "加载用户信息失败" }}</p>
        <UButton size="sm" @click="refresh()">重试</UButton>
      </div>
    </UCard>

    <!-- 编辑表单 -->
    <UCard v-else-if="data">
      <template #header>
        <div class="flex items-center gap-3">
          <UAvatar
            :alt="data.username"
            size="sm"
          >
            {{ data.username.charAt(0).toUpperCase() }}
          </UAvatar>
          <div>
            <h2 class="text-lg font-semibold">编辑用户信息</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400">
              {{ data.username }} ({{ data.email }})
            </p>
          </div>
        </div>
      </template>

      <UserForm
        :user="data"
        :loading="loading"
        :is-edit="true"
        @submit="handleSubmit"
        @cancel="handleCancel"
      />
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { UserUpdate } from "../../../types";

// 页面元数据
definePageMeta({
  title: "编辑用户"
});

// 路由参数
const route = useRoute();
const userId = computed(() => Number(route.params.id));

// API 调用
const usersApi = useUsersApi();
const { data, pending, error, refresh } = await usersApi.getUser(userId.value);

// 状态管理
const loading = ref(false);

// 事件处理
const handleSubmit = async (updateData: UserUpdate) => {
  if (!data.value) return;

  loading.value = true;
  try {
    await usersApi.updateUser(data.value.id, updateData);
    navigateTo(`/users/${userId.value}`);
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    loading.value = false;
  }
};

const handleCancel = () => {
  navigateTo(`/users/${userId.value}`);
};

// 监听路由变化
watch(
  () => route.params.id,
  async (newId) => {
    if (newId) {
      await refresh();
    }
  }
);
</script> 
