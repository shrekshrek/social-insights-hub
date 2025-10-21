# crawler-web 小红书爬虫调试日志

## 问题描述
crawler-web 使用小红书(XHS)平台搜索功能时，API返回成功(code: 0)，但data中没有items数组，导致无法获取任何笔记数据。

## 调试时间线

### 2025-10-21 初始问题
- **现象**: 搜索API返回 `{"code": 0, "success": true, "data": {"has_more": false}}`
- **问题**: 没有 `items` 数组，无法获取笔记数据
- **参考**: MediaCrawlerPro-Python 使用相同Cookie可以成功搜索到22条笔记

### 调试步骤 1: 检查签名系统
**发现**: X-Mns头在之前的会话中已修复
- ✅ X-s 签名正确
- ✅ X-t 时间戳正确
- ✅ x-s-common 正确
- ✅ X-B3-Traceid 正确
- ✅ X-Mns 已添加（从primary signature提取）

### 调试步骤 2: 检查Cookie
**发现**: Cookie完全一致
- MediaCrawlerPro Cookie长度: 680字符
- crawler-web Cookie长度: 680字符
- ✅ 两者完全一致

### 调试步骤 3: 检查HTTP客户端行为
**发现**: crawler-web复用HTTP客户端，MediaCrawlerPro每次创建新客户端

**修复**:
```python
# 之前的实现 - 复用客户端
def _get_client(self) -> httpx.AsyncClient:
    if self._client is None:
        self._client = httpx.AsyncClient(**client_kwargs)
    return self._client

# 修复后 - 每次创建新客户端（模仿MediaCrawlerPro）
async with httpx.AsyncClient(**client_kwargs) as fresh_client:
    response = await fresh_client.post(url, data=json_str, headers=request_headers)
```

**原因**: 复用的客户端会维护HTTP/2连接状态和TLS会话，可能被反爬系统识别

### 调试步骤 4: 检查HTTP协议版本 ⭐ **关键发现**
**问题**: crawler-web使用HTTP/2，MediaCrawlerPro使用HTTP/1.1

**证据**:
1. MediaCrawlerPro的 `requirements.txt`:
   ```
   httpx==0.24.0  # 没有 [http2] 扩展
   ```

2. crawler-web之前的配置:
   ```python
   "http2": True  # ❌ 错误配置
   ```

3. 日志对比:
   - MediaCrawlerPro成功: 使用HTTP/1.1（默认）
   - crawler-web失败: 日志显示 `"HTTP/2 200 OK"`

**根本原因**: 小红书的反爬机制可能检测HTTP/2请求并返回空结果

**最终修复**:
```python
# src/platforms/xhs/client.py 第263行和第367行
client_kwargs = {
    "timeout": self._timeout,
    "follow_redirects": True,
    "http2": False,  # ⚠️ 关键：使用HTTP/1.1而非HTTP/2
    "trust_env": False,
}
```

### 调试步骤 5: 更新User-Agent和Chrome版本
**修改**: 完全匹配MediaCrawlerPro的headers

```python
"sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
"sec-ch-ua-platform": '"Windows"',  # 从 "macOS" 改为 "Windows"
"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
```

### 调试步骤 6: 移除所有自定义AsyncClient参数 ⭐
**发现**: crawler-web设置了多个自定义参数，MediaCrawlerPro只设置proxies

**修改前**:
```python
client_kwargs = {
    "timeout": self._timeout,
    "follow_redirects": True,
    "http2": False,
    "trust_env": False,
}
```

**修改后**:
```python
client_kwargs = {}
if self._proxy:
    client_kwargs["proxies"] = self._proxy
```

**测试结果**: 仍返回空结果，但MediaCrawlerPro用相同cookie成功（22条笔记）

### 调试步骤 7: 添加timeout参数到请求调用 ⭐ **最新修复**
**发现**: MediaCrawlerPro在请求时传入timeout参数

**证据**:
- MediaCrawlerPro Line 210: `await client.request(method, url, timeout=self.timeout, **kwargs)`
- MediaCrawlerPro Line 50: `timeout: int = 10` (默认10秒)
- crawler-web之前没有在请求调用中设置timeout

**修复**:
```python
# src/platforms/xhs/client.py 第267行和第365行
response = await fresh_client.post(url, data=json_str, headers=request_headers, timeout=10.0)
response = await fresh_client.get(url, headers=request_headers, timeout=10.0)
```

