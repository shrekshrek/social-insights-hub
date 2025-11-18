import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  // 自动导入配置 - 支持子模块结构
  imports: {
    dirs: [
      'projects/composables/**',
      'tasks/composables/**',
      'analysis/composables/**',
      'projects/types/**',
      'tasks/types/**',
      'analysis/types/**',
      'stores/**',
      'utils/**'
    ],
    autoImport: true
  },
  // 组件自动导入 - 支持所有子模块的组件
  components: [
    { path: './projects/components', pathPrefix: false },
    { path: './tasks/components', pathPrefix: false },
    { path: './analysis/components', pathPrefix: false }
  ]
})
