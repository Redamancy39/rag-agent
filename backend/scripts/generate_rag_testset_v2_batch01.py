# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
SOURCE_PATH = EVAL_DIR / "tmp_gb2760_llm_chunks.json"
PLAN_PATH = EVAL_DIR / "rag_testset_v2_plan.md"
BATCH_PATH = EVAL_DIR / "rag_testset_v2_batch01_gb2760.json"
ANSWER_KEY_PATH = EVAL_DIR / "rag_testset_v2_batch01_gb2760_answer_key.json"
REPORT_PATH = EVAL_DIR / "rag_testset_v2_batch01_report.md"

DOC_ID_GB2760 = 50
TARGET_BATCH01 = 120
FOOD_CODE_PATTERN = r"(?:0[1-9]|1[0-6])(?:[.][0-9]{1,2}){0,4}"


PLAN_MD = """# RAG 评估测试集 v2 规划（500题版）

**修订日期**: 2026-05-21  
**目标**: 基于当前 24 个已入库国标文档，构建 500 题规模的 RAG 回归测试集，用于后续检索、重排、切块和权限过滤迭代后的统一评测。  
**当前原则**: 先分批生成并离线校验数据集，不在生成阶段直接调用 RAG 问答接口；全部批次完成后再统一运行评测。

---

## 一、当前文档库快照

当前数据库统计为 **24 个文档 / 1202 个 chunks**。其中 GB 2760-2024 已清理上一轮 LLM 补充块，当前为 561 个原始/表格切块。

| 文档 | 当前 chunks | 出题重点 | v2 计划题量 |
|------|------------:|----------|------------:|
| GB 2760-2024 食品添加剂使用标准 | 561 | 添加剂名称、CNS/INS、功能、食品分类号、最大使用量、残留量、加工助剂 | 120 |
| GB 2762-2025 食品中污染物限量 | 176 | 污染物限量、食品类别、检验方法、可食用部分 | 35 |
| GB 2761-2017 食品中真菌毒素限量 | 60 | 真菌毒素、食品类别、限量、检验方法 | 22 |
| GB 2763.1-2018 食品中43种农药最大残留限量 | 60 | 农药 ADI、残留物定义、MRL、检验方法 | 45 |
| GB 31650.1-2022 食品中41种兽药最大残留限量 | 45 | 兽药 ADI、靶组织、MRL、检验方法 | 30 |
| GB 2715-2016 粮食 | 33 | 感官、理化指标、污染物/真菌毒素/农残引用 | 14 |
| GB 2749-2015 蛋与蛋制品 | 12 | 感官、理化、微生物、引用标准 | 10 |
| GB 2716-2018 食品植物油 | 10 | 酸价、过氧化值、溶剂残留、引用标准 | 10 |
| GB 2730-2015 腌腊肉制品 | 8 | 过氧化值、酸价、三甲胺氮、引用标准 | 10 |
| GB 2733-2015 鲜、冻动物性水产品 | 8 | 挥发性盐基氮、组胺、引用标准 | 10 |
| GB 2707-2016 鲜、冻畜禽产品 | 20 | 挥发性盐基氮、铅、引用标准 | 10 |
| 13 个小型产品标准 | 199 | 定义、感官、理化、微生物、标签、引用标准 | 117 |
| 库外负例 | - | 当前知识库不包含的问题，验证“未找到”策略 | 40 |
| 独立跨文档引用题 | - | 产品标准到通用限量标准的链式查询 | 27 |

---

## 二、总量与分布

本版将总量严格修正为 **500 题**。相比原始计划，GB 2760 从 130 题下调到 120 题，批次4修正为 6 个中型标准、64 题。

| 分类 | 文档/范围 | 简单 | 中等 | 困难 | 总计 |
|------|-----------|-----:|-----:|-----:|-----:|
| A | GB 2760 食品添加剂 | 30 | 50 | 40 | 120 |
| B | GB 2762 污染物限量 | 8 | 17 | 10 | 35 |
| C | GB 2761 真菌毒素限量 | 7 | 12 | 3 | 22 |
| D | GB 2763.1 农药残留 | 10 | 27 | 8 | 45 |
| E | GB 31650.1 兽药残留 | 7 | 16 | 7 | 30 |
| F | 6 个中型产品标准 | 13 | 41 | 10 | 64 |
| G | 13 个小型产品标准 | 26 | 65 | 26 | 117 |
| H | 库外负例 | 12 | 14 | 14 | 40 |
| I | 跨文档引用 | 0 | 14 | 13 | 27 |
| **合计** | | **113** | **256** | **131** | **500** |

题型目标：

| 题型 | 目标数量 | 说明 |
|------|---------:|------|
| table_data | 205 | 表格数值、限量、最大使用量、残留量 |
| factual_lookup | 78 | 名称、编号、功能、适用范围 |
| cross_reference | 70 | 引用标准或跨表/跨文档链路 |
| definition | 35 | 术语、食品类别、标准范围 |
| negative | 40 | 库外问题，期望返回未找到 |
| mixed | 72 | 同时要求数值、条件、引用或多字段 |
| **合计** | **500** | |

---

## 三、批次执行计划

| 批次 | 文件名 | 文档范围 | 题量 | 主要覆盖 | 生成状态 |
|------|--------|----------|-----:|----------|----------|
| batch01 | `rag_testset_v2_batch01_gb2760.json` | GB 2760-2024 食品添加剂 | 120 | A.1 添加剂限量、CNS/INS、A.2/GMP、C.2 加工助剂 | 已生成 |
| batch02 | `rag_testset_v2_batch02_contaminants_mycotoxins.json` | GB 2762 + GB 2761 | 57 | 污染物和真菌毒素限量、食品类别、检验方法 | 待生成 |
| batch03 | `rag_testset_v2_batch03_pesticide_veterinary.json` | GB 2763.1 + GB 31650.1 | 75 | 农药/兽药 MRL、ADI、残留物/靶组织、检验方法 | 待生成 |
| batch04 | `rag_testset_v2_batch04_medium_product_standards.json` | GB 2715、2749、2716、2730、2733、2707 | 64 | 中型产品标准的理化指标和引用标准 | 待生成 |
| batch05 | `rag_testset_v2_batch05_small_product_standards.json` | 13 个小型产品标准 | 117 | 定义、感官、理化、标签、引用标准模板题 | 待生成 |
| batch06 | `rag_testset_v2_batch06_negative_crossdoc.json` | 库外负例 + 跨文档引用 | 67 | 未找到策略、产品标准到通用限量标准链式查询 | 待生成 |
| final | `rag_testset_v2.json` | 合并 batch01-batch06 | 500 | 全量回归测试 | 待合并 |

---

## 四、输出格式

每个 batch 输出两个文件：

1. 测试集 JSON：供 `backend/scripts/run_rag_eval.py` 直接读取。
2. 答案键 JSON：记录标准答案、难度、题型、来源页码和表号，便于人工审查和后续修订。

测试集字段遵循当前后端 schema：

```json
{
  "name": "rag-testset-v2-batch01-gb2760",
  "cases": [
    {
      "id": "V2-B01-Q001",
      "question": "...",
      "expected_found": true,
      "expected_answer_keywords": ["..."],
      "expected_citation_keywords": ["GB 2760", "表A.1"],
      "document_ids": [50],
      "top_k": 10,
      "tags": ["v2", "batch01", "gb2760", "table_data", "medium"],
      "notes": "..."
    }
  ]
}
```

---

## 五、离线校验规则

生成后先做离线检查，不消耗 LLM/API：

1. JSON 能被 `RagEvalRunRequest` 校验通过。
2. batch 内题目 ID 唯一、问题文本无重复。
3. `expected_answer_keywords` 和 `expected_citation_keywords` 非空。
4. `document_ids` 与目标文档一致。
5. answer key 与测试集 case ID 一一对应。
6. 统计题型、难度、来源页码覆盖，避免集中在少数页。

---

## 六、统一评测策略

全部 batch 生成并人工抽查后，再统一合并为 `rag_testset_v2.json` 运行全量评测。建议流程：

```powershell
cd E:\\rag_project\\rag-agent-kb-system\\backend
python scripts\\run_rag_eval.py `
  --username admin `
  --testset ..\\data\\eval\\rag_testset_v2.json `
  --output ..\\data\\eval\\results\\rag_eval_v2_final.json
```

全量评测前建议确认：

- GB 2760 是否已经按 `replace_source` 模式完成 LLM 整理。
- ChromaDB 与 SQLite `chunk_count` 是否一致。
- `HYBRID_BM25_ENABLED=true`，reranker 是否按当前实验目标开启。
"""


