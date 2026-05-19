# 模型文件准备与存放位置

本文档记录本项目后续需要的模型、推荐下载名称、本地存放位置和 `.env` 配置方式。

统一建议：把所有本地模型放在项目内的 `data/models/` 下，便于打包、迁移和排查路径问题。

```text
rag-agent-kb-system/
  data/
    models/
      embeddings/
        bge-small-zh-v1.5/
        bge-m3/
      rerankers/
        bge-reranker-base/
        bge-reranker-v2-m3/
        bge-reranker-large/
      ocr/
        paddleocr/
          PP-OCRv5_mobile_det/
          PP-OCRv5_mobile_rec/
          PP-LCNet_x0_25_textline_ori/
      llm/
```

## 1. 当前阶段必须：Embedding 模型

阶段 2 上传入库时必须使用 Embedding 模型。当前代码读取：

```env
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh-v1.5
```

如果使用在线 HuggingFace 模型名，首次运行会自动下载。如果你已经下载过，建议直接移动到：

```text
E:\rag_project\rag-agent-kb-system\data\models\embeddings\bge-small-zh-v1.5
```

然后在 `backend/.env` 中改成：

```env
EMBEDDING_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/embeddings/bge-small-zh-v1.5
```

推荐优先使用：

| 用途 | 模型 | 本地目录 | 说明 |
|---|---|---|---|
| 中文知识库第一版 | `BAAI/bge-small-zh-v1.5` | `data/models/embeddings/bge-small-zh-v1.5` | 体积较小，适合当前阶段快速跑通 |
| 多语言或更长上下文 | `BAAI/bge-m3` | `data/models/embeddings/bge-m3` | 更强但更重，适合后续升级 |

现阶段建议先用 `bge-small-zh-v1.5`，等上传、检索、问答链路稳定后再换 `bge-m3`。

## 2. 第三阶段推荐：Reranker 模型

Reranker 用于“向量召回 Top-K 后二次重排”，不是阶段 2 的必需项。当前配置已预留：

```env
RERANKER_MODEL_NAME=
```

后续接入重排时，优先建议使用：

| 用途 | 模型 | 本地目录 | 说明 |
|---|---|---|---|
| 推荐默认 | `BAAI/bge-reranker-v2-m3` | `data/models/rerankers/bge-reranker-v2-m3` | 新一代 reranker，基于 bge-m3，多语言能力更强，适合作为本项目默认选择 |
| 轻量备选 | `BAAI/bge-reranker-base` | `data/models/rerankers/bge-reranker-base` | 中英双语，旧版但稳定，适合资源更紧张时使用 |
| 效果优先 | `BAAI/bge-reranker-large` | `data/models/rerankers/bge-reranker-large` | 更重，CPU 上会明显更慢 |

如果你已经有 `bge-reranker-v2-m3`，建议移动到：

```text
E:\rag_project\rag-agent-kb-system\data\models\rerankers\bge-reranker-v2-m3
```

并在 `backend/.env` 中配置：

```env
RERANKER_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/rerankers/bge-reranker-v2-m3
```

## 3. LLM 模型

当前规划使用 DeepSeek API。DeepSeek 提供 OpenAI-compatible API，不需要把 LLM 大模型放到本地。只需要在 `backend/.env` 配置：

```env
OPENAI_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL_NAME=deepseek-v4-flash
```

普通 RAG 问答优先用 `deepseek-v4-flash`；如果需要更强推理或更高质量回答，再切到 `deepseek-v4-pro`。

如果后续改成本地 Ollama、vLLM 或 LM Studio，也建议仍然走 OpenAI-compatible API；`data/models/llm/` 只是预留目录，当前不使用。

## 4. PDF / OCR 模型

当前阶段 PDF 解析使用 `pypdf`，只适合文本型 PDF，不需要 OCR 模型。

如果后续要支持扫描件 PDF，再接入 PaddleOCR。PaddleOCR 可以在首次运行时自动下载官方模型；但为了离线运行、打包和复现，建议提前下载并放到本项目目录。

```text
data/models/ocr/paddleocr/
  PP-OCRv5_mobile_det/
  PP-OCRv5_mobile_rec/
  PP-LCNet_x0_25_textline_ori/
```

对应 `.env` 配置：

```env
OCR_DETECTION_MODEL_DIR=E:/rag_project/rag-agent-kb-system/data/models/ocr/paddleocr/PP-OCRv5_mobile_det
OCR_RECOGNITION_MODEL_DIR=E:/rag_project/rag-agent-kb-system/data/models/ocr/paddleocr/PP-OCRv5_mobile_rec
OCR_TEXTLINE_ORIENTATION_MODEL_DIR=E:/rag_project/rag-agent-kb-system/data/models/ocr/paddleocr/PP-LCNet_x0_25_textline_ori
PADDLEOCR_USE_TEXTLINE_ORIENTATION=false
```

建议第一版只准备检测和识别两个核心模型：

| 用途 | 模型 | 本地目录 | 说明 |
|---|---|---|---|
| 文本检测 | `PP-OCRv5_mobile_det` | `data/models/ocr/paddleocr/PP-OCRv5_mobile_det` | 轻量，适合本地开发和 CPU 测试 |
| 文本识别 | `PP-OCRv5_mobile_rec` | `data/models/ocr/paddleocr/PP-OCRv5_mobile_rec` | 支持简中、繁中、英文、日文等常见文字 |
| 行方向分类，可选 | `PP-LCNet_x0_25_textline_ori` | `data/models/ocr/paddleocr/PP-LCNet_x0_25_textline_ori` | 图片或扫描件方向复杂时再启用 |

如果后续对扫描件质量要求更高，可把 mobile 模型换成 `PP-OCRv5_server_det` 和 `PP-OCRv5_server_rec`，但 CPU 上会更慢。

## 5. 移动模型时要保留的文件

移动 HuggingFace 模型目录时，必须移动整个模型文件夹，不要只移动权重文件。常见文件包括：

```text
config.json
model.safetensors 或 pytorch_model.bin
tokenizer.json 或 vocab.txt
tokenizer_config.json
special_tokens_map.json
modules.json
config_sentence_transformers.json
```

如果目录能被下面命令正常加载，就说明路径可用：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('E:/rag_project/rag-agent-kb-system/data/models/embeddings/bge-small-zh-v1.5'); print(m.get_sentence_embedding_dimension())"
```

## 6. 当前推荐最小模型清单

为了尽快跑通项目，当前只准备一个 Embedding 模型即可。当前本机已经准备的是：

```text
data/models/embeddings/bge-m3/
```

对应配置：

```env
EMBEDDING_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/embeddings/bge-m3
RERANKER_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/rerankers/bge-reranker-v2-m3
```

第三阶段做检索质量优化时，再补：

```text
data/models/rerankers/bge-reranker-v2-m3/
```
