<script setup lang="ts">
definePageMeta({
  layout: "default",
});

const route = useRoute();
const taskId = computed(() => Number(route.params.id));

// 智能返回路径：根据来源返回到对应页面
const backPath = computed(() => {
  const from = route.query.from as string;
  const projectId = route.query.project_id;

  if (from === "project" && projectId) {
    return `/social-media/projects/${projectId}`;
  }
  return "/social-media/tasks"; // 默认返回任务列表
});

const { getTask, deleteTask, clearTaskData } = useTasks();
const { getTaskPosts, getTaskComments } = usePosts();

// 获取任务详情（使用顶层 await）
const {
  data: task,
  pending: _taskLoading,
  refresh: refreshTask,
} = await getTask(taskId.value);

// 原文分页状态
const postPage = ref(1);
const postPageSize = ref(20);

// 获取任务的原文列表
const postParams = computed(() => ({
  page: postPage.value,
  page_size: postPageSize.value,
}));

const {
  data: postsResponse,
  pending: postsLoading,
  refresh: refreshPosts,
} = await getTaskPosts(taskId.value, postParams);

// 计算属性：原文列表和总数
const posts = computed(() => postsResponse.value?.items || []);
const postsTotal = computed(() => postsResponse.value?.total || 0);

// 评论分页状态
const commentPage = ref(1);
const commentPageSize = ref(20);

// 评论筛选
const selectedPostIdOnPlatform = ref<string | null>(null);
const selectedPostDbId = ref<number | null>(null);

// 获取评论列表（支持按 post_id 筛选）
const commentParams = computed(() => {
  const params: Record<string, unknown> = {
    page: commentPage.value,
    page_size: commentPageSize.value,
  };
  // 如果选中了特定帖子，添加 post_id 参数
  if (selectedPostDbId.value) {
    params.post_id = selectedPostDbId.value;
  }
  return params;
});

const {
  data: commentsResponse,
  pending: commentsLoading,
  refresh: refreshComments,
} = await getTaskComments(taskId.value, commentParams);

// 计算属性：评论列表和总数
const comments = computed(() => commentsResponse.value?.items || []);
const commentsTotal = computed(() => commentsResponse.value?.total || 0);

// 创建 post_id 到 post_id_on_platform 的映射
const postIdMap = computed(() => {
  if (!posts.value) return new Map<number, string>();
  return new Map(
    posts.value.map((post) => [post.id, post.post_id_on_platform])
  );
});

const refreshing = ref(false);
const handleRefresh = async () => {
  refreshing.value = true;
  await Promise.all([refreshTask(), refreshPosts(), refreshComments()]);
  refreshing.value = false;
};

const handleDelete = async () => {
  if (!task.value) return;

  const { $confirm } = useNuxtApp();
  const confirmed = await $confirm({
    title: "删除任务",
    message: `确定要删除任务 "${task.value.name}" 吗？此操作不可恢复，将同时删除所有相关的原文和评论数据。`,
    confirmText: "删除",
    cancelText: "取消",
    type: "error",
  });

  if (!confirmed) return;

  try {
    await deleteTask(task.value.id);
    await navigateTo("/social-media/tasks");
  } catch (error) {
    console.error("删除任务失败:", error);
  }
};

const handleClearData = async () => {
  if (!task.value) return;

  const { $confirm } = useNuxtApp();
  const confirmed = await $confirm({
    title: "清空任务数据",
    message: `确定要清空任务 "${task.value.name}" 的所有数据吗？\n\n此操作将删除所有原文和评论数据，任务状态将重置为"待处理"，您可以重新上传或采集数据。`,
    confirmText: "清空数据",
    cancelText: "取消",
    type: "warning",
  });

  if (!confirmed) return;

  try {
    await clearTaskData(task.value.id);
    await handleRefresh();
  } catch (error) {
    console.error("清空任务数据失败:", error);
  }
};

// 查看评论
const handleViewComments = (post: SocialPost) => {
  selectedPostIdOnPlatform.value = post.post_id_on_platform;
  selectedPostDbId.value = post.id;
  // 清除评论筛选时重置到第一页
  commentPage.value = 1;
};

// 清除筛选
const handleClearFilter = () => {
  selectedPostIdOnPlatform.value = null;
  selectedPostDbId.value = null;
  commentPage.value = 1;
};

// 格式化函数
const formatDateTime = (dateStr: string | null) => {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString("zh-CN");
};

const formatNumber = (num: number) => {
  if (num >= 10000) {
    return `${(num / 10000).toFixed(1)}万`;
  }
  return num.toString();
};

