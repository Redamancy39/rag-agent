# Backend

FastAPI + SQLAlchemy + JWT 后端，包含文档/文档集权限、受控入库节点、混合检索和异步问答任务。完整项目能力与 Windows 一键启动见 [根 README](../README.md)。

## 环境与配置

完整 Windows RAG/OCR 固定组合验证版本为 Python 3.12。基础接口依赖为 `requirements.txt`；本地模型准备分别见 [LOCAL_RAG](../docs/LOCAL_RAG.md) 和 [LOCAL_OCR](../docs/LOCAL_OCR.md)。历史 `requirements-rag.txt`、`requirements-ocr.txt` 不与本地固定版本同时安装。

```powershell
# 仓库根目录
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
```

已有 `.env` 时不要覆盖。手动启动前设置随机 `SECRET_KEY`；管理员密码和 API Key 在示例中留空，按需自行填写。初始化只创建配置的初始管理员，不重置既有账号密码。

`OPENAI_MODEL_NAME` 是实际模型字段，API 地址、Key 和窗口预算须按提供商配置。数组字段如 `CORS_ORIGINS` 使用 JSON 格式。相对数据/模型路径按后端工作目录解释。

普通文本的 `CHUNK_SIZE=800`、`CHUNK_OVERLAP=120` 按 Python 字符切片计数，不是词数或模型 token；表格使用按行切块策略。

## 运行

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查 `/health`，接口文档 `/docs`，业务前缀 `/api/v1`。手动 uvicorn 读取 `.env`，不会自动加载 Windows 启动器的 `.env.rag`、`.env.ocr`、`.env.llm` 模式；推荐用根目录 `START_LOCAL.bat` 复用独立配置。生产运行需要另外规划进程管理、HTTPS、数据库和任务队列。

## 关键接口

以在线 `/docs` 为完整契约：

| 接口 | 用途 |
| --- | --- |
| `/auth/register`、`/auth/login`、`/auth/me` | 账号与 JWT |
| `/documents/` | 只返回有权访问的文档 |
| `/documents/upload` | 上传，重复内容返回 HTTP 200，新的文档 HTTP 201 |
| `/documents/{id}/jobs`、`/quality-report`、`/chunks` | 入库状态、质量与切块 |
| `/documents/{id}/normalize-chunks` | 显式候选整理 |
| `/document-collections/` | 文档集管理及授权 |
| `/chat/`、`/chat/jobs`、`/chat/jobs/{id}` | 同步或后台问答 |
| `/chat/query-preview`、`/chat/hotwords` | 已登录用户的本地术语预检与词表 |
| `/chat/history` | 当前账号会话记录 |

传入文档 ID 不能绕过权限；后台回答继续校验账号和文档范围。预检不读私有文档、不创建问答任务、不调用模型。

## 数据与后台任务

默认 SQLite `data/app.db`，源文件 `data/uploads/`，向量 `data/chroma/`。启动时补充兼容字段（内容指纹、问答参数快照），更新前先备份。模型、源文件、业务数据库与本机恢复检查点均不纳入 Git。

入库使用 FastAPI 后台任务和本地并发控制，问答使用进程内工作线程，不是独立持久队列。退出网页账号不取消已提交入库任务，但停止后端会影响处理。恢复服务只消费明确的本机检查点，不自动扫描重试所有失败文档。

候选整理预算、实际 LLM 状态和内容外发边界见 [LOCAL_LLM](../docs/LOCAL_LLM.md)。

## 测试

```powershell
# 回到仓库根目录
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
```

本版后端 122 项通过。单元测试使用合成数据、模拟客户端或隔离数据库；真实 GPU/OCR 验证另有显式脚本，付费模型评测也另行执行，不能混为同一种验证。
