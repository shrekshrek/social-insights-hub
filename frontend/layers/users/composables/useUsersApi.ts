import type { User, UserUpdate, UserListResponse, AdminUserCreate, InvitationCreateRequest } from '../types'

export const useUsersApi = () => {
  const { apiRequest, useApiData, showSuccess } = useApi()

  // 获取用户列表
  const getUsers = (params?: Record<string, unknown>) => {
    return useApiData<UserListResponse>('/users/', {
      query: params,
      key: computed(() => {
        const p = unref(params);
        return `users-list-${p?.page || 1}-${p?.page_size || 10}`;
      })
    });
  }

  // 获取单个用户
  const getUser = (id: number) => {
    return useApiData<User>(`/users/${id}`, {
      key: `user-${id}`,
    })
  }

  // 创建用户
  const createUser = async (data: AdminUserCreate) => {
    const payload: Record<string, unknown> = {
      username: data.username,
      email: data.email,
      password: data.password
    }

    if (data.role_ids && data.role_ids.length > 0) {
      payload.role_ids = data.role_ids
    }

    const result = await apiRequest<User>('/users', {
      method: 'POST',
      body: payload,
    })
    showSuccess('用户创建成功！')
    return result
  }

  // 更新用户
  const updateUser = async (id: number, data: UserUpdate) => {
    const result = await apiRequest<User>(`/users/${id}`, {
      method: 'PUT',
      body: data,
    })
    showSuccess('用户更新成功！')
    return result
  }

  // 删除用户
  const deleteUser = async (id: number) => {
    await apiRequest(`/users/${id}`, {
      method: 'DELETE',
    })
    showSuccess('用户删除成功！')
    return true
  }

  // 获取当前用户信息
  const getCurrentUser = () => {
    return useApiData<User>('/users/me', {
      key: 'current-user',
    })
  }

  // 管理员发送注册邀请邮件
  const sendInvitation = async (data: InvitationCreateRequest) => {
    const result = await apiRequest<{ message: string }>('/auth/invitations', {
      method: 'POST',
      body: data,
    })
    showSuccess(result.message || '邀请邮件已发送')
    return result
  }

  // 管理员触发用户密码重置邮件
  const sendPasswordResetEmail = async (userId: number) => {
    const result = await apiRequest<{ message: string }>(
      `/auth/users/${userId}/send-reset-email`,
      { method: 'POST' },
    )
    showSuccess(result.message || '重置邮件已发送')
    return result
  }

  return {
    getUsers,
    getUser,
    createUser,
    updateUser,
    deleteUser,
    getCurrentUser,
    sendInvitation,
    sendPasswordResetEmail,
  }
} 
