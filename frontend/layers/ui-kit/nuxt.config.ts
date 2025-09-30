import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  // UI组件库配置
  imports: {
    // 确保 Vue 和 Nuxt 核心函数在 layer 中可用
    autoImport: true
  },
  // 组件虽然全局注册，但在开发ui-kit时也需要内部自动导入
  components: [
    { path: './components', pathPrefix: false }
  ]
}) 