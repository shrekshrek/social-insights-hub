<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          角色管理
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理系统中的所有角色
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          @click="navigateTo('/rbac/roles/create')"
        >
          新增角色
        </UButton>
        <UButton
          variant="outline"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </div>
    </div>

    <!-- 角色列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">角色列表</h2>
          <UInput
            v-model="searchQuery"
            placeholder="搜索角色名称或描述..."
            icon="i-heroicons-magnifying-glass"
            class="w-80"
          />
        </div>
      </template>

      <!-- 角色表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载角色列表中...</p>
          </div>
        </template>

        <UTable
          :data="paginatedRoles"
          :columns="columns"
          :loading="loading"
          class="w-full"
        />
      </ClientOnly>

      <!-- 分页 -->
      <template #footer>
        <ClientOnly>
          <template #fallback>
            <div class="flex justify-between items-center">
              <div class="h-4 bg-gray-200 rounded w-32 animate-pulse"/>
              <div class="h-8 bg-gray-200 rounded w-64 animate-pulse"/>
            </div>
          </template>

          <div class="flex justify-between items-center">
            <div class="text-sm text-gray-500 dark:text-gray-400">
              显示 {{ (currentPage - 1) * pageSize + 1 }} 到
              {{ Math.min(currentPage * pageSize, total) }} 共
              {{ total }} 条记录
            </div>
            <UPagination
              v-model:page="currentPage"
              :total="total"
              :items-per-page="pageSize"
              :sibling-count="2"
              show-first
              show-last
              show-edges
              :disabled="total === 0"
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { h, ref, computed, watch, resolveComponent } from "vue";
import type { Role, PermissionWithMeta as Permission } from "../../../types";
import type { TableColumn } from "@nuxt/ui";
import { isCoreRole } from "../../../utils/permissions";

// 页面元数据
definePageMeta({
  title: "角色管理",
  description: "管理系统中的所有角色",
});

// 常量定义
const DEFAULT_PAGE_SIZE = 10;

// 路由和查询参数
const route = useRoute();
const router = useRouter();

// 响应式数据
const searchQuery = ref("");
const refreshing = ref(false);

// 从 URL 查询参数获取当前页码，确保 SSR 兼容
const currentPage = computed({
  get: () => parseInt(route.query.page as string) || 1,
  set: (value: number) => {
    router.push({
      query: { ...route.query, page: value.toString() }
    });
  }
});

const pageSize = ref(DEFAULT_PAGE_SIZE);

// API 调用 - 使用后端分页
const rbacApi = useRbacApi();

// 获取角色数据 - 使用响应式参数支持后端分页
const {
  data: rolesData,
  pending,
  refresh,
} = rbacApi.getRoles({
  page: currentPage,
  page_size: pageSize,
});

// 计算属性
const loading = computed(() => pending.value || refreshing.value);

// 计算属性 - 从API数据中获取显示内容
const displayRoles = computed(() => {
  const items = rolesData.value?.items || [];

  // 如果有搜索查询，过滤数据
  if (!searchQuery.value) {
    return items;
  }

  const query = searchQuery.value.toLowerCase();
  return items.filter(
    (role) =>
      role.name.toLowerCase().includes(query) ||
      role.display_name.toLowerCase().includes(query) ||
      (role.description &&
        role.description.toLowerCase().includes(query))
  );
});

// 分页相关计算属性
const total = computed(() => rolesData.value?.total || 0);

// 分页数据
const paginatedRoles = computed(() => {
  // 如果有搜索，使用客户端分页
  if (searchQuery.value) {
    const start = (currentPage.value - 1) * pageSize.value;
    const end = start + pageSize.value;
    return displayRoles.value.slice(start, end);
  }
  // 否则直接使用服务端分页的数据
  return displayRoles.value;
});

// 当搜索查询变化时，重置到第一页
watch(searchQuery, () => {
  if (currentPage.value !== 1) {
    currentPage.value = 1;
  }
});

// 刷新数据
const handleRefresh = async () => {
  refreshing.value = true;
  try {
    await refresh();
  } finally {
    refreshing.value = false;
  }
};

// 工具函数
const _formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// 表格列配置 - Nuxt UI v3 格式
const columns: TableColumn<Role>[] = [
  {
    accessorKey: "display_name",
    header: "角色信息",
    cell: ({ row }) => {
      const displayName = row.getValue("display_name") as string;
      return h("div", { class: "flex flex-col" }, [
        h(
          "span",
          { class: "font-medium text-gray-900 dark:text-white" },
          displayName || "-"
        ),
        h(
          "span",
          { class: "text-sm text-gray-500 dark:text-gray-400" },
          row.original.name || "-"
        ),
      ]);
    },
  },
  {
    accessorKey: "description",
    header: "描述",
    cell: ({ row }) => {
      return h(
        "span",
        { class: "text-gray-600 dark:text-gray-300" },
        row.getValue("description") || "-"
      );
    },
  },
  {
    accessorKey: "permissions",
    header: "权限数量",
    cell: ({ row }) => {
      const UBadge = resolveComponent("UBadge");
      const permissions = row.getValue("permissions") as Permission[] || [];
      return h(
        UBadge,
        { color: "primary", variant: "soft" },
        () => `${permissions.length} 个权限`
      );
    },
  },
  {
    accessorKey: "is_system",
    header: "类型",
    cell: ({ row }) => {
      const UBadge = resolveComponent("UBadge");
      const isSystem = row.getValue("is_system") as boolean;
      return h(
        UBadge,
        {
          color: isSystem ? "warning" : "neutral",
          variant: "soft",
        },
        () => (isSystem ? "系统角色" : "自定义角色")
      );
    },
  },
  {
    id: "actions",
    header: "操作",
    cell: ({ row }) => {
      const UButton = resolveComponent("UButton");
      const isCore = isCoreRole(row.original.name);

      return h("div", { class: "flex items-center gap-2" }, [
        h(UButton, {
          color: "neutral",
          variant: "ghost",
          size: "sm",
          icon: "i-heroicons-eye",
          onClick: () => navigateTo(`/rbac/roles/${row.original.id}`),
        }),
        h(UButton, {
          color: "primary",
          variant: "ghost",
          size: "sm",
          icon: "i-heroicons-key",
          onClick: () => navigateTo(`/rbac/roles/${row.original.id}/permissions`),
        }),
        !isCore &&
          h(UButton, {
            color: "neutral",
            variant: "ghost",
            size: "sm",
            icon: "i-heroicons-pencil-square",
            onClick: () => navigateTo(`/rbac/roles/${row.original.id}/edit`),
          }),
        !isCore &&
          h(UButton, {
            color: "error",
            variant: "ghost",
            size: "sm",
            icon: "i-heroicons-trash",
            onClick: () => confirmDeleteRole(row.original),
          }),
      ].filter(Boolean));
    },
  },
];

// 删除角色确认
const confirmDeleteRole = async (role: Role) => {
  try {
    const { $confirm } = useNuxtApp();
    const confirmed = await $confirm(
      `确定要删除角色 "${role.display_name}" 吗？此操作不可撤销。`
    );
    if (!confirmed) return;

    await rbacApi.deleteRole(role.id);

    // 显示成功消息
    const toast = useToast();
    toast.add({
      title: "删除成功",
      description: `角色 "${role.display_name}" 已被删除`,
      color: "success",
    });

    await handleRefresh();
  } catch {
    // 显示错误消息
    const toast = useToast();
    toast.add({
      title: "删除失败",
      description: "无法删除角色，请稍后重试",
      color: "error",
    });
  }
};
</script> 