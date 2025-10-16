// 检查项目根目录下的 .env 文件是否存在
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const envPath = path.resolve(process.cwd(), '.env')

if (!fs.existsSync(envPath)) {
  console.error('❌ 错误: .env 文件不存在')
  console.error('请先复制 .env.example 到 .env:')
  console.error('  cp .env.example .env')
  process.exit(1)
}

const envContent = fs.readFileSync(envPath, 'utf-8')
const projectNameMatch = envContent.match(/^PROJECT_NAME=(.*)$/m)

if (!projectNameMatch || !projectNameMatch[1]?.trim()) {
  console.error('❌ 错误: PROJECT_NAME 未设置')
  console.error('\n请在 .env 文件中设置 PROJECT_NAME，例如:')
  console.error('  PROJECT_NAME=myapp_crm')
  console.error('\n这对于多项目开发非常重要，可以避免不同项目的 Docker 资源冲突。')
  process.exit(1)
}

const projectName = projectNameMatch[1].trim()
console.log(`✅ 环境检查通过 - PROJECT_NAME: ${projectName}`)
