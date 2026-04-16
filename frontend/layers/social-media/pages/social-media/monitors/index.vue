<script setup lang="ts">
import { h, ref, computed, type Component } from "vue";
import type { TableColumn } from "@nuxt/ui";
import { UButton } from "#components";
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: "default",
});

const { getMonitors, deleteMonitor } = useMonitors();
const { currentUserId, hasPermission } = usePermissions()

// 分页和搜索
const currentPage = ref(1);
const pageSize = ref(10);
const searchQuery = ref("");
const refreshing = ref(false);

// 获取项目列表
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
}));

const { data: monitorsData, pending: loading, refresh } = getMonitors(params);

const monitors = computed(() => monitorsData.value?.items || []);
const total = computed(() => monitorsData.value?.total || 0);

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true;
  await refresh();
  refreshing.value = false;
};

// 删除项目
const handleDelete = async (monitor: SocialMonitor) => {
  const { $confirm } = useNuxtApp();
  const confirmed = await $confirm({
    title: "删除社媒监测",
    message: `确定要删除社媒监测 "${monitor.name}" 吗？此操作不可恢复，所有相关任务和数据也将被删除。`,
    confirmText: "删除",
    cancelText: "取消",
    type: "error",
  });

  if (!confirmed) return;

  try {
    await deleteMonitor(monitor.id);
    await handleRefresh();
  } catch (error) {
    console.error("删除项目失败:", error);
  }
};

// 格式化日期
const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// 表格列定义 - 使用 computed 以避免 SSR 水合问题
const columns = computed<TableColumn<SocialMonitor>[]>(() => {
  const Button = UButton as Component;

  return [
    {
      accessorKey: "id",
      header: "ID",
      meta: { class: { th: "w-14", td: "w-14" } },
      cell: ({ row }) => h("span", { class: "text-xs text-gray-500 font-mono" }, row.original.id),
    },
    {
      accessorKey: "name",
      header: "项目名称",
      meta: { class: { th: "w-[200px]", td: "w-[200px] whitespace-normal" } },
      cell: ({ row }) => h("div", { class: "font-medium leading-snug line-clamp-2", title: row.original.name }, row.original.name),
    },
    {
      accessorKey: "description",
      header: "描述",
      meta: { class: { th: "w-[240px]", td: "w-[240px] whitespace-normal" } },
      cell: ({ row }) =>
        h(
          "div",
          { class: "text-sm text-gray-600 dark:text-gray-400 leading-snug line-clamp-2", title: row.original.description || "" },
          row.original.description || "-"
        ),
    },
    {
      accessorKey: "owner_username",
      header: "创建者",
      meta: { class: { th: "w-[100px]", td: "w-[100px]" } },
      cell: ({ row }) => h("span", { class: "truncate" }, row.original.owner_username || "-"),
    },
    {
      accessorKey: "created_at",
      header: "创建时间",
      meta: { class: { th: "w-[120px]", td: "w-[120px]" } },
      cell: ({ row }) =>
        h(
          "span",
          { class: "text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap" },
          formatDate(row.original.created_at)
        ),
    },
    {
      accessorKey: "actions",
      header: "操作",
      meta: { class: { th: "w-[120px]", td: "w-[120px]" } },
      cell: ({ row }) => {
        return h("div", { class: "flex items-center gap-2" }, [
          h(
            Button,
            {
              size: "xs",
              variant: "ghost",
              icon: "i-heroicons-eye",
              to: `/social-media/monitors/${row.original.id}`,
            },
            () => "查看"
          ),
          (hasPermission(PERMISSIONS.SOCIAL_MONITOR_DELETE) || row.original.user_id === currentUserId.value)
            ? h(Button, {
                size: "xs",
                variant: "ghost",
                icon: "i-heroicons-trash",
                color: "error",
                onClick: () => handleDelete(row.original),
              }, () => "删除")
            : null,
        ]);
      },
    },
  ];
});
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          社媒监测
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理社交媒体监测项目
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          to="/social-media/monitors/create"
        >
          新建项目
        </UButton>
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </div>
    </div>

    <!-- 项目列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">项目列表</h2>
          <UInput
            v-model="searchQuery"
            placeholder="搜索项目名称..."
            icon="i-heroicons-magnifying-glass"
            class="w-80"
          />
        </div>
      </template>

      <!-- 项目表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载项目列表中...</p>
          </div>
        </template>

        <UTable
          :data="monitors"
          :columns="columns"
          :loading="loading"
          class="w-full"
          :ui="{ base: 'w-full table-fixed' }"
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
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>
