<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">编辑角色权限</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          为角色 "{{ roleData?.display_name }}" 分配权限
        </p>
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

    <!-- 角色信息卡片 -->
    <UCard v-if="roleData">
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">角色信息</h2>
          <UBadge
            :color="isCoreRole(roleData?.name) ? 'warning' : 'neutral'"
            variant="soft"
          >
            {{ isCoreRole(roleData?.name) ? '核心角色' : '自定义角色' }}
          </UBadge>
        </div>
      </template>

      <div class="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div class="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
          <span class="text-sm font-medium text-primary-600 dark:text-primary-400">
            {{ roleData.display_name.charAt(0).toUpperCase() }}
          </span>
        </div>
        <div>
          <p class="font-medium text-gray-900 dark:text-white">{{ roleData.display_name }}</p>
          <p class="text-sm text-gray-500 dark:text-gray-400">{{ roleData.description || '暂无描述' }}</p>
        </div>
      </div>
    </UCard>

    <!-- 权限编辑卡片 -->
    <UCard v-if="roleData">
      <template #header>
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold">权限配置</h2>
          </div>
          <div class="flex items-center gap-3">
            <ClientOnly>
              <div class="flex items-center gap-2">
                <span class="text-sm text-gray-500 dark:text-gray-400">
                  当前: {{ roleData?.permissions?.length || 0 }} 个权限
                </span>
                <span class="text-sm text-gray-500 dark:text-gray-400">
                  已选: {{ selectedPermissions.length }} 个权限
                </span>
                <span v-if="hasChanges" class="text-xs text-orange-500 dark:text-orange-400">
                  • 有未保存的更改
                </span>
              </div>
            </ClientOnly>
            <UInput
              v-model="searchQuery"
              placeholder="搜索权限..."
              icon="i-heroicons-magnifying-glass"
              size="sm"
              class="w-64"
            />
          </div>
        </div>
      </template>

      <div class="space-y-6">
        <!-- 系统角色提示 -->
        <UAlert
          v-if="isCoreRole(roleData?.name)"
          color="warning"
          variant="soft"
          icon="i-heroicons-exclamation-triangle"
          title="核心角色"
          description="核心角色的权限由系统管理，修改后可能影响系统功能，请谨慎操作。"
        />

        <!-- 使用 ClientOnly 确保权限列表只在客户端渲染 -->
        <ClientOnly>
          <template #fallback>
            <div class="text-center py-8">
              <UIcon
                name="i-heroicons-arrow-path"
                class="animate-spin h-8 w-8 mx-auto text-gray-400"
              />
              <p class="mt-2 text-gray-600 dark:text-gray-400">正在加载权限数据...</p>
            </div>
          </template>

          <!-- 权限分类列表 -->
          <div v-if="permissionCategories.length > 0" class="space-y-4">
            <div
              v-for="category in permissionCategories"
              :key="category.name"
              class="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
            >
              <div class="flex items-center justify-between mb-3">
                <h3 class="font-medium text-gray-900 dark:text-white">
                  {{ category.label }} ({{ category.permissions.length }} 个)
                </h3>
                <div class="flex items-center gap-2">
                  <UButton
                    size="xs"
                    variant="outline"
                    @click="selectAllInCategory(category.name)"
                  >
                    全选
                  </UButton>
                  <UButton
                    size="xs"
                    variant="outline"
                    color="neutral"
                    @click="deselectAllInCategory(category.name)"
                  >
                    取消全选
                  </UButton>
                </div>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div
                  v-for="permission in category.permissions"
                  :key="permission.id"
                  class="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded transition-colors"
                >
                  <UCheckbox
                    :model-value="selectedPermissionIds.includes(permission.id!)"
                    :disabled="loading"
                    @update:model-value="togglePermission(permission.id!)"
                  />
                  <div class="flex-1">
                    <p class="text-sm font-medium text-gray-900 dark:text-white">
                      {{ permission.display_name }}
                    </p>
                    <p class="text-xs text-gray-500 dark:text-gray-400">
                      {{ `${permission.target}:${permission.action}` }}
                    </p>
                  </div>
                  <UBadge
                    :color="['user', 'role', 'permission'].includes(permission.target) ? 'warning' : 'primary'"
                    variant="soft"
                    size="xs"
                  >
                    {{ ['user', 'role', 'permission'].includes(permission.target) ? 'RBAC核心' : '业务权限' }}
                  </UBadge>
                </div>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-else class="text-center py-8">
            <UIcon name="i-heroicons-shield-exclamation" class="h-12 w-12 mx-auto text-gray-400" />
            <h3 class="mt-2 text-sm font-medium text-gray-900 dark:text-white">暂无权限数据</h3>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {{ searchQuery ? '未找到匹配的权限' : '系统中暂无可配置的权限' }}
            </p>
          </div>
        </ClientOnly>
      </div>

      <template #footer>
        <ClientOnly>
          <template #fallback>
            <div class="flex justify-between items-center">
              <div class="text-sm text-gray-500 dark:text-gray-400">
                正在加载权限数据...
              </div>
              <div class="flex items-center gap-3">
                <UButton variant="outline" disabled>取消</UButton>
                <UButton color="primary" disabled>保存权限</UButton>
              </div>
            </div>
          </template>

          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <UButton
                variant="outline"
                size="sm"
                :disabled="loading"
                @click="resetSelection"
              >
                重置选择
              </UButton>
            </div>
            <div class="flex items-center gap-3">
              <UButton
                variant="outline"
                :disabled="loading"
                @click="handleCancel"
              >
                取消
              </UButton>
              <UButton
                color="primary"
                :loading="loading"
                :disabled="!hasChanges"
                @click="handleSubmit"
              >
                保存权限
              </UButton>
            </div>
          </div>
        </ClientOnly>
      </template>
    </UCard>

    <!-- 加载状态 -->
    <div v-else class="flex justify-center py-8">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin h-6 w-6" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PermissionWithMeta as Permission } from "../../../../types";
