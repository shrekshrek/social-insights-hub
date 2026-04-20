# Knowledge Base 模块

市场知识库：文档上传 → 解析 → 分块 → 向量化（pgvector）→ RAG 检索。
独立功能模块，不与策略研究流程集成（策略产出由社媒/新闻切片 + Research Agent 行业研究驱动）。

`parse_text` 工具函数被 `strategies/service.py` 和 `research_agent/service.py` 复用，用于解析上传的 Brief 文档（PDF/Word → 文本），与知识库 RAG 检索无关。

## Public Interface

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge-base/documents/upload` | 上传文档（multipart/form-data） |
| GET | `/knowledge-base/documents` | 文档列表（平台公共 + 用户私有） |
| GET | `/knowledge-base/documents/{id}` | 文档详情 |
| DELETE | `/knowledge-base/documents/{id}` | 删除文档（仅上传者） |
| POST | `/knowledge-base/search` | RAG 检索测试 |
| GET | `/knowledge-base/crawlers/status` | 各来源文档数/状态统计（需登录） |
| POST | `/knowledge-base/crawlers/{source_type}/run` | 手动触发爬取，后台异步执行（需登录） |

### 权限

`knowledge_base` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### `knowledge_documents`
- `workspace_id = NULL` → 平台公共文档（所有用户可检索）
- `workspace_id = user_id` → 用户私有上传（仅该用户可检索）
- `status`: `pending` → `processing` → `ready` / `failed`
  - 前端 types 使用 `'ready'`（不是 `'completed'`）
- `source_meta._file_bytes_b64`: 文件字节临时存储（Base64），处理完成后自动清除

### `knowledge_chunks`
- `embedding`: `vector(1024)`，BAAI/bge-m3，`normalize_embeddings=True`
- IVFFlat 索引（`lists=100`），余弦距离（`vector_cosine_ops`）
- `chunk_meta`: 页码等元信息（注意：不能命名为 `metadata`，SQLAlchemy 保留字）

## Important Notes

- **pgvector 依赖**: 需要 `pgvector/pgvector:pg16` 镜像（已在 `docker-compose.yml` 与 `docker-compose.prod.yml` 配置），`postgres:16-alpine` 不含该扩展
- **Celery 异步处理**: 上传端点仅创建 DB 记录，通过 `process_document_task.delay(doc_id)` 派发处理；`status` 异步更新
- **RAG 优雅降级**: `retrieve_market_context()` 所有异常静默处理，返回 `""`；策略生成主流程不受 KB 可用性影响
- **Embedding API**: 通过 OpenAI-compatible API 调用（默认 SiliconFlow BAAI/bge-m3），无本地模型，无 NVIDIA 依赖；配置项：`EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL`
- **独立模块**: 不作为策略研究的 channel_plan 渠道，不注入任何产出 stage
- **文件格式**: 上传支持 PDF / DOCX / TXT / MD，上限 50MB；`title` 参数是 Form field（非 Query string）

## Crawlers 子模块

`crawlers/` 目录实现公开数据自动爬取，走相同的 `process_document_task` 处理管线。

### 架构要点

- **BaseCrawler**: 抽象基类，子类实现 `discover() → list[CrawlSource]`
- **CrawlSource**: NamedTuple，包含 `url, title, file_bytes, filename, source_meta`
- **_upsert() 去重**: `source_url + source_type` 联合唯一约束；`ready/processing/pending` → 跳过；`failed` → 重置重试
- **_crawl_url()**: 调用 Crawl4AI REST API（`http://crawl4ai:11235/crawl`），返回 fit_markdown
- **APScheduler 调度**: NBS 每月1日03:00，cnnic 每月15日03:00，govsite 每周一04:00（在 FastAPI asyncio 事件循环中原生运行，无需 gevent 桥接）

### 数据来源

| source_type | 来源 | 内容 | 获取方式 |
|-------------|------|------|---------|
| `cnnic` | cnnic.net.cn | 互联网发展统计报告 + 专题研究 PDF | httpx 直接抓取（无需 Crawl4AI） |
| `nbs` | stats.gov.cn | 月度经济指标月报 | Crawl4AI → Markdown |
| `govsite` | www.gov.cn | 互联网/数字经济/平台经济政策 | Crawl4AI 搜索页 → Markdown |

### 添加新爬虫

1. 继承 `BaseCrawler`，设置 `source_type` 类属性，实现 `discover()`
2. 在 `crawlers/registry.py` 的 `CRAWLER_REGISTRY` 中注册
3. 可选：在 `src/scheduler.py` 的 `create_scheduler()` 中添加定时 job（`crawl_source` 函数已通用，只需传 `args=[source_type]`）

无需改动 `tasks.py`——`crawl_source(source_type)` 函数通过 `CRAWLER_REGISTRY` 动态路由，所有已注册的爬虫均自动支持。
