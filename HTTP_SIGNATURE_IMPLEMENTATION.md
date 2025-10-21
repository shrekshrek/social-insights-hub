# HTTP 签名策略实现说明

## 概述

为了隔离问题是否在签名生成环节，我们实现了一个新的 HTTP 签名策略，使 crawler-web 直接调用外部的 MediaCrawlerPro-SignSrv 签名服务。

这样可以让 MediaCrawlerPro-Python 和 crawler-web 使用完全相同的签名服务，如果仍然出现问题，则可以确定问题不在签名生成环节。

## 实现步骤

### 1. 创建 HTTP 签名策略类

**文件**: `backend/src/signing/strategies/http.py`

该策略实现了与 MediaCrawlerPro-SignSrv 的 HTTP 通信：

- **端点**: `http://host.docker.internal:8989/signsrv/v1/xhs/sign`
- **请求格式**: `{"uri": "...", "data": {...}, "cookies": "..."}`
- **响应处理**: 将 MediaCrawlerPro-SignSrv 的响应格式（下划线命名）转换为 crawler-web 的格式（连字符命名）

关键特性：
- 支持健康检查 (`health_check()`)
- 自动从 settings 读取配置
- 完整的错误处理和日志记录

### 2. 注册策略到工厂

**文件**: `backend/src/signing/factory.py`

```python
from .strategies.http import HttpSignatureStrategy

_STRATEGY_REGISTRY: Dict[str, Type[SignatureStrategy]] = {
    "javascript": JavascriptSignatureStrategy,
    "playwright": PlaywrightSignatureStrategy,
    "http": HttpSignatureStrategy,  # 新增
}
```

### 3. 更新配置验证

**文件**: `backend/src/config.py`

更新 `validate_signing_strategy` 方法，允许使用 "http" 策略：

```python
@field_validator("SIGNING_STRATEGY")
@classmethod
def validate_signing_strategy(cls, v: str) -> str:
    allowed = {"javascript", "playwright", "http"}  # 添加 "http"
    ...
```

### 4. 配置环境变量

**文件**: `.env`

```bash
# 签名策略设置为 http
SIGNING_STRATEGY=http

# MediaCrawlerPro-SignSrv 服务地址
# Docker 容器内访问宿主机使用 host.docker.internal
SIGN_SERVICE_HOST=host.docker.internal
SIGN_SERVICE_PORT=8989
```

## Docker 网络说明

由于 crawler-web 的 backend 和 celery_worker 运行在 Docker 容器中，它们无法直接访问宿主机的 `localhost:8989`。

**解决方案**: 使用 Docker 提供的特殊域名 `host.docker.internal`，它会自动解析为宿主机的 IP 地址。

## MediaCrawlerPro-SignSrv API 格式

### 请求格式
```json
{
  "uri": "/api/sns/web/v1/search/notes",
  "data": {"keyword": "火锅", "page": 1, ...},
  "cookies": "a1=xxx; webId=xxx; ..."
}
```

### 响应格式
```json
{
  "biz_code": 0,
  "msg": "success",
  "isok": true,
  "data": {
    "x_s": "XYW_...",
    "x_t": "1761033647134",
    "x_s_common": "2UQAPsHC...",
    "x_b3_traceid": "2abcf4bd746a7d9a",
    "x_mns": "ajm9aPiZ..."
  }
}
```

## 测试方法

### 1. 验证 MediaCrawlerPro-SignSrv 运行正常

```bash
python3 -c "
import requests
import json

resp = requests.post('http://localhost:8989/signsrv/v1/xhs/sign',
    json={
        'uri': '/api/sns/web/v1/search/notes',
        'data': None,
        'cookies': 'a1=test123'
    }
)
print('Status:', resp.status_code)
print('Response:', json.dumps(resp.json(), indent=2, ensure_ascii=False))
"
```

### 2. 重启 crawler-web 服务

```bash
cd /Users/shrekwang/Workspace/cursor/20250729_crawler/crawler-web
docker-compose restart backend celery_worker
```

### 3. 触发新的爬取任务

通过前端界面或 API 创建并启动一个新的小红书搜索任务，观察日志输出。

### 4. 检查日志

```bash
# 检查 backend 日志
docker-compose logs backend --tail=50

# 检查 celery_worker 日志（关键）
docker-compose logs celery_worker --tail=50 -f
```

关键日志标识：
- `[HttpSignatureStrategy]` - HTTP 策略调用日志
- 如果看到 "Successfully got signature from http://host.docker.internal:8989"，说明签名服务调用成功

## 预期结果分析

### 场景 A: 爬取成功（返回 > 0 条笔记）

**结论**: 问题确实在 crawler-web 的内部 JavaScript 签名实现中
- crawler-web 的 xhs_xs.js 与 MediaCrawlerPro-SignSrv 的实现存在其他差异
- 需要进一步对比两个 JavaScript 文件的细节

### 场景 B: 爬取失败（仍返回 0 条笔记）

**结论**: 问题不在签名生成环节
- 可能的原因：
  1. Cookie 本身有问题（虽然 MediaCrawlerPro-Python 能用）
  2. HTTP 请求的其他 headers 有问题
  3. User-Agent、Referer 等字段不匹配
  4. 网络层面的差异
  5. 请求时序问题

## 当前状态

- ✅ HTTP 签名策略已实现
- ✅ 配置已更新
- ✅ 服务已重启
- ⏳ 等待用户触发新的爬取任务进行测试

## 下一步

请通过前端界面触发一个新的小红书搜索任务（如搜索"火锅"），然后查看日志输出，根据结果判断问题根源。
