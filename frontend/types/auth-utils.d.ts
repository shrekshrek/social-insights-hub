/**
 * 扩展 nuxt-auth-utils 的类型定义
 * 使其与项目的 User 类型保持一致
 */

declare module '#auth-utils' {
  /**
   * 用户信息接口
   * 与后端 FastAPI 的 UserResponse 模型保持一致
   */
  interface User {
    id: number
    email: string
    username: string
    is_active: boolean
    is_superuser: boolean
    created_at: string
    updated_at: string
    roles?: string[]
  }

  /**
   * 用户会话接口
   * 存储在加密 cookie 中的会话数据
   */
  interface UserSession {
    user: User
    accessToken: string
    tokenType: string
  }
  
  /**
   * Session数据类型别名
   * 方便在应用中使用
   */
  type SessionData = UserSession
}

// 确保模块声明被正确识别
export {}