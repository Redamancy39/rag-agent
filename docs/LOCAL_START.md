# Windows 本地启动

在仓库根目录双击 `START_LOCAL.bat`，或执行：

```powershell
.\START_LOCAL.bat -NoBrowser
.\START_LOCAL.bat -Action check
.\STOP_LOCAL.bat
```

页面为 http://127.0.0.1:5173，API 为 http://127.0.0.1:8000。关闭启动窗口不结束后台服务。

## 首次准备

需要 Python 和 Node.js/npm。优先复用根目录 `.venv`；没有时从 Python launcher、`RAG_PYTHON` 或可用 Python/conda 环境创建。启动器识别 3.10–3.13，但完整 RAG/OCR 固定组合只在 Windows Python 3.12 验证，推荐 3.12。

启动器按需安装 `backend/requirements.txt` 的基础依赖和前端 npm 依赖，初次需要网络。损坏的现有虚拟环境保留并报错，不自动覆盖。

没有 `backend/.env` 时生成随机 JWT 密钥，留空 API Key 和管理员密码。普通账号可注册；初始管理员自行填写 `FIRST_SUPERUSER_USERNAME`、`FIRST_SUPERUSER_PASSWORD`。已有账号、权限和配置保留。

## 模型与模式

基础启动不自动安装 RAG/OCR 依赖或下载模型。分别按 [LOCAL_RAG.md](LOCAL_RAG.md)、[LOCAL_OCR.md](LOCAL_OCR.md)、[LOCAL_LLM.md](LOCAL_LLM.md) 准备 `.env.rag`、`.env.ocr`、`.env.llm`。

缺少 `.env.llm` 时默认离线；额外规划/证据判断 LLM 开关关闭。启动器开启本地模型离线保护，日常运行复用模型。独立配置不改写已有 `.env`。

子进程的数据库、上传、Chroma 和日志指向本项目 `data/`，API 前缀固定 `/api/v1`，端口 8000/5173。这些进程级覆盖不写回原配置。

## 安全加载与排查

重复启动校验 PID、创建时间和命令后复用服务。其他程序占用端口时失败，不结束无关进程。停止同样执行归属校验。日志与状态在 `backend/.runtime_logs/local-launcher/`，不上传到 GitHub。

自动化可临时设置 `$env:RAG_LAUNCHER_NO_PAUSE='1'`。ExecutionPolicy Bypass 仅作用于本次脚本进程，不修改系统策略。

加载更新前先等上传、入库与问答结束，再停止和启动。文件夹队列在刷新、关闭和退出登录时的边界见 [FOLDER_IMPORT.md](FOLDER_IMPORT.md)。
