<script setup lang="ts">
import { computed, ref, h, type Component, defineAsyncComponent } from 'vue'
import { UButton } from '#components'
import ExpandableText from '../../../../analysis/components/shared/ExpandableText.vue'

definePageMeta({
  layout: "default",
});

const route = useRoute();
const taskId = computed(() => Number(route.params.id));

// 智能返回路径：根据来源返回到对应页面
const backPath = computed(() => {
  const from = route.query.from as string;
  const monitorId = route.query.monitor_id;

  if (from === "monitor" && monitorId) {
    return `/social-media/monitors/${monitorId}`;
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

// 原文筛选（用于从分析面板跳转查看）
const selectedPostDbIdForPosts = ref<number | null>(null);

// 获取任务的原文列表
const postParams = computed(() => {
  const params: Record<string, unknown> = {
    page: postPage.value,
    page_size: postPageSize.value,
  };
  // 如果选中了特定帖子，添加 post_id 参数
  if (selectedPostDbIdForPosts.value) {
    params.post_id = selectedPostDbIdForPosts.value;
  }
  return params;
});

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

// 创建 post_id 到 post_id_on_platform 的映射（用于评论表格显示主贴平台ID）
const postIdMap = computed(() => {
  if (!posts.value) return new Map<number, string>();
  return new Map(
    posts.value.map((post) => [post.id, post.post_id_on_platform])
  );
});

const refreshing = ref(false);
const analysisPanelRef = ref<{ refresh: () => Promise<void> } | null>(null);

const handleRefresh = async () => {
  refreshing.value = true;
  await Promise.all([
    refreshTask(),
    refreshPosts(),
    refreshComments(),
    analysisPanelRef.value?.refresh?.(),
  ]);
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
    message: `确定要清空任务 "${task.value.name}" 的所有数据吗？\n\n此操作将删除所有原文、评论、分析结果和分析报告，任务状态将重置为"待处理"，您可以重新上传或采集数据。`,
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

// 清除评论筛选
const handleClearFilter = () => {
  selectedPostIdOnPlatform.value = null;
  selectedPostDbId.value = null;
  commentPage.value = 1;
};

// 清除原文筛选
const handleClearPostFilter = () => {
  selectedPostDbIdForPosts.value = null;
  postPage.value = 1;
};

// 处理从分析面板跳转查看原文/评论（同时筛选原文和评论列表）
const handleFocusPost = (postId: number) => {
  // 设置原文筛选
  selectedPostDbIdForPosts.value = postId;
  postPage.value = 1;

  // 同时设置评论筛选（复用现有的评论筛选逻辑）
  selectedPostDbId.value = postId;
  // 评论的平台ID显示需要从 postIdMap 获取，但此时可能还没加载
  // 先设置为 null，UI 会显示 postId
  selectedPostIdOnPlatform.value = null;
  commentPage.value = 1;
};

// 格式化函数
const formatDateTime = (dateStr: string | null): { date: string; time: string } | null => {
  if (!dateStr) return null
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return null
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return {
    date: `${year}-${month}-${day}`,
    time: `${hour}:${min}`,
  }
}

// 格式化日期时间（用于任务信息显示，完整格式）
const formatFullDateTime = (dateStr: string | null) => {
  if (!dateStr) return "-"
  return new Date(dateStr).toLocaleString("zh-CN")
}

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

// 各平台数据支持情况
const platformsWithShares = ['dy', 'wb', 'xhs']      // 有转发数据：抖音、微博、小红书
const platformsWithCollected = ['dy', 'xhs']         // 有收藏数据：抖音、小红书
const platformsWithViews = ['bili', 'ks']            // 有浏览量数据：B站、快手
const platformsWithDanmaku = ['bili']                // 有弹幕数据：B站

// 原文表格列定义 - 使用 computed 避免 SSR 水合问题
const postsColumns = computed(() => {
  const Button = UButton as Component

  // 根据平台决定是否显示各列
  const platformCode = task.value?.platform_code || ''
  const showSharesColumn = platformsWithShares.includes(platformCode)
  const showCollectedColumn = platformsWithCollected.includes(platformCode)
  const showViewsColumn = platformsWithViews.includes(platformCode)
  const showDanmakuColumn = platformsWithDanmaku.includes(platformCode)

  return [
    {
      accessorKey: "id",
      header: () =>
        h("span", { style: { whiteSpace: "nowrap" } as const }, "ID"),
      size: 40,
      cell: ({ row }: { row: { original: SocialPost } }) =>
        h(
          "span",
          { class: "text-xs text-gray-500 font-mono" },
          row.original.id
        ),
    },
    {
      accessorKey: "post_id_on_platform",
      header: () =>
        h("span", { style: { whiteSpace: "nowrap" } as const }, "平台ID"),
      size: 80,
      cell: ({ row }: { row: { original: SocialPost } }) =>
        h(
          "span",
          { class: "text-xs font-mono truncate block max-w-[70px]", title: row.original.post_id_on_platform || "-" },
          row.original.post_id_on_platform || "-"
        ),
    },
  {
    accessorKey: "author_name",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "作者"),
    size: 70,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h("span", { class: "text-sm truncate block max-w-[60px]" }, row.original.author_name || "-"),
  },
  {
    accessorKey: "title",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "标题/内容"),
    size: 150,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(ExpandableText, {
        title: row.original.title || "",
        content: row.original.content || "",
        maxLength: 30,
      }),
  },
  {
    accessorKey: "likes_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "点赞"),
    size: 50,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-xs text-right block" },
        formatNumber(row.original.likes_count)
      ),
  },
  {
    accessorKey: "comments_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "评论"),
    size: 70,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h("div", { class: "text-xs text-right" }, [
        h("span", {}, formatNumber(row.original.comments_count)),
        h("span", { class: "text-gray-400 ml-1" },
          `(${formatNumber(row.original.crawled_comments_count)})`
        ),
      ]),
  },
  // 转发列 - 仅在支持的平台显示
  ...(showSharesColumn ? [{
    accessorKey: "shares_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "转发"),
    size: 50,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-xs text-right block" },
        formatNumber(row.original.shares_count)
      ),
  }] : []),
  // 收藏列 - 仅在支持的平台显示
  ...(showCollectedColumn ? [{
    accessorKey: "collected_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "收藏"),
    size: 50,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-xs text-right block" },
        formatNumber(row.original.collected_count)
      ),
  }] : []),
  // 浏览列 - 仅在支持的平台显示
  ...(showViewsColumn ? [{
    accessorKey: "views_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "浏览"),
    size: 50,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-xs text-right block" },
        formatNumber(row.original.views_count)
      ),
  }] : []),
  // 弹幕列 - 仅B站显示
  ...(showDanmakuColumn ? [{
    accessorKey: "danmaku_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "弹幕"),
    size: 50,
    cell: ({ row }: { row: { original: SocialPost } }) =>
      h(
        "span",
        { class: "text-xs text-right block" },
        formatNumber(row.original.danmaku_count)
      ),
  }] : []),
  {
    accessorKey: "published_at",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "发布时间"),
    size: 90,
    cell: ({ row }: { row: { original: SocialPost } }) => {
      const dt = formatDateTime(row.original.published_at)
      if (!dt) return h("span", { class: "text-xs text-gray-400" }, "-")
      return h("div", { class: "text-xs text-gray-500 leading-tight" }, [
        h("div", {}, dt.date),
        h("div", {}, dt.time),
      ])
    },
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
    size: 80,
    cell: ({ row }: { row: { original: SocialPost } }) => {
      const buttons = [];

      // 查看原文按钮
      if (row.original.url) {
        buttons.push(
          h(
            Button,
            {
              size: "xs",
              variant: "ghost",
              icon: "i-heroicons-arrow-top-right-on-square",
              onClick: () => window.open(row.original.url!, "_blank"),
            },
            () => "原文"
          )
        );
      }

      // 查看评论按钮
      if (row.original.crawled_comments_count > 0) {
        buttons.push(
          h(
            Button,
            {
              size: "xs",
              variant: "ghost",
              onClick: () => handleViewComments(row.original),
            },
            () => "评论"
          )
        );
      }

      if (buttons.length > 0) {
        return h("div", { class: "flex justify-end gap-1" }, buttons);
      }
      return h("span", { class: "text-xs text-gray-400 block text-right" }, "-");
    },
  },
  ]
})

