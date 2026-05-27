/**
 * 认证相关 API 封装
 *
 * 注册流程：邀请制，必须凭 invite_token 注册（管理员邮件邀请）
 * 密码重置：仅管理员触发邮件，用户凭 reset_token 设置新密码
 *
 * 注意：登录/注册/登出/飞书 OAuth 仍走 nuxt-auth-utils 提供的服务端代理端点
 * （/api/auth/*），用裸 $fetch 是因为此时还没 access token，绕过 useApi
 * 的 ensureAuthenticated 检查。
 */
import type { User, UserCreate } from "~/types/user"
import type { MessageResponse } from "~/types/auth"

export const useAuthApi = () => {
  const { showSuccess } = useApi()
  const { fetch: refreshSession, clear: clearSession, session } = useUserSession()
  const userStore = useUserStore()

  /**
   * 用户注册（邀请制）— 直接调用后端 API，注册成功后自动登录
   */
  const register = async (data: UserCreate) => {
    const result = await $fetch<User>('/api/v1/auth/register', {
      method: 'POST',
      body: {
        username: data.username,
        password: data.password,
        invite_token: data.invite_token,
      },
    })

    // 注册成功后用同一组用户名/密码完成登录
    await login({ username: data.username, password: data.password })

    showSuccess('注册成功！已自动登录')
    return result
  }

  /**
   * 用户登录 — 通过服务端认证端点设置 session
   */
  const login = async (data: { username: string; password: string }) => {
    const result = await $fetch<{ success: boolean; user: User }>('/api/auth/login', {
      method: 'POST',
      body: {
        email: data.username, // 后端使用 username 字段，沿用 OAuth2 form 协议
        password: data.password,
      },
    })

    await refreshSession()
    if (result.user) {
      userStore.setUser(result.user)
    }
    showSuccess('登录成功！')
    return result
  }

  /**
   * 用户登出
   */
  const logout = async () => {
    try {
      await $fetch('/api/auth/logout', { method: 'POST' })
      userStore.clearUser()
      await clearSession()
      showSuccess('已安全退出登录')
      await navigateTo('/')
    } catch (error) {
      console.error('Logout error:', error)
      userStore.clearUser()
      await clearSession()
      await navigateTo('/')
    }
  }

  /**
   * 获取当前用户信息（从 session）
   */
  const getMe = async () => {
    if (!session.value?.user) {
      await refreshSession()
    }
    if (!session.value?.user) {
      throw new Error('未登录')
    }
    return session.value.user as User
  }

  /**
   * 凭 reset token 设置新密码（管理员通过邮件发出的链接）
   * 用户此时未登录，必须走裸 $fetch（绕过 apiRequest 的鉴权检查）
   */
  const resetPasswordWithToken = async (data: { token: string; new_password: string }) => {
    const result = await $fetch<MessageResponse>('/api/v1/auth/reset-password', {
      method: 'POST',
      body: data,
    })
    showSuccess(result.message || '密码重置成功')
    return result
  }

  /**
   * 飞书扫码登录 — 跳转到飞书授权页
   */
  const feishuLogin = async () => {
    const data = await $fetch<{ authorize_url: string; state: string }>('/api/auth/feishu/authorize')
    window.location.href = data.authorize_url
  }

  /**
   * 飞书 OAuth 回调处理
   */
  const feishuCallback = async (code: string, state: string) => {
    const result = await $fetch<{ success: boolean; user: User }>('/api/auth/feishu/callback', {
      method: 'POST',
      body: { code, state },
    })
    await refreshSession()
    if (result.user) {
      userStore.setUser(result.user)
    }
    return result
  }

  return {
    register,
    login,
    logout,
    getMe,
    resetPasswordWithToken,
    feishuLogin,
    feishuCallback,
  }
}