import { isCoreRole } from "../../../../utils/permissions";
// 注意：权限分组现在通过API动态获取，无需导入静态配置

// 页面元数据
definePageMeta({
  title: "编辑角色权限",
  description: "为角色分配权限",
});

// 路由参数
const route = useRoute();
const roleId = computed(() => Number(route.params.id));

// 响应式数据
const loading = ref(false);
const selectedPermissionIds = ref<number[]>([]);
const searchQuery = ref("");

// 使用API
const rbacApi = useRbacApi();

// 获取角色详情
const { data: roleData, pending: _roleLoading, error: _roleError } = await rbacApi.getRole(roleId.value);

// 获取所有权限
const { data: permissionsData } = rbacApi.getPermissions();

// 计算属性
const availablePermissions = computed(() => {
  return permissionsData.value?.items || [];
});


// 过滤权限
const filteredPermissions = computed(() => {
  if (!searchQuery.value) return availablePermissions.value;
  
  const query = searchQuery.value.toLowerCase();
  return availablePermissions.value.filter(permission =>
    permission.display_name.toLowerCase().includes(query) ||
    permission.target.toLowerCase().includes(query) ||
    permission.action.toLowerCase().includes(query) ||
    `${permission.target}:${permission.action}`.toLowerCase().includes(query)
  );
});

// 权限分类 - 基于业务逻辑重新设计
const permissionCategories = computed(() => {
  const categories: Record<string, { label: string; permissions: Permission[]; priority: number }> = {};
  
  // 动态分类权限
  filteredPermissions.value.forEach(permission => {
    let categoryKey: string;
    let categoryLabel: string;
    let priority: number;
    
    // 页面访问权限
    if (permission.action === 'access') {
      categoryKey = 'page_access';
      categoryLabel = '页面访问权限';
      priority = 1;
    }
    // RBAC核心权限 
    else if (['user', 'role', 'permission'].includes(permission.target)) {
      categoryKey = 'rbac_core';
      categoryLabel = 'RBAC核心权限';
      priority = 2;
    }
    // 业务功能权限
    else {
      categoryKey = `business_${permission.target}`;
      categoryLabel = `${permission.target}模块权限`;
      priority = 3;
    }
    
    // 创建分类
    if (!categories[categoryKey]) {
      categories[categoryKey] = {
        label: categoryLabel,
        permissions: [],
        priority
      };
    }
    
    categories[categoryKey]?.permissions.push(permission);
  });

  // 按优先级排序并返回
  return Object.entries(categories)
    .filter(([_, category]) => category.permissions.length > 0)
    .sort(([_, a], [__, b]) => a.priority - b.priority)
    .map(([name, category]) => ({
      name,
      label: category.label,
      permissions: category.permissions
    }));
});

const selectedPermissions = computed(() => {
  return availablePermissions.value.filter(permission => 
    selectedPermissionIds.value.includes(permission.id!)
  );
});

// 检查是否有变更
const hasChanges = computed(() => {
  const originalIds = roleData.value?.permissions?.map((p: Permission) => p.id!).sort() || [];
  const currentIds = [...selectedPermissionIds.value].sort();
  
  if (originalIds.length !== currentIds.length) return true;
  
  return originalIds.some((id: number, index: number) => id !== currentIds[index]);
});

// 监听角色数据变化，确保权限选中状态正确初始化
watch(roleData, (newRole) => {
  if (newRole && newRole.permissions) {
    selectedPermissionIds.value = newRole.permissions.map((p: Permission) => p.id!);
  }
}, { immediate: true });

// 权限操作
const togglePermission = (permissionId: number) => {
  const index = selectedPermissionIds.value.indexOf(permissionId);
  if (index > -1) {
    selectedPermissionIds.value.splice(index, 1);
  } else {
    selectedPermissionIds.value.push(permissionId);
  }
};

const selectAllInCategory = (categoryName: string) => {
  const category = permissionCategories.value.find(c => c.name === categoryName);
  if (category) {
    category.permissions.forEach(permission => {
      if (!selectedPermissionIds.value.includes(permission.id!)) {
        selectedPermissionIds.value.push(permission.id!);
      }
    });
  }
};

const deselectAllInCategory = (categoryName: string) => {
  const category = permissionCategories.value.find(c => c.name === categoryName);
  if (category) {
    category.permissions.forEach(permission => {
      const index = selectedPermissionIds.value.indexOf(permission.id!);
      if (index > -1) {
        selectedPermissionIds.value.splice(index, 1);
      }
    });
  }
};

const resetSelection = () => {
  selectedPermissionIds.value = roleData.value?.permissions?.map((p: Permission) => p.id!) || [];
};

// 事件处理
const handleSubmit = async () => {
  if (!roleData.value) return;

  loading.value = true;
  try {
    await rbacApi.updateRolePermissions(roleData.value.id, selectedPermissionIds.value);
    // 返回角色详情页
    navigateTo(`/rbac/roles/${roleId.value}`);
  } catch (error) {
    console.error("更新角色权限失败:", error);
    // 错误已由 useApi 自动处理
  } finally {
    loading.value = false;
  }
};

const handleCancel = () => {
  navigateTo(`/rbac/roles/${roleId.value}`);
};
</script> 
