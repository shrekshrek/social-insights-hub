// https://nuxt.com/docs/api/configuration/nuxt-config
import { defineNuxtConfig } from 'nuxt/config'
import { fileURLToPath } from 'node:url'

const resolve = (path: string) => fileURLToPath(new URL(path, import.meta.url))

// 应用显示名称：优先使用 APP_NAME / NUXT_PUBLIC_APP_NAME，其次 PROJECT_NAME
const appName =
  process.env.NUXT_PUBLIC_APP_NAME ||
  process.env.APP_NAME ||
  process.env.PROJECT_NAME ||
  '全栈脚手架'

export default defineNuxtConfig({
  // 启用 Nuxt 4 兼容模式
  future: {
    compatibilityVersion: 4,
  },

  app: {
    head: {
      title: appName,
      // Nuxt 配置需可序列化，titleTemplate 使用字符串形式
      // 页面级 useHead 可通过 titleTemplate: null 禁用全局模板
      titleTemplate: `%s - ${appName}`
    }
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
    '~': resolve('./'),
    '@': resolve('./'),
    '~/': resolve('./'),
    '@/': resolve('./'),
    '~/app': resolve('./app'),
    '@/app': resolve('./app'),
    '~/layers': resolve('./layers'),
    '@/layers': resolve('./layers'),
    '~/config': resolve('./config'),
    '@config': resolve('./config')
  },

  // 运行时配置
  runtimeConfig: {
    // 私有配置（仅服务端可用）
    // 可以通过环境变量 NUXT_API_SECRET 覆盖
    apiSecret: '',

    // 公共配置（客户端和服务端都可用）
    public: {
      appName,
      // API基础URL - 客户端使用相对路径通过代理，服务端可覆盖为完整URL
      // 开发环境：使用相对路径 /api/v1（通过 nitro devProxy）
      // 生产环境：可通过 NUXT_PUBLIC_API_BASE 覆盖
      apiBase: '/api/v1'
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
    './layers/social-media',
  ],
  components: [
    // 只注册根目录的全局组件和ui-kit组件为全局
    { path: './app/components', pathPrefix: false },
    { path: './layers/ui-kit/components', pathPrefix: false },
    // 业务layer组件都在各自layer内部使用
  ],
  modules: [
    // Nuxt UI v4 配置：禁用字体功能以避免网络连接问题
    // colorMode 由我们显式安装 @nuxtjs/color-mode 来配置
    ['@nuxt/ui', { fonts: false, colorMode: false }],
    // Color Mode 配置（Nuxt UI v4 推荐使用 @nuxtjs/color-mode）
    ['@nuxtjs/color-mode', {
      preference: 'light',
      fallback: 'light',
      classSuffix: '',
      storageKey: 'nuxt-color-mode'
    }],
    '@nuxt/eslint',
    // '@nuxt/image',
    '@nuxt/icon',
    '@pinia/nuxt',
    'nuxt-auth-utils'  // 使用新的认证模块
  ],
})
