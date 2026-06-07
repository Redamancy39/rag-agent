# RAG Agent KB System

多用户权限控制的企业知识库 RAG Agent 系统。当前项目已经形成可演示的主链路：用户登录后上传企业文档，系统完成文件探测、PDF/OCR/表格解析、切块质量评估、LLM 切块整理、向量化入库，并在问答阶段按用户权限范围执行混合检索、Reranker 精排、证据约束生成和引用返回。

当前更准确的项目定位是：

- **RAG 知识库系统**：支持文档上传、解析、分块、Embedding、ChromaDB 入库、权限过滤检索、引用返回和问答日志。
- **轻量 Ingestion Agent**：已接入规则化文件探测与处理策略选择，负责判断是否需要 OCR、表格增强和 LLM 切块整理。
- **高可靠问答链路**：在线问答使用单轮、权限约束的 RAG 流程；复杂问题按需拆成最多 3 条子查询并批量召回，简单问题仍只检索一次，不执行多轮 Agent 重试；生成后校验 `[n]` 引用编号与实际证据来源。

## 当前完成度

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| 前端 | 已跑通 | Vue3 + Vite + TypeScript + Element Plus，包含上传、文档列表、问答测试、系统配置、权限管理和质量报告展示 |
| 后端 | 已跑通 | FastAPI + SQLAlchemy + Pydantic + JWT，接口按 `api / services / models / schemas / rag` 分层 |
| 业务数据库 | 已接入 | SQLite，保存用户、文档、权限、部门、任务、审计和问答日志 |
| 向量数据库 | 已接入 | ChromaDB，持久化目录为 `data/chroma` |
| Embedding | 已接入 | BGE Embedding，模型路径通过 `.env` 配置 |
| Reranker | 已接入 | BGE Reranker，可配置开启/关闭 |
| OCR | 已接入 | PaddleOCR fallback，用于扫描件或文本层质量差的 PDF |
| 混合检索 | 已接入 | 向量召回 + BM25 + 关键词召回 + Reranker 精排 |
| 权限系统 | 已接入 | owner、用户授权、部门授权；后端接口和 RAG 检索阶段都做权限过滤 |
| 日志与可观测性 | 已接入 | 文档处理任务、质量报告、问答日志、权限审计日志 |
| 问答侧 Agent | 有意收缩 | 不启用多轮自主检索；保留规则化查询归一化、证据判断和引用校验，控制延迟与 API 成本 |

## 面试演示主线

推荐演示顺序：

1. 使用管理员账号登录，展示左侧独立的“文档上传 / 文档列表 / 问答测试 / 系统配置”工作区。
2. 在“系统配置”页展示“面试演示总览”“RAG Agent 流程”和“能力矩阵”，说明系统不是单页 demo，而是完整工程链路。
3. 在“文档上传”页展示 LLM 整理开关和上传进度，说明 OCR / LLM / Embedding 是重任务，已经做任务状态记录和并发控制。
4. 在“文档列表”页展示上传者、状态、分块数、处理任务、质量报告、权限管理和管理员删除。
5. 打开质量报告，展示健康分、风险等级、内容类型分布、处理阶段概览和优化建议。
6. 打开权限管理弹窗，展示用户授权和部门授权，强调权限在后端接口和检索阶段生效。
7. 在“问答测试”页选择多个文档提问，展示分类判断、结论、依据、引用和默认折叠的检索依据。

更详细的展示话术和功能边界见 [docs/DEMO_AGENT_SHOWCASE.md](docs/DEMO_AGENT_SHOWCASE.md)。

## RAG 链路

```text
登录/JWT
  -> 上传文档
  -> Ingestion Agent 文件探测
  -> PDF / DOCX / PPTX / XLSX / Markdown / TXT 解析
  -> OCR fallback / 表格事实化 / LLM 切块整理
  -> 规则分块 + chunk 质量评分
  -> BGE Embedding
  -> ChromaDB 入库
  -> 用户/部门权限过滤
  -> 问题归一化 + 复杂问题按需分解
  -> 向量 + BM25 + 关键词混合召回
  -> BGE Reranker 精排
  -> 规则证据充分性判断
  -> 证据约束 Prompt
  -> LLM 生成带 [n] 标注的四行结构化答案
  -> 后端校验引用编号并绑定文件/页码/表号/块 ID
  -> 返回可点击来源 + 写入问答日志
```

回答格式默认按以下结构返回：

- 分类判断
- 结论
- 依据
- 引用

如果检索证据不足，Prompt 要求模型返回“未找到”，避免在企业内部知识库场景中无依据发挥。

## 技术栈

### 前端

- Vue3
- Vite
- TypeScript
- Element Plus

### 后端

- FastAPI
- SQLAlchemy
- Pydantic
- JWT
- Python logging

### 数据与模型

- SQLite：业务数据
- ChromaDB：向量数据
- BGE Embedding：文档和问题向量化
- BGE Reranker：候选片段精排
- PaddleOCR：OCR fallback
- DeepSeek API：OpenAI-compatible LLM

## 目录结构

```text
rag-agent-kb-system/
  backend/
    app/
      api/              # FastAPI 路由
      core/             # 配置、安全、日志
      db/               # SQLAlchemy session 和初始化
      models/           # ORM 模型
      schemas/          # Pydantic schema
      services/         # 业务服务
      rag/              # loader、chunker、embedding、retriever、reranker、OCR
      agent/            # Ingestion Agent 和 LangGraph 预留目录
    scripts/            # 评测和数据集脚本
    .env.example
    requirements.txt
  frontend/
    src/
      api/
      App.vue
      styles.css
      types.ts
  data/
    uploads/            # 本地原始文件，不提交真实内容
    chroma/             # ChromaDB 持久化目录，不提交真实内容
    logs/               # 运行日志，不提交真实内容
    models/             # 本地模型目录，不提交真实内容
    eval/               # RAG 测试集和评测结果
  docs/
```

