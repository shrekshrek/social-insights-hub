export default defineNuxtRouteMiddleware((_to, _from) => {
  // 检查是否有未处理的错误
  const error = useError()
  
  if (error.value) {
    // 根据错误状态码处理不同的错误
    switch (error.value.statusCode) {
      case 401:
        // 清除错误状态，跳转到401页面
        clearError()
        return navigateTo('/401')
      
      case 403:
        // 清除错误状态，跳转到403页面
        clearError()
        return navigateTo('/403')
      
      default:
        // 其他错误交给默认的error.vue处理
        break
    }
  }
}) 