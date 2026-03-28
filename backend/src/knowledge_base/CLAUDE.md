# Knowledge Base 模块

市场知识库：文档上传 → 解析 → 分块 → 向量化（pgvector）→ RAG 检索。
策略模块通过 `retrieve_market_context()` 在 Phase1/2 生成前注入市场背景。

## Public Interface

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge-base/documents/upload` | 上传文档（multipart/form-data） |
| GET | `/knowledge-base/documents` | 文档列表（平台公共 + 用户私有） |
| GET | `/knowledge-base/documents/{id}` | 文档详情 |
| DELETE | `/knowledge-base/documents/{id}` | 删除文档（仅上传者） |
| POST | `/knowledge-base/search` | RAG 检索测试 |

### 核心函数

```python
# strategies/service.py 中的调用方式
from src.knowledge_base.service import retrieve_market_context

market_context = await retrieve_market_context(
    db, query="小米SU7 品牌口碑", user_id=strategy.created_by, top_k=6
)
# 返回格式化 markdown 字符串，或 "" (无结果/出错时)
```

### 权限

`knowledge_base` 模块权限：`access` / `read` / `write` / `delete`

## Data Model

### `knowledge_documents`
- `workspace_id = NULL` → 平台公共文档（所有用户可检索）
- `workspace_id = user_id` → 用户私有上传（仅该用户可检索）
- `processing_status`: `pending` → `processing` → `ready` / `failed`
  - 前端 types 使用 `'ready'`（不是 `'completed'`）
- `source_meta._file_bytes_b64`: 文件字节临时存储（Base64），处理完成后自动清除

### `knowledge_chunks`
- `embedding`: `vector(1024)`，BAAI/bge-large-zh，`normalize_embeddings=True`
- IVFFlat 索引（`lists=100`），余弦距离（`vector_cosine_ops`）
- `chunk_meta`: 页码等元信息（注意：不能命名为 `metadata`，SQLAlchemy 保留字）

## Important Notes

- **pgvector 依赖**: 需要 `pgvector/pgvector:pg16` 镜像（已在 `docker-compose.yml` 配置），`postgres:16-alpine` 不含该扩展
- **Celery 异步处理**: 上传端点仅创建 DB 记录，通过 `process_document_task.delay(doc_id)` 派发处理；`processing_status` 异步更新
- **RAG 优雅降级**: `retrieve_market_context()` 所有异常静默处理，返回 `""`；策略生成主流程不受 KB 可用性影响
- **Embedding 懒加载**: 首次调用 `embed()` 触发 BAAI/bge-large-zh 模型加载（约 10s），后续调用走缓存单例
- **渠道架构**: `strategy_brief_parser_chain.py` 中 `knowledge_base` 标记为 `available=true`；`ecommerce` 和 `industry_data` 已删除
- **文件格式**: 上传支持 PDF / DOCX / TXT / MD，上限 50MB；`title` 参数是 Form field（非 Query string）
