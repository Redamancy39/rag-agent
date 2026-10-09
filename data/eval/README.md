# RAG 评测集与结果口径

当前主评测集为 `rag_testset_v2.json`，包含 500 条食品标准领域问题，答案键为 `rag_testset_v2_answer_key.json`。旧版题集和中间批次保留在 `archive/`，多格式样例为 `office_multiformat_eval_v1.json`。

## 历史结果

| 记录 | 口径 | 结果 |
| --- | --- | --- |
| `results/rag_eval_v2_final.json` | 历史原始调用结果 | 398/500，79.60% |
| `results/rag_eval_v2_after_gb2760_fix.json` | 后续历史调用结果 | 441/500，88.20% |
| 用当前 v2 判分规则重判上述后续结果 | 不重新检索、不调用 LLM | 452/500，90.40% |

2026-10-09 发布准备再次离线核验得到 452/500。重判保留原历史回答，仅使用当前题集/关键词规则判分；这是历史回答在该判分口径下的成绩，不是本版新模型或新入库文档的端到端准确率。原结果文件不覆盖，本机重判输出不上传。

## 完整评测

先准备题目引用的文档、入库索引、评测账号权限和模型配置，再显式运行：

```powershell
# 仓库根目录
.\.venv\Scripts\python.exe backend/scripts/run_rag_eval.py `
  --username admin `
  --testset data/eval/rag_testset_v2.json `
  --output data/eval/results/rag_eval_v2_new_run.json
```

此脚本直接使用本地数据库权限和 RAG 服务，不是 HTTP 客户端；它可能调用生成 API，产生费用并写入评测/问答记录。手动执行读取后端 `.env`，不会自动加载 Windows 启动器的独立 profile；先确认所选模型、目录、开关和权限。不要将 API Key 或密码写入提交的结果文件。

## 只重判历史结果

```powershell
.\.venv\Scripts\python.exe backend/scripts/rejudge_rag_eval.py `
  --testset data/eval/rag_testset_v2.json `
  --result data/eval/results/rag_eval_v2_after_gb2760_fix.json `
  --output backend/.runtime_reports/rag_eval_v2_rejudged.json
```

输出父目录需存在，可先创建 `backend/.runtime_reports/`。不传 `--output` 时只打印摘要，不覆盖题集或历史结果。此流程不运行检索和 LLM。

## 样本和判分边界

- 正例应能在已入库且账号可访问的文档中找到证据；负例与跨文档题分组观察。
- `expected_answer_keywords` 检查回答，`expected_citation_keywords` 检查引用；合理等价写法可用 `||` 分隔。
- 单位必须保留语义，例如 g/kg 不能放宽成 μg/kg；标准号、表号与数值需核对。
- 修改题干后，原回答只适合检查判分脚本，不能算作新题目的真实运行结果。
- 关键词通过率不等同于人工语义正确率；应同时复查来源、权限、拒答、表格/OCR 和引用。
