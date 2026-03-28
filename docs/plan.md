# 实施方案：knowledge_base 模块 — 市场知识库

> 规划日期：2026-03-28
> 参考文档：`docs/channel-architecture-plan.md`

## 模块职责

"参考数据层"：管理文档的上传、解析、分块、向量化全生命周期；在策略生成（Phase 1/2）前通过 RAG 检索注入 `market_context`，为 LLM 提供市场背景。

---

## 数据模型

### `knowledge_documents` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | SERIAL PK | |
| workspace_id | INTEGER NULL | NULL=平台公共；user_id=用户私有上传 |
| title | VARCHAR(500) NOT NULL | |
| source_type | VARCHAR(50) DEFAULT 'upload' | upload / cnnic / nbs / govsite / cninfo |
| source_url | TEXT NULL | 公共数据来源链接 |
| source_meta | JSONB NULL | 年份、报告类型等元信息 |
| file_name | TEXT NULL | 原始文件名 |
| industry_tags | TEXT[] DEFAULT '{}' | 行业标签，用于检索过滤 |
| chunk_count | INTEGER DEFAULT 0 | 处理后分块数 |
| processing_status | VARCHAR(20) DEFAULT 'pending' | pending / processing / ready / failed |
| error_message | TEXT NULL | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `knowledge_chunks` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGSERIAL PK | |
| document_id | INTEGER NOT NULL FK → knowledge_documents.id CASCADE DELETE | |
| content | TEXT NOT NULL | 原文分块 |
| embedding | vector(1024) NOT NULL | BAAI/bge-large-zh 输出维度 |
| chunk_index | INTEGER NOT NULL | 块序号 |
| metadata | JSONB NULL | 页码、章节等 |
| created_at | TIMESTAMPTZ | |

**ORM 关系**：
- `KnowledgeDocument.chunks`: `relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")`
- `KnowledgeChunk.document`: `relationship("KnowledgeDocument", back_populates="chunks")`

**索引**：
- `knowledge_chunks(document_id)`
- `knowledge_chunks` USING ivfflat(embedding vector_cosine_ops) WITH (lists=100) — 手写，autogenerate 不支持
- `knowledge_documents(workspace_id)` WHERE NOT NULL
- `knowledge_documents(source_type)`

---

## API / 接口设计

Router prefix: `/api/v1/knowledge-base`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/documents/upload` | `knowledge_base:write` | 上传文件（multipart），触发 Celery 处理 |
| GET | `/documents` | `knowledge_base:read` | 文档列表（分页 + source_type/status 过滤） |
| GET | `/documents/{id}` | `knowledge_base:read` | 文档详情 + 状态 |
| DELETE | `/documents/{id}` | `knowledge_base:delete` | 删除文档及所有分块 |
| POST | `/search` | `knowledge_base:read` | 测试 RAG 检索 |

**关键 Schemas（均继承 `CustomBaseModel`）**：

```python
class DocumentRead(CustomBaseModel):
    id: int
    title: str
    source_type: str
    source_url: str | None
    file_name: str | None
    industry_tags: list[str]
    chunk_count: int
    processing_status: str  # pending/processing/ready/failed
    error_message: str | None
    created_at: datetime
    updated_at: datetime

class SearchRequest(CustomBaseModel):
    query: str
    top_k: int = Field(6, ge=1, le=20)

class ChunkResult(CustomBaseModel):
    document_id: int
    document_title: str
    content: str
    score: float
    chunk_index: int
```

**RAG 检索服���接口**：

```python
async def retrieve_market_context(
    db: AsyncSession,
    query: str,
    user_id: int | None = None,
    top_k: int = 6,
) -> str:
    """
    检索相关分块，返回格式化的市场背景段落。
    - workspace_id IS NULL（平台公共）OR workspace_id = user_id（用户私有）
    - 无匹配结果时返回 ""，不阻塞策略生成主流程
    """
