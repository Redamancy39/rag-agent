# Backend

阶段 2 后端，基于 FastAPI、SQLAlchemy、Pydantic、JWT、ChromaDB 和 BGE Embedding。

## 1. 创建环境

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

推荐 Python 版本：`3.10` 或 `3.11`。只启动后端基础接口时，不需要 Node.js、PostgreSQL、CUDA 或本地大模型。

需要上传入库时，再安装 RAG 依赖：

```powershell
pip install -r requirements-rag.txt
```

扫描版 PDF 需要 OCR fallback 时，再安装 OCR 依赖：

```powershell
pip install -r requirements-ocr.txt
```

如果使用 HuggingFace 模型名，例如 `BAAI/bge-small-zh-v1.5`，首次上传入库时会下载模型。没有外网时，可以提前把模型下载到本地，并把 `.env` 中的 `EMBEDDING_MODEL_NAME` 改成本地路径。

## 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

至少修改：

- `SECRET_KEY`
- `FIRST_SUPERUSER_USERNAME`
- `FIRST_SUPERUSER_PASSWORD`

Embedding、ChromaDB 相关配置已在阶段 2 使用。LLM 配置会在阶段 3 问答接口中使用。

DeepSeek API 配置写在 `backend/.env`：

```env
OPENAI_API_KEY=你的 DeepSeek API Key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL_NAME=deepseek-v4-flash
```

当前本地 `.env` 已配置好 `OPENAI_BASE_URL` 和 `OPENAI_MODEL_NAME`，只需要补 `OPENAI_API_KEY`。

上传入库阶段的大模型结构化预处理默认关闭。需要让 DeepSeek 参与表格行整理时，开启：

```env
PREPROCESS_LLM_ENABLED=true
PREPROCESS_LLM_TARGET_CHUNK_TYPES=["table_row_fact"]
```

扫描版 PDF 的 PaddleOCR fallback 默认关闭。需要对无法提取文本的 PDF 启用时，开启：

```env
PREPROCESS_OCR_FALLBACK_ENABLED=true
OCR_MIN_EXTRACTED_CHARS=50
PDF_REJECT_GARBLED_TEXT=true
```

`PDF_REJECT_GARBLED_TEXT=true` 会拒绝 `/G21`、控制字符、`Ã/Â` 等明显不可读的 PDF 文本层；如果同时开启 OCR fallback，系统会自动用 OCR 结果替代坏文本层。

注意：`CORS_ORIGINS` 和 `ALLOWED_FILE_EXTENSIONS` 在 `.env` 中使用 JSON 数组格式，例如：

```env
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
ALLOWED_FILE_EXTENSIONS=[".txt",".md",".markdown",".pdf"]
```

## 3. 启动

```powershell
uvicorn app.main:app --reload
```

健康检查：

```text
GET http://127.0.0.1:8000/health
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 4. 阶段 1/2 接口

### 注册

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "username": "demo_user",
  "email": "demo@example.com",
  "password": "demo123456"
}
```

### 登录

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "demo_user",
  "password": "demo123456"
}
```

返回：

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

### 当前用户

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

### 文档列表

```http
GET /api/v1/documents/
Authorization: Bearer <access_token>
```

### 文档切块预览

```http
GET /api/v1/documents/{document_id}/chunks?limit=100
Authorization: Bearer <access_token>
```

该接口只返回当前用户有权限访问的文档切块，用于检查已经写入 ChromaDB 的文本质量、页码和表格转写效果。

### RAG 问答

```http
POST /api/v1/chat/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "question": "较大婴儿配方食品中蛋白质含量要求是多少？",
  "document_ids": [8],
  "top_k": 5
}
```

当前问答策略默认拒绝幻觉：

- 只在当前用户有权限的 `indexed` 文档内检索。
- 检索结果会按相关度和可读性过滤。
- 如果没有可靠片段，直接返回 `未找到相关答案。`。
- 如果配置了 DeepSeek API，也要求模型只根据引用片段回答；证据不足时仍必须返回 `未找到相关答案。`。
- 如果未配置 `OPENAI_API_KEY`，接口会返回检索结果，不调用大模型。

### 上传并入库文档

```http
POST /api/v1/documents/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file=<txt/md/pdf file>
```

PowerShell 示例：

```powershell
$token = "<access_token>"
curl.exe -X POST "http://127.0.0.1:8000/api/v1/documents/upload" `
  -H "Authorization: Bearer $token" `
  -F "file=@E:\path\to\demo.md"
