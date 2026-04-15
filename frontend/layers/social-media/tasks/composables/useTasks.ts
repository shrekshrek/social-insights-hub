import type {
  SocialTask,
  SocialTaskCreate,
  SocialTaskUpdate,
  SocialTaskWithRelations,
} from "../types";

export const useSocialTasks = () => {
  const { apiRequest, useApiData, showSuccess } = useApi();

  // 获取任务列表
  const getTasks = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<SocialTaskWithRelations>>("/social-media/tasks", {
      query: params,
      key: computed(() => {
        const p = unref(params);
        const keys = [
          "page",
          "page_size",
          "monitor_id",
          "platform_id",
          "task_type",
          "status",
          "data_source",
          "user_id",
          "search",
          "phase",
        ];
        const paramStr = keys.map((k) => `${k}=${p?.[k] || ""}`).join("-");
        return `tasks-list-${paramStr}`;
      }),
    });
  };

  // 获取单个任务
  const getTask = (id: number) => {
    return useApiData<SocialTaskWithRelations>(`/social-media/tasks/${id}`, {
      key: `task-${id}`,
    });
  };

  // 创建任务（monitor_id 通过 URL 路径传递）
  const createTask = async (monitorId: number, data: SocialTaskCreate) => {
    const result = await apiRequest<SocialTask>(
      `/social-media/monitors/${monitorId}/tasks`,
      {
        method: "POST",
        body: data,
      },
    );
    showSuccess("任务创建成功！");
    return result;
  };

  // 更新任务
  const updateTask = async (id: number, data: SocialTaskUpdate) => {
    const result = await apiRequest<SocialTask>(`/social-media/tasks/${id}`, {
      method: "PUT",
      body: data,
    });
    showSuccess("任务更新成功！");
    return result;
  };

  // 删除任务
  const deleteTask = async (id: number) => {
    await apiRequest(`/social-media/tasks/${id}`, {
      method: "DELETE",
    });
    showSuccess("任务删除成功！");
    return true;
  };

  // 清空任务数据
  const clearTaskData = async (id: number) => {
    const result = await apiRequest<SocialTask>(`/social-media/tasks/${id}/clear-data`, {
      method: "POST",
    });
    showSuccess("任务数据已清空，可以重新上传或采集");
    return result;
  };

  return {
    getTasks,
    getTask,
    createTask,
    updateTask,
    deleteTask,
    clearTaskData,
  };
};

// Backward-compatible alias
export const useTasks = useSocialTasks;
