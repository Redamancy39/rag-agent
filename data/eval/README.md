# RAG 评测集说明

当前主评测集：`rag_testset_v1.json`

## 设计原则

- 每个正例问题必须能在当前已入库文档中找到依据，避免用不存在的文档指标误罚系统。
- `expected_answer_keywords` 用于判断答案核心信息，`expected_citation_keywords` 用于判断引用来源。
- 关键词不要求逐字完全一致，评测系统会归一化标准号、表号、空格、上标和常见单位写法。
- 单位不做错误放宽：例如 `g/kg` 不会被判定为匹配 `μg/kg`。
- 如果一个关键词有多个可接受写法，可以使用 `||` 分隔，例如 `表29||表4.29`。
- 新增样本时建议填写 `tags` 和 `notes`，方便后续按文档、题型、失败原因做分组分析。

## 运行完整评测

完整评测会调用当前 RAG 链路和 LLM：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend

python scripts\run_rag_eval.py `
  --username admin `
  --testset ..\data\eval\rag_testset_v1.json `
  --output ..\data\eval\results\rag_eval_latest.json
```

## 只重判历史结果

如果只是修改了评测规则或测试集关键词，不想重新调用 LLM，可以重判已有结果：

```powershell
cd E:\rag_project\rag-agent-kb-system\backend

python scripts\rejudge_rag_eval.py `
  --testset ..\data\eval\rag_testset_v1.json `
  --result ..\data\eval\results\rag_eval_bm25_tuned.json `
  --output ..\data\eval\results\rag_eval_bm25_tuned_rejudged.json
```

注意：如果修改了题干本身，历史结果只适合验证判分脚本能否运行，不应作为新的最终分数。

## 当前 v1.1 修正点

- 将与当前知识库不一致的蜂蜜题改为 `GB 2730-2015 腌腊肉制品` 中的可验证问题。
- 修正 `GB 2721-2015 食用盐` 中把低钠盐氯化钾指标误写成水分指标的问题。
- 修正 `GB 2733-2015 鲜、冻动物性水产品` 中题干只问海水鱼/淡水鱼但关键词包含虾/贝类指标的问题。
- 放宽合理等价表达：`100` 可匹配 `10²`，`表4.29` 可匹配 `表29`，`无焦斑和霉斑` 可匹配 `无霉斑`。
