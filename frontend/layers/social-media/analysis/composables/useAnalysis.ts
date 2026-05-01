import type {
  RunAnalysisResponse,
  PostAnalysisListResponse,
  DeepAnalysisPreview,
  TaskAnalysisResultResponse,
  RunAggregationResponse,
  AnalysisJobListResponse,
} from "../types";

/**
 * 社媒分析操作 Composable
 *
 * 仅包含社媒渠道本地的分析操作（任务级分析、监测级切片）。
 * 跨渠道 AnalysisJob 的增删改查见 `layers/jobs/composables/useJobsApi.ts`。
 */
export const useAnalysis = () => {
  const { apiRequest, useApiData, showSuccess } = useApi();

  // ==================== 任务级分析操作 ====================

  /**
   * 运行原文AI初筛分析
   */
  const runPostScreening = async (taskId: number) => {
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/tasks/${taskId}/screening`,
      {
        method: "POST",
      },
    );
    showSuccess("原文初筛任务已启动");
    return result;
  };

  /**
   * 运行原文深度分析
   */
  const runPostDeepAnalysis = async (
    taskId: number,
    params?: { spam_max?: number; value_min?: number; relevance_min?: number },
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.spam_max != null)
      searchParams.set("spam_max", String(params.spam_max));
    if (params?.value_min != null)
      searchParams.set("value_min", String(params.value_min));
    if (params?.relevance_min != null)
      searchParams.set("relevance_min", String(params.relevance_min));

    const query = searchParams.toString();
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/tasks/${taskId}/deep-posts${query ? `?${query}` : ""}`,
      {
        method: "POST",
      },
    );
    showSuccess("原文深度分析任务已启动");
    return result;
  };

  /**
   * 运行评论深度分析
   */
  const runCommentDeepAnalysis = async (
    taskId: number,
    params?: { spam_max?: number; value_min?: number; relevance_min?: number },
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.spam_max != null)
      searchParams.set("spam_max", String(params.spam_max));
    if (params?.value_min != null)
      searchParams.set("value_min", String(params.value_min));
    if (params?.relevance_min != null)
      searchParams.set("relevance_min", String(params.relevance_min));

    const query = searchParams.toString();
    const result = await apiRequest<RunAnalysisResponse>(
      `/social-media/analysis/tasks/${taskId}/deep-comments${query ? `?${query}` : ""}`,
      {
        method: "POST",
      },
    );
    showSuccess("评论深度分析任务已启动");
    return result;
  };

  /**
   * 获取任务下所有原文的分析结果
   */
  const getTaskPostAnalyses = (
    taskId: MaybeRef<number>,
    options?: {
      page?: MaybeRef<number>;
      pageSize?: MaybeRef<number>;
      filterAnalyzed?: MaybeRef<boolean>;
      searchQuery?: MaybeRef<string>;
      searchId?: MaybeRef<number | null>;
      postIds?: MaybeRef<number[] | null>;
      spamGroup?: MaybeRef<string | undefined>;
    },
  ) => {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    const filterAnalyzed = options?.filterAnalyzed ?? true;
    const searchQuery = options?.searchQuery ?? "";
    const searchId = options?.searchId ?? null;
    const postIds = options?.postIds ?? null;
    const spamGroup = options?.spamGroup ?? undefined;

    return useApiData<PostAnalysisListResponse>(
      computed(() => {
        const params = new URLSearchParams({
          page: String(unref(page)),
          page_size: String(unref(pageSize)),
          filter_analyzed: String(unref(filterAnalyzed)),
        });

        const query = unref(searchQuery);
        const id = unref(searchId);
        const ids = unref(postIds);
        const sg = unref(spamGroup);
        if (query) {
          params.set("search_query", query);
        }
        if (typeof id === "number" && !Number.isNaN(id)) {
          params.set("search_id", String(id));
        }
        if (ids && ids.length > 0) {
          params.set("post_ids", ids.join(","));
        }
        if (sg === "high" || sg === "low") {
          params.set("spam_group", sg);
        }

        return `/social-media/analysis/tasks/${unref(taskId)}/posts?${params}`;
      }),
      {
        key: computed(() => {
          const query = unref(searchQuery);
          const id = unref(searchId);
          const ids = unref(postIds);
          const sg = unref(spamGroup);
          const idsKey = ids ? ids.slice(0, 10).join("-") : ""; // 只用前10个ID作为key的一部分
          return `task-post-analyses-${unref(taskId)}-${unref(page)}-${unref(pageSize)}-${query}-${id}-${idsKey}-${sg ?? ""}`;
        }),
      },
    );
  };

  /**
   * 深度分析预览（基于初筛阈值）
   */
  const getDeepAnalysisPreview = async (
    taskId: number,
    params: { spam_max?: number; value_min?: number; relevance_min?: number },
  ) => {
    const searchParams = new URLSearchParams();
    if (params.spam_max != null)
      searchParams.set("spam_max", String(params.spam_max));
    if (params.value_min != null)
      searchParams.set("value_min", String(params.value_min));
    if (params.relevance_min != null)
      searchParams.set("relevance_min", String(params.relevance_min));

    return apiRequest<DeepAnalysisPreview>(
      `/social-media/analysis/tasks/${taskId}/preview?${searchParams.toString()}`,
    );
  };

  /**
   * 删除任务下所有分析结果（方便重新分析）
   */
  const deleteTaskAnalyses = async (taskId: number) => {
    const result = await apiRequest<{
      success: boolean;
      deleted_count: number;
      message: string;
    }>(`/social-media/analysis/tasks/${taskId}/analyses`, {
      method: "DELETE",
    });
    showSuccess(result.message);
    return result;
  };

  /**
   * 运行聚合分析，生成任务级分析报告
   */
  const runTaskAggregation = async (taskId: number) => {
    const result = await apiRequest<RunAggregationResponse>(
      `/social-media/analysis/tasks/${taskId}/aggregation`,
      {
        method: "POST",
      },
    );
    return result;
  };

  /**
   * 获取任务级 AnalysisJob 状态列表（channel-local，供 AnalysisPanel 显示进度）
   *
   * 跨渠道运维查询走 `layers/jobs/composables/useJobsApi.ts` 的 getAnalysisJobs
   * （admin-only）。本端点权限是 social_task:read + 任务访问校验，跟查看任务本体一致。
   */
  const getTaskAnalysisJobs = (
    taskId: MaybeRef<number>,
    params?: MaybeRef<{ page_size?: number; analysis_type?: string; status?: string }>,
  ) => {
    return useApiData<AnalysisJobListResponse>(
      computed(() => `/social-media/analysis/tasks/${unref(taskId)}/jobs`),
      {
        query: params,
        key: computed(() => {
          const p = unref(params)
          return `task-analysis-jobs-${unref(taskId)}-${p?.page_size ?? 50}-${p?.analysis_type ?? ''}-${p?.status ?? ''}`
        }),
        getCachedData: () => undefined,
      },
    );
  };

  /**
   * 获取任务级聚合分析结果
   * 使用 silent404 静默处理 404 错误，因为聚合结果可能尚未生成
   */
  const getTaskAggregation = (taskId: MaybeRef<number>) => {
    return useApiData<TaskAnalysisResultResponse>(
      computed(
        () => `/social-media/analysis/tasks/${unref(taskId)}/aggregation`,
      ),
      {
        key: computed(() => `task-aggregation-${unref(taskId)}`),
        silent404: true,
        // 禁用缓存，确保能获取最新的聚合结果
        getCachedData: () => undefined,
      },
    );
  };

  /**
   * 手动生成监测级合并分析切片（同步完成）
   */
  const createMonitorSlice = async (
    monitorId: number,
    taskIds: number[],
    name?: string,
    options?: {
      subject?: string | null;
      competitors?: string[] | null;
      platform_weights?: Record<string, number> | null;
    },
  ) => {
    const result = await apiRequest<{ id: number; name: string | null }>(
      `/social-media/analysis/monitors/${monitorId}/slices`,
      {
        method: "POST",
        body: {
          task_ids: taskIds,
          name: name || null,
          subject: options?.subject ?? null,
          competitors: options?.competitors ?? null,
          platform_weights: options?.platform_weights ?? null,
        },
      },
    );
    showSuccess("监测切片已生成");
    return result;
  };

  /**
   * 删除监测级合并分析切片
   */
  const deleteMonitorSlice = async (monitorId: number, sliceId: number) => {
    await apiRequest(
      `/social-media/analysis/monitors/${monitorId}/slices/${sliceId}`,
      {
        method: "DELETE",
      },
    );
    showSuccess("切片已删除");
    return true;
  };

  /**
   * 重命名监测级合并分析切片
   */
  const renameMonitorSlice = async (
    monitorId: number,
    sliceId: number,
    name: string,
  ) => {
    const result = await apiRequest<{ id: number; name: string }>(
      `/social-media/analysis/monitors/${monitorId}/slices/${sliceId}`,
      {
        method: "PATCH",
        body: { name },
      },
    );
    showSuccess("切片已重命名");
    return result;
  };

  return {
    // 任务级分析操作
    runPostScreening,
    runPostDeepAnalysis,
    runCommentDeepAnalysis,
    getTaskPostAnalyses,
    getDeepAnalysisPreview,
    deleteTaskAnalyses,
    runTaskAggregation,
    getTaskAggregation,
    getTaskAnalysisJobs,

    // 监测级合并切片
    createMonitorSlice,
    deleteMonitorSlice,
    renameMonitorSlice,
  };
};
