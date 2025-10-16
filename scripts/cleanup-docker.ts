import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { Select, Confirm } from 'enquirer'

const envPath = path.resolve(process.cwd(), '.env')
let projectName = '未知'
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, 'utf-8')
  const match = envContent.match(/^PROJECT_NAME=(.*)$/m)
  if (match) {
    projectName = match[1].trim() || projectName
  }
}

console.log('🧹 Docker 资源清理工具')
console.log('================================')
console.log('')
console.log('此工具可以帮助清理不用的 Docker 资源，释放磁盘空间。')
console.log('')
console.log(`当前项目: ${projectName}`)
console.log('')

const menu = new Select({
  name: 'cleanupOption',
  message: '请选择清理选项',
  choices: [
    { name: 'list', message: '1) 列出所有项目的容器和数据卷' },
    { name: 'down', message: '2) 停止并删除当前项目的容器（保留数据）' },
    { name: 'downVolumes', message: '3) 停止并删除当前项目的容器和数据卷（⚠️ 会删除数据库数据）' },
    { name: 'prune', message: '4) 清理所有未使用的 Docker 资源' },
    { name: 'exit', message: '5) 退出' }
  ]
})

const runCommand = (command: string) => {
  execSync(command, { stdio: 'inherit' })
}

void (async () => {
  const choice = await menu.run()

  switch (choice) {
    case 'list':
      console.log('\n📦 Docker 容器列表:')
      runCommand('docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')
      console.log('\n💾 Docker 数据卷列表:')
      runCommand('docker volume ls')
      break
    case 'down':
      if (!projectName || projectName === '未知') {
        console.error('❌ 错误: 无法读取 PROJECT_NAME，请确保 .env 文件存在并已配置')
        process.exit(1)
      }
      console.log(`\n🛑 停止并删除项目 '${projectName}' 的容器...`)
      runCommand('docker-compose down')
      console.log('✅ 完成！数据卷已保留。')
      break
    case 'downVolumes':
      if (!projectName || projectName === '未知') {
        console.error('❌ 错误: 无法读取 PROJECT_NAME，请确保 .env 文件存在并已配置')
        process.exit(1)
      }
      console.log(`\n⚠️  警告: 这将删除项目 '${projectName}' 的所有数据！`)
      if (await new Confirm({ message: '确定要继续吗? (yes/no)' }).run()) {
        console.log(`\n🛑 停止并删除项目 '${projectName}' 的容器和数据卷...`)
        runCommand('docker-compose down -v')
        console.log('✅ 完成！所有容器和数据卷已删除。')
      } else {
        console.log('❌ 已取消操作')
      }
      break
    case 'prune':
      console.log('\n🧹 清理所有未使用的 Docker 资源...')
      console.log('这将删除:')
      console.log('  - 所有停止的容器')
      console.log('  - 所有未使用的网络')
      console.log('  - 所有悬空的镜像')
      console.log('  - 所有未使用的构建缓存')
      if (await new Confirm({ message: '确定要继续吗? (yes/no)' }).run()) {
        runCommand('docker system prune -a --volumes')
        console.log('✅ 清理完成！')
      } else {
        console.log('❌ 已取消操作')
      }
      break
    default:
      console.log('退出')
      process.exit(0)
  }
})()
