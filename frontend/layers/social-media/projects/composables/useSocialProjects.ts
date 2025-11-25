import type {
  SocialProject,
  SocialProjectCreate,
  SocialProjectUpdate,
  SocialProjectCreateResponse,
} from '../../tasks/types'

export const useSocialProjects = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  // 获取项目列表
  const getProjects = (params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PaginatedResponse<SocialProject>>('/social-media/projects', {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `social-projects-list-${p?.page || 1}-${p?.page_size || 10}`
      }),
    })
  }

  // 获取单个项目
  const getProject = (id: number) => {
    return useApiData<SocialProject>(`/social-media/projects/${id}`, {
      key: `social-project-${id}`,
    })
  }

  // 创建项目
  const createProject = async (data: SocialProjectCreate) => {
    const result = await apiRequest<SocialProjectCreateResponse>('/social-media/projects', {
      method: 'POST',
      body: data,
    })
    // Don't show toast here, let the page handle it based on created_tasks
    return result
  }

  // 更新项目
  const updateProject = async (id: number, data: SocialProjectUpdate) => {
    const result = await apiRequest<SocialProject>(`/social-media/projects/${id}`, {
      method: 'PUT',
      body: data,
    })
    showSuccess('项目更新成功！')
    return result
  }

  // 删除项目
  const deleteProject = async (id: number) => {
    await apiRequest(`/social-media/projects/${id}`, {
      method: 'DELETE',
    })
    showSuccess('项目删除成功！')
    return true
  }

  // 添加项目参与者
  const addParticipant = async (projectId: number, userId: number) => {
    const result = await apiRequest<SocialProject>(
      `/social-media/projects/${projectId}/participants/${userId}`,
      {
        method: 'POST',
      }
    )
    showSuccess('参与者添加成功！')
    return result
  }

  // 移除项目参与者
  const removeParticipant = async (projectId: number, userId: number) => {
    const result = await apiRequest<SocialProject>(
      `/social-media/projects/${projectId}/participants/${userId}`,
      {
        method: 'DELETE',
      }
    )
    showSuccess('参与者移除成功！')
    return result
  }

  return {
    getProjects,
    getProject,
    createProject,
    updateProject,
    deleteProject,
    addParticipant,
    removeParticipant,
  }
}
