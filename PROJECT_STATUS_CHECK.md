# PROJECT_STATUS_CHECK

更新时间：2026-05-19  
用途：招聘会/面试前的项目状态核查。本文档只按当前代码说明，不把预留目录或计划项说成已完成。

## 0. 总体结论

当前项目已经跑通了一个可演示的「多用户权限控制 RAG 知识库系统」核心闭环：

1. 用户注册/登录后上传文档。
2. 后端保存原文件和文档元数据。
3. 入库阶段探测 PDF 文本层质量，选择解析/OCR/LLM 归一化策略。
4. 文档解析后按规则切块，记录页码、文件名、表格、chunk 类型、质量分数等 metadata。
5. 使用 BGE Embedding 生成向量，写入 ChromaDB。
6. 问答阶段先按用户身份计算可访问文档范围，再在权限范围内做向量检索、关键词混合召回、可选 Reranker 精排。
7. LLM 只基于检索证据输出结构化回答；证据不足时返回「未找到相关答案」。
8. 系统记录文档处理任务、问答日志、权限变更审计日志，并在前端展示文档列表、质量报告、权限管理和问答历史。

需要谨慎表述的部分：

- `LangGraph` 问答 Agent 目前只是预留目录，尚未真正接入 `/chat/` 问答链路。
- 当前 Ingestion Agent 更准确地说是「轻量文档处理调度模块」，主要是规则探测 + 可选 LLM 规划，不是完整多步 LangGraph Agent。
- 混合检索已实现「向量 + 关键词召回 + BM25 召回」，并加入标准号、单位、上标数字等归一化 tokenizer。
- OCR fallback、LLM 切块归一化、Reranker 都有代码接入，但稳定性取决于本地模型、GPU/PaddleOCR 环境和 `.env` 配置。
- 任务队列是进程内 semaphore 控制，不是 Celery/RQ 这类生产级持久化队列。

---

## 1. 当前系统整体架构是什么？

**当前是否已实现：部分完成。核心 RAG 闭环已完成，企业级完整产品能力仍在完善。**

**相关代码文件路径：**

- 后端入口：`backend/app/main.py`
- 配置：`backend/app/core/config.py`
- 业务数据库：`backend/app/db/session.py`、`backend/app/db/init_db.py`
- 文档入库：`backend/app/services/document_service.py`
- RAG 问答：`backend/app/services/rag_service.py`
- 向量库：`backend/app/rag/vector_store.py`
- Embedding：`backend/app/rag/embeddings.py`
- Reranker：`backend/app/rag/reranker.py`
- OCR：`backend/app/rag/ocr/paddleocr_engine.py`
- Ingestion Agent：`backend/app/agent/ingestion_agent.py`
- LangGraph 预留：`backend/app/agent/graph.py`、`state.py`、`nodes.py`、`tools.py`
- 前端：`frontend/src/App.vue`、`frontend/src/api/client.ts`

**当前实现逻辑简述：**

- 前端使用 Vue3 + Vite + TypeScript + Element Plus，当前主要逻辑集中在 `App.vue`，已做上传、文档列表、问答测试、系统配置四个视图。
- 后端使用 FastAPI + SQLAlchemy + Pydantic + JWT，API 前缀为 `/api/v1`。
- 业务数据库默认 SQLite：`data/app.db`。
- 向量数据库使用 ChromaDB，持久化目录为 `data/chroma`，collection 为 `knowledge_chunks`。
- LLM 通过 OpenAI-compatible API 封装，`.env.example` 默认 DeepSeek Base URL。
- 当前从上传文档到问答返回已经能跑通。

**是否可以稳定运行：**

- 可演示：登录、上传可读 PDF/TXT/Markdown、入库、检索问答、引用返回、文档删除、权限过滤。
- 依赖环境的部分：OCR、Reranker、GPU 加速、LLM 归一化。

**目前存在的问题或限制：**

- 前端仍是单文件应用，后续应拆成 views/components/stores/router。
- 后端核心服务已模块化，但仍有部分入库逻辑集中在 `document_service.py`。
- LangGraph 问答 Agent 尚未实现。

**面试时建议如何表述：**

> 系统采用 Vue3 前端 + FastAPI 后端 + SQLite 业务库 + ChromaDB 向量库。用户登录后上传文档，后端完成解析、切块、向量化入库，并在问答时按用户权限过滤可检索文档，再结合 BGE Embedding、关键词召回、可选 Reranker 和 LLM 生成带引用的答案。

**下一步建议优化内容：**

- 拆分前端页面和状态管理。
- 把问答链路迁移为 LangGraph 节点。
- 将文档入库任务改为持久化队列。

---

## 2. 用户登录和权限系统完成到什么程度？

**当前是否已实现：已完成基础版本。**

**相关代码文件路径：**

- 认证接口：`backend/app/api/auth.py`
- 安全工具：`backend/app/core/security.py`
- 用户模型：`backend/app/models/user.py`
- 用户服务：`backend/app/services/auth_service.py`
- 权限模型：`backend/app/models/permission.py`
- 用户组/部门模型：`backend/app/models/group.py`
- 权限服务：`backend/app/services/permission_service.py`
- 文档权限过滤：`backend/app/services/document_service.py`
- RAG 权限过滤：`backend/app/services/rag_service.py`
- 前端调用：`frontend/src/api/client.ts`

