import type {
  SocialMonitor,
  SocialMonitorCreate,
  SocialMonitorUpdate,
  MonitorCreateResponse,
  SocialQuickTaskCreate,
  BatchTasksCreateResponse,
} from "../../tasks/types";

export const useSocialMonitors = () => {
  const { apiRequest, useApiData, showSuccess } = useApi();

  // 获取监测列表
  const getMonitors = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<SocialMonitor>>("/social-media/monitors", {
      query: params,
      key: computed(() => {
        const p = unref(params);
        return `monitors-list-${p?.page || 1}-${p?.page_size || 10}`;
      }),
    });
  };

  // 获取单个监测
  const getMonitor = (id: number) => {
    return useApiData<SocialMonitor>(`/social-media/monitors/${id}`, {
      key: `monitor-${id}`,
    });
  };

  // 创建监测
  const createMonitor = async (data: SocialMonitorCreate) => {
    const result = await apiRequest<MonitorCreateResponse>("/social-media/monitors", {
      method: "POST",
      body: data,
    });
    return result;
  };

  // 更新监测
  const updateMonitor = async (id: number, data: SocialMonitorUpdate) => {
    const result = await apiRequest<SocialMonitor>(`/social-media/monitors/${id}`, {
      method: "PUT",
      body: data,
    });
    showSuccess("监测更新成功！");
    return result;
  };

  // 删除监测
  const deleteMonitor = async (id: number) => {
    await apiRequest(`/social-media/monitors/${id}`, {
      method: "DELETE",
    });
    showSuccess("监测删除成功！");
    return true;
  };

  // 批量创建任务
  const batchCreateTasks = async (monitorId: number, data: SocialQuickTaskCreate) => {
    const result = await apiRequest<BatchTasksCreateResponse>(
      `/social-media/monitors/${monitorId}/batch-tasks`,
      {
        method: "POST",
        body: data,
      },
    );
    showSuccess(`已成功创建 ${result.created_tasks.length} 个任务`);
    return result;
  };

  // 添加监测参与者
  const addParticipant = async (monitorId: number, userId: number) => {
    const result = await apiRequest<SocialMonitor>(
      `/social-media/monitors/${monitorId}/participants/${userId}`,
      {
        method: "POST",
      },
    );
    showSuccess("参与者添加成功！");
    return result;
  };

  // 移除监测参与者
  const removeParticipant = async (monitorId: number, userId: number) => {
    const result = await apiRequest<SocialMonitor>(
      `/social-media/monitors/${monitorId}/participants/${userId}`,
      {
        method: "DELETE",
      },
    );
    showSuccess("参与者移除成功！");
    return result;
  };

  return {
    getMonitors,
    getMonitor,
    createMonitor,
    updateMonitor,
    deleteMonitor,
    batchCreateTasks,
    addParticipant,
    removeParticipant,
  };
};

// Backward-compatible alias
export const useMonitors = useSocialMonitors;