```

---

## 实施步骤

### Step 1：依赖 + pgvector 迁移
**文件**：`backend/pyproject.toml`（改），新 Alembic migration 文件

**操作**：
```bash
pnpm be:add sentence-transformers pgvector
pnpm be:migrate:make "add_knowledge_base_pgvector"
```

**迁移内容**（需手写，autogenerate 无法生成）：
```python
def upgrade():
    # 1. 启用 pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # 2. 创建 knowledge_documents 表
    op.create_table("knowledge_documents", ...)
    # 3. 创建 knowledge_chunks 表（含 vector 列）
    op.create_table("knowledge_chunks", ...)
    # 4. 手写 IVFFlat 索引（autogenerate 不支持）
    op.execute(
        "CREATE INDEX ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
```

**验证**：`pnpm be:migrate:up` 无报错；`\dx` 确认 vector 扩展已启用

**依赖**：无

---

### Step 2：`backend/src/knowledge_base/models.py`（新建）
**接口**：
```python
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id, workspace_id, title, source_type, source_url, source_meta,
    file_name, industry_tags, chunk_count, processing_status, error_message,
    created_at, updated_at
    # 关系
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id, document_id, content, embedding (Vector(1024)), chunk_index, metadata, created_at
    # 关系
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument", back_populates="chunks"
    )
```

**关键断言**：`embedding` 列类型为 `Vector(1024)`（从 `pgvector.sqlalchemy` 导入）

**验证**：`pnpm be:lint` 无报错

**依赖**：Step 1

---

### Step 3：`backend/src/knowledge_base/schemas.py`（新建）
**接口**：`DocumentRead`, `DocumentUploadResponse`, `SearchRequest`, `SearchResponse`, `ChunkResult`

**关键断言**：所有 Pydantic 模型继承 `src.schemas.CustomBaseModel`（不得直接继承 `pydantic.BaseModel`）

**依赖**：Step 2

---

### Step 4：`backend/src/knowledge_base/embedding.py`（新建）
**接口**：
```python
class EmbeddingService:
    """BAAI/bge-large-zh 懒加载单例"""
    _model = None  # 首次调用时加载，~10s

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """CPU 密集型 → 必须用 run_cpu_bound_task"""
        from src.utils import run_cpu_bound_task
        return await run_cpu_bound_task(self._encode, texts)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("BAAI/bge-large-zh")
        return self._model.encode(texts, normalize_embeddings=True).tolist()

def get_embedding_service() -> EmbeddingService: ...  # 模块级单例
```

**关键断言**：
- 输出维度 == 1024（bge-large-zh）
- `normalize_embeddings=True`（余弦相似度要求单位向量）
- 严禁在 `async def` 中直接调用 `_encode`，必须通过 `run_cpu_bound_task`

**依赖**：Step 1（sentence-transformers 已安装）

---

### Step 5：`backend/src/knowledge_base/service.py`（新建）
**接口**：
```python
def parse_text(file_bytes: bytes, filename: str) -> str:
    """从文件字节提取纯文本（复用 strategies/service.py 的 _extract_text_from_bytes 逻辑）
    支持：PDF（pdfplumber）/ DOCX（python-docx）/ TXT / MD
    文件大小上限：50MB（router 层校验）"""

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """按字符分块，中文友好（不在单词中间截断）"""

async def process_document(db: AsyncSession, doc_id: int) -> None:
    """解析 → 分块 → 向量化 → 批量写入 knowledge_chunks → 更新 status=ready
    异常时 status=failed + error_message，不抛出（Celery 任务不重试）"""

async def retrieve_market_context(
    db: AsyncSession, query: str,
    user_id: int | None = None, top_k: int = 6,
) -> str:
    """pgvector 余弦相似度检索
    WHERE workspace_id IS NULL OR workspace_id = user_id
    ORDER BY embedding <=> query_vec LIMIT top_k
    返回格式化段落或 "" （无结果时）"""

