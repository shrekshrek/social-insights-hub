/**
 * ECharts 图表组合函数
 * 
 * 提供统一的图表初始化、配置和管理功能
 * 支持响应式、主题切换和自动清理
 */
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'

interface UseChartsOptions {
  /**
   * 图表主题
   * @default 'default'
   */
  theme?: string | object
  
  /**
   * 是否自动响应窗口大小变化
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
    theme = 'default',
    autoResize = true,
    resizeDelay = 100,
    initOptions = {}
  } = options

  // 图表实例
  const chartInstance = ref<ECharts | null>(null)
  
  // 图表容器引用
  const chartRef = ref<HTMLElement>()
  
  // 加载状态
  const loading = ref(false)
  
  // 错误状态
  const error = ref<string | null>(null)

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

      // 如果已存在实例，先销毁
      if (chartInstance.value) {
        chartInstance.value.dispose()
      }

      // 创建新实例
      chartInstance.value = echarts.init(element, theme, initOptions)
      
      // 设置自动响应
      if (autoResize) {
        setupAutoResize()
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
    if (chartInstance.value) {
      chartInstance.value.dispose()
      chartInstance.value = null
    }
    
    // 清理事件监听
    if (autoResize && resizeHandler) {
      window.removeEventListener('resize', resizeHandler)
      resizeHandler = null
    }
  }

  // 响应式处理
  let resizeHandler: (() => void) | null = null
  
  const setupAutoResize = () => {
    if (resizeHandler) {
      window.removeEventListener('resize', resizeHandler)
    }
    
    // 防抖处理
    let resizeTimer: NodeJS.Timeout | null = null
    resizeHandler = () => {
      if (resizeTimer) {
        clearTimeout(resizeTimer)
      }
      resizeTimer = setTimeout(() => {
        resize()
      }, resizeDelay)
    }
    
    window.addEventListener('resize', resizeHandler)
  }

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
    
    // 高级功能
    getInstance,
    getDataURL,
  }
}

/**
 * 预设的图表配置
 */
export const chartPresets = {
  /**
   * 柱状图预设
   */
  bar: (data: { categories: string[]; series: { name: string; data: number[] }[] }): EChartsOption => ({
    title: {
      text: '柱状图',
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: data.series.map(s => s.name),
      top: '10%'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: data.categories
    },
    yAxis: {
      type: 'value'
    },
    series: data.series.map(s => ({
      name: s.name,
      type: 'bar',
      data: s.data
    }))
  }),

  /**
   * 饼图预设
   */
  pie: (data: { name: string; value: number }[], title: string = '饼图'): EChartsOption => ({
    title: {
      text: title,
      left: 'center'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b} : {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      data: data.map(d => d.name)
    },
    series: [
      {
        name: title,
        type: 'pie',
        radius: '55%',
        center: ['50%', '60%'],
        data,
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        }
      }
    ]
  }),

  /**
   * 折线图预设
   */
  line: (data: { categories: string[]; series: { name: string; data: number[] }[] }): EChartsOption => ({
    title: {
      text: '折线图',
      left: 'center'
    },
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: data.series.map(s => s.name),
      top: '10%'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: data.categories
    },
    yAxis: {
      type: 'value'
    },
    series: data.series.map(s => ({
      name: s.name,
      type: 'line',
      data: s.data
    }))
  })
} 