# 入库预处理 Agent 设计

## 目标

RAG 的上限首先由入库质量决定。文档如果在解析、OCR、表格转写、分块阶段已经丢失结构或产生乱码，后面的 embedding、reranker、LLM 都很难补救。

本模块目标是把“上传文件后怎么处理”从固定流水线升级为可解释、可观测、可回退的入库决策系统。

## 核心原则

1. 先探测，再决策，不让 LLM 凭文件名猜工具。
2. LLM 只做策略建议，不直接绕过确定性质量规则。
3. 所有工具选择都要写入任务状态和日志，方便排查。
4. OCR、LLM 表格整理都是成本较高步骤，只有在必要或收益明确时启用。
5. 最终入库前必须做质量验收，不合格就回退或失败提示。

## 总体流程

```text
上传文件
  -> 保存原文件
  -> 轻量探测 Probe
  -> Agent 生成 IngestionPlan
  -> 执行解析工具
  -> 文本质量验收
  -> 必要时 OCR / LLM 表格整理
  -> 切块
  -> 分块质量验收
  -> Embedding
  -> ChromaDB 入库
```

## 1. 轻量探测 Probe

探测阶段只读取少量页面，不做完整入库。

PDF 探测字段：

- `file_type`
- `file_size`
- `page_count`
- `sampled_pages`
- `text_chars`
- `table_count`
- `readable`
- `quality`
- `sample_text`
- `probe_error`

质量指标来自 `text_quality_summary`：

- 文本长度
- 可读字符数量
- CJK 字符数量
- `/Gxx` 等乱码 token 比例
- 控制字符比例
- mojibake 标记比例

这一步能判断：

- 是否是扫描件；
- PDF 文本层是否为空；
- 文本是否乱码；
- 是否存在表格；
- PyMuPDF 是否能打开；
- 是否需要 OCR；
- 是否值得做 LLM 表格事实整理。

## 2. Agent 决策计划

Agent 输出 `IngestionPlan`：

```json
{
  "primary_reader": "pymupdf_text_table",
  "use_ocr": false,
  "use_llm_preprocessing": true,
  "reason": "PDF 文本层可读，探测到表格，启用表格事实整理。"
}
```

可选工具：

- `pymupdf_text_table`：正常 PDF 文本层 + 表格探测。
- `pypdf_text`：PyMuPDF 不可用时的文本层回退。
- `paddleocr`：扫描件、乱码、文本层为空。
- `llm_table_normalizer`：表格多、需要把表格行整理成事实句。

当前策略：

- 先由规则生成 fallback plan；
- 如果 `INGESTION_AGENT_LLM_ENABLED=true` 且配置了 API Key，再让 LLM 基于探测信息修正策略；
- 规则仍是安全门：如果探测认定文本不可读，LLM 不能关闭 OCR。

## 3. 执行策略

典型分支：

### 正常文本型 PDF

```text
PyMuPDF -> 表格抽取 -> 表格规则转写 -> 可选 LLM 表格事实整理
```

适合大部分国标 PDF。

### 扫描件或文本层乱码 PDF

```text
跳过普通文本层 -> PaddleOCR -> OCR 文本质量检查 -> 可选 LLM 表格事实整理
```

适合无法直接读取或复制出来是乱码的 PDF。

### PyMuPDF 打不开但 pypdf 可读

```text
pypdf -> 文本质量检查 -> 切块
```

这类只能保底读取文本，表格质量通常不如 PyMuPDF。

### 非 PDF 文档

```text
txt/markdown loader -> 切块
```

不启用 OCR。

## 4. 质量验收

入库不能只看“有没有文本”，需要验收：

### 文本级验收

- 文本长度是否足够；
- 是否存在大量乱码；
- 是否包含可读中文/英文/数字；
- OCR 后文本是否比原文本更可用。

### 表格级验收

后续建议增加：

- 表格行列数；
- 空单元格比例；
- 单位字段是否保留；
- 页码、表号、表题是否保留；
- 是否生成了可问答的事实句。

### 分块级验收

后续建议增加：

- chunk 数是否异常低；
- 单 chunk 是否过长/过短；
- 每个 chunk 是否带 `document_id/page/chunk_type`；
- 表格事实是否包含“对象-指标-数值-单位-条件-来源”。

## 5. 状态和可观测性

当前状态建议：

- `queued`
- `agent_planning`
- `parsing`
- `preprocessing`
- `ocr`
- `llm_preprocessing`
- `chunking`
- `embedding`
- `indexing`
- `indexed`
- `failed`

每个阶段写：

- `documents.status`
- `documents.status_message`
- `document_processing_jobs.stage`
- `document_processing_jobs.message`
- `document_processing_jobs.error_message`

用户能看到“正在使用 PyMuPDF”、“文本层不可读，正在 OCR”、“正在用大模型整理表格事实”等状态。

## 6. 推荐后续增强

### A. 处理计划持久化

新增字段或表保存完整 `probe_json` 和 `plan_json`：

```text
document_processing_jobs.probe_json
document_processing_jobs.plan_json
```

这样后续能解释为什么某文件走了 OCR。

### B. 质量报告

新增 `document_quality_reports`：

- 原始文本质量；
- OCR 文本质量；
- 表格数量；
- 事实句数量；
- chunk 数；
- 页码覆盖率；
- 是否建议人工复核。

### C. 自动二次修复

如果入库后质量不达标：

```text
PyMuPDF 结果差 -> OCR
OCR 结果差 -> 标记 failed/manual_review
表格事实少 -> LLM table normalizer
chunk 异常少 -> 调整 chunk_size 后重跑
```

### D. 人工覆盖策略

前端后续可提供：

- 强制 OCR；
- 跳过 OCR；
- 强制大模型整理表格；
- 重新入库；
- 查看 Agent 决策理由。

## 当前代码落点

- Agent 决策：`backend/app/agent/ingestion_agent.py`
- 入库执行：`backend/app/services/document_service.py`
- 质量判断：`backend/app/rag/text_quality.py`
- OCR fallback：`backend/app/rag/preprocessor.py`
- 状态记录：`document_processing_jobs`

## 结论

这个 Agent 不应该是一个“会聊天的黑盒”，而应该是入库流水线的控制器。它基于可验证的探测结果选择工具，并把每一步决策和结果写入状态表。这样后续即使 RAG 答错，也能追溯问题是在解析、OCR、表格转写、分块、检索还是生成阶段。
