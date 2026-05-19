                                        # RAG Agent KB System

多用户权限控制的 RAG Agent 知识库系统。当前处于阶段 2：文件上传、解析、分块和 ChromaDB 入库。

## 当前已完成

- FastAPI 后端工程骨架。
- SQLAlchemy + SQLite 数据库连接和自动建表。
- 用户、文档、权限、问答日志数据模型。
- 注册、登录、JWT 鉴权、当前用户接口。
- 用户、文档、权限、日志路由骨架。
- Vue3 + Element Plus 文档上传测试工作台。
- txt、markdown、pdf 文档上传和文件类型识别。
- 规则分块、BGE Embedding 封装和 ChromaDB 持久化入库。
- Agent 目录预留。
- `data/uploads`、`data/chroma`、`data/logs` 本地数据目录。


## 当前环境要求

- Python 3.10 或 3.11。
- SQLite 使用 Python 内置能力，不需要单独安装数据库。
- 阶段 2 上传入库需要安装 `backend/requirements-rag.txt`。
- 不需要 PostgreSQL；SQLite 仍是当前默认业务数据库。
- 不强制需要 CUDA；CPU 可以运行 BGE embedding，但首次加载模型会较慢。
- 阶段 4 做前端时再需要 Node.js。

## 模型文件

本地模型建议统一放到 `data/models/` 下。详细清单见 [docs/MODEL_ASSETS.md](docs/MODEL_ASSETS.md)。

当前本地配置使用：

- Embedding：`data/models/embeddings/bge-m3`
- Reranker：`data/models/rerankers/bge-reranker-v2-m3`
- OCR：`data/models/ocr/paddleocr`
- LLM：DeepSeek API，配置在 `backend/.env`

PDF 表格预处理策略见 [docs/PDF_PREPROCESSING.md](docs/PDF_PREPROCESSING.md)。

上传后的切块抽查方法见 [docs/CHUNK_QUALITY_CHECK.md](docs/CHUNK_QUALITY_CHECK.md)。

OCR fallback 和 DeepSeek 结构化预处理见 [docs/INGESTION_PREPROCESSING_V2.md](docs/INGESTION_PREPROCESSING_V2.md)。
入库 Agent 的“轻量探测 -> 处理策略 -> 工具执行 -> 任务记录”设计见 [docs/INGESTION_AGENT_DESIGN.md](docs/INGESTION_AGENT_DESIGN.md)。
OCR GPU 切换与 MinerU 初步评估见 [docs/OCR_GPU_AND_MINERU.md](docs/OCR_GPU_AND_MINERU.md)。
OCR 行级增强、切块质量评分与 LLM 归一化见 [docs/OCR_CHUNK_QUALITY_LLM.md](docs/OCR_CHUNK_QUALITY_LLM.md)。
用户组/部门权限、检索权限过滤和权限变更审计日志见 [docs/PERMISSION_AUDIT.md](docs/PERMISSION_AUDIT.md)。

## 目录

```text
rag-agent-kb-system/
  backend/
    app/
    requirements.txt
    .env.example
    README.md
  frontend/
    src/
  data/
    uploads/
    chroma/
    logs/
```

## 下一阶段

阶段 3 将实现基于权限范围的 ChromaDB 检索、OpenAI-compatible LLM 问答、引用来源返回和问答日志记录。