**当前实现逻辑简述：**

- 支持 `/api/v1/auth/register`、`/api/v1/auth/login`、`/api/v1/auth/me`。
- 密码使用 bcrypt hash。
- 登录后返回 JWT，后续接口通过 Bearer Token 识别用户。
- `users` 表有 `is_admin` 字段，支持 admin/user 区分。
- 文档有 `owner_id`，上传者默认拥有访问权限。
- 直接用户权限表：`permissions`，包含 `can_read`、`can_write`。
- 用户组/部门权限表：`groups`、`user_groups`、`group_permissions`，也支持 `can_read`、`can_write`。
- 权限变更写入 `audit_logs`。
- 文档列表、chunk 预览、质量报告、问答检索都会先检查当前用户是否有权限。

**是否可以稳定运行：**

- 基础登录、注册、JWT 鉴权、admin 管理权限、用户/用户组读写权限可以演示。

**目前存在的问题或限制：**

- `owner` 不是单独权限枚举，而是通过 `documents.owner_id` 隐式表达。
- `can_write` 已用于 LLM 整理等写操作判断，但当前写权限场景不多；文档删除仍限制 admin。
- 没有刷新 token、密码重置、账号锁定、企业 SSO、多租户隔离。

**面试时建议如何表述：**

> 权限控制不是只在前端隐藏，而是在后端接口和检索阶段都生效。用户提问前会根据 owner、直接授权和部门授权计算可访问文档集合，检索时只把这些 document_id 传入 ChromaDB metadata filter。

**下一步建议优化内容：**

- 增加显式角色表和权限策略表。
- 补充更完整的 write/manage/delete 权限语义。
- 增加权限变更前后 diff 和审计筛选。

---

## 3. 文档上传与文档管理完成了哪些？

**当前是否已实现：已完成基础版本。**

**相关代码文件路径：**

- 文档接口：`backend/app/api/documents.py`
- 文档服务：`backend/app/services/document_service.py`
- 文档模型：`backend/app/models/document.py`
- 任务模型：`backend/app/models/document_job.py`
- 前端上传/文档列表：`frontend/src/App.vue`
- API 客户端：`frontend/src/api/client.ts`

**当前实现逻辑简述：**

- 支持上传 `.pdf`、`.txt`、`.md`、`.markdown`。
- 单文件大小默认限制 50 MB。
- 原文件保存到 `data/uploads/<user_id>/`。
- 文档 metadata 写入 `documents` 表，包括文件名、类型、路径、大小、状态、chunk_count、owner_id、error_message。
- 上传后创建 `document_processing_jobs` 任务记录，后台入库。
- 文档状态覆盖 queued、agent_planning、parsing、preprocessing、ocr、llm_preprocessing、chunking、embedding、indexing、indexed、failed 等阶段。
- admin 可以删除文档；删除时会调用 `ChromaVectorStore.delete_document(document.id)` 同步删除向量 chunk，并删除源文件。

**是否可以稳定运行：**

- 可读 PDF、Markdown、TXT 上传入库可以演示。
- 文档删除和 ChromaDB 同步删除可以演示。

**目前存在的问题或限制：**

- 后台任务基于 FastAPI BackgroundTasks + 进程内 semaphore，不是持久化任务队列；服务重启时正在执行的任务不会自动恢复。
- 没有文档版本管理。
- 非 admin 用户当前不能删除自己上传的文档。

**面试时建议如何表述：**

> 文档上传后会保存原文件和 metadata，并记录入库任务状态。索引成功后状态更新为 indexed，失败则写入 error_message，方便定位解析、OCR、Embedding 或 ChromaDB 写入问题。

**下一步建议优化内容：**

- 引入 Celery/RQ/Arq 或数据库任务调度。
- 增加文档版本号、重新入库、批量取消任务。
- 增加用户级删除策略。

---

## 4. 文档解析模块目前做到什么程度？

**当前是否已实现：部分完成。可读 PDF/TXT/Markdown 较稳定，复杂扫描件和复杂表格仍是重点优化项。**

**相关代码文件路径：**

- loader 入口：`backend/app/rag/loaders/__init__.py`
- PDF loader：`backend/app/rag/loaders/pdf_loader.py`
- Markdown loader：`backend/app/rag/loaders/markdown_loader.py`
- TXT loader：`backend/app/rag/loaders/txt_loader.py`
- 预处理：`backend/app/rag/preprocessor.py`
- OCR：`backend/app/rag/ocr/paddleocr_engine.py`
- 表格转写：`backend/app/rag/normalizers/table_normalizer.py`
- LLM 归一化：`backend/app/rag/normalizers/llm_normalizer.py`
- 文本质量判断：`backend/app/rag/text_quality.py`
- 入库 Agent 探测：`backend/app/agent/ingestion_agent.py`

**当前实现逻辑简述：**

- PDF 优先使用 PyMuPDF 提取文本和表格。
- 如果 PyMuPDF 不可用，会 fallback 到 pypdf。
- PyMuPDF 能识别的表格会转为 markdown 表格和行级事实文本。
- Markdown/TXT 直接读取文本。
- 如果 PDF 文本层为空、长度过低或质量不可用，并且 `.env` 开启 `PREPROCESS_OCR_FALLBACK_ENABLED=true`，会进入 PaddleOCR fallback。
- OCR 输出会保留页码、OCR 行数、平均置信度、低置信行数量、表格形态判断等 metadata。
- 如果 `PDF_REJECT_GARBLED_TEXT=true` 且文本不可用，同时 OCR 未启用或失败，则入库失败并记录错误。

