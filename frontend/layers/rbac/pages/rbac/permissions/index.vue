<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          权限查看
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          查看系统中定义的所有权限，权限通过代码管理
        </p>
      </div>

      <div class="flex items-center gap-3">
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

    <!-- 代码驱动权限管理说明 -->
    <UAlert
      color="info"
      variant="soft"
      icon="i-heroicons-information-circle"
      title="权限管理说明"
    >
      <template #description>
        <div class="space-y-2">
          <p><strong>权限定义</strong>：所有权限通过代码定义（<code>backend/src/rbac/init_data.py</code>），确保版本控制和环境一致性。</p>
          <p><strong>权限分配</strong>：使用角色管理页面为角色分配权限，使用用户管理页面为用户分配角色。</p>
          <div class="flex gap-2 mt-3">
            <UButton size="sm" @click="navigateTo('/rbac/roles')">管理角色权限</UButton>
            <UButton size="sm" variant="outline" @click="navigateTo('/users')">管理用户角色</UButton>
          </div>
        </div>
      </template>
    </UAlert>

    <!-- 权限列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">权限列表</h2>
          <UInput
            v-model="searchQuery"
            placeholder="搜索权限名称、资源或操作..."
            icon="i-heroicons-magnifying-glass"
            class="w-80"
          />
        </div>
      </template>

      <!-- 权限表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载权限列表中...</p>
          </div>
        </template>

        <UTable
          :data="paginatedPermissions"
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
import type { PermissionWithMeta as Permission } from "../../../types";
import type { TableColumn } from "@nuxt/ui";

// 页面元数据
definePageMeta({
  title: "权限管理",
  description: "管理系统中的所有权限",
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

// 获取权限数据 - 使用响应式参数支持后端分页
const {
  data: permissionsData,
  pending,
  refresh,
} = rbacApi.getPermissions({
  page: currentPage,
  page_size: pageSize,
});

// 计算属性
const loading = computed(() => pending.value || refreshing.value);

// 计算属性 - 从API数据中获取显示内容
const displayPermissions = computed(() => {
  const items = permissionsData.value?.items || [];

  // 如果有搜索查询，过滤数据
  if (!searchQuery.value) {
    return items;
  }

  const query = searchQuery.value.toLowerCase();
  return items.filter(
    (permission) =>
      permission.display_name.toLowerCase().includes(query) ||
      permission.target.toLowerCase().includes(query) ||
      permission.action.toLowerCase().includes(query) ||
      `${permission.target}:${permission.action}`.toLowerCase().includes(query) ||
      (permission.description &&
        permission.description.toLowerCase().includes(query))
  );
});

// 分页相关计算属性
const total = computed(() => permissionsData.value?.total || 0);

// 分页数据
const paginatedPermissions = computed(() => {
  // 如果有搜索，使用客户端分页
  if (searchQuery.value) {
    const start = (currentPage.value - 1) * pageSize.value;
    const end = start + pageSize.value;
    return displayPermissions.value.slice(start, end);
  }
  // 否则直接使用服务端分页的数据
  return displayPermissions.value;
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

// 权限类型分类函数 - 基于业务逻辑重新分类
const getPermissionCategory = (permission: Permission): { label: string; color: "primary" | "secondary" | "success" | "warning" | "error" | "info" | "neutral" } => {
  // 页面访问权限
  if (permission.action === 'access') {
    return { label: '页面访问', color: 'info' }
  }
  
  // RBAC核心权限
  if (['user', 'role', 'permission'].includes(permission.target)) {
    return { label: 'RBAC核心', color: 'warning' }
  }
  
  // 业务功能权限
  return { label: '业务功能', color: 'success' }
}

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
const columns: TableColumn<Permission>[] = [
  {
    accessorKey: "display_name",
    header: "权限信息",
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
          `${row.original.target}:${row.original.action}`
        ),
      ]);
    },
  },
  {
    accessorKey: "target",
    header: "目标:操作",
    cell: ({ row }) => {
      const UBadge = resolveComponent("UBadge");
      const target = row.getValue("target") as string;
      const action = row.original.action as string;
      return h("div", { class: "flex items-center space-x-2" }, [
        h(
          UBadge,
          { color: "primary", variant: "soft" },
          () => target || "未知"
        ),
        h("span", { class: "text-gray-400" }, ":"),
        h(
          UBadge,
          { color: "success", variant: "soft" },
          () => action || "未知"
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
    accessorKey: "resource",
    header: "权限类型",
    cell: ({ row }) => {
      const UBadge = resolveComponent("UBadge");
      const permission = row.original;
      const { label, color } = getPermissionCategory(permission);
      
      return h(
        UBadge,
        {
          color,
          variant: "soft",
        },
        () => label
      );
    },
  },
  {
    id: "view",
    header: "查看详情",
    cell: ({ row }) => {
      const UButton = resolveComponent("UButton");

      return h(UButton, {
        color: "neutral",
        variant: "ghost",
        size: "sm",
        icon: "i-heroicons-eye",
        onClick: () => navigateTo(`/rbac/permissions/${row.original.id}`),
      });
    },
  },
];
</script>