// 评论表格列定义 - 使用 computed 避免 SSR 水合问题
const commentsColumns = computed(() => {
  return [
  {
    accessorKey: "post_id",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "主贴ID"),
    size: 50,
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h("span", { class: "text-xs text-gray-500 font-mono" }, row.original.post_id),
  },
  {
    accessorKey: "post_id_on_platform",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "主贴平台ID"),
    size: 80,
    cell: ({ row }: { row: { original: SocialComment } }) => {
      const postIdOnPlatform = postIdMap.value.get(row.original.post_id) || "-";
      return h("span", { class: "text-xs font-mono truncate block max-w-[70px]", title: postIdOnPlatform }, postIdOnPlatform);
    },
  },
  {
    accessorKey: "author_name",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "作者"),
    size: 70,
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h("span", { class: "text-sm truncate block max-w-[60px]" }, row.original.author_name || "-"),
  },
  {
    accessorKey: "content",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "评论内容"),
    size: 180,
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h(ExpandableText, {
        text: row.original.content || "",
        maxLength: 30,
      }),
  },
  {
    accessorKey: "likes_count",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "点赞"),
    size: 50,
    cell: ({ row }: { row: { original: SocialComment } }) =>
      h(
        "span",
        { class: "text-xs text-right block" },
        formatNumber(row.original.likes_count)
      ),
  },
  {
    accessorKey: "published_at",
    header: () =>
      h("span", { style: { whiteSpace: "nowrap" } as const }, "评论时间"),
    size: 90,
    cell: ({ row }: { row: { original: SocialComment } }) => {
      const dt = formatDateTime(row.original.published_at)
      if (!dt) return h("span", { class: "text-xs text-gray-400" }, "-")
      return h("div", { class: "text-xs text-gray-500 leading-tight" }, [
        h("div", {}, dt.date),
        h("div", {}, dt.time),
      ])
    },
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
          :to="backPath"
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
            :to="`/social-media/tasks/${taskId}/upload`"
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
                  <UButton
                    v-if="task.monitor_id"
                    variant="link"
                    size="sm"
                    class="mt-1 p-0 font-normal"
                    :to="`/social-media/monitors/${task.monitor_id}`"
                    :title="task.monitor_name || '-'"
                  >
                    {{ task.monitor_name || "-" }}
                  </UButton>
                  <p
                    v-else
                    class="mt-1 text-sm text-gray-900 dark:text-white truncate"
                  >
                    -
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
                    {{ formatFullDateTime(task.created_at) }}
                  </p>
                </div>
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    开始时间
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ formatFullDateTime(task.started_at) }}
                  </p>
                </div>
                <div>
                  <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">
                    完成时间
                  </h3>
                  <p class="mt-1 text-sm text-gray-900 dark:text-white">
                    {{ formatFullDateTime(task.completed_at) }}
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
                <div class="flex items-center justify-between gap-3">
                  <h2 class="text-lg font-semibold">原文数据</h2>
                  <div
                    v-if="selectedPostDbIdForPosts"
                    class="flex items-center gap-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-1.5"
                  >
                    <span
                      class="text-sm text-blue-700 dark:text-blue-300 whitespace-nowrap"
                    >
                      正在查看:
                      <span class="font-mono font-medium">ID {{ selectedPostDbIdForPosts }}</span>
                    </span>
                    <UButton
                      size="xs"
                      variant="ghost"
                      icon="i-heroicons-x-mark"
                      @click="handleClearPostFilter"
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
                    v-if="selectedPostDbId"
                    class="flex items-center gap-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-1.5"
                  >
                    <span
                      class="text-sm text-blue-700 dark:text-blue-300 whitespace-nowrap"
                    >
                      正在查看:
                      <span class="font-mono font-medium">
                        {{ selectedPostIdOnPlatform || `ID ${selectedPostDbId}` }}
                      </span>
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
                    {{ selectedPostDbId ? "该帖子暂无评论" : "暂无评论数据" }}
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
                        selectedPostDbId ? "评论" : "记录"
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
              <AnalysisPanel
                ref="analysisPanelRef"
                :task-id="taskId"
                @focus-post="handleFocusPost"
              />
            </ClientOnly>
          </div>
  </div>
</template>
