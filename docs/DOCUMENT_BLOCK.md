# DocumentBlock 统一中间结构

`DocumentBlock` 是各类文档解析器与后续 RAG 入库流程之间的稳定契约。

```text
PDF / TXT / Markdown / DOCX / PPTX / XLSX
                    |
                 Loader
                    |
              DocumentBlock[]
                    |
     Normalize -> ChunkQuality -> Chunk -> Index
```

它不只是临时中转对象，还负责统一三类信息：

- 内容：`text`、`block_type`、`document_format`
- 处理来源：`source`、`extraction_method`
- 原文定位：`SourceLocator`

## 当前字段

| 字段 | 作用 |
| --- | --- |
| `text` | 当前语义块的正文 |
| `block_type` | `page_text`、`paragraph`、`table_row_fact` 等内容类型 |
| `document_format` | `pdf`、`docx`、`pptx`、`xlsx`、`txt`、`markdown` |
| `source` | 原始文件名 |
| `extraction_method` | PyMuPDF、pypdf、PaddleOCR 或对应 Office 解析器 |
| `locator` | 页码、幻灯片、章节路径、段落、工作表、单元格和表格位置 |
| `metadata` | 业务扩展字段，并保留旧版 `chunk_type` 兼容 |

`SourceLocator` 输出为扁平标量 metadata，避免 ChromaDB 不接受嵌套对象：

```text
page, slide, sheet, cell_range, section_path,
paragraph_index, table_index, block_index
```

应用层统一将这些扁平字段还原为来源定位对象：

```json
{
  "kind": "sheet",
  "key": "sheet:Standards|cell_range:A12:D12",
  "label": "工作表 Standards / 单元格 A12:D12",
  "sheet": "Standards",
  "cell_range": "A12:D12"
}
```

- `kind`：主要定位类型，如 `page`、`slide`、`section`、`sheet`
- `key`：稳定位置键，用于去重、质量统计和追踪
- `label`：统一中文显示文本，后端引用和前端表格共同使用
- 其余字段：保留机器可读的精确位置，便于后续实现原文跳转

ChromaDB 中仍使用扁平字段，文档接口的 `DocumentChunkRead`，以及问答 API 的
`Citation`、`EvidenceRow` 和 `RetrievalTraceHit` 都会返回统一 `location`
对象。旧问答日志只有扁平字段时，Pydantic 模型会自动补全 `location`，因此
无需重建已有向量库。

## 格式映射

| 文件格式 | 推荐 block | 推荐定位 |
| --- | --- | --- |
| PDF | 页面正文、OCR 页面、表格行 | `page`、`table_index` |
| DOCX | 标题、段落、表格行 | `section_path`、`paragraph_index`、`table_index` |
| PPTX | 文本框、表格行、备注 | `slide`、`block_index`、`table_index` |
| XLSX | 表格区域、数据行 | `sheet`、`cell_range`、`block_index` |
| TXT / Markdown | 文档正文或章节 | `section_path`、`block_index` |

新增文件类型时，loader 只负责输出 `list[DocumentBlock]`。文本修复、LLM 整理、
质量评分、切块、来源前缀和向量入库不应再按文件格式复制实现。

当前 `DocxLoader`、`PptxLoader` 和 `XlsxLoader` 已按此契约实现。普通 Office
文档的结构提取分别由 `python-docx`、`python-pptx` 和 `openpyxl` 本地完成，
只有经过质量筛选的有限候选块才按系统配置进入后续 LLM 整理。
