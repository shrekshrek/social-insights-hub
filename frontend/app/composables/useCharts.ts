/**
 * ECharts 图表组合函数
 * 
 * 提供统一的图表初始化、配置和管理功能
 * 
 * 功能特性：
 * - ✅ 自动响应窗口和容器大小变化 (ResizeObserver)
 * - ✅ 暗色模式自动切换
 * - ✅ 加载动画
 * - ✅ 自动清理（组件卸载时）
 * - ✅ 防抖处理
 * - ✅ 导出图片
 * 
 * 注意：使用 shallowRef 存储 ECharts 实例，避免 Vue 响应式系统干扰
 */
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'
import { shallowRef, markRaw } from 'vue'

interface UseChartsOptions {
  /**
   * 图表主题（'light' | 'dark' | 'auto'）
   * 'auto' 会根据系统/应用的暗色模式自动切换
   * @default 'auto'
   */
  theme?: 'light' | 'dark' | 'auto' | string | object
  
  /**
   * 是否自动响应容器大小变化
   * @default true
   */
  autoResize?: boolean
  
  /**
   * 防抖延迟（毫秒）
   * @default 100
   */
  resizeDelay?: number
  
  /**
   * 图表初始化配置
   */
  initOptions?: {
    devicePixelRatio?: number
    renderer?: 'canvas' | 'svg'
    width?: number | string
    height?: number | string
  }
}