// 任务状态颜色（使用 Nuxt UI 标准颜色）
const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'neutral',
    running: 'info',
    completed: 'success',
    failed: 'error',
  };
  return colors[status] || 'neutral';
};

const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    pending: "待处理",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
  };
  return texts[status] || status;
};

// 原文表格列定义 - 使用 computed 避免 SSR 水合问题
const postsColumns = computed(() => {
  if (!import.meta.client) return []

  return [
    {
      accessorKey: "post_id_on_platform",
      header: () =>
        h("span", { style: { whiteSpace: "nowrap" } as const }, "平台ID"),
      cell: ({ row }: { row: { original: SocialPost } }) =>
        h(
          "span",
          { class: "text-xs font-mono" },
          row.original.post_id_on_platform || "-"
        ),
    },
  {
    accessorKey: "author_name",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "作者"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h("span", { class: "text-sm truncate" }, row.original.author_name || "-"),
  },
  {
    accessorKey: "title",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "标题/内容"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h("div", { class: "max-w-md" }, [
        row.original.title
          ? h(
              "p",
              { class: "font-medium text-sm truncate" },
              row.original.title
            )
          : null,
        h(
          "p",
          { class: "text-xs text-gray-600 dark:text-gray-400 truncate mt-1" },
          row.original.content?.substring(0, 60) || "无内容"
        ),
      ]),
  },
  {
    accessorKey: "likes_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "点赞"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-sm text-right block" },
        formatNumber(row.original.likes_count)
      ),
  },
  {
    accessorKey: "comments_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "评论"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-sm text-right block" },
        formatNumber(row.original.comments_count)
      ),
  },
  {
    accessorKey: "shares_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "转发"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-sm text-right block" },
        formatNumber(row.original.shares_count)
      ),
  },
  {
    accessorKey: "views_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "浏览"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-sm text-right block" },
        formatNumber(row.original.views_count)
      ),
  },
  {
    accessorKey: "collected_at",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "采集时间"),
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-xs" },
        formatDateTime(row.original.collected_at)
      ),
  },
  {
    accessorKey: "actions",
    header: () =>
      h(
        "span",
        {
          style: { whiteSpace: "nowrap" } as const,
          class: "block w-full",
        },
        "操作"
      ),
    cell: ({ row }: { row: { original: SocialPost } }) => {
      const UButton = resolveComponent("UButton");
      if (row.original.comments_count > 0) {
        return h("div", { class: "flex justify-end" }, [
          h(
            UButton,
            {
              size: "xs",
              variant: "ghost",
              onClick: () => handleViewComments(row.original),
            },
            () => "查看评论"
          ),
        ]);
      }
      return h("span", { class: "text-xs text-gray-400 block" }, "无评论");
    },
  },
  ]
})

