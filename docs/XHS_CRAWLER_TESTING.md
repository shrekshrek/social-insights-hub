# 小红书爬虫功能测试指南

本文档指导如何测试小红书爬虫的完整功能，包括账号配置、代理设置和任务执行。

---

## 前置准备

### 1. 启动项目

```bash
# 在项目根目录执行
pnpm dev
```

等待所有服务启动：
- ✅ PostgreSQL (5432)
- ✅ Redis (6379)
- ✅ Backend API (8000)
- ✅ Celery Worker
- ✅ Frontend (3000)

### 2. 登录系统

访问 http://localhost:3000

- **默认管理员账号**：`admin` / `admin123`

---

## 第一步：配置小红书账号

### 1. 获取小红书 Cookies

1. 打开浏览器（推荐 Chrome）
2. 访问 https://www.xiaohongshu.com/ 并登录
3. 打开开发者工具（F12）
4. 切换到 **Network** 标签
5. 刷新页面，找到任意请求
6. 在请求头中找到 **Cookie** 字段
7. 复制完整的 Cookie 字符串

**示例格式**：
```
a1=xxx; webId=xxx; gid=xxx; web_session=xxx; ...
```

### 2. 添加账号到系统

1. 访问 http://localhost:3000/crawler-resources
2. 点击 **"新增账号"** 按钮
3. 填写表单：
   - **平台**：选择 `小红书`
   - **账号标识**：`test_xhs_account` （自定义名称）
   - **Cookies**：粘贴刚才复制的 Cookie 字符串
4. 点击 **保存**

**验证**：列表中应显示新创建的账号，状态为"启用"。

---

## 第二步：配置快代理服务商（可选）

> ⚠️ 如果没有快代理账号，可以跳过此步骤，系统将使用直连方式。

### 1. 获取快代理凭证

