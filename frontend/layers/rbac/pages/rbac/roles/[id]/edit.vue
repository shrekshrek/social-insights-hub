<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">编辑角色</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">修改角色信息</p>
      </div>
      
      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-arrow-left"
          variant="outline"
          size="sm"
          @click="handleCancel"
        >
          返回
        </UButton>
      </div>
    </div>

    <!-- 编辑表单卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">角色信息</h2>
          <UBadge
            v-if="role"
            :color="isCoreRole(role?.name) ? 'warning' : 'neutral'"
            variant="soft"
          >
            {{ isCoreRole(role?.name) ? '核心角色' : '自定义角色' }}
          </UBadge>
        </div>
      </template>

      <RoleForm
        v-if="role"
        :role="role"
        :loading="loading"
        :is-edit="true"
        @submit="handleSubmit"
        @cancel="handleCancel"
      />
      
      <div v-else class="flex justify-center py-8">
        <UIcon name="i-heroicons-arrow-path" class="animate-spin h-6 w-6" />
      </div>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { Role, RoleUpdate } from "../../../../types";
import RoleForm from "../../../../components/RoleForm.vue";
import { isCoreRole } from "../../../../utils/permissions";

// 页面元数据
definePageMeta({
  title: "编辑角色",
  description: "修改角色信息",
});

// 路由参数
const route = useRoute();
const roleId = computed(() => Number(route.params.id));

// 响应式数据
const role = ref<Role | null>(null);
const loading = ref(false);

// 使用API
const rbacApi = useRbacApi();

// 获取角色详情
const fetchRole = async () => {
  try {
    const response = await rbacApi.getRole(roleId.value);
    role.value = response.data.value ?? null;
  } catch (error) {
    console.error("获取角色详情失败:", error);
    
    const toast = useToast();
    toast.add({
      title: "获取数据失败",
      description: "无法获取角色详情，请稍后重试",
      color: "error",
    });
    
    // 如果获取失败，返回列表页
    navigateTo("/rbac/roles");
  }
};

// 初始化数据
onMounted(async () => {
  await fetchRole();
});

// 处理表单提交
const handleSubmit = async (data: RoleUpdate) => {
  loading.value = true;
  try {
    await rbacApi.updateRole(roleId.value, data);
    
    // 显示成功消息
    const toast = useToast();
    toast.add({
      title: "更新成功",
      description: `角色 "${data.display_name}" 已更新`,
      color: "success",
    });
    
    // 返回详情页
    navigateTo(`/rbac/roles/${roleId.value}`);
  } catch (error) {
    console.error("更新角色失败:", error);
    
    // 显示错误消息
    const toast = useToast();
    toast.add({
      title: "更新失败",
      description: "无法更新角色，请稍后重试",
      color: "error",
    });
  } finally {
    loading.value = false;
  }
};

// 处理取消
const handleCancel = () => {
  navigateTo(`/rbac/roles/${roleId.value}`);
};
</script> 