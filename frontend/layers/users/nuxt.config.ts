import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  // 自动导入配置
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