# RAG Testset v2 Batch01 离线生成报告

生成日期: 2026-05-21  
测试集: `E:/rag_project/rag-agent-kb-system/data/eval/rag_testset_v2_batch01_gb2760.json`  
答案键: `E:/rag_project/rag-agent-kb-system/data/eval/rag_testset_v2_batch01_gb2760_answer_key.json`  
来源素材: `E:/rag_project/rag-agent-kb-system/data/eval/tmp_gb2760_llm_chunks.json`

## 结果

| 检查项 | 结果 |
|--------|------|
| 题目数量 | 120 |
| answer key 数量 | 120 |
| 重复问题数 | 0 |
| 空答案关键词 | 0 |
| 空引用关键词 | 0 |
| 固定 document_ids | [50] |
| 是否运行 RAG 评测 | 否，本轮只做数据集构建 |

## 难度分布

```json
{
  "medium": 70,
  "hard": 12,
  "easy": 38
}
```

## 题型分布

```json
{
  "table_data": 52,
  "mixed": 12,
  "factual_lookup": 56
}
```

## 页码覆盖 Top 20

```json
{
  "86": 5,
  "81": 5,
  "54": 4,
  "141": 3,
  "15": 3,
  "72": 2,
  "80": 2,
  "87": 2,
  "97": 2,
  "124": 2,
  "126": 2,
  "127": 2,
  "23": 2,
  "36": 2,
  "37": 2,
  "38": 2,
  "66": 2,
  "78": 2,
  "145": 2,
  "228": 2
}
```

## 后续建议

1. 人工抽查 10-20 条 GB 2760 题目，重点看自动提取的添加剂名称是否过长或不自然。
2. 如果 GB 2760 重新执行 LLM 整理，建议再生成一版 batch01 或补充更精细的食品分类号题。
3. 全部 batch 完成后再合并运行 `run_rag_eval.py`，避免现在消耗 API 额度。
