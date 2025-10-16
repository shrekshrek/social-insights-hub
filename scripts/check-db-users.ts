#!/usr/bin/env node
import { spawnSync } from 'node:child_process'
import process from 'node:process'

const composeCandidates: string[][] = [
  ['docker', 'compose'],
  ['docker-compose'],
]

const resolveCompose = (): string[] => {
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

const composeCommand = resolveCompose()

const runCompose = (args: string[], stdio: 'pipe' | 'inherit' = 'pipe') =>
  spawnSync(composeCommand[0], [...composeCommand.slice(1), ...args], {
    stdio,
  })

const ensureServiceRunning = (service: string) => {
  const result = runCompose(['ps', '-q', service])

  if (result.status !== 0 || !result.stdout?.toString().trim()) {
    console.error(`❌ 服务 \`${service}\` 未运行，请先执行 \`docker compose up -d ${service}\`。`)
    process.exit(1)
  }
}

const main = () => {
  ensureServiceRunning('postgres_db')

  const dbUser = process.env.POSTGRES_USER ?? 'postgres'
  const dbName = process.env.POSTGRES_DB ?? 'postgres'

  console.log('🔍 查询用户列表...')

  const result = runCompose(
    [
      'exec',
      '-T',
      'postgres_db',
      'psql',
      '-U',
      dbUser,
      '-d',
      dbName,
      '-P',
      'pager=off',
      '-c',
      "SELECT id, username, email FROM users ORDER BY id;",
    ],
    'inherit'
  )

  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

main()
