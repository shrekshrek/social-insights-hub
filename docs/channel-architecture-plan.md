# 数据渠道架构规划

> 规划日期：2026-03-28

## 最终渠道列表

社媒以外保留 3 个渠道，去掉 `ecommerce`（技术复杂 + 法律风险），合并 `industry_data` → `knowledge_base`：

| 渠道 | 标识 | 状态 | 说明 |
|------|------|------|------|
| 社交媒体 | `social_media` | ✅ 已有 | 不变 |
| 市场知识库 | `knowledge_base` | 下一步实现 | 合并了原 `industry_data` |
| 新闻舆情 | `news_media` | P1 | 较轻，之后实现 |

## knowledge_base 渠道

### 定位

"参考数据层"——策略生成时的市场背景注入，不是实时流数据。
通过 RAG 在 Phase1/2 Chain 生成时动态检索并注入 `market_context`。

### 数据来源

**模式 A：全量预下载 + 定期更新**

| 来源 | 初始量 | 更新频率 |
|------|--------|---------|
| CNNIC 互联网报告 | ~50份历史全部 | 每半年检测新报告 |
| 国家统计局精选指标 | ~100个核心指标 × 近3年 | 每月1日拉取 |
| gov.cn 产业政策 | 近3年重点政策文件 | 每周检测新文件 |

**模式 B：按需触发 + 缓存**

| 来源 | 触发时机 | 缓存 |
|------|---------|------|
| 巨潮资讯（A股招股书/年报） | 策略创建时按 subject 搜索 | 同公司180天内不重复爬 |
| 港交所披露易 | 同上 | 同上 |

**模式 C：用户上传**

用户自行上传 PDF / Word / Excel 私有文档（研报、内部资料等）。

### RAG 方案

- **向量存储**：PostgreSQL + pgvector 扩展（无新服务依赖）
- **Embedding 模型**：BAAI/bge-large-zh（中文最优开源模型，离线运行）
- **实现方式**：自建（不用 LlamaIndex / Haystack），核心 ~200 行
- **检索策略**：余弦相似度 + industry_tags 过滤，top-k=6
- **多租户**：`workspace_id = NULL` 为平台公共数据，`workspace_id = <id>` 为用户私有上传

### 数据量估算

| 来源 | chunks 约数 | 向量存储 |
|------|------------|---------|
| CNNIC 历史报告 | ~2,000 | 8MB |
| 统计局指标 | ~1,500 | 6MB |
| gov.cn 政策 | ~5,000 | 20MB |
| 巨潮资讯（动态增长） | 视使用 | — |

总量极小，pgvector 无需特殊优化。

### 注入位置

`strategies/service.py` → `generate_phase1()` / `generate_phase2()` 调用前：

```
subject + analysis_goal → 向量化 → pgvector 检索 top-6 → 格式化 → market_context
                                                                         ↓
                                               注入 Phase1/2 Chain 的 USER_TEMPLATE
```

## news_media 渠道

### 定位

实时/近期新闻监测，与 knowledge_base 区别：时效性优先，不做 RAG，按关键词 + 时间范围检索。

### 数据来源

| 来源 | 方案 | 法律风险 |
|------|------|---------|
| gov.cn 政策原文 | 定向爬取 | 无 |
| 极速数据新闻 API | 官方 API，~¥200/年 | 无 |

### 注入位置

Phase1 Chain 注入"近30天相关事件"段落（非向量检索，直接按 keywords 时序查询）。

## 存量代码改动清单

| 文件 | 改动 |
|------|------|
| `strategies/schemas.py` | `ChannelPlanItem.type` 注释去掉 `industry_data` / `ecommerce` |
| `langchain/chains/strategy_brief_parser_chain.py` | 合并 `industry_data`→`knowledge_base`（available=true），去掉 `ecommerce` |
| `langchain/chains/strategy_phase1_chain.py` | USER_TEMPLATE 加 `{market_context}` |
| `langchain/chains/strategy_phase2_chain.py` | 同上 |
| `strategies/service.py` | Phase1/2 生成前调 RAG 检索，结果注入 `market_context` |
| `rbac/init_data.py` | 注册 `knowledge_base` 模块权限 |
| `main.py` | 注册新 router |
| `frontend/app/config/routes.ts` | 添加知识库路由权限 |
| `frontend/nuxt.config.ts` | `extends` 加 `knowledge-base` layer |
| `frontend/layers/strategies/composables/useStrategyConstants.ts` | 更新 `CHANNEL_LABELS` |

## 新增模块结构

### 后端

```
backend/src/knowledge_base/
├── models.py            # KnowledgeDocument, KnowledgeChunk
├── schemas.py
├── service.py           # 文档处理、RAG 检索
├── router.py
├── tasks.py             # Celery：文档处理 + 定时爬取
├── permissions_def.py
└── crawlers/
    ├── base.py
    ├── nbs.py           # 国家统计局 API
    ├── cnnic.py         # CNNIC 报告
    └── cninfo.py        # 巨潮资讯（按需）

backend/src/news_media/  # P1，较轻
├── models.py
├── schemas.py
├── service.py
├── router.py
├── tasks.py
└── sources/
    ├── govsite.py
    └── jisuapi.py
```

### 前端

```
frontend/layers/knowledge-base/
├── nuxt.config.ts
├── pages/knowledge-base/index.vue
├── composables/useKnowledgeBase.ts
└── types/index.ts
```

## 实现顺序

```
P0-Week1: knowledge_base 后端核心
  models + migration（pgvector）
  文档上传 → 解析 → 分块 → 向量化（Celery）
  router: 上传/列表/删除/状态

P0-Week2: 前端 + 策略集成
  knowledge-base layer（上传UI + 文档列表）
  RAG 检索注入 Phase1/2 Chain
  Brief Parser 更新渠道定义

P0.5-Week3: 公开数据接入
  国家统计局 API + APScheduler
  CNNIC PDF 解析
  巨潮资讯按需爬取

P1-Week4: news_media
  gov.cn + 极速 API
  Phase1 近期事件注入
```
