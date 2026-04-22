/**
 * 全局错误处理插件
 *
 * 原则：错误处理器必须是**纯函数**，只做 console/log 记录，不触发任何会引发 Vue 渲染
 * 或 reactivity 更新的副作用（比如 toast.add / reactive ref 赋值 / navigateTo）。
 * 违反此原则会在某些 null-deref 场景下形成"渲染→error→副作用→再渲染→再 error"
 * 的无限循环，最终 Nuxt 显示 500 兜底页（参见 2026-04-22 事故：已删除新闻任务详情
 * 页 404 后，vue:error hook 里的 toast.add 和 Nuxt UI 组件的 getComponentPublicInstance
 * null-deref 互相触发，6000+ 次循环后 Nuxt 放弃兜底）。
 *
 * 如果业务需要在特定错误发生时通知用户（如 401/403），请走路由中间件 `error-handler.global.ts`
 * 的显式分派，而不是放在这里。
 */

/** 重入守卫：防止错误处理器自己触发错误导致递归。 */
const createReentryGuard = () => {
  let active = false
  return (fn: () => void, skipLabel: string) => {
    if (active) {
      // 用原生 console.warn，避免依赖可能已经挂掉的 Nuxt 上下文
      console.warn(`[error-handler] ${skipLabel} reentry skipped`)
      return
    }
    active = true
    try {
      fn()
    } catch (handlerError) {
      console.error('[error-handler] handler itself threw, swallowing:', handlerError)
    } finally {
      active = false
    }
  }
}

export default defineNuxtPlugin((nuxtApp) => {
  const vueGuard = createReentryGuard()
  const rejectionGuard = createReentryGuard()

  // Vue 错误处理器——只记录，不触发任何 reactive 副作用
  nuxtApp.vueApp.config.errorHandler = (error, instance, info) => {
    vueGuard(() => {
      console.error('[Vue Error]', error)

      if (import.meta.dev) {
        console.error('Error details:', {
          component: instance?.$options?.name || instance?.$?.type?.name || 'Unknown',
          info,
          error,
        })
      } else {
        console.error('Error context:', {
          component: instance?.$options?.name || instance?.$?.type?.name || 'Unknown',
          errorInfo: info,
          message: error instanceof Error ? error.message : String(error),
        })
        // 未来接入 Sentry 等错误追踪服务时放在这里（调用必须同步/纯副作用于外部服务）
      }
    }, 'Vue errorHandler')
  }

  // Nuxt 的 vue:error hook 和 vueApp.config.errorHandler 会被同一个错误触发，
  // config.errorHandler 已经记录了全部信息，这里不再重复——尤其不能调用 toast.add
  // 之类会进入 Vue 渲染流程的 API，否则就是重现 2026-04-22 的事故。

  // 未处理的 Promise rejection——只记录，不 toast
  if (import.meta.client) {
    window.addEventListener('unhandledrejection', (event) => {
      rejectionGuard(() => {
        console.error('[Unhandled Promise Rejection]', event.reason)
      }, 'unhandledrejection')
      // 不 preventDefault：让浏览器 devtools 照常标红，dev 可见性有保障
    })
  }
})
