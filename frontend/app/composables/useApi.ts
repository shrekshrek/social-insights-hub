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
import { isJwtExpiring } from '~/app/utils/token'
import { getCurrentInstance } from 'vue'

export const useApi = () => {
  // 防御：useApi 可能在非组件 setup 场景被调用（例如某些 composable/工具函数）。
  // 这时调用 useToast() 会触发 Vue 的 inject() 警告，因此仅在存在当前组件实例时才初始化 toast。
  const toast = getCurrentInstance() ? useToast() : null
  const config = useRuntimeConfig()
  const { session, fetch: fetchSession, clear: clearSession } = useUserSession()

  let sessionFetchPromise: Promise<void> | null = null
  type SessionLoadState = 'unloaded' | 'loaded' | 'loaded-with-token'
  let sessionState: SessionLoadState = 'unloaded'

  const normalizeHeaders = (input?: HeadersInit | Record<string, string>): Record<string, string> => {
    if (!input) {
      return {}
    }

    if (input instanceof Headers) {
      const result: Record<string, string> = {}
      input.forEach((value, key) => {
        result[key] = value
      })
      return result
    }

    if (Array.isArray(input)) {
      return Object.fromEntries(input)
    }

    return { ...input }
  }

  // 确保在首次请求前已经恢复会话，避免因 token 未加载造成 401 重试
  const ensureSessionLoaded = async () => {
    const token = session.value?.accessToken
    const hasToken = Boolean(token)
    const tokenExpired = isJwtExpiring(token)
    if (
      sessionState === 'loaded-with-token' && hasToken && !tokenExpired
    ) {
      return
    }

    if (
      sessionState === 'loaded' && !hasToken
    ) {
      return
    }

    if (!sessionFetchPromise) {
      sessionFetchPromise = fetchSession()
        .catch((error: unknown) => {
          console.warn('Failed to fetch user session before API request', error)
        })
        .finally(() => {
          sessionFetchPromise = null
          sessionState = session.value?.accessToken
            ? 'loaded-with-token'
            : 'loaded'
        })
    }

    await sessionFetchPromise

    const refreshedToken = session.value?.accessToken
    if (!refreshedToken || isJwtExpiring(refreshedToken)) {
      sessionState = 'unloaded'
      if (import.meta.client) {
        await clearSession().catch((error: unknown) => {
          console.warn('Failed to clear session when unauthenticated', error)
        })
        window.location.href = '/login'
      }
      throw new Error('Unauthorized')
    }
  }

  const ensureAuthenticated = async (): Promise<string> => {
    await ensureSessionLoaded()
    const token = session.value?.accessToken
    if (!token) {
      sessionState = 'unloaded'
      if (import.meta.client) {
        await clearSession().catch((error: unknown) => {
          console.warn('Failed to clear session when unauthenticated', error)
        })
        window.location.href = '/login'
      }
      throw new Error('Unauthorized')
    }
    return token as string
  }

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
    // ofetch 使用 _data，普通 fetch 使用 data
    const errorObj = error as {
      status?: number
      statusCode?: number
      data?: {
        error?: { code?: string; message?: string }
        detail?: string | Array<{ msg: string }>
      }
      _data?: {
        error?: { code?: string; message?: string }
        detail?: string | Array<{ msg: string }>
      }
    }
    const status = errorObj.status || errorObj.statusCode
    let message = '请求失败'

    // 获取响应数据（兼容 ofetch 的 _data 和普通 fetch 的 data）
    const responseData = errorObj._data || errorObj.data

    // 解析错误消息 - 优先使用后端统一格式
    if (responseData?.error?.message) {
      // 后端统一错误格式: { error: { code, message } }
      message = responseData.error.message
    } else if (responseData?.detail) {
      // FastAPI 默认格式: { detail: string | array }
      if (typeof responseData.detail === 'string') {
        message = responseData.detail
      } else if (Array.isArray(responseData.detail) && responseData.detail.length > 0) {
        message = responseData.detail[0]?.msg || message
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
          const { clear } = useUserSession()
          sessionState = 'unloaded'
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
    if (!toast) {
      console.info('[toast:success]', message)
      return
    }
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
    if (!toast) {
      console.warn('[toast:error]', message)
      return
    }
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
    if (!toast) {
      console.warn('[toast:warning]', message)
      return
    }
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
    const token = await ensureAuthenticated()

    const headers = normalizeHeaders(options.headers as HeadersInit | Record<string, string> | undefined)

    headers.Authorization = `Bearer ${token}`

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
   *
   * @param options.silent404 - 静默处理 404 错误（不显示 toast），适用于可选数据查询
   */
  const useApiData = <T = unknown>(path: MaybeRef<string>, options: Record<string, unknown> = {}) => {
    const fullPath = computed(() => buildApiPath(unref(path)))
    const userOnRequest = options.onRequest as ((ctx: unknown) => unknown | Promise<unknown>) | undefined
    const userOnResponseError = options.onResponseError as
      ((ctx: unknown) => unknown | Promise<unknown>) | undefined
    const baseHeaders = normalizeHeaders(options.headers as HeadersInit | Record<string, string> | undefined)
    const silent404 = options.silent404 as boolean | undefined

    return useFetch<T>(fullPath, {
      ...options,
      baseURL: '', // 使用空字符串确保相对路径，避免CORS问题
      async onRequest(context) {
        const token = await ensureAuthenticated()

        const mergedHeaders = {
          ...baseHeaders,
          ...normalizeHeaders(context.options.headers as HeadersInit | Record<string, string> | undefined),
        }

        mergedHeaders.Authorization = `Bearer ${token}`

        const headersInstance = new Headers()
        Object.entries(mergedHeaders).forEach(([key, value]) => {
          headersInstance.set(key, value)
        })
        context.options.headers = headersInstance

        if (userOnRequest) {
          await userOnRequest(context)
        }
      },
      async onResponseError(context) {
        if (userOnResponseError) {
          await userOnResponseError(context)
        }
        // 静默处理 404 错误（适用于可选数据查询，如聚合结果可能不存在）
        const status = context.response?.status
        if (silent404 && status === 404) {
          return
        }
        const { message } = handleApiError(context.response)
        showError(message)
      },
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
