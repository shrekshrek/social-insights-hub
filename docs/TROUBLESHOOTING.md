# 常见问题排查指南

本文档帮助解决使用过程中可能遇到的常见问题。

---

## 前端界面问题

### 1. 按钮没有显示或显示为"—"

**症状**：
- 资源管理页面的"操作"列显示横线（—）
- 按钮不可见或不可点击

**可能原因**：
- 页面未完全加载
- 浏览器缓存问题
- 组件渲染异常

**解决方案**：
```bash
# 1. 刷新浏览器页面（Cmd+R 或 Ctrl+R）
# 2. 清除浏览器缓存并硬性重新加载（Cmd+Shift+R 或 Ctrl+Shift+R）
# 3. 重启前端开发服务器
pnpm stop
pnpm dev
```

### 2. 代理池刷新按钮位置

在代理服务商表格的"操作"列中，从左到右有三个按钮：

| 按钮 | 图标 | 样式 | 功能 | Tooltip |
|------|------|------|------|---------|
| 1 | ✏️ 铅笔 | 灰色边框 | 编辑配置 | "编辑" |
| 2 | ⏸️/▶️ 暂停/播放 | 黄色 | 启用/禁用 | "禁用"/"启用" |
| 3 | 🔄 循环箭头 | 蓝色边框 | 刷新代理池 | "刷新代理池" |

**确认方法**：
- 鼠标悬停在按钮上会显示tooltip提示
- 第三个按钮应该是蓝色边框的循环箭头图标

---

## 后端服务问题

### 1. Docker 容器未启动

**症状**：
- 访问 http://localhost:8000 无响应
- 前端显示 API 连接错误

**检查服务状态**：
```bash
docker-compose ps
```

**预期输出**：
```
NAME                      STATUS
crawler-backend-1         Up
crawler-celery_worker-1   Up
crawler-postgres_db-1     Up
crawler-redis-1           Up
```

**解决方案**：
```bash
# 重启所有服务
pnpm stop
pnpm dev
```

### 2. 数据库连接失败

**症状**：
- Backend 日志显示 "connection refused"
- API 请求返回 500 错误

**检查数据库**：
```bash
# 查看 PostgreSQL 日志
docker-compose logs postgres_db

# 测试数据库连接
docker-compose exec postgres_db psql -U postgres -d crawler_db -c "SELECT 1;"
```

**解决方案**：
```bash
# 重启数据库
docker-compose restart postgres_db

# 如果问题持续，清理并重建
pnpm cleanup
pnpm setup
pnpm dev
```

---

## 账号和代理问题

### 1. 小红书 Cookies 失效

**症状**：
- 任务日志显示 "未授权" 或 "登录失效"
- 搜索结果为空
- HTTP 401 错误

**确认方法**：
1. 访问 https://www.xiaohongshu.com/
2. 检查是否需要重新登录

**解决方案**：
1. 重新登录小红书网页版
2. 获取新的 Cookies（参考测试文档）
3. 在资源管理页面更新账号 Cookies：
   - 点击账号行的"编辑"按钮
   - 粘贴新的 Cookies
   - 保存

### 2. 快代理连接失败

**症状**：
- 代理池刷新失败
- 任务日志显示代理连接错误
- HTTP 407 错误（Proxy Authentication Required）

**检查清单**：
```bash
# 1. 登录快代理控制台
# 2. 检查余额是否充足
# 3. 检查 IP 白名单（如果配置了）
# 4. 验证凭证是否正确
```

**测试代理**：
```bash
# 使用 curl 测试代理
curl -x http://用户名:密码@代理地址:端口 https://www.xiaohongshu.com/
```

**解决方案**：
1. 更新快代理凭证
2. 检查账户余额
3. 联系快代理客服

### 3. 没有可用账号或代理

**症状**：
- 任务日志显示 "未找到可用账号"
- 任务日志显示 "未分配代理"

**检查账号**：
```sql
-- 连接数据库
docker-compose exec postgres_db psql -U postgres -d crawler_db

-- 查看账号状态
SELECT id, platform, account_name, is_active, locked_by_task_id
FROM crawler_accounts
WHERE platform = 'xhs';

-- 查看被锁定的账号
SELECT id, account_name, locked_by_task_id, locked_at
FROM crawler_accounts
WHERE locked_by_task_id IS NOT NULL;
```

**解决方案**：
1. 确保至少有一个启用的小红书账号
2. 如果账号被锁定很久，可能是任务异常退出：
   ```sql
   -- 手动释放账号
   UPDATE crawler_accounts SET locked_by_task_id = NULL, locked_at = NULL;
   ```

---

## 任务执行问题

### 1. 签名生成失败

**症状**：
- 任务日志显示 "签名失败"
- HTTP 请求返回签名错误

**检查签名策略**：
```bash
# 查看 .env 配置
cat .env | grep SIGNING

# 应该看到：
# SIGNING_STRATEGY=javascript
```

**解决方案**：
```bash
# 1. 确认签名服务已启动
docker-compose logs backend | grep -i sign

# 2. 如果使用 Playwright 策略，确保已安装浏览器
docker-compose exec backend playwright install chromium

# 3. 切换回 JavaScript 策略（更稳定）
# 编辑 .env
SIGNING_STRATEGY=javascript

# 重启服务
pnpm stop
pnpm dev
```

