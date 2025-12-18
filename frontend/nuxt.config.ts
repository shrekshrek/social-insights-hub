// https://nuxt.com/docs/api/configuration/nuxt-config
import { defineNuxtConfig } from 'nuxt/config'
import { fileURLToPath } from 'node:url'
import fs from 'node:fs'

const resolve = (path: string) => fileURLToPath(new URL(path, import.meta.url))

function stripEnvValueQuotes(value: string): string {
  const v = value.trim()
  if (
    (v.startsWith('"') && v.endsWith('"')) ||
    (v.startsWith("'") && v.endsWith("'"))
  ) {
    return v.slice(1, -1)
  }
  return v
}

function readEnvFileSafe(envFilePath: string): Record<string, string> {
  try {
    if (!fs.existsSync(envFilePath)) {
      return {}
    }
    const content = fs.readFileSync(envFilePath, 'utf-8')
    const result: Record<string, string> = {}
    for (const rawLine of content.split('\n')) {
      const line = rawLine.trim()
      if (!line || line.startsWith('#')) continue
      const eq = line.indexOf('=')
      if (eq <= 0) continue
      const key = line.slice(0, eq).trim()
      const value = stripEnvValueQuotes(line.slice(eq + 1))
      if (key) result[key] = value
    }
    return result
  } catch {
    return {}
  }
}

// 应用显示名称：优先使用 APP_NAME，其次 PROJECT_NAME
// 说明：本地前端 dev（nuxt dev）默认只会加载 frontend/.env，因此这里额外读取根目录 ../.env 作为 fallback，
// 以便 dev/prod 行为更一致（只读取展示名相关字段，不引入敏感配置到前端进程）。
const rootEnv = readEnvFileSafe(resolve('../.env'))
const appName =
  process.env.APP_NAME ||
  process.env.PROJECT_NAME ||
  rootEnv.APP_NAME ||
  rootEnv.PROJECT_NAME ||
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
