# 本地 BGE 检索与问答参数

## 模型与环境

| 模型 | 目录 | 用途 |
| --- | --- | --- |
| [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | `data/models/embeddings/bge-m3/` | 文档和问题的 1024 维稠密向量 |
| [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | `data/models/rerankers/bge-reranker-v2-m3/` | 对召回候选重新排序 |

完整本地组合在 Windows Python 3.12、PyTorch 2.7.1 + CUDA 12.8 验证。以下固定依赖是该组合，不是所有显卡、CUDA 或操作系统的通用安装方案。GPU 不适用时需选择匹配设备的 Torch 依赖并单独验证；`EMBEDDING_DEVICE`、`RERANKER_DEVICE` 可配置为 `cpu`。

```powershell
# 仓库根目录，先准备基础 .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-rag-local.txt --extra-index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe scripts/download-rag-models.py
.\.venv\Scripts\python.exe scripts/configure-local-rag.py
.\.venv\Scripts\python.exe scripts/verify-local-rag.py
```

下载固定官方 revision 并验证文件大小、SHA-256 或 Git blob SHA-1。两个主权重各约 2.27 GB，须显式运行下载脚本；现有校验通过的文件复用，不匹配时保留并报错。`--proxy` 可为 curl 下载指定本次进程代理；元数据请求使用 Python 当前网络代理设置。

配置脚本只创建独立 `.env.rag`，不改写凭据。启动器加载模型并开启离线保护。版本固定 SentenceTransformers 3.3.1、Transformers 4.44.2、FlagEmbedding 1.3.3、ChromaDB 1.0.20，保留历史依赖文件供旧环境参考，不混装两套 pin。

既有 Chroma 数据迁移不能仅靠改版本号完成；先备份，验证目标版本与模型维度后操作。模型验证脚本使用合成数据和隔离目录，可运行本地推理，不发送外部 LLM 请求。

## Chroma 分批写入

所有写入经过 `vector_batches.py`，读取当前 Chroma 客户端上限，保持 ID、文本、向量和 metadata 对齐。写入前检查数量、ID 唯一性与向量维度。失败报告批次及已完成行数，中止后续批次，不把部分写入标成整份入库。

分批没有跨批原子事务；入库流程标记失败，重试清理该文档旧向量。适用于新上传、恢复与 LLM 整理后重建。

## 用户可调参数

知识问答侧栏的检索范围和参数互斥展开。普通账号可指定自己有权访问的文档，后端继续取权限交集。

| 参数 | 行为 |
| --- | --- |
| Top-K | 5–40，默认 5；可能附加少量关键召回，记录实际数量 |
| 候选数 | 自动 `max(32, 2 × Top-K)`；手动 16–128，不小于 Top-K |
| 上下文 | 自动 `max(16000, 1200 × Top-K)` 字符；手动 8000–64000 |
| 重排 | 每次请求独立开关，模型不可用时回退并记录 |
| 偏好 | 按账号保存在本浏览器，跨设备不自动同步 |
| 参数快照 | 发送时冻结到 `chat_jobs.retrieval_options_json`，调整不影响已有任务 |

快速：Top-K 5、候选 16；均衡：Top-K 5、候选自动 32；深入：Top-K 20、候选自动 40。三个预设使用自动上下文，自定义可精确调整。

## 上下文和输出

按完整证据块选择，不截断原文；超预算块跳过后继续尝试后面的块。证据判断、输入与引用使用同一组选中证据。回答记录实际召回、可用和上下文数量、字符数、省略原因、重排与生成状态。

默认配置 `QA_MODEL_CONTEXT_TOKENS=1048576`、`QA_OUTPUT_RESERVE_RATIO=0.30`、`QA_MAX_OUTPUT_TOKENS=65536`、`QA_MODEL_MAX_OUTPUT_TOKENS=393216`。这只是应用配置，换提供商或模型必须核实并更新；不证明 API 一定接受这些上限。

使用 UTF-8 字节数与协议余量作为保守 token 上界，未安装对应 tokenizer。实际 API usage 单独记录，缺失保留空值。窗口预留不保证模型生成足够长的回答。
