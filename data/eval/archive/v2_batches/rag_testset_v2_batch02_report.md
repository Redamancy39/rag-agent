# RAG Testset v2 Batch02 离线生成报告

生成日期: 2026-05-21  
测试集: `E:/rag_project/rag-agent-kb-system/data/eval/rag_testset_v2_batch02_contaminants_mycotoxins.json`  
答案键: `E:/rag_project/rag-agent-kb-system/data/eval/rag_testset_v2_batch02_contaminants_mycotoxins_answer_key.json`  
来源素材: ChromaDB 已入库切块（doc_id 52, 51）

## 结果

| 检查项 | 结果 |
|--------|------|
| 题目数量 | 57 |
| answer key 数量 | 57 |
| 重复问题数 | 0 |
| 空答案关键词 | 0 |
| 空引用关键词 | 0 |
| 文档分布 | {52: 35, 51: 22} |
| 是否运行 RAG 评测 | 否，本轮只做数据集构建 |

## 难度分布

```json
{
  "easy": 6,
  "medium": 39,
  "hard": 12
}
```

## 题型分布

```json
{
  "factual_lookup": 3,
  "definition": 4,
  "cross_reference": 2,
  "table_data": 36,
  "mixed": 12
}
```

## 页码覆盖 Top 20

```json
{
  "GB 2761-2017 p6": 8,
  "GB 2761-2017 p4": 7,
  "GB 2762-2025 p4": 5,
  "GB 2762-2025 p7": 5,
  "GB 2762-2025 p11": 5,
  "GB 2762-2025 p3": 4,
  "GB 2762-2025 p13": 4,
  "GB 2761-2017 p3": 3,
  "GB 2762-2025 p9": 3,
  "GB 2762-2025 p8": 3,
  "GB 2762-2025 p12": 3,
  "GB 2761-2017 p5": 3,
  "GB 2762-2025 p14": 2,
  "GB 2762-2025 p2": 1,
  "GB 2761-2017 p7": 1
}
```
