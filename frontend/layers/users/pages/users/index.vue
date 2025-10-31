<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          用户管理
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理系统中的所有用户
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton icon="i-heroicons-plus" @click="navigateTo('/users/create')">
          新增用户
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

    <!-- 用户列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">用户列表</h2>
          <UInput
            v-model="searchQuery"
            placeholder="搜索用户名、邮箱或角色..."
            icon="i-heroicons-magnifying-glass"
            class="w-80"
          />
        </div>
      </template>

      <!-- 用户表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载用户列表中...</p>
          </div>
        </template>

        <UTable
          :data="paginatedUsers"
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
              <div class="h-4 bg-gray-200 rounded w-32 animate-pulse" />
              <div class="h-8 bg-gray-200 rounded w-64 animate-pulse" />
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
import type { User } from "../../types";
import type { TableColumn } from "@nuxt/ui";
import { getRoleDisplayName } from "../../../rbac/utils/permissions";  // 明确的跨模块依赖

// 页面元数据
definePageMeta({
  title: "用户管理",
  description: "管理系统中的所有用户",
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
      query: { ...route.query, page: value.toString() },
    });
  },
});

const pageSize = ref(DEFAULT_PAGE_SIZE);

// API 调用 - 使用改造后的 usersApi 支持响应式参数
const usersApi = useUsersApi();

// 使用 usersApi.getUsers 的响应式参数支持
const {
  data: userData,
  pending,
  refresh,
} = usersApi.getUsers({
  page: currentPage,
  page_size: pageSize,
});

// 计算属性
const loading = computed(() => pending.value || refreshing.value);

// 计算属性 - 从API数据中获取显示内容
const displayUsers = computed(() => {
  const items = userData.value?.items || [];

  // 如果有搜索查询，过滤数据
  if (!searchQuery.value) {
    return items;
  }

  const query = searchQuery.value.toLowerCase();
  return items.filter(
    (user) =>
      user.username.toLowerCase().includes(query) ||
      user.email.toLowerCase().includes(query)
  );
});

// 分页相关计算属性
const total = computed(() => userData.value?.total || 0);

// 分页数据
const paginatedUsers = computed(() => {
  // 如果有搜索，使用客户端分页
  if (searchQuery.value) {
    const start = (currentPage.value - 1) * pageSize.value;
    const end = start + pageSize.value;
    return displayUsers.value.slice(start, end);
  }
  // 否则直接使用服务端分页的数据
  return displayUsers.value;
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
const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// 表格列配置 - Nuxt UI v3 格式
const columns: TableColumn<User>[] = [
  {
    accessorKey: "username",
    header: "用户信息",
    cell: ({ row }) => {
      const UAvatar = resolveComponent("UAvatar");
      const username = row.getValue("username") as string;
      return h("div", { class: "flex items-center space-x-3" }, [
        h(UAvatar, {
          size: "sm",
          text: username.charAt(0).toUpperCase(),
        }),
        h("div", { class: "flex flex-col" }, [
          h(
            "span",
            { class: "font-medium text-gray-900 dark:text-white" },
            username
          ),
          h(
            "span",
            { class: "text-sm text-gray-500 dark:text-gray-400" },
            row.original.email || "未知"
          ),
        ]),
      ]);
    },
  },
  {
    accessorKey: "roles",
    header: "角色",
    cell: ({ row }) => {
      const UBadge = resolveComponent("UBadge");
      const roles = row.getValue("roles") as string[];

      if (!roles || roles.length === 0) {
        return h("span", { class: "text-gray-400" }, "无角色");
      }

      return h(
        "div",
        { class: "flex flex-wrap gap-1" },
        roles.map((roleName) =>
          h(
            UBadge,
            {
              key: roleName,
              color: "primary",
              variant: "soft",
              size: "sm",
            },
            () => getRoleDisplayName(roleName)
          )
        )
      );
    },
  },
  {
    accessorKey: "created_at",
    header: "创建时间",
    cell: ({ row }) => {
      return h(
        "span",
        { class: "text-sm text-gray-500 dark:text-gray-400" },
        formatDate(row.getValue("created_at"))
      );
    },
  },
  {
    id: "actions",
    header: "操作",
    cell: ({ row }) => {
      const UButton = resolveComponent("UButton");

      return h("div", { class: "flex items-center gap-2" }, [
        h(UButton, {
          color: "neutral",
          variant: "ghost",
          size: "sm",
          icon: "i-heroicons-eye",
          onClick: () => navigateTo(`/users/${row.original.id}`),
        }),
        h(UButton, {
          color: "primary",
          variant: "ghost",
          size: "sm",
          icon: "i-heroicons-user-group",
          onClick: () => navigateTo(`/users/${row.original.id}/roles`),
        }),
        h(UButton, {
          color: "neutral",
          variant: "ghost",
          size: "sm",
          icon: "i-heroicons-pencil-square",
          onClick: () => navigateTo(`/users/${row.original.id}/edit`),
        }),
        h(UButton, {
          color: "error",
          variant: "ghost",
          size: "sm",
          icon: "i-heroicons-trash",
          onClick: () => confirmDeleteUser(row.original),
        }),
      ]);
    },
  },
];

// 删除用户确认
const confirmDeleteUser = async (user: User) => {
  try {
    const { $confirm } = useNuxtApp();
    const confirmed = await $confirm(`确定要删除用户 "${user.username}" 吗？`);
    if (!confirmed) return;

    await usersApi.deleteUser(user.id);
    await handleRefresh();
  } catch {
    // 错误已由 useApi 自动处理
  }
};
</script>