async def list_documents(db, workspace_id, source_type, status, skip, limit) -> tuple[list, int]: ...
async def get_document(db, doc_id) -> KnowledgeDocument | None: ...
async def delete_document(db, doc) -> None: ...
```

**关键断言**：
- `process_document` 失败不抛出，仅写 `status='failed'`
- `retrieve_market_context` 无匹配时返回 `""`

**验证**：单元测试（mock DB + mock embedding）

**依赖**：Step 2, 3, 4

---

### Step 6：`backend/src/knowledge_base/tasks.py`（新建）
**接口**：
```python
@celery_app.task(name="knowledge_base.process_document")
def process_document_task(document_id: int) -> None:
    """同步 Celery 任务包装器，内部通过 asyncio.run 调用 service.process_document"""
```

**依赖**：Step 5

---

### Step 7：`backend/src/knowledge_base/router.py`（新建）
**接口**：5 个端点，含 `response_model`, `status_code`, `tags`, `summary`
- 上传：接收 `UploadFile`，校验 size ≤ 50MB，创建 `KnowledgeDocument`，派发 `process_document_task.delay(doc.id)`
- 所有 I/O 用 `async def`
- 权限通过 FastAPI Depends 注入（参考 strategies/router.py 模式）

**依赖**：Step 5, 6

---

### Step 8：权限注册 + 路由注册
**文件**：`backend/src/rbac/init_data.py`（改），`backend/src/main.py`（改）

**init_data.py** — 在 BUSINESS_PERMISSIONS 尾部追加：
```python
*create_module_permissions(
    "knowledge_base",
    ["access", "read", "write", "delete"],
    display_names={
        "access": "访问知识库",
        "read": "查看文档",
        "write": "上传文档",
        "delete": "删除文档",
    },
    descriptions={
        "access": "允许访问市场知识库页面",
        "read": "允许查看和检索知识库文档",
        "write": "允许上传文档到知识库",
        "delete": "允许删除知识库文档",
    },
),
```

**main.py**：
```python
from src.knowledge_base.router import router as knowledge_base_router
app.include_router(knowledge_base_router, prefix=settings.API_PREFIX)
```

**验证**：重启服务后 `pnpm be:lint`；GET `/api/v1/knowledge-base/documents` 返回 200

**依赖**：Step 7

---

### Step 9：`backend/src/celery_app.py`（改）
**操作**：在 `include` 列表中加入 `"src.knowledge_base.tasks"`

**依赖**：Step 6

---

### Step 10：`strategy_phase1_chain.py` Phase1 Chain 注入（改）
**文件**：`backend/src/langchain/chains/strategy_phase1_chain.py`

**USER_TEMPLATE 改动**（在 brief_section 之后、切片数据之前插入）：
```python
USER_TEMPLATE = """{brief_section}

{research_context_section}

{market_context}

## 切片数据

{slice_data}"""
```

**`format_slice_data_for_phase1()` 改动**：
```python
def format_slice_data_for_phase1(
    slices, brief=None, research_design=None,
    market_context: str = "",   # 新增参数
) -> dict[str, Any]:
    ...
    return {
        "brief_section": brief_section,
        "research_context_section": research_context_section,
        "slice_data": slice_data,
        "market_context": market_context,   # 新增
    }
```

**关键断言**：`market_context=""` 时链调用不报错，LLM 输出结构不变

**依赖**：Step 8

---

### Step 11：`strategy_phase2_chain.py` Phase2 Chain 注入（改）
**文件**：`backend/src/langchain/chains/strategy_phase2_chain.py`

**USER_TEMPLATE 改动**（在 brief_section 之后插入）：
```python
USER_TEMPLATE = """{brief_section}

{research_context_section}

{market_context}

## Phase 1 洞察结果

{phase1_result}

## 补充数据

{supplementary_data}"""
```

**`format_data_for_phase2()` 改动**：加 `market_context: str = ""` 参数，写入返回 dict

**依赖**：Step 8

---

### Step 12：`strategies/service.py` RAG 注入（改）
**文件**：`backend/src/strategies/service.py`

**改动**：
```python
from src.knowledge_base.service import retrieve_market_context

