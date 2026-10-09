# 模型文件与配置

当前本地配置使用 BGE-M3、BGE Reranker v2-m3 与 PaddleOCR。权重不随 GitHub 仓库发布，下载/配置须显式执行。

```text
data/models/
  embeddings/bge-m3/
  rerankers/bge-reranker-v2-m3/
  ocr/paddleocr/PP-OCRv5_mobile_det/
  ocr/paddleocr/PP-OCRv5_mobile_rec/
  llm/                              预留，当前生成使用 API
```

| 模型 | 功能 | 配置指南 |
| --- | --- | --- |
| [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | 入库与查询稠密向量 | [LOCAL_RAG](LOCAL_RAG.md) |
| [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | 检索候选重排 | [LOCAL_RAG](LOCAL_RAG.md) |
| PaddleOCR mobile det/rec | 本地 CPU 页面识别 | [LOCAL_OCR](LOCAL_OCR.md) |
| OpenAI-compatible 生成 API | 依据整理与问答 | [LOCAL_LLM](LOCAL_LLM.md) |

下载脚本固定官方 revision 并检查大小和哈希，复用通过验证的本地文件。移动模型时保留完整目录及 tokenizer/config，不只复制权重。配置采用相对于后端目录的项目路径，不含开发者机器绝对路径。

Windows 启动器用独立 `.env.rag`、`.env.ocr` 加载模型，并开启 HuggingFace 离线保护，日常启动不重复下载。普通手动启动的配置默认值与该 profile 不完全相同，按实际运行入口配置。

变更 Embedding 模型或向量维度通常需要重新生成索引；先备份并明确旧数据迁移策略，不在现有向量库中直接混用不同模型的向量。
