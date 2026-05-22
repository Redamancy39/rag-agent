# BM25 混合检索与归一化 tokenizer

## 当前目标

国标类问答中，标准号、限量值、单位、食品名称、表格字段通常比普通语义更关键。向量检索适合语义相近问题，但对 `GB2716`、`μg/kg`、`10³` 这类精确符号不一定稳定。因此当前检索链路加入 BM25 召回，并统一使用归一化 tokenizer。

## 已接入模块

- `backend/app/rag/search_tokenizer.py`
  - 统一归一化检索文本。
  - 处理全角字符、GB 标准号空格差异、`μg/ug/渭g` 单位差异、`10³/10^3` 上标差异。
  - 对中文长词生成 2-4 gram，提升食品名称、项目名称和条款表述的命中率。

- `backend/app/rag/bm25_retriever.py`
  - 在当前用户可访问的 chunk 范围内构建临时 BM25 统计。
  - 使用词频、文档频率和长度归一化计算 BM25 分数。
  - 返回 `bm25_score`、`raw_bm25_score`、`matched_terms`。

- `backend/app/rag/retriever.py`
  - 原向量召回保留。
  - 原关键词召回保留。
  - 新增 BM25 召回。
  - 混合检索阶段只从 ChromaDB 拉取一次权限范围内 chunk，避免关键词和 BM25 重复读取。
  - 按 chunk id 去重后融合 `vector_score`、`keyword_score`、`bm25_score`。

## 关键配置

```env
HYBRID_RETRIEVAL_ENABLED=true
HYBRID_KEYWORD_CANDIDATE_TOP_K=20
HYBRID_KEYWORD_MAX_CHUNKS=3000

HYBRID_BM25_ENABLED=true
HYBRID_BM25_CANDIDATE_TOP_K=12
HYBRID_BM25_MAX_CHUNKS=3000
HYBRID_BM25_K1=1.5
HYBRID_BM25_B=0.75

HYBRID_VECTOR_WEIGHT=0.62
HYBRID_KEYWORD_WEIGHT=0.08
HYBRID_BM25_WEIGHT=0.30
HYBRID_LEXICAL_ONLY_MAX_SCORE=0.82
```

## 当前限制

- BM25 目前是请求时从 ChromaDB 拉取权限范围内 chunk 后本地计算，适合当前本地 demo 和中小规模知识库。
- 还没有持久化倒排索引，文档规模变大后建议迁移到 SQLite FTS5、rank-bm25 缓存索引、OpenSearch 或 Elasticsearch。
- BM25 能提升“文本已正确入库但向量召回不稳”的问题；如果 OCR/表格解析阶段本身没有得到正确文本，仍需要回到入库预处理优化。

## 面试表述

可以说：

> 系统检索阶段采用向量召回、关键词召回和 BM25 召回的混合策略。针对国标文档中常见的标准号、单位、上标数字和数值表达差异，我单独实现了归一化 tokenizer，再将 BM25 结果与向量结果融合，提升专业术语和精确数值问题的召回稳定性。

不建议说：

> 已经实现生产级搜索引擎或持久化倒排索引。

当前更准确的说法是：

> 已实现请求时 BM25 基础版，后续可升级为持久化倒排索引或 SQLite FTS5。
