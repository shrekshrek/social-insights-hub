/**
 * 认证相关 API 封装
 * 基于 nuxt-auth-utils 模块，遵循官方最佳实践
 */

import type { User, UserCreate } from "~/types/user"
import type { Msg, PasswordResetRequest, PasswordReset, StandardError } from "~/types/auth"

export const useAuthApi = () => {
  const { showSuccess, showError } = useApi()
  const { fetch: refreshSession, clear: clearSession, session } = useUserSession()
  const userStore = useUserStore()
  
  /**
   * 用户注册 - 直接调用后端API
   */
  const register = async (data: UserCreate) => {
    try {
      // 直接调用后端注册接口（通过Nuxt代理）
      const result = await $fetch<User>('/api/v1/auth/register', {
        method: 'POST',
        body: {
          email: data.email,
          username: data.username,
          password: data.password
        }
      })
      
      // 注册成功后自动登录
      await login({
        username: data.username,
        password: data.password
      })
      
      showSuccess('注册成功！已自动登录')
      return result
    } catch (error: unknown) {
      const message = (error as StandardError)?.data?.error?.message 
        || (error as StandardError)?.data?.detail 
        || (error as StandardError)?.data?.statusMessage 
        || '注册失败'
      showError(message)
      throw error
    }
  }
  
  /**
   * 用户登录 - 通过服务端认证端点设置session
   */
  const login = async (data: { username: string; password: string }) => {
    try {
      // 调用服务端认证端点，它会设置session
      const result = await $fetch<{ success: boolean; user: User }>('/api/auth/login', {
        method: 'POST',
        body: {
          email: data.username, // 后端使用email作为username
          password: data.password
        }
      })
      
      // 刷新客户端session状态
      await refreshSession()
      
      // 更新用户store
      if (result.user) {
        userStore.setUser(result.user)
      }
      
      showSuccess('登录成功！')
      return result
    } catch (error: unknown) {
      const message = (error as StandardError)?.data?.error?.message 
        || (error as StandardError)?.data?.statusMessage 
        || (error as StandardError)?.data?.detail 
        || '登录失败'
      showError(message)
      throw error
    }
  }
  
  /**
   * 用户登出 - 通过服务端端点处理
   */
  const logout = async () => {
    try {
      // 调用服务端登出端点（会处理后端通知和session清除）
      await $fetch('/api/auth/logout', {
        method: 'POST'
      })
      
      // 确保前端状态完全清除
      userStore.clearUser()
      await clearSession()
      
      showSuccess('已安全退出登录')
      
      // 统一在这里处理跳转，避免调用方重复处理
      await navigateTo('/')
    } catch (error) {
      console.error('Logout error:', error)
      // 确保清除本地状态
      userStore.clearUser()
      await clearSession()
      
      // 即使出错也跳转到安全页面
      await navigateTo('/')
    }
  }
  
  /**
   * 获取当前用户信息 - 从session中获取
   */
  const getMe = async () => {
    // 如果session中没有用户信息，尝试刷新
    if (!session.value?.user) {
      await refreshSession()
    }
    
    if (!session.value?.user) {
      throw new Error('未登录')
    }
    
    return session.value.user as User
  }
  
  /**
   * 请求密码重置 - 直接调用后端API
   */
  const requestPasswordReset = async (data: PasswordResetRequest) => {
    try {
      const result = await $fetch<Msg>('/api/v1/auth/request-password-reset', {
        method: 'POST',
        body: data,
      })
      showSuccess('密码重置邮件已发送，请查收邮箱')
      return result
    } catch {
      // 为了安全，不暴露具体错误
      showSuccess('如果该邮箱已注册，重置链接已发送')
      return { msg: 'Request processed' } as Msg
    }
  }
  
  /**
   * 重置密码 - 直接调用后端API
   */
  const resetPassword = async (data: PasswordReset) => {
    try {
      const result = await $fetch<Msg>('/api/v1/auth/reset-password', {
        method: 'POST',
        body: data,
      })
      showSuccess('密码重置成功！请使用新密码登录')
      return result
    } catch (error: unknown) {
      const message = (error as StandardError)?.data?.error?.message 
        || (error as StandardError)?.data?.detail 
        || (error as StandardError)?.data?.statusMessage 
        || '密码重置失败'
      showError(message)
      throw error
    }
  }
  
  /**
   * 修改当前用户密码
   */
  const changePassword = async (data: { current_password: string; new_password: string }) => {
    try {
      // 确保用户已登录
      if (!session.value?.accessToken) {
        throw new Error('未登录')
      }
      
      const result = await $fetch<Msg>('/api/v1/auth/change-password', {
        method: 'POST',
        body: data,
        headers: {
          'Authorization': `Bearer ${session.value.accessToken}`
        }
      })
      
      showSuccess('密码修改成功！')
      return result
    } catch (error: unknown) {
      const message = (error as StandardError)?.data?.error?.message 
        || (error as StandardError)?.data?.detail 
        || '密码修改失败'
      showError(message)
      throw error
    }
  }
  
  return {
    register,
    login,
    logout,
    getMe,
    requestPasswordReset,
    resetPassword,
    changePassword,
  }
} 