def clean(value: object) -> str:
    text = str(value or "").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip(" ：:，,。；;|｜\"'“”")


def short(value: str, limit: int = 28) -> str:
    value = clean(value)
    value = re.split(r"[，,；;。|｜]", value)[0]
    return value if len(value) <= limit else value[:limit]


def body_of(content: str) -> str:
    return re.sub(r"^来源文件：.*?内容类型：[^。]+。\s*", "", content, flags=re.S)


def page_of(content: str) -> int | None:
    match = re.search(r"页码：第([0-9]+)页", content)
    return int(match.group(1)) if match else None


def table_of(content: str) -> str:
    if "表C.2" in content or "加工助剂" in content:
        return "表C.2"
    # Many A.1 chunks mention "表A.2中编号..." as an exclusion condition, not as
    # their own source table. For batch01 material, non-C.2 rows are A.1 rows.
    return "表A.1"


def infer_topic(content: str) -> str:
    body = body_of(content)
    primary_patterns = [
        r"食品添加剂[:：]?\s*([^（，。:：\n]+)[（(]",
        r"([A-Za-z0-9+'’·\-\u4e00-\u9fff、，]{2,36})[（(][^）)]*CNS号",
        r"([A-Za-z0-9+'’·\-\u4e00-\u9fff、，]{2,36})\s+CNS号",
    ]
    fallback_patterns = [
        r"以([^，。；;（）()]{2,12})计",
    ]
    bad_tokens = (
        "食品分类号",
        "最大使用量",
        "根据GB",
        "GB 2760",
        "表A",
        "来源文件",
        "文件",
        "标准",
        "页码",
        "OCR",
        "待核验",
        "缺失",
        "即饮状态",
    )
    for patterns in (primary_patterns, fallback_patterns):
        candidates: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, body):
                name = clean(match.group(1)).replace("，", "、")
                name = re.sub(r"^(中|和|及|为|食品添加剂[:：]?)", "", name)
                if 1 < len(name) <= 36 and not any(token in name for token in bad_tokens):
                    candidates.append(name)
        if candidates:
            return candidates[-1]
    return ""


