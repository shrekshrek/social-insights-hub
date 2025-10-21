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

## 最终配置总结

### 关键配置参数
```python
# HTTP协议配置
http2: False  # ⭐ 必须使用HTTP/1.1

# 每次请求创建新客户端
async with httpx.AsyncClient(**client_kwargs) as fresh_client:
    # ...

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
   - 第263行: `http2: False` (search_notes方法)
   - 第367行: `http2: False` (query_self方法)
   - 第228-244行: 更新headers匹配MediaCrawlerPro
   - 第258-272行: 每次创建新AsyncClient

2. **pyproject.toml** (已在之前修改)
   - 依赖: `httpx[http2]>=0.27.0` (保留，但不启用)

### 签名系统文件（已在之前修复）
3. **src/signing/platforms/xhs/javascript.py**
   - 第140-146行: X-Mns提取逻辑
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
