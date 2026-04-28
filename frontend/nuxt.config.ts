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

// 统一环境变量来源：nuxt dev 默认只读 frontend/.env，这里把根目录 ../.env 作为
// 唯一 source of truth 注入 process.env（已存在的变量不覆盖，保留 shell/CI 显式设置）。
// 注入后 Nuxt 的 runtimeConfig 自动映射机制即可读到 NUXT_* 变量，无需 frontend/.env。
const rootEnv = readEnvFileSafe(resolve('../.env'))
for (const [key, value] of Object.entries(rootEnv)) {
  if (process.env[key] === undefined) {
    process.env[key] = value
  }
}

const appName =
  process.env.APP_NAME ||
  process.env.PROJECT_NAME ||
  ''

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
    apiSecret: '',
    // 服务端内网 API 地址（SSR 请求后端时使用），通过 NUXT_API_BASE_INTERNAL 覆盖
    // 生产环境示例：NUXT_API_BASE_INTERNAL=http://prod-backend:8000/api/v1
    apiBaseInternal: '',

    // nuxt-auth-utils session cookie 配置
    // 默认 secure: true（HTTPS）；HTTP 生产环境通过 NUXT_SESSION_COOKIE_SECURE=false 覆盖
    session: {
      cookie: {
        secure: true as boolean,
      }
    },

    // 公共配置（客户端和服务端都可用）
    public: {
      appName,
      // API基础URL - 客户端使用相对路径通过代理，服务端可覆盖为完整URL
      // 开发环境：使用相对路径 /api/v1（通过 nitro devProxy）
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
    './layers/jobs',
    './layers/social-media',
    './layers/news-media',
    './layers/strategies',
    './layers/knowledge-base',
    './layers/research-agent',
    './layers/audit',
  ],
  components: [
    // 只注册根目录的全局组件和ui-kit组件为全局
    { path: './app/components', pathPrefix: false },
    { path: './layers/ui-kit/components', pathPrefix: false },
    // 业务layer组件都在各自layer内部使用
  ],
  modules: [
    // Nuxt UI v4 配置：禁用字体功能，使用内置 colorMode（不再单独引入 @nuxtjs/color-mode）
    ['@nuxt/ui', {
      fonts: false,
      colorMode: {
        preference: 'light',
        fallback: 'light',
        classSuffix: '',
      }
    }],
    '@nuxt/eslint',
    // '@nuxt/image',
    '@nuxt/icon',
    '@pinia/nuxt',
    'nuxt-auth-utils'  // 使用新的认证模块
  ],
})
