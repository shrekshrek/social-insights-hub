<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        数据图表
      </h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">
        数据可视化展示
      </p>
    </div>

    <!-- 图表展示 -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 柱状图 -->
      <UCard>
        <template #header>
          <h3 class="text-lg font-semibold">年度销售额</h3>
        </template>

        <ClientOnly>
          <div ref="barChartRef" class="h-80"/>
          <template #fallback>
            <div class="h-80 flex items-center justify-center text-gray-500">
              <UIcon name="i-heroicons-chart-bar" class="text-4xl animate-pulse" />
              <p class="ml-2">图表加载中...</p>
            </div>
          </template>
        </ClientOnly>
      </UCard>

      <!-- 饼图 -->
      <UCard>
        <template #header>
          <h3 class="text-lg font-semibold">产品类别分布</h3>
        </template>

        <ClientOnly>
          <div ref="pieChartRef" class="h-80"/>
          <template #fallback>
            <div class="h-80 flex items-center justify-center text-gray-500">
              <UIcon name="i-heroicons-chart-pie" class="text-4xl animate-pulse" />
              <p class="ml-2">图表加载中...</p>
            </div>
          </template>
        </ClientOnly>
      </UCard>
    </div>

    <!-- 技术说明 -->
    <div class="text-sm text-gray-500 dark:text-gray-400 space-y-1">
      <p>📊 图表基于 ECharts 实现</p>
      <p>🚀 支持响应式设计和暗色模式</p>
      <p>💡 使用 useCharts 组合函数，确保最佳实践</p>
    </div>
  </div>
</template>

<script setup lang="ts">
// 页面元数据
useHead({
  title: '数据图表',
  meta: [
    { name: 'description', content: '数据可视化展示' }
  ]
})

// 图表容器引用
const barChartRef = ref()
const pieChartRef = ref()

// 初始化柱状图
const barChart = useCharts({
  autoResize: true,
  resizeDelay: 100
})

// 初始化饼图
const pieChart = useCharts({
  autoResize: true,
  resizeDelay: 100
})

// 在客户端挂载后初始化图表
onMounted(() => {
  // 初始化柱状图
  if (barChartRef.value) {
    barChart.initChart(barChartRef.value)
    barChart.setOption({
      title: {
        text: '年度销售额',
        left: 'center'
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: ['2019', '2020', '2021', '2022', '2023', '2024']
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name: '销售额',
          type: 'bar',
          data: [120, 200, 150, 80, 70, 110],
          itemStyle: {
            color: '#3B82F6'
          }
        }
      ]
    })
  }

  // 初始化饼图
  if (pieChartRef.value) {
    pieChart.initChart(pieChartRef.value)
    pieChart.setOption({
      title: {
        text: '产品类别分布',
        left: 'center'
      },
      tooltip: {
        trigger: 'item',
        formatter: '{a} <br/>{b} : {c} ({d}%)'
      },
      legend: {
        orient: 'vertical',
        left: 'left',
        data: ['电子产品', '服装', '食品', '图书', '家具']
      },
      series: [
        {
          name: '产品类别',
          type: 'pie',
          radius: '55%',
          center: ['50%', '60%'],
          data: [
            { value: 335, name: '电子产品' },
            { value: 310, name: '服装' },
            { value: 234, name: '食品' },
            { value: 135, name: '图书' },
            { value: 158, name: '家具' }
          ],
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }
      ]
    })
  }
})
</script>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
}
</style> 