def first_food_fact(content: str) -> tuple[str, str, str, str, str]:
    body = body_of(content)
    patterns = [
        rf"[-—]?\s*({FOOD_CODE_PATTERN})\s+([^:：；;。|｜-]{{2,60}})[:：]\s*([≤<]?\s*(?:按生产需要适量使用|[0-9]+(?:[.][0-9]+)?\s*(?:g/kg|mg/kg|g/L|mg/L)?))",
        rf"食品分类号\s*({FOOD_CODE_PATTERN})[，,：:\s|｜]*(?:食品名称)?[：:]?\s*[“\"「]?([^，,；;。|｜]+?)[”\"」]?[,，|｜\s]+最大使用量(?:为|[:：])?\s*([≤<]?\s*(?:按生产需要适量使用|[0-9]+(?:[.][0-9]+)?\s*(?:g/kg|mg/kg|g/L|mg/L)?))",
        rf"({FOOD_CODE_PATTERN})\s*[|｜]\s*([^|｜。；;]+?)\s*[|｜]\s*([≤<]?\s*(?:按生产需要适量使用|[0-9]+(?:[.][0-9]+)?\s*(?:g/kg|mg/kg|g/L|mg/L)?))",
        rf"食品分类号\s*({FOOD_CODE_PATTERN})[（(]([^）)]+)[）)](?:的)?最大使用量(?:为)?\s*([≤<]?\s*(?:按生产需要适量使用|[0-9]+(?:[.][0-9]+)?\s*(?:g/kg|mg/kg|g/L|mg/L)?))",
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if not match:
            continue
        code, food, value = (clean(part) for part in match.groups())
        tail = body[match.end() : match.end() + 140]
        remark_match = re.search(r"备注[:：]?\s*([^。；;|｜]+)", tail)
        remark = clean(remark_match.group(1)) if remark_match else ""
        if code and food and value:
            local_context = body[max(0, match.start() - 260) : match.start()]
            local_topic = infer_topic(local_context)
            return code, food, value, remark, local_topic
    return "", "", "", "", ""


def cns_fact(content: str) -> tuple[str, str, str, str]:
    body = body_of(content)
    patterns = [
        r"([^。；;，,：:]{2,36})[（(][^）)]*CNS号\s*([0-9.、,，]+)[，,；;\s]+INS号\s*([^，,；;）)]+)[，,；;\s]+功能[:：]?([^。；;，,]+)",
        r"([^。；;，,：:]{2,36})，?CNS号\s*([0-9.、,，]+)[，,；;\s]+INS号\s*([^，,；;）)]+)[，,；;\s]+功能[:：]?([^。；;，,]+)",
    ]
    bad_tokens = ("食品分类号", "根据", "GB 2760", "表A", "来源文件", "OCR", "待核验", "缺失")
    for pattern in patterns:
        match = re.search(pattern, body)
        if not match:
            continue
        name, cns, ins, func = (clean(part) for part in match.groups())
        func = clean(re.split(r"[）)]\s*[-—]| - ", func)[0])
        func = clean(func.split("）")[0].split(")")[0])
        name = re.sub(r"^(中|和|及|为|食品添加剂[:：]?)", "", name)
        name = re.sub(r"^[0-9]+[.、]\s*", "", name)
        if 1 < len(name) <= 36 and not any(token in name for token in bad_tokens):
            return name, cns, ins, func
    return "", "", "", ""


def processing_aid(content: str) -> tuple[str, str, str, str]:
    body = body_of(content)
    patterns = [
        r"(?:序号)?\s*([0-9]{1,3})[：:、. ]+([^（，。；;]+)[（(]([^）)]+)[）)]，?功能[:：]?([^，。；;]+)，?使用范围[:：]?([^。；;]+)",
        r"序号([0-9]{1,3})：([^（，。；;]+)[（(]([^）)]+)[）)]，功能为?([^，。；;]+)，使用范围为?([^。；;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if match:
            no, name, _en, func, scope = (clean(part) for part in match.groups())
            return no, name, func, scope
    return "", "", "", ""


def make_case(source_index: int, item: dict) -> tuple[dict, dict]:
    content = str(item.get("content") or "")
    page = page_of(content)
    table = table_of(content)
    _no, aid_name, aid_func, aid_scope = processing_aid(content)
    topic = infer_topic(content)
    code, food, value, remark, local_topic = first_food_fact(content)
    cns_name, cns, ins, func = cns_fact(content)
    qtype = "table_data"
    difficulty = "medium"

    if aid_name:
        qtype = "factual_lookup"
        question = f"GB 2760-2024表C.2中，{aid_name}作为食品工业用加工助剂的功能和使用范围是什么？"
        keywords = [aid_name, aid_func, short(aid_scope, 18)]
        answer = f"GB 2760-2024{table}中，{aid_name}的功能为{aid_func}，使用范围为{aid_scope}。"
    elif local_topic and food and value:
        topic = local_topic
        difficulty = "hard" if (remark or "按生产需要适量使用" in value) else "medium"
        qtype = "mixed" if difficulty == "hard" else "table_data"
        question = f"GB 2760-2024中，{topic}在{short(food, 30)}中的最大使用量或备注是什么？"
        keywords = [topic, short(food, 18), value]
        if remark:
            keywords.append(short(remark, 18))
        answer = f"GB 2760-2024{table}中，{topic}用于{food}时，最大使用量为{value}。"
        if remark:
            answer += f"备注：{remark}。"
    elif cns_name and cns and func:
        qtype = "factual_lookup"
        difficulty = "easy"
        question = f"GB 2760-2024中，{cns_name}的CNS号、INS号和功能是什么？"
        keywords = [cns_name, cns.split("、")[0].split(",")[0], short(func, 14)]
        if ins and ins not in {"—", "-", "空白", "未列出"}:
            keywords.append(ins.split("、")[0].split(",")[0])
        answer = f"GB 2760-2024{table}中，{cns_name}的CNS号为{cns}，INS号为{ins}，功能为{func}。"
    elif food and value:
        question = f"GB 2760-2024中，食品分类号{code}（{short(food, 28)}）对应的最大使用量或备注是什么？"
        keywords = [code, short(food, 18), value]
        answer = f"GB 2760-2024{table}中，食品分类号{code}（{food}）的最大使用量为{value}。"
        if remark:
            answer += f"备注：{remark}。"
    else:
        topic = topic or cns_name or f"第{page or source_index}页相关条目"
        qtype = "factual_lookup"
        question = f"GB 2760-2024中，{short(topic, 24)}的使用规定或适用范围是什么？"
        fallback_keyword = (
            "使用范围"
            if table == "表C.2"
            else "使用规定"
            if "使用规定" in content
            else "最大使用量"
            if "最大使用量" in content
            else "GB 2760"
        )
        keywords = [short(topic, 16), fallback_keyword]
        answer = clean(body_of(content)[:300])

    keywords = [keyword for keyword in dict.fromkeys(clean(item) for item in keywords) if keyword]
    if len(keywords) < 2:
        keywords.append("GB 2760")
    case_id = f"V2-B01-Q{source_index:03d}"
    case = {
        "id": case_id,
        "question": question,
        "expected_found": True,
        "expected_answer_keywords": keywords[:5],
        "expected_citation_keywords": ["GB 2760", table],
        "document_ids": [DOC_ID_GB2760],
        "top_k": 12 if difficulty == "hard" else 10,
        "tags": ["v2", "batch01", "gb2760", qtype, difficulty],
        "notes": f"source=tmp_gb2760_llm_chunks.json; chunk={source_index}; page={page or ''}; table={table}",
    }
    key = {
        "id": case_id,
        "difficulty": difficulty,
        "question_type": qtype,
        "standard_answer": answer,
        "source_file": "GB 2760-2024 食品添加剂使用标准.pdf",
        "source_page": page,
        "source_table": table,
        "expected_found": True,
        "source_chunk": source_index,
    }
    return case, key


def extra_cns_cases(start_index: int, source_items: list[dict], seen_questions: set[str]) -> list[tuple[dict, dict]]:
    pairs: list[tuple[dict, dict]] = []
    for item in source_items:
        content = str(item.get("content") or "")
        page = page_of(content)
        table = table_of(content)
        body = body_of(content)
        for match in re.finditer(
            r"([^。；;，,：:]{2,36})[（(][^）)]*CNS号\s*([0-9.、,，]+)[，,；;\s]+INS号\s*([^，,；;）)]+)[，,；;\s]+功能[:：]?([^。；;，,]+)",
            body,
        ):
            name, cns, ins, func = (clean(part) for part in match.groups())
            func = clean(re.split(r"[）)]\s*[-—]| - ", func)[0])
            func = clean(func.split("）")[0].split(")")[0])
            name = re.sub(r"^(中|和|及|为|食品添加剂[:：]?)", "", name)
            name = re.sub(r"^[0-9]+[.、]\s*", "", name)
            if not (1 < len(name) <= 30) or any(token in name for token in ("食品分类号", "根据", "GB 2760", "表A", "OCR", "待核验", "缺失")):
                continue
            question = f"GB 2760-2024中，{name}的CNS号和主要功能是什么？"
            if question in seen_questions:
                continue
            index = start_index + len(pairs)
            case_id = f"V2-B01-Q{index:03d}"
            case = {
                "id": case_id,
                "question": question,
                "expected_found": True,
                "expected_answer_keywords": [name, cns.split("、")[0].split(",")[0], short(func, 14)],
                "expected_citation_keywords": ["GB 2760", table],
                "document_ids": [DOC_ID_GB2760],
                "top_k": 8,
                "tags": ["v2", "batch01", "gb2760", "factual_lookup", "easy"],
                "notes": f"extra_cns_case; page={page or ''}; table={table}",
            }
            key = {
                "id": case_id,
                "difficulty": "easy",
                "question_type": "factual_lookup",
                "standard_answer": f"GB 2760-2024{table}中，{name}的CNS号为{cns}，INS号为{ins}，功能为{func}。",
                "source_file": "GB 2760-2024 食品添加剂使用标准.pdf",
                "source_page": page,
                "source_table": table,
                "expected_found": True,
                "source_chunk": None,
            }
            pairs.append((case, key))
            seen_questions.add(question)
            if start_index + len(pairs) > TARGET_BATCH01:
                return pairs
    return pairs


def build_batch01() -> tuple[dict, dict, str]:
    source_items = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    pairs: list[tuple[dict, dict]] = []
    seen_questions: set[str] = set()
    for source_index, item in enumerate(source_items, start=1):
        case, key = make_case(source_index, item)
        if _is_low_quality_generated_case(case):
            continue
        if case["question"] in seen_questions:
            page = key.get("source_page")
            case["question"] = case["question"].rstrip("？") + f"（来源页约第{page}页）？"
        if case["question"] in seen_questions:
            continue
        seen_questions.add(case["question"])
        pairs.append((case, key))
        if len(pairs) >= TARGET_BATCH01:
            break
    if len(pairs) < TARGET_BATCH01:
        pairs.extend(extra_cns_cases(len(pairs) + 1, source_items, seen_questions))
    pairs = pairs[:TARGET_BATCH01]

    cases = []
    questions = []
    for index, (case, key) in enumerate(pairs, start=1):
        case_id = f"V2-B01-Q{index:03d}"
        case["id"] = case_id
        key["id"] = case_id
        cases.append(case)
        questions.append(key)

    testset = {"name": "rag-testset-v2-batch01-gb2760", "cases": cases}
    answer_key = {
        "name": "rag-testset-v2-batch01-gb2760-answer-key",
        "version": "v2.0-batch01",
        "created": str(date.today()),
        "description": "GB 2760-2024 食品添加剂使用标准批次测试题。基于 tmp_gb2760_llm_chunks.json 离线生成，尚未运行 RAG 全量评测。",
        "total_questions": len(questions),
        "difficulty_distribution": dict(Counter(item["difficulty"] for item in questions)),
        "type_distribution": dict(Counter(item["question_type"] for item in questions)),
        "questions": questions,
    }
    page_counter = Counter(str(item.get("source_page") or "unknown") for item in questions)
    duplicate_questions = len(cases) - len({case["question"] for case in cases})
    report = f"""# RAG Testset v2 Batch01 离线生成报告

生成日期: {date.today()}  
测试集: `{BATCH_PATH.as_posix()}`  
答案键: `{ANSWER_KEY_PATH.as_posix()}`  
来源素材: `{SOURCE_PATH.as_posix()}`

## 结果

| 检查项 | 结果 |
|--------|------|
| 题目数量 | {len(cases)} |
| answer key 数量 | {len(questions)} |
| 重复问题数 | {duplicate_questions} |
| 空答案关键词 | {sum(1 for case in cases if not case.get("expected_answer_keywords"))} |
| 空引用关键词 | {sum(1 for case in cases if not case.get("expected_citation_keywords"))} |
| 固定 document_ids | {[DOC_ID_GB2760]} |
| 是否运行 RAG 评测 | 否，本轮只做数据集构建 |

## 难度分布

```json
{json.dumps(answer_key["difficulty_distribution"], ensure_ascii=False, indent=2)}
```

## 题型分布

```json
{json.dumps(answer_key["type_distribution"], ensure_ascii=False, indent=2)}
```

## 页码覆盖 Top 20

```json
{json.dumps(dict(page_counter.most_common(20)), ensure_ascii=False, indent=2)}
```

## 后续建议

1. 人工抽查 10-20 条 GB 2760 题目，重点看自动提取的添加剂名称是否过长或不自然。
2. 如果 GB 2760 重新执行 LLM 整理，建议再生成一版 batch01 或补充更精细的食品分类号题。
3. 全部 batch 完成后再合并运行 `run_rag_eval.py`，避免现在消耗 API 额度。
"""
    return testset, answer_key, report


def _is_low_quality_generated_case(case: dict) -> bool:
    question = str(case.get("question") or "")
    keywords = " ".join(str(item) for item in case.get("expected_answer_keywords") or [])
    bad_markers = ("相关条目", "OCR显示", "待核验", "第unknown页", "缺失")
    if any(marker in question or marker in keywords for marker in bad_markers):
        return True
    if "第" in keywords and "页" in keywords:
        return True
    return False


def main() -> None:
    PLAN_PATH.write_text(PLAN_MD, encoding="utf-8")
    testset, answer_key, report = build_batch01()
    BATCH_PATH.write_text(json.dumps(testset, ensure_ascii=False, indent=2), encoding="utf-8")
    ANSWER_KEY_PATH.write_text(json.dumps(answer_key, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"cases={len(testset['cases'])}")
    print(f"difficulty={answer_key['difficulty_distribution']}")
    print(f"types={answer_key['type_distribution']}")
    print(BATCH_PATH)
    print(ANSWER_KEY_PATH)
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
