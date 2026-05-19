# 入库预处理 v2

当前实现把预处理放在 `loader -> preprocessor -> chunker -> embedding -> Chroma` 中间。默认不调用 OCR 或大模型，确保普通文本型 PDF 的入库路径稳定。

## 1. 默认流程

默认配置下仍然使用低成本规则流程：

1. PyMuPDF 按页抽取正文，生成 `page_text`。
2. PyMuPDF 识别表格，生成 `table_markdown`。
3. 规则转写表格行，生成 `table_row_fact`。
4. 固定长度切块后写入 ChromaDB。

## 2. OCR fallback

当 PDF 抽取文本过少时，可启用 PaddleOCR fallback：

```env
PREPROCESS_OCR_FALLBACK_ENABLED=true
OCR_MIN_EXTRACTED_CHARS=50
OCR_MAX_PAGES=
```

依赖单独安装：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
pip install -r requirements-ocr.txt
```

OCR 结果会生成 `chunk_type=ocr_page_text`，并保留页码。该流程适合扫描版 PDF，不建议一开始对所有文本型 PDF 强制启用。

还有一类 PDF 视觉上可以正常打开，但文本层使用自定义字体编码。PyMuPDF/pypdf 能抽到字符，但内容会出现 `/G21`、控制字符或 `Ã/Â` 这类乱码。当前系统会先做文本质量检测：

- 文本质量正常：继续使用 PDF 文本层。
- 文本质量异常且 `PREPROCESS_OCR_FALLBACK_ENABLED=true`：自动改用 PaddleOCR 结果入库。
- 文本质量异常且未启用 OCR：拒绝入库，并提示需要 OCR。

这能避免把不可读文本写入向量库，后续问答也不会基于乱码产生幻觉。

## 3. LLM 结构化整理

当需要把表格行进一步整理成更准确的问答事实时，可启用大模型预处理：

```env
OPENAI_API_KEY=你的 DeepSeek API Key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL_NAME=deepseek-v4-flash

PREPROCESS_LLM_ENABLED=true
PREPROCESS_LLM_TARGET_CHUNK_TYPES=["table_row_fact"]
PREPROCESS_LLM_MAX_INPUT_CHARS=4000
PREPROCESS_LLM_TIMEOUT_SECONDS=60
```

LLM 预处理不会替换原文切块，而是额外生成 `chunk_type=llm_structured_fact` 的结构化检索事实。这样后续检索可以同时命中：

- 原始页文本 `page_text`
- 原始表格 markdown `table_markdown`
- 规则转写表格行 `table_row_fact`
- 大模型整理事实 `llm_structured_fact`

## 4. 结构化事实内容

大模型输出会被转换成类似文本：

```text
结构化检索事实：
可检索问法：某项目在某食品中的限量是多少
答案：限量为 0.5 mg/kg
适用对象：某食品
项目：某污染物
限量值：0.5
单位：mg/kg
适用条件：...
原文证据：...
```

metadata 会继续保留页码、表格号、表题、来源文件、用户和文档 ID。

## 5. 对已有向量库的影响

修改预处理逻辑不会自动改变已经写入 ChromaDB 的旧文档。要让旧文档使用新逻辑，需要重新入库：

1. 删除测试用旧数据后重新上传，或
2. 后续增加“重新索引”接口，对已有 `document_id` 重新跑解析和入库。

当前上传流程会在同一个 `document_id` 重新索引时先删除该文档旧向量，但重复上传同一文件会创建新的文档记录和新的向量。

## 6. 建议测试顺序

1. 先保持 `PREPROCESS_LLM_ENABLED=false`，检查当前规则切块质量。
2. 对失败的扫描版 PDF 单独打开 `PREPROCESS_OCR_FALLBACK_ENABLED=true` 测试。
3. 对表格型 PDF 打开 `PREPROCESS_LLM_ENABLED=true`，只处理 `table_row_fact`。
4. 在前端“查看切块”里确认是否出现 `llm_structured_fact`。
5. 抽查 5-10 条结构化事实，看限量值、单位、页码和原文证据是否准确。