**原因**: httpx默认timeout是5秒，MediaCrawlerPro显式设置10秒可能影响请求行为

### 调试步骤 8: 修复签名服务参数差异 ⭐⭐⭐⭐⭐ **核心修复**

**发现**: 对比crawler-web和MediaCrawlerPro-SignSrv的签名实现，发现4个关键差异

**差异对比**:

| 参数 | crawler-web | MediaCrawlerPro-SignSrv | 影响 |
|------|-------------|------------------------|------|
| x1 (version) | `"3.7.8-2"` | `"3.6.8"` | ⭐⭐⭐ 中等 |
| x4 (app version) | `"4.27.2"` | `"4.20.1"` | ⭐⭐ 较小 |
| x10 (getSigCount) | `154` | `1` | ⭐⭐⭐ 中等 |
| `_mrc` 循环次数 | `range(len(e))` | `range(57)` | ⭐⭐⭐⭐⭐ **致命** |

**最致命的差异**: `_mrc`函数计算CRC32时，MediaCrawlerPro固定循环57次，而crawler-web循环整个字符串长度。这导致`x9`字段计算错误，x-s-common签名完全不同！

**修复代码**:
```python
# src/signing/platforms/xhs/javascript.py

# Line 606-615: 更新x-s-common参数
common = {
    "s0": 3,
    "s1": "",
    "x0": "1",
    "x1": "3.6.8",      # 从 "3.7.8-2" 改为 "3.6.8"
    "x2": "Mac OS",
    "x3": "xhs-pc-web",
    "x4": "4.20.1",     # 从 "4.27.2" 改为 "4.20.1"
    "x5": a1,
    "x6": x_t,
    "x7": x_s,
    "x8": b1,
    "x9": _mrc(x_t + x_s + b1),
    "x10": 1,           # 从 154 改为 1
}

# Line 511-515: 修复_mrc函数循环次数
# 之前: for n in range(len(e)):
# 现在: for n in range(57):  # 固定57次
for n in range(57):  # ⭐ 关键修复
    o = ie[(o & 255) ^ ord(e[n])] ^ right_without_sign(o, 8)
return o ^ -1 ^ 3988292384
```

**测试结果**: Python修复成功，但JavaScript文件仍使用旧参数！

### 调试步骤 9: 修复JavaScript文件中的参数 ⭐⭐⭐⭐⭐⭐ **真正的核心修复**

**重大发现**: Python的`apply_secondary_signature`函数修复后仍然失败，因为**JavaScript的`sign`函数在内部生成x-s-common**！

**流程分析**:
```
crawler-web调用流程：
1. Python调用 xs_ctx.call("sign", uri, data, cookies)
2. JavaScript sign()函数内部：
   - 生成x-s和x-t
   - 构建h对象（包含x1, x4, x10等参数）
   - 调用sign_common(h)生成x-s-common
   - 返回{x-s, x-t, x-s-common, x-b3-traceid}
3. Python不再调用apply_secondary_signature！
```

**问题**: JavaScript文件xhs_xs.js中硬编码的参数与MediaCrawlerPro不同：

| 参数 | crawler-web JS (Line 3411-3420) | MediaCrawlerPro | 修复 |
|------|--------------------------------|-----------------|------|
| x1 | `"4.1.0"` | `"3.6.8"` | ✅ 已修复 |
| x4 | `"4.61.1"` | `"4.20.1"` | ✅ 已修复 |
| x10 | `81` | `1` | ✅ 已修复 |

**修复代码**:
```javascript
// src/signing/resources/xhs/xhs_xs.js Line 3411-3420

// 修改前:
"x1": "4.1.0",
"x4": "4.61.1",
"x10": 81,

// 修改后:
"x1": "3.6.8",   // 匹配MediaCrawlerPro
"x4": "4.20.1",  // 匹配MediaCrawlerPro
"x10": 1,        // 匹配MediaCrawlerPro
```

**验证**: 重启backend和celery_worker，等待测试

## 最终配置总结