async def generate_phase1(db, strategy):
    ...
    # RAG 注入（有 brief 时执行，无数据时优雅降级为 ""）
    market_context = ""
    if strategy.brand_brief:
        brief = strategy.brand_brief
        query = f"{brief.get('subject', '')} {brief.get('analysis_goal', '')}".strip()
        if query:
            market_context = await retrieve_market_context(
                db, query, user_id=strategy.created_by, top_k=6
            )

    inputs = format_slice_data_for_phase1(
        slices_data, strategy.brand_brief,
        research_design=strategy.research_design,
        market_context=market_context,   # 注入
    )
    ...

# generate_phase2() 同样处理，使用相同的 market_context 逻辑
```

**关键断言**：
- `brand_brief` 为 None 时跳过 RAG，`market_context=""`
- RAG 异常不应中断策略生成（`try/except`，降级为 `""`）

**依赖**：Step 10, 11

---

### Step 13：`strategy_brief_parser_chain.py` 渠道更新（改）
**文件**：`backend/src/langchain/chains/strategy_brief_parser_chain.py`

**SYSTEM_TEMPLATE 改动**：
- 删除 `ecommerce` 渠道条目（淘宝/京东）
- 删除 `industry_data` 条目（行业研报，已合并）
- `knowledge_base` 改为 `available=true`，说明扩展：
  ```
  **knowledge_base**（市场知识库，当前**可用**）：平台内置公共数据（CNNIC报告、国家统计局指标、政策文件）+ 用户上传的内部文档（研报、历史资料）；适合需要市场数据背景、行业趋势参考、内部资料佐证的场景
  ```
- 更新示例 JSON，`available` 字段为 `true`

**依赖**：Step 8

---

### Step 14：`strategies/schemas.py`（改）
**文件**：`backend/src/strategies/schemas.py`

**改动**：`ChannelPlanItem.type` Field description 更新：
```python
type: str = Field(description="渠道类型: social_media / knowledge_base / news_media")
```

**依赖**：Step 13

---

### Step 15：`frontend/config/permissions.ts`（改）
**改动**：在 PERMISSIONS 末尾追加：
```typescript
// 知识库
KB_ACCESS: { target: 'knowledge_base', action: 'access' },
KB_READ: { target: 'knowledge_base', action: 'read' },
KB_WRITE: { target: 'knowledge_base', action: 'write' },
KB_DELETE: { target: 'knowledge_base', action: 'delete' },
```

**依赖**：Step 8（后端权限注册）

---

### Step 16：`frontend/config/routes.ts`（改）
**改动**：在策略路由之后追加：
```typescript
// 知识库模块
'/knowledge-base': {
  permission: PERMISSIONS.KB_ACCESS,
  label: '市场知识库',
  showInNav: true,
  order: 95,
},
'/knowledge-base/[id]': { permission: PERMISSIONS.KB_READ },
```

**依赖**：Step 15

---

### Step 17：`frontend/nuxt.config.ts`（改）
**改动**：`extends` 数组末尾追加 `'./layers/knowledge-base'`

**依赖**：Step 16

---

### Step 18：`frontend/layers/knowledge-base/`（新建）

**文件结构**：
```
frontend/layers/knowledge-base/
├── nuxt.config.ts
├── pages/knowledge-base/index.vue
├── composables/useKnowledgeBase.ts
└── types/index.ts
```

**`nuxt.config.ts`**：仿 rbac layer，声明 imports + components

**`types/index.ts`**：
```typescript
export interface KnowledgeDocument {
  id: number
  title: string
  source_type: string
  source_url: string | null
  file_name: string | null
  industry_tags: string[]
  chunk_count: number
  processing_status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null
  created_at: string
  updated_at: string
}
```

**`composables/useKnowledgeBase.ts`**：
```typescript
export const useKnowledgeBase = () => {
  const { apiRequest, useApiData } = useApi()

  // 文档列表（SSR 友好）
  const useDocuments = (params: Ref<{ source_type?: string; page?: number }>) =>
    useApiData<PaginatedResponse<KnowledgeDocument>>('/knowledge-base/documents', { query: params })

  // 上传（复用 strategies 的 FormData 模式）
  const uploadDocument = async (file: File, title?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    if (title) formData.append('title', title)
    return await apiRequest<KnowledgeDocument>('/knowledge-base/documents/upload', {
      method: 'POST',
      body: formData,
    })
  }

  const deleteDocument = async (id: number) =>
    await apiRequest(`/knowledge-base/documents/${id}`, { method: 'DELETE' })

  return { useDocuments, uploadDocument, deleteDocument }
}
```

**`pages/knowledge-base/index.vue`** 关键约定：
- 文档列表用 `useApiData()`（SSR 友好）
- 文件上传组件和列表 wrap 在 `<ClientOnly>` 中（浏览器 API）
  ```vue
  <ClientOnly>
    <KbUploadForm @uploaded="refresh()" />
    <template #fallback><USkeleton class="h-32" /></template>
  </ClientOnly>
  ```

**依赖**：Step 15, 16, 17

---

### Step 19：`frontend/layers/strategies/composables/useStrategyConstants.ts`（改）
**改动**：更新 `CHANNEL_LABELS`：
```typescript
export const CHANNEL_LABELS: Record<string, string> = {
  social_media: '社交媒体',
  knowledge_base: '市场知识库',
  news_media: '新闻媒体',
}
```

删除 `ecommerce` 和 `industry_data` 条目。

**依赖**：Step 13

---

## 边界情况 & 错误处理

| 场景 | 处理方式 |
|------|---------|
| KB 无文档时生成策略 | `retrieve_market_context` 返回 `""`，Phase1/2 正常执行 |
| RAG 检索异常（DB 超时等） | `try/except` 捕获，降级返回 `""`，记录 logger.warning |
| 文档解析失败（损坏 PDF） | `process_document` 设 `status='failed'` + `error_message`，不重试 |
| 上传文件 > 50MB | Router 层 size ���验，返回 HTTP 413 |
| `brand_brief` 为 None 时 generate | 跳过 RAG 调用，`market_context=""` |
| Embedding 模型首次加载 (~10s) | Celery worker 懒加载，首个任务慢，后续正常 |
| pgvector 扩展未启用 | 迁移时保证；连接时失败报错明确 |

---

## 测试策略

| 层级 | 测试点 | 工具 |
|------|--------|------|
| Unit | `chunk_text()` 边界情况（空文本、超长文本、中文截断） | pytest |
| Unit | `retrieve_market_context()` mock DB — 无结果返回 `""` | pytest + mock |
| Unit | `format_slice_data_for_phase1()` 带 market_context 参数 | pytest |
| Integration | 上传 → Celery 处理 → status=ready → `/search` 返回结果 | pytest + httpx |
| Integration | `generate_phase1()` mock `retrieve_market_context` → inputs 含 market_context key | pytest |

---

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Embedding 模型 | BAAI/bge-large-zh (sentence-transformers) | 中文最优开源，离线，按规划 |
| workspace_id P0 | workspace_id=NULL 平台公共；user_id 用于用户上传隔离 | 最小多租户，schema 留扩展点 |
| market_context 降级 | 无文档/无 brief/异常时传 `""`，不阻塞生成 | 知识库是增强非必需 |
| CPU-bound 执行 | `run_cpu_bound_task`（非 raw executor） | 符合项目约定 |
| 分块策略 | 800 char / 100 overlap | 中文文档经验值，易调整 |
| IVFFlat 索引 | lists=100，数据量 <10K 时适合 | pgvector 文档推荐 |
| ecommerce 渠道 | 完全删除（非延期） | 法律风险（蝉妈妈诉讼案例）+ 技术复杂度 |
| industry_data 渠道 | 合并入 knowledge_base | 数据可公开爬取，定位一致 |
