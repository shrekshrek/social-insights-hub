#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process'
import process from 'node:process'

const composeCandidates: string[][] = [
  ['docker', 'compose'],
  ['docker-compose'],
]

const resolveComposeCommand = (): string[] => {
  for (const candidate of composeCandidates) {
    const result = spawnSync(candidate[0], [...candidate.slice(1), 'version'], {
      stdio: 'ignore',
    })

    if (result.status === 0) {
      return candidate
    }
  }

  console.error('❌ 未检测到 Docker Compose，请先安装或升级 Docker。')
  process.exit(1)
}

const composeCommand = resolveComposeCommand()

const runComposeSync = (args: string[]) =>
  spawnSync(composeCommand[0], [...composeCommand.slice(1), ...args], {
    stdio: 'pipe',
  })

const ensureBackendContainerRunning = () => {
  const result = runComposeSync(['ps', '-q', 'backend'])

  if (result.status !== 0 || !result.stdout.toString().trim()) {
    console.error('❌ backend 服务未运行，请先执行 `pnpm dev` 或 `docker compose up backend`。')
    process.exit(1)
  }
}

const startCeleryWorker = (extraArgs: string[]) => {
  console.log('🚀 在 backend 服务内启动 Celery Worker...')
  const commandArgs = [
    ...composeCommand.slice(1),
    'exec',
    'backend',
    'uv',
    'run',
    'celery',
    '-A',
    'src.celery_app.celery_app',
    'worker',
    '--loglevel=info',
    ...extraArgs,
  ]

  const child = spawn(composeCommand[0], commandArgs, {
    stdio: 'inherit',
  })

  child.on('exit', (code, signal) => {
    if (signal) {
      console.log(`⚠️  Celery Worker 被信号 ${signal} 终止。`)
      process.exit(1)
    }

    process.exit(code ?? 0)
  })
}

const main = () => {
  ensureBackendContainerRunning()
  startCeleryWorker(process.argv.slice(2))
}

main()
