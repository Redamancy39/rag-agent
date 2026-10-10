# LLM 模式、整理预算与真实状态

API Key、地址和模型写在未跟踪的 `backend/.env`：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME`。按提供商实际可用模型配置，不把仓库默认模型名或窗口大小当作账号能力证明。

## 本地模式

```powershell
Copy-Item backend/.env.llm.example backend/.env.llm
```

已有文件先编辑原文件，不覆盖。此文件只含 `LOCAL_LLM_MODE`，不保存密钥。

| 模式 | 生成式问答 | 上传候选整理 |
| --- | --- | --- |
| `offline` | 不调用外部 LLM，返回检索证据 | 关闭 |
| `chat` | 启用 | 关闭 |
| `chat_and_normalization` | 启用 | 按策略与候选规则执行 |

没有 `.env.llm` 默认离线，进程变量 `LOCAL_LLM_MODE` 可覆盖。修改后等队列空闲再 STOP/START。启用时，问答选中证据及整理候选发送到配置服务，可能产生 API 费用。

本地启动器关闭 `INGESTION_AGENT_LLM_ENABLED`、`QUERY_AGENT_LLM_ENABLED`、`QUERY_AGENT_EVIDENCE_LLM_ENABLED`，保留规则流程。食品术语预检也只在本地执行。`chat` 与 `chat_and_normalization` 会打开 `AGENTIC_RAG_ENABLED`：模型只根据问题决定是否查询知识库，查询之后仍走现有规划、混合检索和证据判断。`offline` 关闭该开关，每次提问都按原检索路径执行。

## 预算与保留规则

完整模式启用 `PREPROCESS_LLM_ENABLED` 和 `CHUNK_LLM_NORMALIZATION_ENABLED`。前置逐行事实 LLM 由独立开关控制，默认关闭，规则提取继续。

| 配置 | 默认 | 含义 |
| --- | --- | --- |
| `PREPROCESS_FACT_LLM_ENABLED` | `false` | 不对每条表格事实额外调用 LLM |
| `CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT` | `120` | 候选上限 |
| `INGESTION_LLM_MAX_CALLS` | `120` | 前置、候选、重试共享的实际请求上限 |
| `INGESTION_LLM_MAX_SECONDS` | `600` | 首次整理请求起的时间预算 |
| `INGESTION_LLM_MAX_RETRIES` | `1` | 每项最多一次显式重试 |
| `INGESTION_LLM_MAX_OUTPUT_TOKENS` | `2048` | 每次整理输出上限 |

关闭 SDK 隐式重试，显式计数请求。连接、超时、429 和服务端错误有限重试；配置错误或连续三项失败停止后续发送。剩余时间限制新请求及单次超时，不是整个 OCR/向量化/写库流程的十分钟终止期限。

达到数量、时间或异常约束时保留原文与已有结果，并说明跳过原因。候选处理不是全文审核，响应成功也不保证产生可用新块或写库成功。

## 页面和记录

进度区分排队、请求、重试、整理完成、向量化和写库，展示真实已处理/总数、尝试、更新时间。无法计数的阶段显示加载状态，不推算金额或虚构百分比。

文档列表区分 LLM 检测与整理，可筛选、查看记录。无候选显示未调用；收到模型响应才记实际检测，整理块写库成功才记整理结果。生成成功但写库失败单独说明，旧任务计数缺失显示记录不足。

启用模式不会重处理旧文档；“整理”操作显式提交现有候选，前端提示内容外发和费用。精确重复上传复用已有文档，不因此重复整理。

## 验证

预算、重试和状态测试使用模拟客户端。可显式进行一次合成 API 联通验证：

```powershell
.\.venv\Scripts\python.exe scripts/verify-local-llm.py --allow-api-call
```

这会真实调用配置的官方 DeepSeek API，不是日常启动步骤。报告在忽略的 `.runtime_reports/`，不保存密钥或响应正文。发布验证不执行该命令，不发送真实文档。