1. 登录 [快代理控制台](https://www.kuaidaili.com/)
2. 进入 **动态转发代理** 产品
3. 获取以下信息：
   - Secret ID
   - Signature（签名）
   - 用户名
   - 密码

### 2. 添加代理服务商

1. 在资源管理页面，点击 **"新增代理服务商"** 按钮
2. 填写表单：
   - **名称**：`快代理主账号`
   - **Secret ID**：从控制台复制
   - **Signature**：从控制台复制
   - **用户名**：代理用户名
   - **密码**：代理密码
   - **池容量**：`10`（建议值）
   - **同步间隔**：`5` 分钟
3. 点击 **保存**

### 3. 测试代理池

1. 在代理服务商列表中，找到刚创建的配置
2. 在该行的"操作"列中，有三个按钮：
   - **✏️ 编辑按钮**（铅笔图标）- 编辑配置
   - **⏸️/▶️ 启用/禁用按钮**（暂停/播放图标）- 切换状态
   - **🔄 刷新按钮**（循环箭头图标，蓝色边框）- 刷新代理池 ← 点击这个
3. 点击刷新按钮后，查看提示消息：
   - ✅ 成功：显示 "代理池已刷新"
   - ❌ 失败：检查下方故障排除

> **提示**：鼠标悬停在按钮上会显示tooltip说明

### 4. 故障排除

**问题：刷新代理池时出现"请求超时"错误**

原因：Docker 容器网络访问快代理 API 超时（默认 30 秒）

解决方案：
1. **检查网络连接**：确保 Docker 容器可以访问外网
   ```bash
   docker-compose exec backend curl -I https://dps.kdlapi.com
   ```

2. **验证凭证**：在浏览器中测试快代理 API
   ```
   https://dps.kdlapi.com/api/getdps/?secret_id=YOUR_SECRET_ID&signature=YOUR_SIGNATURE&num=1&pt=1&format=json
   ```
   应返回 JSON 格式的代理列表

3. **检查 Docker 网络设置**：
   - 如果使用代理上网，需要配置 Docker HTTP_PROXY
   - 如果在国内，可能需要配置 DNS（如 `8.8.8.8`）

4. **查看详细日志**：
   ```bash
   docker-compose logs backend | grep -A 10 "快代理"
   ```

**问题：返回 "服务商配置内部错误"**

原因：Secret ID 或 Signature 不正确

解决方案：
1. 重新从快代理控制台复制凭证
2. 注意不要复制多余的空格
3. 确保使用的是"动态转发代理"产品的凭证

---

## 第三步：创建爬虫任务

### 1. 创建搜索任务

1. 访问 http://localhost:3000/crawler-tasks
2. 点击 **"创建任务"** 按钮（或直接访问 `/crawler-tasks/create`）
3. 填写表单：

#### 基础信息
- **任务名称**：`测试小红书搜索-手机`
- **平台**：`小红书`
- **爬取模式**：`搜索`

#### 任务配置
- **关键词**：`手机,数码` （多个关键词用逗号分隔）
- **最大爬取数量**：`10` （每个关键词最多爬取10条）
- **爬取评论**：✅ 开启（可选）
- **爬取二级评论**：❌ 关闭（建议）
- **使用代理**：❌ **关闭**（重要！因为我们跳过了代理配置）
- **启用断点续传**：✅ 开启（推荐）

> ⚠️ **重要**：如果没有配置代理服务商，必须关闭"使用代理"开关，否则任务会因为无法获取代理而失败！

4. 点击 **"创建任务"**

### 2. 任务自动分配逻辑

创建任务后，系统会在执行时自动分配资源：

**账号分配**：
- 系统自动从 `小红书` 平台的账号池中选择一个可用账号
- 使用 LRU 策略（最少最近使用）
- 如果没有可用账号，任务会失败并提示

**代理分配**（如果开启了"使用代理"）：
- 系统自动从代理池中获取一个可用代理
- 如果代理池为空，任务会失败
- 无代理模式下此步骤被跳过

### 3. 配置字段说明

| 字段 | 说明 | 默认值 | 备注 |
|------|------|--------|------|
| 关键词 | 搜索关键词，多个用逗号分隔 | - | 搜索模式必填 |
| 最大爬取数量 | 每个关键词最多爬取的笔记数 | 40 | 建议测试时设为 10 |
| 爬取评论 | 是否采集笔记的评论 | ✅ | 会增加采集时间 |
| 爬取二级评论 | 是否采集评论的回复 | ❌ | 会显著增加采集时间 |
| 使用代理 | 是否使用代理池 | ✅ | **无代理环境必须关闭** |
| 启用断点续传 | 任务中断后可恢复 | ✅ | 推荐开启 |

### 4. 高级配置（可选）

如果需要更精细的控制，可以手动编辑任务的 config JSON：

```json
{
  "keywords": "手机,数码",
  "max_count": 10,
  "sort_type": "general",
  "note_type": 0,
  "enable_comments": true,
  "enable_sub_comments": false,
  "proxy_enabled": false,
  "enable_checkpoint": true
}
```

**额外字段说明**：
- `sort_type`: 排序方式
  - `general`: 综合排序（默认）
  - `popularity_descending`: 最热
  - `time_descending`: 最新
- `note_type`: 笔记类型
  - `0`: 全部（默认）
  - `1`: 仅视频
  - `2`: 仅图文

---

## 第四步：执行任务并查看结果

### 1. 启动任务

1. 在任务列表中找到刚创建的任务
2. 点击任务卡片进入详情页
3. 点击 **"启动任务"** 按钮

### 2. 实时监控

任务详情页会实时显示：

- **任务状态**：pending → running → completed
- **进度条**：0% → 100%
- **已爬取数量**：实时更新
- **执行日志**：
  ```
  [INFO] 已分配账号 test_xhs_account
  [INFO] 已分配代理 http://xxx.xxx.xxx.xxx:xxxx
  [INFO] 开始搜索小红书笔记，关键词: 程序员, ChatGPT
  [INFO] [1/2] 搜索关键词: 程序员
  [DEBUG] 签名生成成功: x-s=XYS...
  [INFO] 关键词 程序员 搜索到 10 条笔记
  [INFO] [2/2] 搜索关键词: ChatGPT
  [INFO] 关键词 ChatGPT 搜索到 10 条笔记
  [INFO] 保存 20 条笔记到数据库...
  [INFO] 搜索任务完成，共获取 20 条笔记
  ```

### 3. 查看爬取结果

1. 在任务详情页，点击 **"查看结果"** 标签
2. 显示爬取到的笔记列表：
   - 笔记ID
   - 标题
   - 描述
   - 作者昵称
   - 互动数据（点赞、收藏、评论、分享）
   - 关键词

### 4. 通过 API 查看结果

```bash
# 查看任务结果
curl http://localhost:8000/api/v1/crawler-tasks/{task_id}/results
```

---

## 常见问题排查

### 1. 任务启动后立即失败

**可能原因**：
- 未配置小红书账号
- 账号 Cookies 已过期

**解决方案**：
1. 检查资源管理页面是否有可用账号
2. 重新获取并更新 Cookies
3. 查看任务日志的详细错误信息

### 2. 签名生成失败

**可能原因**：
- 签名服务未启动
- 签名策略配置错误

**解决方案**：
1. 检查 `.env` 文件中的签名配置：
   ```bash
   SIGNING_STRATEGY=javascript  # 或 playwright
   ```
2. 查看 Backend 日志：
   ```bash
   docker-compose logs backend
   ```

### 3. HTTP 429 错误（请求过于频繁）

**可能原因**：
- 短时间内请求过多
- 未使用代理

**解决方案**：
1. 配置快代理服务商
2. 减少 `max_count` 数量
3. 增加任务间隔（代码中已内置 2 秒间隔）

### 4. 搜索结果为空

**可能原因**：
- 关键词被限流或屏蔽
- 账号未登录或登录态失效

**解决方案**：
1. 更换关键词测试
2. 检查账号 Cookies 是否有效
3. 查看 Backend 日志中的 API 响应：
   ```bash
   docker-compose logs backend | grep "Search API response"
   ```

### 5. 代理连接失败

**可能原因**：
- 快代理余额不足
- 快代理凭证错误

**解决方案**：
1. 登录快代理控制台检查余额
2. 验证 Secret ID 和 Signature 是否正确
3. 测试代理池刷新功能

---

## 进阶测试

### 1. 测试笔记详情爬取

修改任务配置，开启详情获取：

```json
{
  "keywords": "美食推荐",
  "max_count": 5,
  "enable_details": true
}
```

**预期结果**：
- 每条笔记包含完整详情
- 日志显示 "获取笔记详情成功"

### 2. 测试 detail 模式

创建新任务：

```json
{
  "crawler_type": "detail",
  "urls": [
    "https://www.xiaohongshu.com/explore/60e1234567890abcdef",
    "60e1234567890abcdef"
  ]
}
```

**注意**：将 URL 或 note_id 替换为真实的笔记ID。

### 3. 测试资源分配

1. 创建多个小红书账号
2. 同时启动多个任务
3. 观察账号和代理的分配情况
4. 验证资源自动释放

---

## API 测试（可选）

使用 Swagger UI 测试：http://localhost:8000/docs

### 1. 创建任务
```
POST /api/v1/crawler-tasks
```

### 2. 启动任务
```
POST /api/v1/crawler-tasks/{task_id}/start
```

### 3. 查看任务详情
```
GET /api/v1/crawler-tasks/{task_id}
```

### 4. 查看任务结果
```
GET /api/v1/crawler-tasks/{task_id}/results
```

---

## 数据库验证

```sql
-- 查看任务列表
SELECT id, name, platform, status, crawled_count, created_at
FROM crawler_tasks
ORDER BY created_at DESC;

-- 查看爬取结果
SELECT id, note_id, title, keyword, created_at
FROM crawler_note_results
WHERE task_id = 1
LIMIT 10;

-- 查看任务日志
SELECT level, message, created_at
FROM crawler_task_logs
WHERE task_id = 1
ORDER BY created_at DESC;
```

---

## 成功标志

完整测试通过应满足：

- ✅ 账号和代理配置成功
- ✅ 任务创建成功
- ✅ 任务启动后状态变为 running
- ✅ 日志显示账号和代理分配成功
- ✅ 日志显示签名生成成功
- ✅ 成功搜索到笔记
- ✅ 数据保存到数据库
- ✅ 任务状态变为 completed
- ✅ 资源自动释放（账号 locked_by_task_id 为空）

---

## 下一步

测试成功后，可以继续：

1. 优化配置参数（max_count、sort_type 等）
2. 测试大规模爬取（多关键词、多任务）
3. 添加评论爬取功能
4. 实现断点续爬
5. 配置定时任务（Celery Beat）

有问题请查看项目文档或提交 Issue。
