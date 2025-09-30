/**
 * 全局错误处理插件
 * 
 * 捕获并处理所有Vue运行时错误，提升应用稳定性
 */
export default defineNuxtPlugin((nuxtApp) => {
  // Vue错误处理器
  nuxtApp.vueApp.config.errorHandler = (error, instance, info) => {
    console.error('[Vue Error]', error)
    
    // 开发环境显示详细信息
    if (import.meta.dev) {
      console.error('Error details:', {
        component: instance?.$options?.name || instance?.$?.type?.name || 'Unknown',
        info,
        error
      })
    }
    
    // 生产环境可以发送到错误追踪服务
    if (!import.meta.dev) {
      // 简单的错误记录，不过度设计
      console.error('Error context:', {
        component: instance?.$options?.name || instance?.$?.type?.name || 'Unknown',
        errorInfo: info,
        message: error instanceof Error ? error.message : String(error)
      })
      
      // 未来可以集成 Sentry 或其他错误追踪服务
      // window.Sentry?.captureException(error, { extra: { info } })
    }
  }

  // Nuxt错误钩子
  nuxtApp.hook('vue:error', (error, _instance, _info) => {
    console.error('[Nuxt Hook] Vue error:', error)
    
    // 可以在这里添加额外的错误处理逻辑
    // 例如：显示全局错误提示
    const toast = useToast()
    if (import.meta.dev) {
      // 开发环境显示错误提示
      toast.add({
        title: '运行时错误',
        description: error instanceof Error ? error.message : '发生了未知错误',
        color: 'error',
        duration: 5000
      })
    }
  })
  
  // 捕获未处理的Promise rejection
  if (import.meta.client) {
    window.addEventListener('unhandledrejection', (event) => {
      console.error('[Unhandled Promise Rejection]', event.reason)
      
      // 开发环境显示警告
      if (import.meta.dev) {
        const toast = useToast()
        toast.add({
          title: 'Promise Rejection',
          description: event.reason?.message || '未处理的Promise错误',
          color: 'warning',
          duration: 5000
        })
      }
      
      // 阻止默认行为（防止控制台报错）
      event.preventDefault()
    })
  }
})