export const useCharts = (options: UseChartsOptions = {}) => {
  const {
    theme = 'auto',
    autoResize = true,
    resizeDelay = 100,
    initOptions = {}
  } = options

  // 图表实例（使用 shallowRef 避免 Vue 响应式系统深度代理 ECharts 内部属性）
  const chartInstance = shallowRef<ECharts | null>(null)
  
  // 图表容器引用
  const chartRef = ref<HTMLElement>()
  
  // 当前容器元素
  let currentContainer: HTMLElement | null = null
  
  // 加载状态
  const loading = ref(false)
  
  // 错误状态
  const error = ref<string | null>(null)
  
  // 暗色模式检测
  const colorMode = useColorMode()
  
  // 保存用户设置的原始配置（用于主题切换时恢复）
  let savedOption: EChartsOption | null = null
  
  // 计算当前主题
  const currentTheme = computed(() => {
    if (theme === 'auto') {
      return colorMode.value === 'dark' ? 'dark' : undefined
    }
    return theme === 'light' ? undefined : theme
  })

  /**
   * 初始化图表
   */
  const initChart = (container?: HTMLElement) => {
    try {
      error.value = null
      
      const element = container || chartRef.value
      if (!element) {
        throw new Error('图表容器不存在')
      }
      
      currentContainer = element

      // 如果已存在实例，先销毁
      if (chartInstance.value) {
        chartInstance.value.dispose()
      }

      // 创建新实例（使用 markRaw 避免响应式代理）
      chartInstance.value = markRaw(echarts.init(
        element, 
        currentTheme.value as string | object | undefined, 
        initOptions
      ))
      
      // 设置自动响应
      if (autoResize) {
        setupAutoResize(element)
      }
      
      return chartInstance.value
    } catch (err) {
      error.value = err instanceof Error ? err.message : '图表初始化失败'
      console.error('ECharts 初始化错误:', err)
      return null
    }
  }

  /**
   * 设置图表配置
   */
  const setOption = (option: EChartsOption, opts?: {
    notMerge?: boolean
    replaceMerge?: string | string[]
    silent?: boolean
  }) => {
    try {
      if (!chartInstance.value) {
        throw new Error('图表实例未初始化')
      }
      
      loading.value = true
      error.value = null
      
      // 保存配置（用于主题切换时恢复）
      savedOption = option
      
      chartInstance.value.setOption(option, opts)
      
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : '设置图表配置失败'
      console.error('ECharts 配置错误:', err)
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 显示加载动画
   */
  const showLoading = (text: string = '加载中...', options?: object) => {
    if (chartInstance.value) {
      chartInstance.value.showLoading({
        text,
        color: '#3B82F6',
        textColor: '#374151',
        maskColor: 'rgba(255, 255, 255, 0.8)',
        zlevel: 0,
        ...options
      })
    }
  }

  /**
   * 隐藏加载动画
   */
  const hideLoading = () => {
    if (chartInstance.value) {
      chartInstance.value.hideLoading()
    }
  }

  /**
   * 手动触发图表重绘
   */
  const resize = () => {
    if (chartInstance.value) {
      chartInstance.value.resize()
    }
  }

  /**
   * 清空图表
   */
  const clear = () => {
    if (chartInstance.value) {
      chartInstance.value.clear()
    }
  }

  /**
   * 销毁图表实例
   */
  const dispose = () => {
    // 清理 ResizeObserver
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
    
    // 清理 window resize 监听
    if (resizeHandler) {
      window.removeEventListener('resize', resizeHandler)
      resizeHandler = null
    }
    
    // 销毁图表实例
    if (chartInstance.value) {
      chartInstance.value.dispose()
      chartInstance.value = null
    }
    
    currentContainer = null
  }

  // 响应式处理
  let resizeHandler: (() => void) | null = null
  let resizeObserver: ResizeObserver | null = null
  let resizeTimer: ReturnType<typeof setTimeout> | null = null
  
  // 防抖 resize
  const debouncedResize = () => {
    if (resizeTimer) {
      clearTimeout(resizeTimer)
    }
    resizeTimer = setTimeout(() => {
      resize()
    }, resizeDelay)
  }
  
  const setupAutoResize = (element: HTMLElement) => {
    // 清理旧的监听
    if (resizeHandler) {
      window.removeEventListener('resize', resizeHandler)
    }
    if (resizeObserver) {
      resizeObserver.disconnect()
    }
    
    // 使用 ResizeObserver 监听容器大小变化（更精确）
    resizeObserver = new ResizeObserver(debouncedResize)
    resizeObserver.observe(element)
    
    // 同时监听 window resize（作为后备）
    resizeHandler = debouncedResize
    window.addEventListener('resize', resizeHandler)
  }
  
  // 监听暗色模式变化，自动重新初始化图表
  // 使用 { flush: 'post' } 确保在 DOM 更新后执行
  watch(currentTheme, (newTheme, oldTheme) => {
    // 跳过初始化时的触发（oldTheme 为 undefined）
    if (oldTheme === undefined) return
    
    // 确保所有条件都满足
    if (!chartInstance.value || !currentContainer || !savedOption) return
    
    try {
      // 重新初始化（使用新主题，markRaw 避免响应式代理）
      chartInstance.value.dispose()
      chartInstance.value = markRaw(echarts.init(
        currentContainer, 
        newTheme as string | object | undefined, 
        initOptions
      ))
      
      // 恢复用户保存的原始配置
      chartInstance.value.setOption(savedOption)
      
      // 重新设置 resize 监听
      if (autoResize) {
        setupAutoResize(currentContainer)
      }
    } catch (err) {
      console.error('主题切换失败:', err)
    }
  }, { flush: 'post' })

  /**
   * 获取图表实例（用于高级操作）
   */
  const getInstance = () => chartInstance.value

  /**
   * 获取图表的 DataURL
   */
  const getDataURL = (opts?: {
    type?: 'svg' | 'png' | 'jpeg'
    pixelRatio?: number
    backgroundColor?: string
    excludeComponents?: string[]
  }) => {
    if (chartInstance.value) {
      return chartInstance.value.getDataURL(opts)
    }
    return null
  }
  
  /**
   * 绑定事件
   */
  const on = (eventName: string, handler: (...args: unknown[]) => void) => {
    if (chartInstance.value) {
      chartInstance.value.on(eventName, handler)
    }
  }
  
  /**
   * 解绑事件
   */
  const off = (eventName: string, handler?: (...args: unknown[]) => void) => {
    if (chartInstance.value) {
      chartInstance.value.off(eventName, handler)
    }
  }

  // 组件卸载时自动清理
  onUnmounted(() => {
    dispose()
  })

  return {
    // 响应式状态
    chartRef,
    loading: readonly(loading),
    error: readonly(error),
    
    // 核心方法
    initChart,
    setOption,
    resize,
    clear,
    dispose,
    
    // 加载状态
    showLoading,
    hideLoading,
    
    // 事件绑定
    on,
    off,
    
    // 高级功能
    getInstance,
    getDataURL,
  }
}