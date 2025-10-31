import type { User, UserUpdate, UserListResponse, AdminUserCreate } from '../types'

export const useUsersApi = () => {
  const { apiRequest, useApiData, showSuccess, showError } = useApi()

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

  return {
    getUsers,
    getUser,
    createUser,
    updateUser,
    deleteUser,
    getCurrentUser,
  }
} 
