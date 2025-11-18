<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            @click="handleCancel"
          />
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ role?.display_name || '加载中...' }}
            </h1>
            <p class="text-gray-600 dark:text-gray-400 mt-1">
              编辑角色信息
            </p>
          </div>
        </div>
      </div>

      <ClientOnly>
        <div v-if="role" class="flex items-center gap-3">
          <UButton
            variant="outline"
            :disabled="loading"
            @click="handleCancel"
          >
            取消
          </UButton>
          <UButton
            :loading="loading"
            @click="handleFormSubmit"
          >
            保存
          </UButton>
        </div>
      </ClientOnly>
    </div>

    <!-- 编辑表单卡片 -->
    <ClientOnly>
      <template #fallback>
        <UCard>
          <div class="flex justify-center py-8">
            <UIcon name="i-heroicons-arrow-path" class="animate-spin h-6 w-6" />
          </div>
        </UCard>
      </template>

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
          ref="roleFormRef"
          :role="role"
          :loading="loading"
          :is-edit="true"
          :hide-actions="true"
          @submit="handleSubmit"
          @cancel="handleCancel"
        />
      </UCard>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import type { RoleUpdate } from "../../../../types";
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

// 使用API
const rbacApi = useRbacApi();

// 获取角色详情（使用顶层 await）
const { data: role, pending: _rolePending, error: _roleError } = await rbacApi.getRole(roleId.value);

// 如果获取失败，返回列表页
if (_roleError.value) {
  console.error("获取角色详情失败:", _roleError.value);
  navigateTo("/rbac/roles");
}

// 响应式数据
const loading = ref(false);
const roleFormRef = ref<InstanceType<typeof RoleForm> | null>(null);

// 处理表单提交
const handleSubmit = async (data: RoleUpdate) => {
  loading.value = true;
  try {
    await rbacApi.updateRole(roleId.value, data);
    // 返回详情页
    navigateTo(`/rbac/roles/${roleId.value}`);
  } catch (error) {
    console.error("更新角色失败:", error);
    // 错误已由 useApi 自动处理
  } finally {
    loading.value = false;
  }
};

// 处理取消
const handleCancel = () => {
  navigateTo(`/rbac/roles/${roleId.value}`);
};

const handleFormSubmit = () => {
  if (roleFormRef.value) {
    roleFormRef.value.handleSubmit();
  }
};
</script> 
