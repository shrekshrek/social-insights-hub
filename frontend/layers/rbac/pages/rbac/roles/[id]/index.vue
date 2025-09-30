<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">角色详情</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">查看角色详细信息</p>
      </div>
      
      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo('/rbac/roles')"
      >
        返回列表
      </UButton>
    </div>

    <!-- 加载状态 -->
    <UCard v-if="pending">
      <div class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载角色信息中...</p>
      </div>
    </UCard>

    <!-- 错误状态 -->
    <UCard v-else-if="error">
      <div class="text-center py-8">
        <p class="text-red-500 mb-4">{{ error.message || '加载角色信息失败' }}</p>
        <UButton size="sm" @click="refresh()">重试</UButton>
      </div>
    </UCard>
    
    <!-- 角色详情 -->
    <RoleDetail
      v-else-if="data"
      :role="data"
      :can-edit="canEdit"
      :can-delete="canDelete"
      @edit="handleEdit"
      @edit-permissions="handleEditPermissions"
      @delete="handleDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { isCoreRole } from "../../../../utils/permissions";
import { PERMISSIONS } from "../../../../../../config/permissions";

// 页面元数据
definePageMeta({
  title: "角色详情",
  description: "查看角色详细信息",
});

// 路由参数
const route = useRoute();
const roleId = computed(() => Number(route.params.id));

// API 调用
const rbacApi = useRbacApi();
const { data, pending, error, refresh } = await rbacApi.getRole(roleId.value);

// 权限检查
const permissions = usePermissions();

const canEdit = computed(() => {
  if (!data.value) return false;
  return permissions.hasPermission(PERMISSIONS.ROLE_WRITE);
});

const canDelete = computed(() => {
  if (!data.value) return false;
  return permissions.hasPermission(PERMISSIONS.ROLE_DELETE) && !isCoreRole(data.value?.name);
});

// 事件处理
const handleEdit = () => {
  navigateTo(`/rbac/roles/${roleId.value}/edit`);
};

const handleEditPermissions = () => {
  navigateTo(`/rbac/roles/${roleId.value}/permissions`);
};

const handleDelete = async () => {
  if (!data.value) return;
  
  const { $confirm } = useNuxtApp();
  const confirmed = await $confirm(`确定要删除角色 "${data.value.display_name}" 吗？此操作不可撤销。`);
  if (!confirmed) return;
  
  try {
    await rbacApi.deleteRole(data.value.id);
    
    // 显示成功消息
    const toast = useToast();
    toast.add({
      title: '删除成功',
      description: `角色 "${data.value.display_name}" 已被删除`,
      color: 'success'
    });
    
    navigateTo('/rbac/roles');
  } catch {
    // 显示错误消息
    const toast = useToast();
    toast.add({
      title: '删除失败',
      description: '无法删除角色，请稍后重试',
      color: 'error'
    });
  }
};

// 监听路由变化
watch(() => route.params.id, async (newId) => {
  if (newId) {
    await refresh();
  }
});
</script> 