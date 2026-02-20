/**
 * 项目切片洞察组件
 * 对应 PROJECT_SLICE_PIPELINE_FINAL.md Step 3 分层指标计算
 */

// Landscape Layer (大盘层)
export { default as SOVRankingChart } from './SOVRankingChart.vue'
export { default as GroupShareTable } from './GroupShareTable.vue'
export { default as PlatformDNAChart } from './PlatformDNAChart.vue'
export { default as IndustryQuadrantChart } from './IndustryQuadrantChart.vue'

// Topic Layer (话题层)
export { default as TopicRadarChart } from './TopicRadarChart.vue'
export { default as TopicDrilldownPanel } from './TopicDrilldownPanel.vue'

// Focus Layer (聚焦层)
export { default as SWOTMatrixChart } from './SWOTMatrixChart.vue'
export { default as ProductLineHealthTable } from './ProductLineHealthTable.vue'
export { default as PlatformScissorsChart } from './PlatformScissorsChart.vue'
export { default as GapAnalysisChart } from './GapAnalysisChart.vue'