## 环境准备

建议使用 conda：

```powershell
conda create -n rag-agent python=3.11
conda activate rag-agent
cd E:\rag_project\rag-agent-kb-system\backend
pip install -r requirements.txt
```

前端依赖：

```powershell
cd E:\rag_project\rag-agent-kb-system\frontend
npm install
```

## 配置

复制环境变量模板：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
copy .env.example .env
```

关键配置放在 `backend/.env`，不要提交真实 `.env`：

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat

EMBEDDING_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/embeddings/bge-m3
RERANKER_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/rerankers/bge-reranker-v2-m3
CHROMA_DIR=E:/rag_project/rag-agent-kb-system/data/chroma
UPLOAD_DIR=E:/rag_project/rag-agent-kb-system/data/uploads
```

本地模型建议放在：

```text
data/models/embeddings/bge-m3
data/models/rerankers/bge-reranker-v2-m3
data/models/ocr/paddleocr
```

模型下载和放置说明见 [docs/MODEL_ASSETS.md](docs/MODEL_ASSETS.md)。

## 启动

后端：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
conda activate rag-agent
uvicorn app.main:app --reload
```

前端：

```powershell
cd E:\rag_project\rag-agent-kb-system\frontend
npm run dev
```

默认访问：

- 后端健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 前端页面：[http://127.0.0.1:5173](http://127.0.0.1:5173)

## 评测

当前 v2 测试集包含 500 条问题。最近一次基于清理后测试集的离线重判结果为：

```text
452 / 500 = 90.40%
```

完整评测会调用 LLM API，耗时和 token 成本都较高，建议只在关键版本节点运行：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
python scripts\run_rag_eval.py `
  --username admin `
  --testset ..\data\eval\rag_testset_v2.json `
  --output ..\data\eval\results\rag_eval_v2_latest.json
```

离线重判旧结果：

```powershell
python scripts\rejudge_rag_eval.py `
  --result ..\data\eval\results\rag_eval_v2_after_gb2760_fix.json `
  --testset ..\data\eval\rag_testset_v2.json
```

## 当前工程边界

- 当前 Agent 更准确地说是轻量 Ingestion Agent，不应包装成完整自主 Agent。
- 在线问答采用单轮受控 RAG 链路：权限过滤、查询归一化、按需查询分解、混合检索、精排、证据判断、生成和引用校验。查询分解只扩展同一轮候选召回，不触发自动反思和多轮重试。
- 文档处理任务目前使用 FastAPI BackgroundTasks + 本地 semaphore，后续可以迁移到 Celery / RQ。
- 当前业务库是 SQLite，生产环境可以迁移 PostgreSQL。
- ChromaDB 负责向量和 metadata 检索；后续建议增加 `document_chunks` 表，把 chunk 正文同步保存到 SQLite，提升 BM25 和质量报告稳定性。

## 后续路线

下一阶段优先增强文档适配和可解释性：

1. **Ingestion Agent 节点化**
   - FileProbe
   - StrategyPlanner
   - Parse/OCR
   - Normalize
   - ChunkQuality
   - Index
   - QualityReport

2. **多类型文档与统一来源定位**
   - 已完成 DOCX 标题层级、连续段落和表格行解析
   - 已完成 PPTX 幻灯片、文本框、表格和演讲者备注解析
   - 已完成 XLSX 工作表、数据区域、表头、公式和单元格范围解析
   - 已完成统一 `DocumentBlock` 中间结构，现有 PDF / DOCX / PPTX / XLSX / TXT / Markdown
     解析结果均转换为格式无关的文本块、内容类型、提取方式和来源定位
   - PDF 页码 / DOCX 标题路径 / PPTX 幻灯片 / XLSX 工作表与单元格范围等来源定位
   - 检索、引用、质量报告和前端统一使用 `SourceLocator` 的位置类型、稳定键和中文标签

3. **工程稳定性**
   - 增加 `document_chunks` SQLite 表
   - 完善任务队列和 GPU 并发控制
   - 增加失败任务重试和可恢复入库
   - 增加更细粒度的质量报告和失败案例分析

## 相关文档

- [面试展示说明](docs/DEMO_AGENT_SHOWCASE.md)
- [模型文件说明](docs/MODEL_ASSETS.md)
- [PDF 预处理策略](docs/PDF_PREPROCESSING.md)
- [切块质量检查](docs/CHUNK_QUALITY_CHECK.md)
- [Ingestion Agent 设计](docs/INGESTION_AGENT_DESIGN.md)
- [DocumentBlock 统一中间结构](docs/DOCUMENT_BLOCK.md)
- [OCR GPU 与 MinerU 评估](docs/OCR_GPU_AND_MINERU.md)
- [OCR、切块质量与 LLM 归一化](docs/OCR_CHUNK_QUALITY_LLM.md)
- [用户组、部门权限与审计日志](docs/PERMISSION_AUDIT.md)
- [BM25 混合检索说明](docs/BM25_HYBRID_RETRIEVAL.md)

## Git 注意事项

以下内容不应提交到 GitHub：

- `backend/.env`
- API Key、Base URL 中的私密 token
- `data/uploads/` 中的真实文档
- `data/chroma/` 和 `data/chroma_db/` 中的向量库持久化数据
- `data/models/` 中的本地模型权重
- `data/logs/` 中的运行日志

仓库中只保留 `.env.example`、`.gitkeep`、源码、文档和可复现实验资产。