```

上传成功后，原始文件保存到 `data/uploads/<user_id>/`，分块和向量写入 `data/chroma`。

PDF 入库策略：

- 优先使用 PyMuPDF 提取页面正文和表格。
- 正文块标记为 `chunk_type=page_text`。
- 表格会额外生成 `chunk_type=table_markdown` 和 `chunk_type=table_row_fact`。
- 表格行会转成类似“某添加剂在某食品中的限量为多少”的检索事实，并保留页码、表格序号和表题。
- 写入 Chroma 的文本会加上来源文件、页码、内容类型等前缀，方便后续引用溯源。

## 5. 数据与日志

- SQLite 默认路径：`E:\rag_project\rag-agent-kb-system\data\app.db`
- 上传目录：`E:\rag_project\rag-agent-kb-system\data\uploads`
- ChromaDB 目录：`E:\rag_project\rag-agent-kb-system\data\chroma`
- 日志目录：`E:\rag_project\rag-agent-kb-system\data\logs`

## 6. 基础校验

```powershell
python -m compileall -q app
python -c "from app.db.init_db import init_db; init_db(); from app.main import app; print('app ok', len(app.routes))"
```

当前阶段已验证注册、登录和 `GET /api/v1/auth/me` 的 JWT 闭环。

阶段 2 的上传入库依赖 `requirements-rag.txt`，如果未安装，后端仍可启动，但上传接口会返回明确的依赖缺失错误。

## 7. 管理员删除文档

```http
DELETE /api/v1/documents/{document_id}
Authorization: Bearer <admin_access_token>
```

该接口仅管理员可用。删除时会尽量同时清理 SQLite 文档记录、权限记录、`data/uploads` 下的原始文件，以及 ChromaDB 中该 `document_id` 对应的向量切块。

## 8. GPU 说明

当前环境如果显示 `torch ... +cpu` 且 `torch.cuda.is_available()` 为 `False`，Embedding 和检索 query embedding 都会走 CPU。机器有 NVIDIA GPU 时，可按 PyTorch 官方安装页选择 Windows、Conda/Pip 和对应 CUDA 版本后安装 GPU 版 PyTorch。

## 9. Ingestion Agent 预处理策略

当前已接入轻量入库 Agent，不是完整 LangGraph 工作流。上传文件后会先执行轻量探测，再生成处理计划：

- PDF 探测：采样前几页，记录页数、文本字符数、表格数、可读性、文本质量和错误信息。
- 规则兜底：文本层不可读或字符数过低时选择 OCR；表格明显时开启 LLM 表格归一化。
- LLM 规划：`INGESTION_AGENT_LLM_ENABLED=true` 且配置了 OpenAI-compatible API 时，会让 DeepSeek 等模型基于探测结果给出处理建议；规则仍作为安全兜底。
- 任务记录：`document_processing_jobs.probe_json` 保存探测结果，`plan_json` 保存最终策略。前端文档列表点击“任务”可查看。

相关配置：

```env
INGESTION_AGENT_ENABLED=true
INGESTION_AGENT_LLM_ENABLED=true
INGESTION_AGENT_SAMPLE_PAGES=3
INGESTION_EXECUTOR=pipeline
```

如果上传速度或 API 成本敏感，可以先把 `INGESTION_AGENT_LLM_ENABLED=false`，系统仍会使用规则规划 PyMuPDF / pypdf / PaddleOCR / LLM 表格预处理。

`INGESTION_EXECUTOR` 默认使用稳定的 `pipeline`。如果已经安装 `requirements-rag.txt` 中的 `langgraph`，可以改为：

```env
INGESTION_EXECUTOR=langgraph
```

当前 LangGraph 执行器是顺序图适配层，复用同一批 FileProbe、StrategyPlanner、Parse/OCR、Normalize、ChunkQuality、Index、Report 节点；如果未安装 LangGraph，会自动回退到 `pipeline`，不影响入库。
当前图中已显式加入两个轻量条件路由：

- `RouteTextFirst / RouteOcrFirst`：展示策略选择文本层优先还是 OCR 优先。
- `RouteLlmNormalize / RouteSkipLlmNormalize`：展示是否进入 LLM 切块整理路径。

路由节点只负责可观测决策，真正的解析、OCR fallback 和 LLM 整理仍由后续业务节点执行。

环境自检：

```powershell
conda activate rag-agent
python scripts\check_runtime.py
```

该脚本会检查当前 Python、LangGraph、日志目录、SQLite 和 Chroma 目录是否可用。若主日志目录不可写，系统会自动回退到 `backend/.runtime_logs`。

单机 GPU 环境建议限制入库并发，避免同时上传多个 PDF 时 PaddleOCR、Embedding 和 LLM 整理一起占用显存：

```env
INGESTION_MAX_CONCURRENT_JOBS=1
RELEASE_GPU_CACHE_AFTER_INGESTION=true
```

当前实现为 FastAPI 进程内队列，适合本地演示和单机开发；后续如果需要多进程或服务器部署，应升级为 Redis/RQ、Celery 或独立 worker。

## 10. 用户组/部门权限与审计日志

当前已经支持管理员维护用户组/部门，并按部门给文档批量授权。普通用户最终可访问范围为：

- 自己上传的文档。
- 管理员直接授权给该用户的文档。
- 用户所在部门/用户组被授权的文档。

这些权限会在后端文档列表、文档详情、切块预览、质量报告和 RAG 检索阶段统一生效，不依赖前端隐藏按钮。

管理员接口：

```http
GET /api/v1/permissions/groups
POST /api/v1/permissions/groups
GET /api/v1/permissions/groups/{group_id}/members
POST /api/v1/permissions/groups/{group_id}/members
GET /api/v1/permissions/documents/{document_id}/group-permissions
POST /api/v1/permissions/group-permissions
GET /api/v1/permissions/audit-logs?limit=100
```

前端入口：

- `系统配置`：创建部门、维护成员、查看权限审计日志。
- `文档列表 -> 权限`：按用户授权或按部门授权。

详细说明见 `docs/PERMISSION_AUDIT.md`。
