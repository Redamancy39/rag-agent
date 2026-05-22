# RAG 测试集 v2 batch03 生成报告

- 生成日期：2026-05-21
- 测试集文件：`rag_testset_v2_batch03_pesticide_veterinary.json`
- 答案键文件：`rag_testset_v2_batch03_pesticide_veterinary_answer_key.json`
- 总题量：75
- 文档分布：GB 2763.1=45，GB 31650.1=30
- 难度分布：{'easy': 14, 'hard': 17, 'medium': 44}
- 类型分布：{'cross_reference': 8, 'definition': 3, 'factual_lookup': 16, 'table_data': 48}

## 说明

- 本批次不调用 RAG 问答接口，只构建离线评测数据。
- GB 2763.1 的题目优先选择 OCR 中较清晰的 ADI、残留物、检测方法和表格数值。
- GB 31650.1 的题目主要来自 LLM 归一化切块，部分单位在源切块中带有待核验提示，评测答案统一按当前归一化结果记录为 μg/kg。
- citation 关键词仅强制匹配标准号，避免 OCR/归一化切块缺少稳定表号 metadata 时造成误判。
