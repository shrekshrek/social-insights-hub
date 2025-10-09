/**
 * 统一的 API 请求工具
 * 
 * 提供两种主要的 API 请求方式：
 * 1. apiRequest: 基于 $fetch，用于客户端操作（如表单提交、登录等）
 * 2. useApiData: 基于 useFetch，用于数据获取，支持 SSR
 * 
 * 响应格式说明：
 * - 后端采用 FastAPI 原生响应格式，直接返回业务数据
 * - 成功响应：直接返回数据对象（如 UserResponse）
 * - 错误响应：通过 HTTP 状态码和标准错误格式处理
 */
export const useApi = () => {
  const toast = useToast()
  const config = useRuntimeConfig()

  /**
   * 构建完整的API路径
   * @param path 接口路径，如 '/auth/login'
   * @returns 完整路径，如 'http://localhost:8000/api/v1/auth/login'
   */
  const buildApiPath = (path: string): string => {
    // 确保路径以 / 开头
    const cleanPath = path.startsWith('/') ? path : `/${path}`
    
    // 动态构建完整的API路径
    return `${config.public.apiBase}${cleanPath}`
  }

  /**
   * 处理 API 错误
   * 根据 HTTP 状态码进行不同的处理
   */
  const handleApiError = (error: unknown) => {
    console.error('API 错误:', error)

    // 获取错误信息
    const errorObj = error as {
      status?: number
      statusCode?: number
      data?: {
        error?: { code?: string; message?: string }
        detail?: string | Array<{ msg: string }>
      }
    }
    const status = errorObj.status || errorObj.statusCode
    let message = '请求失败'

    // 解析错误消息 - 优先使用后端统一格式
    if (errorObj.data?.error?.message) {
      // 后端统一错误格式: { error: { code, message } }
      message = errorObj.data.error.message
    } else if (errorObj.data?.detail) {
      // FastAPI 默认格式: { detail: string | array }
      if (typeof errorObj.data.detail === 'string') {
        message = errorObj.data.detail
      } else if (Array.isArray(errorObj.data.detail) && errorObj.data.detail.length > 0) {
        message = errorObj.data.detail[0]?.msg || message
      }
    }
    
    // 根据状态码处理
    switch (status) {
      case 400:
        message = `请求错误: ${message}`
        break
      case 401: {
        message = '登录已过期，请重新登录'
        // 处理token过期，自动登出
        if (import.meta.client) {
          const { clear, session } = useUserSession()
          session.value = null
          clear()
            .catch((error: unknown) => {
              console.warn('Failed to clear expired session', error)
            })
            .finally(() => {
              navigateTo('/login')
            })
        }
        break
      }
      case 403:
        message = '权限不足'
        break
      case 404:
        message = '请求的资源不存在'
        break
      case 422:
        message = `数据验证失败: ${message}`
        break
      case 500:
        message = '服务器内部错误'
        break
      default:
        message = `请求失败 (${status}): ${message}`
    }
    
    return { status, message }
  }

  /**
   * 显示成功提示
   */
  const showSuccess = (message: string) => {
    toast.add({
      title: '成功',
      description: message,
      color: 'success',
    })
  }

  /**
   * 显示错误提示
   */
  const showError = (message: string) => {
    toast.add({
      title: '错误',
      description: message,
      color: 'error',
    })
  }

  /**
   * 显示警告提示
   */
  const showWarning = (message: string) => {
    toast.add({
      title: '警告',
      description: message,
      color: 'warning',
    })
  }

  /**
   * 基于 $fetch 的 API 请求
   * 用于客户端操作（如表单提交、登录等）
   */
  const apiRequest = async <T = unknown>(path: string, options: Record<string, unknown> = {}): Promise<T> => {
    const fullPath = buildApiPath(path)
    
    // 获取认证 token
    const { session } = useUserSession()
    const headers = { ...((options.headers as Record<string, string>) || {}) }
    
    // 如果有认证 token，添加到请求头
    if (session.value?.accessToken) {
      headers.Authorization = `Bearer ${session.value.accessToken}`
    }
    
    const response = await $fetch<T>(fullPath, {
      ...options,
      headers,
      baseURL: '', // 使用空字符串确保相对路径，避免CORS问题
      onResponseError({ response }) {
        const { message } = handleApiError(response)
        showError(message)
      }
    })
    return response as T
  }

  /**
   * 基于 useFetch 的数据获取
   * 支持 SSR，用于页面数据获取
   */
  const useApiData = <T = unknown>(path: string, options: Record<string, unknown> = {}) => {
    const fullPath = buildApiPath(path)
    
    // 获取认证 token
    const { session } = useUserSession()
    const headers = { ...((options.headers as Record<string, string>) || {}) }
    
    // 如果有认证 token，添加到请求头
    if (session.value?.accessToken) {
      headers.Authorization = `Bearer ${session.value.accessToken}`
    }
    
    return useFetch<T>(fullPath, {
      ...options,
      headers,
      baseURL: '', // 使用空字符串确保相对路径，避免CORS问题
      onResponseError({ response }) {
        const { message } = handleApiError(response)
        showError(message)
      }
    })
  }

  return {
    apiRequest,
    useApiData,
    showSuccess,
    showError,
    showWarning,
  }
} 
