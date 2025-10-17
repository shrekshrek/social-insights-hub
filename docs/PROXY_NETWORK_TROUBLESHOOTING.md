# 代理服务网络故障排查指南

## 问题现象

点击"刷新代理池"按钮时出现错误：
- 前端显示：`刷新代理池失败` 或 `服务内部错误`
- 后端日志显示：`httpx.ConnectTimeout` 或 `Connection timed out`

## 根本原因

**Docker 容器无法访问快代理 API（`https://dps.kdlapi.com`）**

这通常是由以下原因之一导致：

1. **网络限制**：公司/校园网络屏蔽了该域名
2. **DNS 解析失败**：Docker 容器 DNS 配置不正确
3. **防火墙规则**：系统防火墙阻止了 Docker 容器的出站连接
4. **需要代理**：本地环境需要通过 HTTP 代理访问外网

## 诊断步骤

### 1. 测试容器网络连接

```bash
# 测试 DNS 解析
docker-compose exec backend nslookup dps.kdlapi.com

# 测试 HTTP 连接（10秒超时）
docker-compose exec backend curl -I -m 10 https://dps.kdlapi.com

# 测试 HTTPS 握手
docker-compose exec backend curl -v -m 10 https://dps.kdlapi.com
```

**预期结果**：
- DNS 应返回 IP 地址（如 `1.2.3.4`）
- curl 应返回 `HTTP/1.1 200 OK` 或类似响应
- 握手应显示 SSL 证书信息

**实际结果（问题）**：
- `Connection timed out` - 网络不通
- `Could not resolve host` - DNS 解析失败

### 2. 测试宿主机网络连接

```bash
# 在宿主机（非 Docker 容器）测试
curl -I -m 10 https://dps.kdlapi.com
```

如果宿主机可以访问，说明是 Docker 网络配置问题。

## 解决方案

### 方案 A：配置 Docker DNS（推荐）

如果 DNS 解析失败，修改 Docker DNS 设置：

**1. 编辑 `docker-compose.yml`**

```yaml
services:
  backend:
    # ... 其他配置 ...
    dns:
      - 8.8.8.8      # Google DNS
      - 223.5.5.5    # 阿里云 DNS
      - 114.114.114.114  # 国内公共 DNS
```

**2. 重启服务**

```bash
docker-compose down
docker-compose up -d
```

**3. 验证**

```bash
docker-compose exec backend nslookup dps.kdlapi.com
```

### 方案 B：配置 Docker HTTP 代理

如果需要通过 HTTP 代理访问外网：

**1. 创建 `.env.proxy` 文件**

```bash
# 在项目根目录创建
cat > .env.proxy <<EOF
HTTP_PROXY=http://your-proxy-server:port
HTTPS_PROXY=http://your-proxy-server:port
NO_PROXY=localhost,127.0.0.1,postgres,redis
EOF
```

**2. 修改 `docker-compose.yml`**

```yaml
services:
  backend:
    # ... 其他配置 ...
    env_file:
      - .env
      - .env.proxy  # 添加这行
```

**3. 重启服务**

```bash
docker-compose down
docker-compose up -d
```

### 方案 C：使用宿主机网络模式（临时方案）

⚠️ **不推荐生产使用**，仅用于开发测试：

**修改 `docker-compose.yml`**

```yaml
services:
  backend:
    # ... 其他配置 ...
    network_mode: "host"  # 使用宿主机网络
```

**注意**：
- 使用 `host` 模式后，端口映射会失效
- 需要修改后端配置使用 `127.0.0.1` 连接数据库

### 方案 D：暂时跳过代理功能

如果短期内无法解决网络问题，可以暂时跳过代理池功能：

**1. 不配置代理服务商**
   - 创建任务时不选择代理
   - 系统将使用直连方式采集

**2. 等待任务失败后重试**
   - 如果 IP 被限制，稍后再试

## 验证修复

完成上述任何一个方案后，按以下步骤验证：

### 1. 测试容器网络

```bash
# 应该成功（不超时）
docker-compose exec backend curl -I -m 10 https://dps.kdlapi.com
```

### 2. 测试 Python httpx

```bash
# 进入容器测试 httpx
docker-compose exec backend uv run python -c "
import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get('https://dps.kdlapi.com')
        print(f'Status: {resp.status_code}')

asyncio.run(test())
"
```

**预期输出**：`Status: 200` 或类似

### 3. 在前端测试刷新代理池

1. 访问 http://localhost:3000/crawler-resources
2. 点击代理服务商的"刷新代理池"按钮
3. 应该看到成功提示："代理池已刷新"

## 常见问题

### Q1: 修改 docker-compose.yml 后没生效？

**A**: 必须完全重启容器：
```bash
docker-compose down
docker-compose up -d
```

### Q2: 宿主机可以访问，容器还是超时？

**A**: 可能是 Docker 网络隔离问题：
1. 尝试方案 A（配置 DNS）
2. 检查防火墙是否阻止 Docker 子网出站连接
3. 尝试重启 Docker 服务

### Q3: 公司网络必须用代理，但不知道代理地址？

**A**:
1. 询问 IT 部门获取 HTTP 代理地址
2. 或在浏览器中查看：设置 → 代理 → 查看代理配置
3. macOS: `System Preferences → Network → Advanced → Proxies`

### Q4: 还是不行怎么办？

**A**: 查看详细日志诊断：
```bash
# 查看后端错误日志
docker-compose logs backend | tail -n 100

# 查看网络连接
docker-compose exec backend netstat -an | grep ESTABLISHED

# 测试其他 HTTPS 站点
docker-compose exec backend curl -I https://www.baidu.com
```

## 技术细节

### 超时设置

当前代码中的超时配置：
- **HTTP 连接超时**：30 秒（`httpx.AsyncClient(timeout=30.0)`）
- **快代理 API 端点**：`https://dps.kdlapi.com/api/getdps/`

### 代码位置

- **后端代理刷新逻辑**：`backend/src/resources/service.py:109-133`
- **超时异常处理**：`backend/src/resources/service.py:128-133`

### 为什么不增加超时时间？

30 秒已经足够长，如果还超时说明网络根本不通，继续等待没有意义。正确做法是修复网络配置。

## 生产环境建议

在生产环境部署时：

1. **使用专用网络**：配置 Docker 自定义网络，隔离服务
2. **配置可靠 DNS**：使用云服务商的 DNS（如阿里云 223.5.5.5）
3. **监控网络连接**：使用 Prometheus 监控外部 API 调用成功率
4. **设置重试机制**：代理池刷新失败时自动重试（已实现）
5. **告警通知**：网络异常时发送告警（需实现）

## 相关资源

- [Docker DNS 配置文档](https://docs.docker.com/config/containers/container-networking/#dns-services)
- [Docker 网络代理配置](https://docs.docker.com/network/proxy/)
- [快代理 API 文档](https://www.kuaidaili.com/doc/api/)
