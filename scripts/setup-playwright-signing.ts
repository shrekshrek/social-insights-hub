#!/usr/bin/env node
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const rootDir = path.resolve(__dirname, '..')
const backendDir = path.join(rootDir, 'backend')

const defaultUserDataDir =
  process.env.SIGNING_PLAYWRIGHT_USER_DATA_DIR ?? path.join(backendDir, '.playwright', 'xhs')

const run = (command: string, args: string[], options: { cwd?: string } = {}) => {
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    cwd: options.cwd,
  })

  if (result.status !== 0) {
    const code = result.status ?? 1
    console.error(`❌ 命令 \`${command} ${args.join(' ')}\` 执行失败，退出码 ${code}`)
    process.exit(code)
  }
}

const main = () => {
  console.log(`[info] Node.js 版本: ${process.version}`)

  console.log('[info] 安装 Playwright 浏览器依赖 (chromium)...')
  run('uv', ['run', 'playwright', 'install', 'chromium'], { cwd: backendDir })

  console.log(`[info] 创建用户数据目录: ${defaultUserDataDir}`)
  fs.mkdirSync(defaultUserDataDir, { recursive: true })

  console.log('[info] Playwright 签名环境准备完成')
}

main()
