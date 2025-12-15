import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { execSync } from 'node:child_process'

const run = (command: string) => {
  console.log(`➤ ${command}`)
  execSync(command, { stdio: 'inherit' })
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const main = async () => {
  console.log('🚀 Starting production deployment...')
  console.log('==================================')

  const envProdPath = path.resolve('.env.production')
  const envProdExamplePath = path.resolve('.env.production.example')

  if (!fs.existsSync(envProdPath)) {
    console.error('❌ Error: .env.production not found in root directory!')

    if (fs.existsSync(envProdExamplePath)) {
      console.log('📋 Creating from example file...')
      fs.copyFileSync(envProdExamplePath, envProdPath)
      console.log('⚠️  IMPORTANT: Edit .env.production with your production values:')
      console.log('   - Generate SECRET_KEY: openssl rand -hex 32')
      console.log('   - Generate NUXT_SESSION_PASSWORD: openssl rand -base64 32')
      console.log('   - Update POSTGRES_PASSWORD with a strong password')
      console.log('   - Update BACKEND_CORS_ORIGINS with your domain')
    } else {
      console.log('💡 Please create production environment configuration first.')
      console.log('   Copy .env.production.example to .env.production and update values.')
    }
    process.exit(1)
  }

  const envProdContent = fs.readFileSync(envProdPath, 'utf-8')
  if (envProdContent.includes('CHANGE_THIS')) {
    console.error('⚠️  WARNING: Some configuration values have not been changed from defaults!')
    console.error('   Please update ALL values containing "CHANGE_THIS" in .env.production.')
    process.exit(1)
  }

  const passwordMatch = envProdContent.match(/^POSTGRES_PASSWORD=(.*)$/m)
  const databaseUrlMatch = envProdContent.match(/^DATABASE_URL=(.*)$/m)

  if (passwordMatch && databaseUrlMatch) {
    const password = passwordMatch[1].trim().replace(/^"|"$/g, '')
    const databaseUrl = databaseUrlMatch[1]
    if (!databaseUrl.includes(`:${password}@postgres_db`)) {
      console.error("⚠️  WARNING: DATABASE_URL password doesn't match POSTGRES_PASSWORD!")
      console.error('   Ensure both use the same password value.')
      process.exit(1)
    }
  }

  const composeProdPath = path.resolve('docker-compose.prod.yml')
  if (!fs.existsSync(composeProdPath)) {
    console.error('❌ Error: docker-compose.prod.yml not found!')
    process.exit(1)
  }

  const composeCmd = 'docker-compose --env-file .env.production -f docker-compose.prod.yml'

  console.log('🛑 Stopping existing production containers...')
  try {
    run(`${composeCmd} down`)
  } catch (error) {
    console.warn('ℹ️  No existing containers to stop.')
  }

  console.log('🏗️ Building production images...')
  // 默认使用 Docker 缓存构建，提升日常部署速度
  run(`${composeCmd} build`)

  console.log('🚀 Starting production services...')
  run(`${composeCmd} up -d`)

  console.log('⏳ Waiting for services to start...')
  await wait(10_000)

  console.log('🔍 Checking service status...')
  run(`${composeCmd} ps`)

  console.log('🏥 Checking backend health...')
  const urls = ['http://localhost/health', 'http://localhost:8000/health']
  let healthy = false

  for (const url of urls) {
    try {
      const response = await fetch(url, { method: 'GET' })
      if (response.ok) {
        console.log(`✅ Backend is reachable at ${url}`)
        healthy = true
        break
      }
    } catch {
      // ignore and try next
    }
  }

  if (!healthy) {
    console.error('⚠️ Backend health check failed. Showing recent logs...')
    run(`${composeCmd} logs --tail=20 backend`)
  }

  console.log('==================================')
  console.log('🎉 Production deployment completed!')
  console.log('')
  console.log('📍 Services:')
  console.log('   🌐 Application: http://localhost')
  console.log('   🔧 API: http://localhost/api/v1')
  console.log('   📖 API Docs: http://localhost/docs')
  console.log('   🏥 Health: http://localhost/health')
  console.log('')
  console.log('📊 To view logs:')
  console.log(`   ${composeCmd} logs -f`)
  console.log('')
  console.log('🛑 To stop:')
  console.log('   pnpm prod:down')
}

main().catch((error) => {
  console.error('❌ Deployment failed:', error)
  process.exit(1)
})