**是否可以稳定运行：**

- 可读 PDF、TXT、Markdown：可以稳定演示。
- OCR：代码已接入，但依赖 PaddleOCR、PaddlePaddle、CUDA/cuDNN、模型路径和显卡架构，环境正确时可演示。
- 表格转写：对 PyMuPDF 可检测表格有效；对扫描件表格、复杂跨页表格仍不稳定。

**目前存在的问题或限制：**

- `.env.example` 中 OCR 默认关闭，需要明确开启。
- OCR 能识别文本，但自动还原复杂表格行列关系仍有限。
- 当前水印处理不是独立模块，只能依赖 OCR/文本质量规则间接过滤。

**面试时建议如何表述：**

> 文档解析会根据文件类型选择 loader。PDF 优先走 PyMuPDF 文本和表格解析，如果探测到文本层为空或乱码，会进入 OCR fallback。解析结果会保留文件名、页码、表格序号、chunk 类型和抽取方法，后续用于引用和质量分析。

**下一步建议优化内容：**

- 增加版面分析和表格结构恢复。
- 对 OCR 后的行列关系做更强的表格重建。
- 引入 MinerU/PaddleOCR PP-Structure 等文档解析引擎做对比。

---

## 5. 文档分块策略是怎么设计的？

**当前是否已实现：已完成基础规则分块，并加入质量评分。**

**相关代码文件路径：**

- 分块器：`backend/app/rag/chunkers/rule_chunker.py`
- 分块基类：`backend/app/rag/chunkers/base_chunker.py`
- chunk schema：`backend/app/rag/schemas.py`
- 质量评分：`backend/app/rag/chunk_quality.py`
- 入库调用：`backend/app/services/document_service.py`

**当前实现逻辑简述：**

- 默认 `CHUNK_SIZE=800`，`CHUNK_OVERLAP=120`。
- 分块是按每个 `LoadedDocumentPart` 的文本做固定长度滑窗切分，不是完整语义分块。
- 由于上游 `LoadedDocumentPart` 已经按页码、表格、OCR 页等粒度组织，因此 chunk 继承了页码和表格 metadata。
- 切块后会调用 `annotate_chunk_quality`，记录：
  - `chunk_quality_score`
  - `chunk_quality_label`
  - `chunk_quality_flags`
  - `text_length`
  - `line_count`
  - `short_line_ratio`
  - `numeric_line_ratio`
  - `is_table_like`
  - `needs_llm_normalization`
- 入库前会补充：
  - `document_id`
  - `owner_id`
  - `filename`
  - `file_type`
  - `chunk_index`
  - `status`

**是否可以稳定运行：**

- 规则分块和质量评分可以稳定运行。

**目前存在的问题或限制：**

- 目前还不是严格的标题/章节/条款感知分块。
- 对国标类文档已有页码、表格、行级事实增强，但条款层级和跨页表格合并仍不够强。

**面试时建议如何表述：**

> 分块不是只保存纯文本，而是把 document_id、filename、page、table_index、chunk_type、owner_id、chunk_index、质量评分等 metadata 一并写入向量库，用于引用追踪、权限过滤和后续低质量 chunk 的二次整理。

**下一步建议优化内容：**

- 增加国标条款识别，例如第 4.7.1、表 7、附录 A。
- 增加跨页表格合并。
- 引入 semantic chunking 或 heading-aware chunking。

---

## 6. BGE-M3 Embedding 是怎么接入的？

**当前是否已实现：已完成。**

**相关代码文件路径：**

- Embedding 封装：`backend/app/rag/embeddings.py`
- 配置：`backend/app/core/config.py`
- 示例配置：`backend/.env.example`
- 入库调用：`backend/app/services/document_service.py`
- 检索调用：`backend/app/rag/retriever.py`

**当前实现逻辑简述：**

- 使用 `sentence-transformers` 的 `SentenceTransformer` 加载 embedding 模型。
- `.env.example` 中 `EMBEDDING_MODEL_NAME` 指向本地 `data/models/embeddings/bge-m3`。
- `EMBEDDING_DEVICE=auto` 时会自动判断 CUDA 是否可用。
- 文档 chunk 通过 `embed_texts()` 批量生成向量，默认 batch size 为 16。
- 用户 query 通过 `embed_query()` 单独生成向量。
- 模型加载使用 `lru_cache` 缓存，避免每次请求重复加载模型。

**是否可以稳定运行：**

- 本地模型路径正确、torch/sentence-transformers 环境正确时可以稳定运行。

**目前存在的问题或限制：**

- 没有 chunk 级 embedding 缓存或内容去重；重新入库会重新生成向量。
- 代码默认值是 `BAAI/bge-small-zh-v1.5`，但 `.env.example` 已给出 BGE-M3 本地路径；简历写 BGE-M3 时要确保实际 `.env` 配置一致。

**面试时建议如何表述：**

