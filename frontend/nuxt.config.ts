// https://nuxt.com/docs/api/configuration/nuxt-config
import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  // 启用 Nuxt 4 兼容模式
  future: {
    compatibilityVersion: 4,
  },

  css: ['./app/assets/css/main.css'],
  compatibilityDate: '2025-05-15',
  devtools: { enabled: true },

  // Vite 配置优化
  vite: {
    optimizeDeps: {
      exclude: ['zod']
    }
  },

  // 别名配置，解决Layer中的import路径问题
  alias: {
    "~/config": "./config",
    "@config": "./config"
  },

  // 运行时配置
  runtimeConfig: {
    // 私有配置（仅服务端可用）
    // 可以通过环境变量 NUXT_API_SECRET 覆盖
    apiSecret: '',
    
    // 公共配置（客户端和服务端都可用）
    public: {
      // API基础URL - 可以通过 NUXT_PUBLIC_API_BASE 覆盖
      apiBase: 'http://localhost:8000/api/v1'
    }
  },
  
  // 开发服务器配置
  nitro: {
    devProxy: {
      '/api/v1': 'http://localhost:8000/api/v1'
    }
  },
  extends: [
    './layers/ui-kit',
    './layers/auth',
    './layers/users',
    './layers/rbac',
  ],
  components: [
    // 只注册根目录的全局组件和ui-kit组件为全局
    { path: './app/components', pathPrefix: false },
    { path: './layers/ui-kit/components', pathPrefix: false },
    // 业务layer组件都在各自layer内部使用
  ],
  modules: [
    ['@nuxt/ui', {
      // 禁用字体功能以避免网络连接问题
      fonts: false,
      colorMode: {
        preference: 'light', // 默认浅色模式
        fallback: 'light',   // 当检测不到系统偏好时使用浅色
        classSuffix: '',     // 使用 'dark' 类而不是 'dark-mode'
        storageKey: 'nuxt-color-mode'
      }
    }],
    '@nuxt/eslint',
    // '@nuxt/image',
    '@nuxt/icon',
    '@pinia/nuxt',
    'nuxt-auth-utils'  // 使用新的认证模块
  ]
})
