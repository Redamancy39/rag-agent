# OCR 增强、切块质量评分与 LLM 归一化

本阶段目标是解决 OCR 后文本断行、表格结构丢失、低质量切块直接入库导致检索不准的问题。

## 当前流程

```text
PDF
-> 入库 Agent 探测
-> PyMuPDF / PaddleOCR
-> OCR 行级结果增强
-> 规则切块
-> chunk 质量评分
-> 条件式 LLM 归一化
-> Embedding
-> ChromaDB
```

## OCR 增强

PaddleOCR 现在不再只返回纯文本，会尽量保留：

- `ocr_line_count`：OCR 行数
- `ocr_avg_score`：平均识别置信度
- `ocr_min_score`：最低识别置信度
- `ocr_low_confidence_count`：低置信行数量
- `ocr_table_like`：是否疑似表格
- `ocr_lines_json`：前若干行的文本、置信度和 bbox 预览

当 PaddleOCR 返回 bbox 时，系统会按页面坐标重排 OCR 行。对于表格型内容，会尽量形成类似：

```text
动物种类 | 靶组织 | 最大残留限量，μg/kg
家禽 | 蛋 | 4
```

这一步不会猜测缺失值，只改善原始 OCR 的阅读顺序。

## Chunk 质量评分

每个入库 chunk 会写入：

- `chunk_quality_score`：0-1 分
- `chunk_quality_label`：`high` / `medium` / `low`
- `chunk_quality_flags`：质量问题标签
- `is_table_like`：是否表格型
- `needs_llm_normalization`：是否建议 LLM 归一化

当前主要识别这些问题：

- `short_text`
- `low_readability`
- `garbled_tokens`
- `mojibake`
- `fragmented_lines`
- `many_numeric_lines`
- `repeated_lines`
- `low_ocr_confidence`
- `table_like`

## LLM 归一化

LLM 只处理被标记为 `needs_llm_normalization=true` 的 chunk，且最多处理 `CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT` 个。归一化结果不会覆盖原始 chunk，而是新增：

```text
chunk_type=llm_normalized_chunk
extraction_method=llm_chunk_normalization
```

这样向量库里同时保留原始 OCR 文本和更适合检索的结构化文本。引用时仍可回到原始页码、文件和原始 chunk。

## 配置项

```env
CHUNK_QUALITY_ENABLED=true
CHUNK_LLM_NORMALIZATION_ENABLED=true
CHUNK_LLM_MIN_QUALITY_SCORE=0.82
CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT=20
CHUNK_LLM_MIN_INPUT_CHARS=20
```

如果上传速度或 API 成本较敏感，可以先关闭：

```env
CHUNK_LLM_NORMALIZATION_ENABLED=false
```

质量评分和 OCR 增强仍会保留。

## 上传时开关与进度

前端上传页提供“启用大模型整理 OCR / 表格切块”开关。关闭时，系统仍会执行 OCR 增强、切块质量评分和向量化，但跳过 LLM chunk 归一化。

开启时，后端会在任务表中写入：

- `progress_total`
- `progress_current`
- `progress_percent`
- `progress_detail`

前端上传队列会轮询 `/api/v1/documents/{document_id}/jobs`，显示类似：

```text
正在整理 OCR/表格切块：7 / 23
```

这样可以区分“上传完成”和“后台仍在做慢速 LLM 整理”。
