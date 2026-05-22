# RAG Agent 面试展示说明

## 项目定位

本项目可以表述为：多用户权限控制的企业知识库 RAG Agent 系统。当前重点不是通用聊天机器人，而是企业文档从上传、解析、入库、权限过滤到可溯源问答的完整工程链路。

更稳妥的 Agent 表述：

- 已实现轻量 Ingestion Agent：根据文件探测结果选择 PDF 文本解析、OCR fallback、表格处理、LLM 切块整理和入库策略。
- 已实现权限感知 RAG 问答链路：用户提问前先计算可访问文档范围，再进行混合检索、Reranker 精排、证据约束生成和引用返回。
- LangGraph 问答 Agent 目前作为后续演进方向，不应在面试中说成已经完全落地。

## 推荐演示路径

1. 登录管理员账号，说明 JWT 鉴权和管理员 / 普通用户角色。
2. 打开系统配置页，展示“面试演示总览”“流程看板”“能力矩阵”。
3. 在文档上传页展示 LLM 整理开关和上传进度，说明 OCR / LLM / Embedding 是重任务，已经做了任务状态记录和并发控制。
4. 在文档列表页展示上传者、状态、分块数、处理任务、质量报告、权限管理和删除。
5. 打开质量报告，说明健康分、风险项、内容类型分布和优化建议如何帮助判断入库质量。
6. 打开权限管理，展示用户授权和部门授权，强调权限不只在前端隐藏，而是在后端接口和检索阶段过滤。
7. 到问答测试页选择多个文档提问，展示分类判断、结论、依据、引用和检索依据表格。

## 面试时可强调的工程点

- 文档入库不是简单读取文本，而是先做文件探测，再按策略选择解析、OCR、表格事实化和 LLM 归一化。
- 对国标类 PDF 的表格、页码、标准号、限量值做了更适合检索的结构化处理。
- 检索阶段融合向量检索、BM25、关键词匹配和 Reranker，兼顾语义问题和标准号 / 数值类精确问题。
- 权限控制落在后端和检索层，用户只能检索自己有权限的 document_id。
- 回答阶段要求证据不足时返回“未找到”，并返回引用来源，降低企业内部知识库场景下的幻觉风险。
- 系统有任务表、质量报告、问答日志、权限审计日志，便于排查入库失败和 RAG 失败案例。

## 当前边界

- 问答 Agent 还没有完全迁移到 LangGraph；当前是规则化 RAG 服务链路。
- 文件处理任务仍使用 FastAPI BackgroundTasks + 本地 semaphore，后续可迁移 Celery / RQ。
- ChromaDB 是当前向量库，业务库仍是 SQLite；生产环境可迁移 PostgreSQL。
- OCR 和 LLM 整理会增加处理耗时，适合对高价值文档开启，不适合所有临时文件强制开启。

## 后续包装方向

下一步建议把当前流程拆成两个更清晰的 Agent：

1. Ingestion Agent：FileProbe -> StrategyPlanner -> Parse/OCR -> Normalize -> ChunkQuality -> Index -> Report。
2. QA Agent：Permission -> QuestionClassifier -> RetrievalPlanner -> HybridRetrieve -> Rerank -> EvidenceCheck -> Answer -> Log。

这样既能保留当前可运行系统，又能自然解释后续为什么引入 LangGraph。