### 2. 任务卡在 running 状态

**症状**：
- 任务状态一直是 "running"
- 没有新的日志输出
- 进度条不更新

**检查 Celery Worker**：
```bash
# 查看 Worker 日志
docker-compose logs celery_worker

# 查看是否有错误
docker-compose logs celery_worker | grep -i error
```

**解决方案**：
```bash
# 1. 重启 Worker
docker-compose restart celery_worker

# 2. 如果任务长时间无响应，可以手动标记为失败
# 访问数据库：
docker-compose exec postgres_db psql -U postgres -d crawler_db

# 更新任务状态
UPDATE crawler_tasks
SET status = 'failed', error_message = '任务超时，手动停止'
WHERE id = <task_id> AND status = 'running';
```

### 3. HTTP 429 错误（请求过于频繁）

**症状**：
- 任务日志显示 "429 Too Many Requests"
- 搜索失败或返回空结果

**原因**：
- 短时间内请求过多
- 被小红书限流
- 未使用代理

**解决方案**：
1. **配置代理**（推荐）：
   - 添加快代理服务商
   - 刷新代理池
   - 重试任务

2. **减少请求频率**：
   ```json
   {
     "keywords": "单个关键词",
     "max_count": 5
   }
   ```

3. **等待冷却期**：
   - 等待 10-30 分钟后重试
   - 更换账号或代理

---

## 数据问题

### 1. 爬取结果为空

**症状**：
- 任务完成但没有数据
- 结果列表为空

**检查数据库**：
```sql
-- 查看爬取结果数量
SELECT COUNT(*) FROM crawler_note_results WHERE task_id = <task_id>;

-- 查看具体数据
SELECT * FROM crawler_note_results WHERE task_id = <task_id> LIMIT 10;
```

**检查任务日志**：
```bash
# 查看任务详情页的日志
# 或通过 API：
curl http://localhost:8000/api/v1/crawler-tasks/<task_id>/logs
```

**可能原因**：
- 关键词搜索无结果
- 账号未登录或权限不足
- 被限流

### 2. 数据不完整

**症状**：
- 部分字段为空
- 缺少详情信息

**检查配置**：
```json
{
  "enable_details": true  // 是否开启了详情获取
}
```

**说明**：
- 不开启 `enable_details` 只会获取搜索列表的基础信息
- 开启后会逐个获取笔记详情，耗时更长

---

## 性能问题

### 1. 任务执行很慢

**可能原因**：
- 大量关键词
- 开启了详情获取
- 网络延迟

**优化建议**：
```json
{
  "keywords": "关键词1,关键词2",  // 减少关键词数量
  "max_count": 10,                // 减少每个关键词的数量
  "enable_details": false,        // 暂时关闭详情
  "timeout": 15                   // 减少超时时间
}
```

### 2. 内存占用高

**检查资源使用**：
```bash
# 查看容器资源占用
docker stats

# 查看具体容器
docker stats crawler-backend-1 crawler-celery_worker-1
```

**优化方案**：
```bash
# 重启服务释放内存
docker-compose restart backend celery_worker

# 清理未使用的资源
docker system prune -a
```

---

## 日志查看

### 查看所有服务日志
```bash
docker-compose logs -f
```

### 查看特定服务日志
```bash
# Backend API
docker-compose logs -f backend

# Celery Worker
docker-compose logs -f celery_worker

# PostgreSQL
docker-compose logs postgres_db

# Redis
docker-compose logs redis
```

### 查看最近的错误
```bash
# Backend 错误
docker-compose logs backend | grep -i error

# Worker 错误
docker-compose logs celery_worker | grep -i error
```

---

## 重置和清理

### 完全重置项目
```bash
# 1. 停止所有服务
pnpm stop

# 2. 清理 Docker 资源（会删除数据库数据）
docker-compose down -v

# 3. 重新初始化
pnpm setup
pnpm dev
```

### 仅重置数据库
```bash
# 1. 停止服务
docker-compose stop

# 2. 删除数据库数据卷
docker volume rm crawler_postgres_data

# 3. 重启服务（会自动重建数据库）
pnpm dev
```

### 清理 Redis 缓存
```bash
# 连接 Redis
docker-compose exec redis redis-cli

# 清空所有缓存
> FLUSHALL

# 退出
> exit
```

---

## 获取帮助

如果以上方法都无法解决问题：

1. **查看完整日志**：
   ```bash
   docker-compose logs > logs.txt
   ```

2. **查看数据库状态**：
   ```sql
   -- 任务列表
   SELECT * FROM crawler_tasks ORDER BY created_at DESC LIMIT 10;

   -- 账号状态
   SELECT * FROM crawler_accounts;

   -- 代理服务商
   SELECT * FROM crawler_proxy_providers;
   ```

3. **提交 Issue**：
   - 提供错误日志
   - 说明复现步骤
   - 附上配置信息（隐藏敏感数据）

4. **检查文档**：
   - [测试指南](./XHS_CRAWLER_TESTING.md)
   - [配置文档](./CONFIGURATION.md)
   - [部署指南](../DEPLOYMENT.md)