> Embedding 模块被独立封装，文档 chunk 和用户问题都通过统一接口生成向量。目前使用 BGE-M3 本地模型路径配置，后续可以替换为其他本地模型或远程 embedding API。

**下一步建议优化内容：**

- 增加内容 hash，避免重复 embedding。
- 增加 embedding 批次失败重试。
- 评估 BGE-M3 dense+sparse 能力，进一步优化标准号和数值类检索。

---

## 7. ChromaDB 的 collection 和 metadata 是怎么设计的？

**当前是否已实现：已完成。**

**相关代码文件路径：**

- 向量库封装：`backend/app/rag/vector_store.py`
- 入库写入：`backend/app/services/document_service.py`
- 检索调用：`backend/app/rag/retriever.py`
- 配置：`backend/app/core/config.py`

**当前实现逻辑简述：**

- ChromaDB 使用 `PersistentClient`，持久化路径为 `data/chroma`。
- collection 名称为 `knowledge_chunks`。
- collection metadata 设置为 cosine 距离：`{"hnsw:space": "cosine"}`。
- chunk id 格式为 `doc:{document.id}:chunk:{index}`。
- 每个 chunk metadata 至少包含：
  - `document_id`
  - `owner_id`
  - `filename`
  - `file_type`
  - `chunk_index`
  - `status`
  - 上游解析带来的 `page`、`table_index`、`chunk_type`、`extraction_method` 等。
- 查询时支持按 `document_id` 或 `$in` 过滤。
- 删除文档时会按 `document_id` 删除对应向量。

**是否可以稳定运行：**

- 单机本地持久化可以稳定演示。

**目前存在的问题或限制：**

- 权限过滤主要是在 SQL 层先算出 allowed document ids，再传给 ChromaDB `where` 过滤；不是直接把复杂权限表达式全部放进 ChromaDB。
- ChromaDB 适合本地 demo 和中小规模知识库，生产级多租户和大规模并发需要进一步评估。

**面试时建议如何表述：**

> ChromaDB 负责存储 chunk 文本、向量和 metadata。检索时不会全库检索，而是先根据用户权限得到可访问 document_id，再通过 ChromaDB metadata filter 限制检索范围。

**下一步建议优化内容：**

- 增加 collection migration/version 机制。
- 增加向量库备份和重建脚本。
- 评估 Milvus/Qdrant/PGVector 作为后续扩展。

---

## 8. 混合检索目前是否实现？

**当前是否已实现：已完成基础版。向量 + 关键词 + BM25 混合召回已接入。**

**相关代码文件路径：**

- 检索编排：`backend/app/rag/retriever.py`
- 关键词检索：`backend/app/rag/keyword_retriever.py`
- BM25 检索：`backend/app/rag/bm25_retriever.py`
- 归一化 tokenizer：`backend/app/rag/search_tokenizer.py`
- Chroma 检索：`backend/app/rag/vector_store.py`
- 配置：`backend/app/core/config.py`

**当前实现逻辑简述：**

- 首先对 query 生成 embedding，在 ChromaDB 中做向量召回。
- 如果 `HYBRID_RETRIEVAL_ENABLED=true`，同时执行轻量关键词召回和 BM25 召回。
- 归一化 tokenizer 会处理 GB 标准号空格差异、`μg/ug/渭g` 单位差异、`10³/10^3` 上标差异、全角字符和中文 ngram。
- BM25 会在当前用户可访问的 chunk 范围内计算词频、文档频率和长度归一化分数。
- 合并时按 chunk id 去重，融合 `vector_score`、`keyword_score` 和 `bm25_score`。
- 默认权重：`HYBRID_VECTOR_WEIGHT=0.62`，`HYBRID_KEYWORD_WEIGHT=0.08`，`HYBRID_BM25_WEIGHT=0.30`。
- 纯关键词/BM25 召回不会直接把分数顶到 1.0，默认通过 `HYBRID_LEXICAL_ONLY_MAX_SCORE=0.82` 限制上限，避免干扰可靠的向量召回结果。

**是否可以稳定运行：**

- BM25 和关键词混合召回可以演示，对标准号、数值、单位、专有名词有帮助。

**目前存在的问题或限制：**

- 当前 BM25 是请求时从 ChromaDB 拉取权限范围内 chunk 后本地建索引打分，默认上限 `HYBRID_BM25_MAX_CHUNKS=3000`。
- 还没有持久化倒排索引，文档规模变大后需要迁移到 SQLite FTS5、专门搜索引擎或缓存索引。

**面试时建议如何表述：**

> 向量检索适合语义匹配，但标准号、添加剂名称、限量值、单位这类查询对关键词更敏感，所以系统实现了向量召回、关键词召回和 BM25 召回的混合检索，并在 tokenizer 中对标准号、单位和上标数字做归一化。

**下一步建议优化内容：**

- 将当前请求时 BM25 升级为持久化倒排索引或 SQLite FTS5。
- 继续扩展化学名、别名、单位换算和食品分类词典。
- 增加检索召回诊断页。

---

## 9. BGE Reranker 是否完成？如何使用？

**当前是否已实现：部分完成。代码已接入，可配置启用；稳定性取决于本地模型和依赖。**

**相关代码文件路径：**

