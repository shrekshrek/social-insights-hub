import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  // 爬虫任务管理模块
  // 提供爬虫任务的创建、管理、监控功能
  imports: {
    dirs: ['composables/**', 'stores/**', 'types/**', 'utils/**'],
    // 确保 Vue 和 Nuxt 核心函数在 layer 中可用
    autoImport: true
  },
  // 组件自动导入（仅在本layer内可用）
  components: [
    { path: './components', pathPrefix: false }
  ]
})