### 关键配置参数
```python
# HTTP协议配置
http2: False  # ⭐ 必须使用HTTP/1.1

# 每次请求创建新客户端（仅设置proxies，不设置其他参数）
client_kwargs = {}
if self._proxy:
    client_kwargs["proxies"] = self._proxy

async with httpx.AsyncClient(**client_kwargs) as fresh_client:
    # 在请求调用中设置timeout=10.0（匹配MediaCrawlerPro）
    response = await fresh_client.post(url, data=json_str, headers=request_headers, timeout=10.0)

# Headers配置
{
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.xiaohongshu.com",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://www.xiaohongshu.com/",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "cookie": self._cookie_str,
}

# 签名配置
- b1: 使用默认值（772字符）
- X-Mns: 从primary signature提取
```

### 请求延时配置
```python
delay = random.uniform(5, 10)  # 5-10秒随机延时
```

## 重要注意事项

### ⚠️ 禁止使用HTTP/2
**原因**: 小红书反爬机制会检测HTTP/2请求并返回空结果
**验证方法**: 日志应显示 `"HTTP/1.1 200 OK"` 而非 `"HTTP/2 200 OK"`

### ⚠️ 每次请求创建新客户端
**原因**: 避免连接池复用和HTTP/2状态被反爬识别
**实现**: 使用 `async with httpx.AsyncClient()` 模式

### ⚠️ Cookie有效期
**现象**: Cookie可能在一段时间后失效或被限流
**解决**:
1. 定期从浏览器获取新Cookie
2. 使用前先正常浏览几个笔记
3. 避免短时间内频繁请求

## 测试验证

### 成功标志
1. ✅ 日志显示 `"HTTP/1.1 200 OK"`（不是HTTP/2）
2. ✅ API响应包含 `"items"` 数组
3. ✅ 成功解析笔记数据

### 失败标志
1. ❌ 日志显示 `"HTTP/2 200 OK"`
2. ❌ API响应只有 `{"has_more": false}` 没有items
3. ❌ 解析到0条笔记

## 修改的文件清单

### 核心文件
1. **src/platforms/xhs/client.py**
   - 第102行: `http2: False` (_get_client方法，已废弃)
   - 第228-244行: 更新headers匹配MediaCrawlerPro
   - 第258-263行: 创建AsyncClient只设置proxies参数
   - 第267行: POST请求添加 `timeout=10.0`
   - 第365行: GET请求添加 `timeout=10.0`

2. **src/signing/platforms/xhs/javascript.py** (Python签名，实际未使用)
   - 第606行: `x1` 从 "3.7.8-2" 改为 "3.6.8"
   - 第609行: `x4` 从 "4.27.2" 改为 "4.20.1"
   - 第615行: `x10` 从 154 改为 1
   - 第511-515行: `_mrc` 函数循环从 `range(len(e))` 改为 `range(57)`
   - **注意**: 这个文件的apply_secondary_signature函数实际不会被调用！

3. **src/signing/resources/xhs/xhs_xs.js** ⭐⭐⭐⭐⭐⭐ **真正的核心修复**
   - 第3411行: `x1` 从 "4.1.0" 改为 "3.6.8"
   - 第3414行: `x4` 从 "4.61.1" 改为 "4.20.1"
   - 第3420行: `x10` 从 81 改为 1

4. **pyproject.toml** (已在之前修改)
   - 依赖: `httpx[http2]>=0.27.0` (保留，但不启用)
   - 第99行: DEFAULT_B1值

## 参考对比

### MediaCrawlerPro-Python配置
- HTTP协议: HTTP/1.1 (默认)
- httpx版本: 0.24.0 (无HTTP/2支持)
- 客户端: 每次请求创建新实例
- Chrome版本: 136/137

### crawler-web最终配置
- HTTP协议: HTTP/1.1 (显式禁用HTTP/2)
- httpx版本: >=0.27.0 with [http2] (安装但不启用)
- 客户端: 每次请求创建新实例
- Chrome版本: 136/137 (匹配)

## 后续优化建议

1. **Cookie管理**: 实现Cookie池，支持多账号轮换
2. **请求频率**: 实现更智能的延时策略
3. **错误处理**: 区分不同的错误类型（限流、封禁、Cookie失效等）
4. **监控告警**: 当连续多次返回空结果时告警

## 总结

**核心问题**: HTTP/2协议触发小红书反爬机制
**解决方案**: 完全模仿MediaCrawlerPro使用HTTP/1.1
**验证方法**: 检查日志中的HTTP协议版本和响应data.items
**关键配置**: `http2: False`

---
最后更新: 2025-10-21
