import type {
  AnalysisJob,
  AnalysisJobListResponse,
  AnalysisJobFilterParams,
  AnalysisProgressResponse,
} from "../types";

/**
 * 跨渠道 AnalysisJob 操作 Composable
 */
export const useJobs = () => {
  const { apiRequest, useApiData, showSuccess } = useApi();

  /**
   * 获取全局分析任务列表
   */
  const getAnalysisJobs = (params?: MaybeRef<AnalysisJobFilterParams>) => {
    return useApiData<AnalysisJobListResponse>(
      computed(() => {
        const p = unref(params) || {};
        const searchParams = new URLSearchParams();

        if (p.page) searchParams.set("page", String(p.page));
        if (p.page_size) searchParams.set("page_size", String(p.page_size));
        if (p.social_monitor_id)
          searchParams.set("social_monitor_id", String(p.social_monitor_id));
        if (p.social_task_id)
          searchParams.set("social_task_id", String(p.social_task_id));
        if (p.news_monitor_id)
          searchParams.set("news_monitor_id", String(p.news_monitor_id));
        if (p.news_task_id)
          searchParams.set("news_task_id", String(p.news_task_id));
        if (p.analysis_type) searchParams.set("analysis_type", p.analysis_type);
        if (p.status) searchParams.set("status", p.status);
        if (p.start_date) searchParams.set("start_date", p.start_date);
        if (p.end_date) searchParams.set("end_date", p.end_date);

        const query = searchParams.toString();
        return `/jobs${query ? `?${query}` : ""}`;
      }),
      {
        key: computed(() => {
          const p = unref(params) || {};
          return `analysis-jobs-${JSON.stringify(p)}`;
        }),
        getCachedData: () => undefined,
      },
    );
  };

  /**
   * 获取单个分析任务详情
   */
  const getAnalysisJob = (jobId: MaybeRef<number>) => {
    return useApiData<AnalysisJob>(
      computed(() => `/jobs/${unref(jobId)}`),
      {
        key: computed(() => `analysis-job-${unref(jobId)}`),
      },
    );
  };

  /**
   * 获取分析任务进度
   */
  const getAnalysisProgress = (jobId: MaybeRef<number>) => {
    return useApiData<AnalysisProgressResponse>(
      computed(() => `/jobs/${unref(jobId)}/progress`),
      {
        key: computed(() => `analysis-progress-${unref(jobId)}`),
      },
    );
  };

  /**
   * 取消分析任务
   */
  const cancelAnalysisJob = async (jobId: number) => {
    await apiRequest(`/jobs/${jobId}/cancel`, { method: "POST" });
    showSuccess("分析任务已取消");
    return true;
  };

  /**
   * 删除分析任务
   */
  const deleteAnalysisJob = async (jobId: number) => {
    await apiRequest(`/jobs/${jobId}`, { method: "DELETE" });
    showSuccess("分析任务已删除");
    return true;
  };

  return {
    getAnalysisJobs,
    getAnalysisJob,
    getAnalysisProgress,
    cancelAnalysisJob,
    deleteAnalysisJob,
  };
};