// 评论表格列定义 - 使用 computed 避免 SSR 水合问题
const commentsColumns = computed(() => {
  if (!import.meta.client) return []

  return [
  {
    accessorKey: "post_id",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "关联主贴ID"),
    cell: ({ row }: { row: { original: SocialComment } }) => {
      // 通过 post_id 从映射中获取 post_id_on_platform
      const postIdOnPlatform =
        postIdMap.value.get(row.original.post_id) ||
        (row.original.raw_data?.post_id_on_platform as string) ||
        "-";
      return h("span", { class: "text-xs font-mono" }, postIdOnPlatform);
    },
  },
  {
    accessorKey: "author_name",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "作者"),
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h("span", { class: "text-sm truncate" }, row.original.author_name || "-"),
  },
  {
    accessorKey: "content",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "评论内容"),
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h(
        "p",
        { class: "text-sm truncate max-w-md" },
        row.original.content || "无内容"
      ),
  },
  {
    accessorKey: "likes_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "点赞"),
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h(
        "span",
        { class: "text-sm text-right block" },
        formatNumber(row.original.likes_count)
      ),
  },
  {
    accessorKey: "collected_at",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "评论时间"),
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h(
        "span",
        { class: "text-xs" },
        formatDateTime(row.original.collected_at)
      ),
  },
  ]
})
// 分析组件引用
const AnalysisPanel = defineAsyncComponent(() =>
  import('./components/AnalysisPanel.vue')
)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="navigateTo(backPath)"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ task?.name || "加载中..." }}
          </h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">任务详情</p>
        </div>
      </div>

      <ClientOnly>
        <div v-if="task" class="flex gap-3">
          <UButton
            v-if="task.status === 'pending' && task.data_source === 'local_upload'"
            icon="i-heroicons-arrow-up-tray"
            @click="navigateTo(`/social-media/tasks/${taskId}/upload`)"
          >
            上传数据
          </UButton>
          <UButton
            variant="outline"
            icon="i-heroicons-arrow-path"
            :loading="refreshing"
            @click="handleRefresh"
          >
            刷新
          </UButton>
          <UButton
            v-if="task.posts_count > 0 || task.comments_count > 0"
            variant="outline"
            icon="i-heroicons-x-circle"
            color="warning"
            @click="handleClearData"
          >
            清空数据
          </UButton>
          <UButton
            variant="outline"
            icon="i-heroicons-trash"
            color="error"
            @click="handleDelete"
          >
            删除
          </UButton>
        </div>
      </ClientOnly>
    </div>

    <!-- 任务信息卡片 -->
    <UCard v-if="task">
            <template #header>
              <h2 class="text-lg font-semibold">任务信息</h2>
            </template>

            <div class="space-y-4">
              <!-- 第一行：核心标识（4列） -->
              <div class="grid grid-cols-4 gap-4">
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    任务名称
                  </h3>
                  <p
                    class="mt-1 text-sm text-gray-900 dark:text-white truncate"
                    :title="task.name"
                  >
                    {{ task.name }}
                  </p>
                </div>

                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    所属项目
                  </h3>
                  <p
                    class="mt-1 text-sm text-gray-900 dark:text-white truncate"
                    :title="task.project_name || '-'"
                  >
                    {{ task.project_name || "-" }}
                  </p>
                </div>

                <div v-if="task.description" class="col-span-2">
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    任务描述
                  </h3>
                  <p
                    class="mt-1 text-sm text-gray-900 dark:text-white line-clamp-3"
                    :title="task.description"
                  >
                    {{ task.description }}
                  </p>
                </div>
              </div>

              <!-- 第二行：描述和关键词（条件显示，整合到网格） -->
              <div class="grid grid-cols-4 gap-4">
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    平台
                  </h3>
                  <div class="mt-1">
                    <UBadge variant="subtle" size="sm">
                      {{ task.platform_name || "-" }}
                    </UBadge>
                  </div>
                </div>

                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    任务类型
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ task.task_type }}
                  </p>
                </div>

                <!-- 搜索关键词（仅 search 类型） -->
                <div
                  v-if="task.task_type === 'search' && task.keywords"
                  class="col-span-2"
                >
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    搜索关键词
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ task.keywords }}
                  </p>
                </div>

                <!-- 任务参数（detail/creator 类型） -->
                <div
                  v-else-if="(task.task_type === 'detail' || task.task_type === 'creator') && task.task_params && Object.keys(task.task_params).length > 0"
                  class="col-span-2"
                >
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                    任务参数
                  </h3>
                  <div class="space-y-1.5">
                    <div
                      v-for="(value, key) in task.task_params"
                      :key="key"
                      class="bg-gray-50 dark:bg-gray-800 rounded-md px-2 py-1.5"
                    >
                      <div class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                        {{ key }}
                      </div>
                      <div v-if="Array.isArray(value)" class="space-y-0.5">
                        <div
                          v-for="(item, index) in value"
                          :key="index"
                          class="text-xs font-mono text-gray-900 dark:text-white break-all"
                        >
                          {{ item }}
                        </div>
                      </div>
                      <div
                        v-else
                        class="text-xs font-mono text-gray-900 dark:text-white break-all"
                      >
                        {{ value }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 分隔线 -->
              <div class="border-t border-gray-200 dark:border-gray-700" />

              <!-- 第三行：配置和归属（4列） -->
              <div class="grid grid-cols-4 gap-4">
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    数据源
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{
                      task.data_source === "local_upload" ? "本地上传" : "远程爬虫"
                    }}
                  </p>
                </div>

                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    状态
                  </h3>
                  <div class="mt-1">
                    <UBadge
                      :color="getStatusColor(task.status)"
                      variant="solid"
                      size="sm"
                    >
                      {{ getStatusText(task.status) }}
                    </UBadge>
                  </div>
                </div>

                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    原文数量
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ task.posts_count }}
                  </p>
                </div>
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    评论数量
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ task.comments_count }}
                  </p>
                </div>
              </div>

              <!-- 第四行：人员和时间（4列） -->
              <div class="grid grid-cols-4 gap-4">
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    创建者
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ task.creator_username || "-" }}
                  </p>
                </div>
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    创建时间
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ formatDateTime(task.created_at) }}
                  </p>
                </div>
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    开始时间
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ formatDateTime(task.started_at) }}
                  </p>
                </div>
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    完成时间
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ formatDateTime(task.completed_at) }}
                  </p>
                </div>
              </div>

              <!-- 错误信息（失败时显示） -->
              <UAlert
                v-if="task.status === 'failed' && task.error_message"
                color="error"
                variant="soft"
                title="任务执行失败"
                :description="task.error_message"
                icon="i-heroicons-exclamation-triangle"
              />
            </div>
          </UCard>

          <!-- 双栏数据展示 - 响应式布局 -->
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- 左侧：原文列表 -->
            <UCard>
              <template #header>
                <h2 class="text-lg font-semibold">原文数据</h2>
              </template>

              <ClientOnly>
                <template #fallback>
                  <div class="text-center py-8">
                    <p class="text-gray-600 dark:text-gray-400">加载中...</p>
                  </div>
                </template>

                <UTable
                  v-if="!postsLoading && posts && posts.length > 0"
                  sticky
                  :data="posts"
                  :columns="postsColumns"
                  class="max-h-[600px]"
                />

                <div v-else-if="postsLoading" class="text-center py-8">
                  <p class="text-gray-600 dark:text-gray-400">加载中...</p>
                </div>

                <div v-else class="text-center py-8">
                  <p class="text-gray-600 dark:text-gray-400">暂无数据</p>
                </div>
              </ClientOnly>

              <template #footer>
                <ClientOnly>
                  <div class="flex justify-between items-center">
                    <div class="text-sm text-gray-500 dark:text-gray-400">
                      显示 {{ (postPage - 1) * postPageSize + 1 }} 到
                      {{ Math.min(postPage * postPageSize, postsTotal) }}
                      共 {{ postsTotal }} 条记录
                    </div>
                    <UPagination
                      v-model:page="postPage"
                      :total="postsTotal"
                      :items-per-page="postPageSize"
                      :sibling-count="2"
                    />
                  </div>
                </ClientOnly>
              </template>
            </UCard>

            <!-- 右侧：评论列表 -->
            <UCard>
              <template #header>
                <div class="flex items-center justify-between gap-3">
                  <h2 class="text-lg font-semibold">评论数据</h2>
                  <div
                    v-if="selectedPostIdOnPlatform"
                    class="flex items-center gap-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-1.5"
                  >
                    <span
                      class="text-sm text-blue-700 dark:text-blue-300 whitespace-nowrap"
                    >
                      正在查看:
                      <span class="font-mono font-medium">{{
                        selectedPostIdOnPlatform
                      }}</span>
                    </span>
                    <UButton
                      size="xs"
                      variant="ghost"
                      icon="i-heroicons-x-mark"
                      @click="handleClearFilter"
                    >
                      查看全部
                    </UButton>
                  </div>
                </div>
              </template>

              <ClientOnly>
                <template #fallback>
                  <div class="text-center py-8">
                    <p class="text-gray-600 dark:text-gray-400">加载中...</p>
                  </div>
                </template>

                <UTable
                  v-if="!commentsLoading && comments && comments.length > 0"
                  sticky
                  :data="comments"
                  :columns="commentsColumns"
                  class="max-h-[600px]"
                />

                <div v-else-if="commentsLoading" class="text-center py-8">
                  <p class="text-gray-600 dark:text-gray-400">加载中...</p>
                </div>

                <div v-else class="text-center py-8">
                  <p class="text-gray-600 dark:text-gray-400">
                    {{ selectedPostIdOnPlatform ? "该帖子暂无评论" : "暂无评论数据" }}
                  </p>
                </div>
              </ClientOnly>

              <template #footer>
                <ClientOnly>
                  <div class="flex justify-between items-center">
                    <div class="text-sm text-gray-500 dark:text-gray-400">
                      显示 {{ (commentPage - 1) * commentPageSize + 1 }} 到
                      {{ Math.min(commentPage * commentPageSize, commentsTotal) }}
                      共 {{ commentsTotal }} 条{{
                        selectedPostIdOnPlatform ? "评论" : "记录"
                      }}
                    </div>
                    <UPagination
                      v-model:page="commentPage"
                      :total="commentsTotal"
                      :items-per-page="commentPageSize"
                      :sibling-count="2"
                    />
                  </div>
                </ClientOnly>
              </template>
            </UCard>
          </div>

          <!-- AI 分析卡片 -->
          <div class="mt-6">
            <ClientOnly>
              <AnalysisPanel :task-id="taskId" />
            </ClientOnly>
          </div>
  </div>
</template>