- Reranker 封装：`backend/app/rag/reranker.py`
- 检索调用：`backend/app/rag/retriever.py`
- 配置：`backend/app/core/config.py`
- 示例配置：`backend/.env.example`
- 依赖：`backend/requirements-rag.txt`

**当前实现逻辑简述：**

- `RERANKER_ENABLED=true` 且 `RERANKER_MODEL_NAME` 非空时启用。
- `.env.example` 推荐本地 `data/models/rerankers/bge-reranker-v2-m3`。
- 初召回 candidate top_n 默认 `RERANKER_CANDIDATE_TOP_K=20`。
- Rerank 后保留前端或接口传入的 `top_k`，默认 `RAG_TOP_K=5`。
- 优先尝试 `FlagEmbedding.FlagReranker`，如果不可用则尝试 `sentence-transformers` 的 `CrossEncoder`。
- Reranker 加载失败或推理失败时会记录 warning，并降级返回原始检索结果。

**是否可以稳定运行：**

- 本地 reranker 模型和依赖正确时可以演示。
- 依赖缺失时不会使问答接口整体失败，会降级。

**目前存在的问题或限制：**

- Reranker 是同步推理，文档多或 top_n 大时会增加延迟。
- 没有单独的 reranker 服务化或批处理队列。

**面试时建议如何表述：**

> 系统先召回较多候选片段，再用 BGE Reranker 对 query-chunk pair 做相关性精排，最后取 top-k 进入 prompt。Reranker 可配置开关，失败时会降级到原始检索结果。

**下一步建议优化内容：**

- 增加 reranker latency 统计。
- 增加 GPU/CPU 切换提示。
- 尝试 bge-reranker-v2-m3 与 bge-reranker-base 的实际评测对比。

---

## 10. RAG 问答接口完整链路是什么？

**当前是否已实现：已完成基础版本。**

**相关代码文件路径：**

- 问答接口：`backend/app/api/chat.py`
- 问答服务：`backend/app/services/rag_service.py`
- 检索：`backend/app/rag/retriever.py`
- LLM 客户端：`backend/app/rag/llm_client.py`
- 日志：`backend/app/services/log_service.py`
- schema：`backend/app/schemas/chat.py`
- 前端问答：`frontend/src/App.vue`

**当前实现逻辑简述：**

- 接口路径：`POST /api/v1/chat/`。
- 需要登录，依赖 `get_current_user`。
- 请求体包含 `question`、可选 `document_ids`、`top_k`。
- 后端先计算当前用户可访问且状态为 `indexed` 的文档。
- 如果用户指定文档，则取指定文档和可访问文档的交集。
- 检索时只传入 allowed document ids。
- 检索后过滤低分、不可读、乱码 chunk。
- 有 LLM API Key 时调用 OpenAI-compatible API 生成 JSON 结构化答案。
- 没有 API Key 或 LLM 失败时，返回 retrieval-only 结果。
- 返回内容包括：
  - `answer`
  - `sections.classification`
  - `sections.conclusion`
  - `sections.basis`
  - `sections.citation`
  - `evidence_rows`
  - `citations`
  - `retrieval_only`
  - `log_id`
- 问答记录写入 `chat_logs`。

**是否可以稳定运行：**

