<script setup lang="ts">
import { watch, onMounted, nextTick } from 'vue'
import type { EChartsOption, SeriesOption } from 'echarts'
import type { IpaAnalysis, IpaPoint } from '../types'

const props = defineProps<{
  data?: IpaAnalysis
}>()

const emit = defineEmits<{
  (e: 'click-point', title: string, postIds: number[]): void
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

// 象限定义（用于图例展示，实际数据在 props.data 中）
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const quadrants = [
  { name: '优势区 (保持)', color: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' }, // Q1: High Imp, High Perf
  { name: '改进区 (重点)', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)' }, // Q2: High Imp, Low Perf
  { name: '维持区 (次要)', color: '#6b7280', bg: 'rgba(107, 114, 128, 0.1)' }, // Q3: Low Imp, Low Perf
  { name: '机会区 (挖掘)', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.1)' }  // Q4: Low Imp, High Perf
]

const getOption = (): EChartsOption => {
  if (!props.data?.quadrants) return {}

  const { quadrants: qData } = props.data
  
  // --- 预处理：解决重叠点 (Collision Resolution) ---
  // 1. 收集所有点
  const allPoints: (IpaPoint & { seriesIndex: number })[] = []
  const seriesData = [
    { name: '优势区', data: qData.strength || [], color: '#10b981' },
    { name: '改进区', data: qData.improvement || [], color: '#ef4444' },
    { name: '维持区', data: qData.maintain || [], color: '#9ca3af' },
    { name: '机会区', data: qData.opportunity || [], color: '#3b82f6' }
  ]
  
  seriesData.forEach((s, idx) => {
    s.data.forEach(p => allPoints.push({ ...p, seriesIndex: idx }))
  })

  // 2. 按坐标分组
  const groups = new Map<string, typeof allPoints>()
  allPoints.forEach(p => {
    const key = `${p.x},${p.y}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(p)
  })

  // 3. 计算偏移后的坐标 (向日葵螺旋布局)
  // 缩放因子：根据坐标轴大致范围调整，使偏移在视觉上接近正圆
  // 假设 X轴范围 ~20, Y轴范围 ~2
  const scaleX = 2.2 // X轴偏移系数
  const scaleY = 0.7 // Y轴偏移系数
  const baseSpacing = 0.2 // 基础间距

  const processedPoints = new Map<string, { x: number, y: number }>() // name -> {x, y}

  groups.forEach((points) => {
    if (points.length <= 1 && points[0]) {
      // 只有一个点，不偏移
      processedPoints.set(points[0].name, { x: points[0].x, y: points[0].y })
      return
    }

    // 多个点，螺旋排列
    // 第一个点保持中心 (n=0)
    points.forEach((p, i) => {
      if (i === 0) {
        processedPoints.set(p.name, { x: p.x, y: p.y })
      } else {
        // 向日葵螺旋公式
        // const angle = i * 137.508 * (Math.PI / 180) // 黄金角弧度
        // const r = baseSpacing * Math.sqrt(i)
        
        // const offsetX = r * Math.cos(angle) * scaleX
        // const offsetY = r * Math.sin(angle) * scaleY

        const offsetX = -i * baseSpacing * scaleX
        const offsetY = i * baseSpacing * scaleY
        
        processedPoints.set(p.name, { 
          x: p.x + offsetX, 
          y: p.y + offsetY 
        })
      }
    })
  })
  
  return {
    animation: false,  // 关闭动画，避免 resize 时的渲染问题
    tooltip: {
      trigger: 'item',
      confine: true,  // 限制在图表区域内
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        // 安全检查：确保 params 和 data 存在
        if (!params || !params.data) return ''
        
        const item = params.data
        if (!item || !item.name) return ''
        
        // 安全获取数值
        const displayX = item.x ?? 0
        const displayY = typeof item.y === 'number' ? item.y.toFixed(2) : '0.00'
        const heat = typeof item.heat === 'number' ? item.heat.toFixed(1) : '0.0'
        
        return `
          <div class="font-medium mb-1">${item.name}</div>
          <div class="text-xs text-gray-500">
            关注度: ${displayX} <br/>
            情感: ${displayY} <br/>
            影响力: ${heat}
          </div>
        `
      }
    },
    grid: {
      top: 10,
      right: 10,
      bottom: 40,
      left: 50,  // 给 Y 轴标签留足空间
      containLabel: false  // 手动控制边距
    },
    xAxis: {
      type: 'value',
      name: '关注度 (Mentions)', // 更新 X 轴标签
      nameLocation: 'middle',
      nameGap: 25,
      splitLine: {
        lineStyle: {
          type: 'dashed'
        }
      },
      axisLabel: {
        fontSize: 10
      }
    },
    yAxis: {
      type: 'value',
      name: '情感 (满意度)',
      nameLocation: 'middle',
      nameGap: 35,
      min: -1,
      max: 1.5,
      splitLine: {
        lineStyle: {
          type: 'dashed'
        }
      },
      axisLabel: {
        fontSize: 10
      }
    },
    series: [
      // 数据 series（已用颜色区分四象限，无需额外辅助线）
      ...seriesData.map((s): SeriesOption => ({
        name: s.name,
        type: 'scatter',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        symbolSize: (data: any) => {
          // data 是 [x, y, z(size), name, post_ids, originalX, originalY]
          // 这里 data[2] 是后端计算好的 z 值 (log smoothed heat)
          // 范围通常在 1~10 之间
          
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          let zVal = Array.isArray(data) ? data[2] : ((data as any)?.z || 0)
          
          if (isNaN(zVal)) zVal = 1

          // 直接作为基础大小，适当放大
          // 后端 zVal ≈ 2 (heat=10) -> size ≈ 6
          // 后端 zVal ≈ 9 (heat=10000) -> size ≈ 27
          // 加上基础大小 4px
          const size = 4 + (zVal * 3)
          
          return Math.min(Math.max(size, 8), 40) // 限制在 8px - 40px 之间
        },
        itemStyle: {
          color: s.color,
          shadowBlur: 5,
          shadowColor: 'rgba(0,0,0,0.2)',
          opacity: 0.8
        },
        // 转换为 ECharts 标准格式: [x, y, score, name, post_ids, originalX, originalY]
        // 这样 ECharts 可以正确处理，且 symbolSize 回调中的 data 会是这个数组
        data: s.data.filter(item => item && typeof item.x === 'number' && typeof item.y === 'number').map(item => {
          // 获取预计算的布局坐标
          const pos = processedPoints.get(item.name) || { x: item.x, y: item.y }
          
          return {
            // 使用布局后的坐标进行绘图
            value: [
              pos.x, 
              pos.y, 
              item.z || 1, // 索引 2: 使用后端计算的 z 值 (Bubble Size)
              item.name, 
              item.post_ids,
              item.x, // 索引 5: 原始 X
              item.y  // 索引 6: 原始 Y
            ],
            // 保留原始属性以便 tooltip 使用
            ...item
          }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        }) as any[], // 类型断言绕过 ECharts 严格类型检查
        label: {
          show: true,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter: (params: any) => {
            const name = params?.data?.name || ''
            if (!name) return ''
            return name.length > 5 ? name.slice(0, 5) + '...' : name
          },
          position: 'right',
          fontSize: 10,
          color: '#374151'
        },
        labelLayout: {
          hideOverlap: true, // 隐藏重叠标签
          moveOverlap: 'shiftY' // 尝试纵向移动避让
        },
        emphasis: {
          focus: 'self',
          label: {
            show: true,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter: (params: any) => params?.data?.name || '' // 高亮时显示全名
          }
        }
      }))
    ]
  }
}

// 点击处理
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const handleClick = (params: any) => {
  if (params.componentType === 'series') {
    const item = params.data as IpaPoint
    if (item && item.post_ids?.length) {
      emit('click-point', `${item.name} 相关内容`, item.post_ids)
    }
  }
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && props.data) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      instance?.on('click', handleClick)
    }
    const option = getOption()
    if (option && Object.keys(option).length > 0) {
      setOption(option)
    }
  }
}

watch(() => props.data, updateChart, { deep: true })

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">产品力诊断 (IPA)</h3>
      <div class="flex gap-2 text-xs">
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-emerald-500" />
          <span class="text-gray-500">优势区</span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-red-500" />
          <span class="text-gray-500">改进区</span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-blue-500" />
          <span class="text-gray-500">机会区</span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-gray-400" />
          <span class="text-gray-500">维持区</span>
        </div>
      </div>
    </div>
    <div ref="chartRef" class="w-full h-96" />
  </div>
</template>