- 检索链路可以运行。
- LLM 生成依赖 `.env` 中 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME`。

**目前存在的问题或限制：**

- 当前问答不是流式接口，前端等待阶段的进度条不是真实后端分阶段进度。
- LLM 客户端设置了 timeout，但未显式设置 max_tokens。
- 复杂问题、多跳引用和表格精确数值仍是当前评测薄弱点。

**面试时建议如何表述：**

> 问答接口会先做用户身份校验和权限过滤，再执行向量检索、关键词混合召回、可选重排、prompt 构造和 LLM 生成。回答包括分类判断、结论、依据、引用和检索证据表，并且证据不足时强制返回未找到，降低幻觉风险。

**下一步建议优化内容：**

- 改成任务轮询或 SSE/WebSocket 流式接口，展示真实检索/重排/生成进度。
- 对 prompt 输出做更严格 JSON schema 校验。
- 增加引用一致性验证。

---

## 11. Ingestion Agent 目前到底完成到什么程度？

**当前是否已实现：部分完成。是轻量入库调度 Agent，不是完整 LangGraph Agent。**

**相关代码文件路径：**

- Ingestion Agent：`backend/app/agent/ingestion_agent.py`
- 入库调用：`backend/app/services/document_service.py`
- 任务记录：`backend/app/models/document_job.py`

**当前实现逻辑简述：**

- 上传后进入 `agent_planning` 阶段。
- `probe_document()` 会对 PDF 进行轻量探测：
  - 文件大小
  - 页数
  - 抽样页数
  - 文本字符数
  - 表格数量
  - 可读性
  - 文本质量指标
  - 文本样本
  - 探测错误
- 规则规划会选择：
  - `pymupdf_text_table`
  - `pypdf_text`
  - `paddleocr`
  - 是否启用 `llm_table_normalizer`
- 如果 `INGESTION_AGENT_LLM_ENABLED=true` 且配置 API Key，会用 LLM 基于探测结果给出处理建议。
- LLM 规划会被规则安全门约束，例如不能关闭已判断必要的 OCR。
- 规划结果写入 `document_processing_jobs.plan_json` 和 `probe_json`。

**是否可以稳定运行：**

- 规则探测和规则规划可以运行。
- LLM 规划默认关闭，开启后依赖 LLM API。

**目前存在的问题或限制：**

- 没有使用 LangGraph。
- 没有工具调用循环，也没有多步反思/重试策略。
- 当前 Agent 主要影响文档入库，不参与在线问答。

**面试时建议如何表述：**

> 当前 Ingestion Agent 更准确地说是轻量文档处理调度模块。它先对上传文件做文本层、乱码、表格密度和可读性探测，再决定走 PyMuPDF、pypdf、PaddleOCR 或 LLM 表格归一化。第一版以规则为主，预留了 LLM 参与规划，后续会迁移到 LangGraph 状态节点。

**下一步建议优化内容：**

- 将 probe、plan、parse、ocr、normalize、index 拆成 LangGraph 节点。
- 增加失败重试和策略回退。
- 记录每个节点耗时、输入输出摘要。

---

## 12. LangGraph 问答 Agent 是否已经实现？

**当前是否已实现：未完成。当前只是预留。**

**相关代码文件路径：**

- `backend/app/agent/graph.py`
- `backend/app/agent/state.py`
- `backend/app/agent/nodes.py`
- `backend/app/agent/tools.py`
- 当前实际问答链路：`backend/app/services/rag_service.py`

**当前实现逻辑简述：**

- `state.py` 定义了简单 `AgentState`。
- `graph.py`、`nodes.py`、`tools.py` 目前直接抛出 `NotImplementedError`。
- `/api/v1/chat/` 当前没有调用 LangGraph，而是走 `RagService().answer()`。

**是否可以稳定运行：**

- LangGraph Agent 不可演示。
- 普通 RAG 问答链路可以演示。

**目前存在的问题或限制：**

- 不能在面试中说「已经实现 LangGraph 问答 Agent」。
- 可以说「已预留 Agent 目录，并优先完成普通 RAG 闭环；下一步把问答链路拆成 LangGraph 节点」。

**面试时建议如何表述：**

> 当前 RAG 问答链路已经完成，LangGraph 工作流正在重构中。我的设计目标是把权限获取、检索、上下文判断、答案生成、fallback 和日志记录拆成可观察节点，方便后续接入合规判断或工具调用。

**下一步建议优化内容：**

- 实现 `class AgentState` 的完整字段。
- 增加节点：question_classify、permission_scope、retrieve、rerank、context_check、generate、fallback、log。
- 设置最大步数和异常回退。

---

## 13. 日志、任务表和可观测性做到什么程度？

**当前是否已实现：部分完成。文档任务、问答日志、审计日志已实现，细粒度性能指标仍需补充。**

**相关代码文件路径：**

- 日志配置：`backend/app/core/logger.py`
- 文档任务模型：`backend/app/models/document_job.py`
- 文档任务服务：`backend/app/services/document_service.py`
- 问答日志模型：`backend/app/models/chat_log.py`
- 问答日志服务：`backend/app/services/log_service.py`
- 审计日志模型：`backend/app/models/group.py`
- 审计日志服务：`backend/app/services/permission_service.py`
- 日志接口：`backend/app/api/logs.py`
- 前端任务/质量/审计展示：`frontend/src/App.vue`

**当前实现逻辑简述：**

- Python logging 会记录启动、入库、检索、错误等信息。
- 文档任务表 `document_processing_jobs` 记录：
  - status/stage/message/error_message
  - probe_json/plan_json/options_json
  - progress_total/progress_current/progress_percent/progress_detail
  - started_at/finished_at/updated_at
- 问答日志 `chat_logs` 记录 user_id、question、answer、citations_json、created_at。
- 权限和用户组变更写入 `audit_logs`。
- 前端可以查看文档处理任务、质量报告、审计日志、问答历史，并支持删除单条问答历史。

**是否可以稳定运行：**

- 文档任务进度、问答历史、审计日志可以演示。

**目前存在的问题或限制：**

- chat_logs 没有单独记录 latency、token usage、retrieved_document_ids 字段；目前 retrieved 信息主要在 citations_json 内。
- 没有专门的后端日志查询页面，前端系统配置页主要展示权限/审计。
- 在线问答进度还不是后端真实任务进度。

**面试时建议如何表述：**

> 系统记录文档入库状态、入库 Agent 探测结果、问答日志、检索引用和权限变更审计，方便排查解析失败、检索失败、权限误配和 RAG 效果问题。

**下一步建议优化内容：**

- 给问答日志补充 latency、模型名、top_k、reranker 是否启用、retrieved_document_ids。
- 增加 RAG 调试面板。
- 增加错误类型枚举和失败重试记录。

---

## 14. 资源控制和稳定性目前有哪些实现？

**当前是否已实现：部分完成。已有基础限制和降级，生产级稳定性还需增强。**

**相关代码文件路径：**

- 配置：`backend/app/core/config.py`
- 文档入库资源控制：`backend/app/services/document_service.py`
- Embedding/Reranker 设备选择：`backend/app/rag/embeddings.py`、`backend/app/rag/reranker.py`
- OCR 子进程：`backend/app/rag/ocr/paddleocr_engine.py`
- LLM timeout：`backend/app/rag/llm_client.py`
- 检索参数限制：`backend/app/schemas/chat.py`

**当前实现逻辑简述：**

- 文件大小限制：默认 50 MB。
- 文件类型白名单：PDF/TXT/Markdown。
- 文档入库和 LLM 归一化通过进程内 `BoundedSemaphore` 控制并发，默认 `INGESTION_MAX_CONCURRENT_JOBS=1`。
- 后台任务等待时会把文档状态标记为 queued 或 llm_preprocessing_queued。
- 任务结束后尝试释放 torch/paddle GPU cache。
- 问答 `top_k` 限制在 1 到 20。
- RAG 上下文长度默认限制为 6000 字符。
- LLM client 设置 timeout，默认 60 秒。
- Reranker 加载或推理失败时会降级为原始检索结果。
- 无 API Key 时问答可以返回 retrieval-only。

**是否可以稳定运行：**

- 单机开发环境可运行。
- 一次上传大量文件时已具备基础串行入库控制，但不是生产级队列。

**目前存在的问题或限制：**

- 进程内 semaphore 在多 worker 或服务重启下不可持久化。
- 没有任务取消、重试次数、优先级、失败恢复。
- LLM 没有显式 max_tokens。
- 在线问答没有 GPU 并发控制。

**面试时建议如何表述：**

> 系统把文档入库这类重任务与在线问答分开，入库阶段记录任务状态并通过进程内并发限制避免 OCR/Embedding 同时占满显存。在线问答阶段限制 top_k、上下文长度、LLM timeout，并为 Reranker 和 LLM 配置失败降级。

**下一步建议优化内容：**

- 引入持久化任务队列。
- 增加 GPU 任务全局队列和显存水位监控。
- 增加 max_tokens、重试策略和熔断。

---

## 15. 当前项目哪些功能已经完成，哪些只是设计或待完成？

| 功能模块 | 状态 | 代码位置 | 能否演示 | 面试建议说法 |
| --- | --- | --- | --- | --- |
| 登录 / JWT | 已完成 | `backend/app/api/auth.py`、`backend/app/core/security.py` | 是 | 已实现基础用户认证，登录后用 JWT 访问后端接口。 |
| 用户注册 | 已完成 | `backend/app/api/auth.py`、`backend/app/services/auth_service.py` | 是 | 支持注册普通用户，初始 admin 可通过 `.env` seed。 |
| 用户角色 admin/user | 已完成 | `backend/app/models/user.py` | 是 | 通过 `is_admin` 区分管理员和普通用户。 |
| 用户组/部门权限 | 已完成 | `backend/app/models/group.py`、`backend/app/services/permission_service.py` | 是 | 已支持 group、user_group、group_permission。 |
| 审计与权限变更日志 | 已完成 | `backend/app/models/group.py`、`backend/app/services/permission_service.py` | 是 | 权限、用户组、成员变更会写入 audit_logs。 |
| 文档上传 | 已完成 | `backend/app/api/documents.py`、`backend/app/services/document_service.py` | 是 | 支持 PDF/TXT/Markdown 上传并后台入库。 |
| 上传者标记 | 已完成 | `backend/app/models/document.py`、`frontend/src/types.ts` | 是 | 文档记录 owner_id，并返回 owner_username。 |
| 文档权限 | 已完成 | `backend/app/models/permission.py`、`backend/app/models/group.py` | 是 | 支持 owner、直接用户授权、部门授权。 |
| 文档删除 | 已完成 | `backend/app/services/document_service.py` | 是 | admin 删除文档时同步删除 ChromaDB chunk 和源文件。 |
| PDF 解析 | 已完成基础版 | `backend/app/rag/loaders/pdf_loader.py` | 是 | PyMuPDF 优先，pypdf fallback。复杂 PDF 仍需 OCR/版面增强。 |
| TXT / Markdown 解析 | 已完成 | `backend/app/rag/loaders/txt_loader.py`、`markdown_loader.py` | 是 | 普通文本类文档可稳定入库。 |
| OCR fallback | 部分完成 | `backend/app/rag/ocr/paddleocr_engine.py`、`preprocessor.py` | 部分 | 代码已接入 PaddleOCR，环境和 `.env` 正确时可用；复杂表格仍需优化。 |
| 表格转写 | 部分完成 | `backend/app/rag/normalizers/table_normalizer.py` | 部分 | PyMuPDF 可识别表格会转 markdown 和行级事实；扫描件表格仍弱。 |
| LLM 表格/切块归一化 | 部分完成 | `backend/app/rag/normalizers/llm_normalizer.py` | 部分 | 可对低质量 OCR/表格 chunk 做二次整理，但依赖 LLM API，默认可开关。 |
| chunking | 已完成 | `backend/app/rag/chunkers/rule_chunker.py` | 是 | 当前是规则滑窗分块，并继承页码/表格来源 metadata。 |
| 分块质量分数 | 已完成 | `backend/app/rag/chunk_quality.py` | 是 | 每个 chunk 写入质量分、质量标签和是否需要 LLM 整理。 |
| BGE Embedding | 已完成 | `backend/app/rag/embeddings.py` | 是 | Embedding 独立封装，可配置本地 BGE-M3 路径。 |
| ChromaDB 入库 | 已完成 | `backend/app/rag/vector_store.py` | 是 | 向量和 metadata 持久化到 ChromaDB collection。 |
| 权限过滤检索 | 已完成 | `backend/app/services/rag_service.py`、`backend/app/rag/vector_store.py` | 是 | 先算可访问 document_id，再传入 ChromaDB where filter。 |
| 向量检索 | 已完成 | `backend/app/rag/retriever.py` | 是 | Query embedding 后在 ChromaDB 检索。 |
| 关键词混合检索 | 已完成 | `backend/app/rag/keyword_retriever.py` | 是 | 已实现轻量关键词打分召回，与向量和 BM25 结果融合。 |
| BM25 | 已完成基础版 | `backend/app/rag/bm25_retriever.py`、`backend/app/rag/search_tokenizer.py` | 是 | 已实现请求时 BM25 和归一化 tokenizer，后续可升级为持久化倒排索引/FTS5。 |
| BGE Reranker | 部分完成 | `backend/app/rag/reranker.py` | 部分 | 可配置本地 reranker，失败自动降级。 |
| RAG 问答 | 已完成 | `backend/app/api/chat.py`、`backend/app/services/rag_service.py` | 是 | 已完成权限过滤、检索、生成、未找到 fallback、日志记录。 |
| sources 引用 | 已完成 | `backend/app/schemas/chat.py`、`rag_service.py` | 是 | 返回 citations 和 evidence_rows，包含文件名、页码、chunk_id。 |
| 拒绝幻觉 prompt | 已完成 | `backend/app/services/rag_service.py` | 是 | prompt 要求证据不足返回 found=false/未找到。 |
| chat_logs | 已完成 | `backend/app/models/chat_log.py`、`backend/app/services/log_service.py` | 是 | 按用户保存问答历史和引用 JSON。 |
| 问答历史删除 | 已完成 | `backend/app/api/chat.py`、`frontend/src/App.vue` | 是 | 支持删除当前用户自己的问答记录。 |
| 文档处理任务表 | 已完成基础版 | `backend/app/models/document_job.py` | 是 | 记录入库阶段、错误和 LLM 归一化进度。 |
| 文档处理质量报告 | 已完成 | `backend/app/services/document_service.py`、`frontend/src/App.vue` | 是 | 前端可查看 chunk 类型分布、质量分、OCR/LLM 情况和建议。 |
| Ingestion Agent | 部分完成 | `backend/app/agent/ingestion_agent.py` | 是 | 当前是轻量规则调度 + 可选 LLM 规划，不是完整 LangGraph。 |
| LangGraph 问答 Agent | 未完成 | `backend/app/agent/graph.py`、`nodes.py`、`tools.py` | 否 | 当前只是预留目录，问答仍走 `RagService`。 |
| Vue3 前端 | 已完成可演示版 | `frontend/src/App.vue`、`frontend/src/api/client.ts` | 是 | 已有上传、列表、问答、系统配置页面；后续需组件化拆分。 |
| 系统配置页 | 部分完成 | `frontend/src/App.vue` | 是 | 目前主要放部门/权限/审计管理，不是完整配置中心。 |
| 任务队列 | 部分完成 | `backend/app/services/document_service.py` | 部分 | 进程内 semaphore 控制并发，不是持久化队列。 |
| GPU 并发控制 | 部分完成 | `backend/app/services/document_service.py` | 部分 | 入库/LLM 整理有并发限制和 cache 释放，在线问答未做全局 GPU 队列。 |
| RAG 测试集 | 部分完成 | `data/eval/`、`backend/app/services/evaluation_service.py` | 是 | 已有 70 题测试集和接口，当前报告显示整体通过率 72.86%。 |
| README / 启动文档 | 部分完成 | `README.md`、`backend/README.md` | 是 | 已有文档，但应继续同步最新权限、队列、Agent 状态。 |

---

## 面试时最稳妥的一句话版本

> 这是一个本地企业知识库 RAG 系统，已经实现 Vue3 前端、FastAPI 后端、JWT 登录、文档上传、PDF/TXT/Markdown 解析、OCR fallback、BGE Embedding、ChromaDB 入库、权限过滤检索、关键词混合召回、可选 BGE Reranker、DeepSeek 兼容 API 生成答案、引用返回、问答日志和权限审计。Agent 部分目前主要落在文档入库阶段，是规则探测加可选 LLM 决策的轻量 Ingestion Agent；LangGraph 问答 Agent 还在预留和重构中。

## 简历表述边界

可以写：

- 设计并实现多用户权限控制的 RAG 知识库系统。
- 接入 BGE Embedding、ChromaDB、DeepSeek-compatible LLM API、PaddleOCR fallback。
- 实现基于 owner/user/group 的文档级权限控制，并在检索阶段按权限过滤。
- 引入轻量 Ingestion Agent，对 PDF 可读性、表格密度、OCR 需求进行探测并选择处理路径。
- 实现向量检索 + 关键词混合召回 + 可选 BGE Reranker 精排。
- 建立文档处理任务表、chunk 质量评分、问答日志和权限审计日志，支持问题排查和效果评估。

不建议写成：

- 已完整实现 LangGraph Agent。
- 已实现生产级任务队列。
- 已实现生产级持久化 BM25/倒排索引。
- OCR 和复杂表格解析已完全稳定。
- 已完成企业级多租户权限系统。
