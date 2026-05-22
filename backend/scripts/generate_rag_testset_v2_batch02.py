# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
PLAN_PATH = EVAL_DIR / "rag_testset_v2_plan.md"
BATCH_PATH = EVAL_DIR / "rag_testset_v2_batch02_contaminants_mycotoxins.json"
ANSWER_KEY_PATH = EVAL_DIR / "rag_testset_v2_batch02_contaminants_mycotoxins_answer_key.json"
REPORT_PATH = EVAL_DIR / "rag_testset_v2_batch02_report.md"

DOC_2762 = 52
DOC_2761 = 51
TARGETS = {DOC_2762: 35, DOC_2761: 22}
DOC_INFO = {
    DOC_2762: {
        "standard": "GB 2762-2025",
        "source_file": "GB 2762-2025 食品中污染物限量.pdf",
        "name": "contaminants",
        "topic": "污染物",
        "allowed_tables": {f"表{index}" for index in range(1, 13)},
    },
    DOC_2761: {
        "standard": "GB 2761-2017",
        "source_file": "GB 2761-2017 食品中真菌毒素限量.pdf",
        "name": "mycotoxins",
        "topic": "真菌毒素",
        "allowed_tables": {f"表{index}" for index in range(1, 7)},
    },
}


def clean(value: object) -> str:
    text = str(value or "").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip(" ：:，,。；;|｜\"'“”")


def short(value: str, limit: int = 42) -> str:
    value = clean(value)
    return value if len(value) <= limit else value[:limit]


def compact_food(value: str) -> str:
    value = clean(value)
    value = re.sub(r"[a-z][、，]?", "", value)
    value = re.sub(r"\s+", " ", value)
    if len(value) <= 48:
        return value
    tokens = value.split()
    if len(tokens) >= 2 and len(" ".join(tokens[:2])) <= 48:
        return " ".join(tokens[:2])
    return value[:48]


def parse_table_row_fact(text: str, metadata: dict) -> dict | None:
    table = str(metadata.get("table_label") or "")
    if not re.fullmatch(r"表\d+", table):
        return None
    if "表格第" in text and "检索事实：" not in text:
        return None
    match = re.search(
        r"检索事实：(?P<food>.+?)的(?P<field>限量[^为，。]*)为(?P<value>[^，。]+)",
        text,
        re.S,
    )
    if not match:
        return None
    food = clean(match.group("food"))
    field = clean(match.group("field"))
    value = clean(match.group("value"))
    if not food or not value:
        return None
    if food.startswith(("注", "a ", "b ", "c ", "d ")) or "注:" in food:
        return None
    if value in {"—", "-", "总汞", "总砷"}:
        return None
    analyte = analyte_from_text(text, table)
    if not analyte:
        return None
    return {
        "food": food,
        "field": field,
        "value": value,
        "analyte": analyte,
        "table": table,
        "page": metadata.get("page"),
        "chunk_index": metadata.get("chunk_index"),
        "unit": unit_from(field, value),
    }


def analyte_from_text(text: str, table: str) -> str:
    title_match = re.search(r"表题：表\d+\s*食品中(.+?)限量指标", text)
    if title_match:
        return clean(title_match.group(1))
    label_map = {
        "表1": "铅",
        "表2": "镉",
        "表3": "汞",
        "表4": "砷",
        "表5": "锡",
        "表6": "镍",
        "表7": "铬",
        "表8": "亚硝酸盐、硝酸盐",
        "表9": "苯并[a]芘",
        "表10": "N-二甲基亚硝胺",
        "表11": "多氯联苯",
        "表12": "3-氯-1,2-丙二醇",
    }
    return label_map.get(table, "")


def unit_from(field: str, value: str) -> str:
    match = re.search(r"(μg/kg|ug/kg|mg/kg|μg/L|ug/L|mg/L)", f"{field} {value}", re.I)
    if not match:
        return ""
    return match.group(1).replace("ug", "μg")


def primary_value(value: str) -> str:
    match = re.search(r"[0-9]+(?:\.[0-9]+)?\s*(?:μg/kg|ug/kg|mg/kg|μg/L|ug/L|mg/L)?", value, re.I)
    if match:
        return clean(match.group(0).replace("ug", "μg"))
    return short(value, 16)


def manual_cases() -> list[tuple[dict, dict]]:
    rows = [
        (
            DOC_2762,
            "easy",
            "factual_lookup",
            "GB 2762-2025规定了哪些食品中污染物限量指标？",
            ["铅", "镉", "汞", "3-氯-1,2-丙二醇"],
            "GB 2762-2025规定了食品中铅、镉、汞、砷、锡、镍、铬、亚硝酸盐、硝酸盐、苯并[a]芘、N-二甲基亚硝胺、多氯联苯、3-氯-1,2-丙二醇的限量指标。",
            3,
            None,
        ),
        (
            DOC_2762,
            "easy",
            "definition",
            "GB 2762-2025中污染物的定义是什么？",
            ["非有意加入", "化学性危害物质", "农药残留"],
            "污染物是在食品生产、加工、包装、贮存、运输、销售直至食用等过程中产生的或由环境污染带入的、非有意加入的化学性危害物质；本标准所指污染物不包括农药残留、兽药残留、生物毒素和放射性物质。",
            3,
            None,
        ),
        (
            DOC_2762,
            "easy",
            "definition",
            "GB 2762-2025中可食用部分指什么？",
            ["机械手段", "去除非食用部分", "用于食用"],
            "可食用部分是食品原料经过机械手段去除非食用部分后得到的用于食用的部分。",
            3,
            None,
        ),
        (
            DOC_2762,
            "medium",
            "cross_reference",
            "GB 2762-2025代替了哪个污染物限量标准？",
            ["GB 2762—2022", "第1号修改单"],
            "GB 2762-2025代替GB 2762—2022《食品安全国家标准 食品中污染物限量》及第1号修改单。",
            2,
            None,
        ),
        (
            DOC_2762,
            "medium",
            "factual_lookup",
            "GB 2762-2025要求食品生产和加工者如何控制污染物？",
            ["采取控制措施", "最低水平"],
            "无论是否制定污染物限量，食品生产和加工者均应采取控制措施，使食品中污染物的含量达到最低水平。",
            3,
            None,
        ),
        (
            DOC_2761,
            "easy",
            "factual_lookup",
            "GB 2761-2017规定了哪些食品中真菌毒素限量指标？",
            ["黄曲霉毒素B1", "黄曲霉毒素M1", "展青霉素", "玉米赤霉烯酮"],
            "GB 2761-2017规定了食品中黄曲霉毒素B1、黄曲霉毒素M1、脱氧雪腐镰刀菌烯醇、展青霉素、赭曲霉毒素A及玉米赤霉烯酮的限量指标。",
            3,
            None,
        ),
        (
            DOC_2761,
            "easy",
            "definition",
            "GB 2761-2017中真菌毒素的定义是什么？",
            ["真菌", "生长繁殖", "次生有毒代谢产物"],
            "真菌毒素是真菌在生长繁殖过程中产生的次生有毒代谢产物。",
            3,
            None,
        ),
        (
            DOC_2761,
            "easy",
            "definition",
            "GB 2761-2017中限量的含义是什么？",
            ["食品原料", "食品成品", "最大含量水平"],
            "限量是真菌毒素在食品原料和（或）食品成品可食用部分中允许的最大含量水平。",
            3,
            None,
        ),
        (
            DOC_2761,
            "medium",
            "cross_reference",
            "GB 2761-2017中黄曲霉毒素B1的检验方法按哪个标准测定？",
            ["GB 5009.22", "黄曲霉毒素B1"],
            "GB 2761-2017中黄曲霉毒素B1的检验方法按GB 5009.22规定的方法测定。",
            4,
            "表1",
        ),
    ]
    pairs: list[tuple[dict, dict]] = []
    for doc_id, difficulty, question_type, question, keywords, answer, page, table in rows:
        pairs.append(
            build_pair(
                doc_id=doc_id,
                difficulty=difficulty,
                question_type=question_type,
                question=question,
                keywords=keywords,
                citation_keywords=[DOC_INFO[doc_id]["standard"].split("-")[0], table or DOC_INFO[doc_id]["standard"].split("-")[0]],
                answer=answer,
                page=page,
                table=table,
                source_chunk=None,
            )
        )
    return pairs


def build_pair(
    *,
    doc_id: int,
    difficulty: str,
    question_type: str,
    question: str,
    keywords: list[str],
    citation_keywords: list[str],
    answer: str,
    page: int | None,
    table: str | None,
    source_chunk: int | None,
) -> tuple[dict, dict]:
    info = DOC_INFO[doc_id]
    tags = ["v2", "batch02", info["name"], question_type, difficulty]
    case = {
        "id": "",
        "question": question,
        "expected_found": True,
        "expected_answer_keywords": [item for item in dict.fromkeys(clean(k) for k in keywords) if item],
        "expected_citation_keywords": [item for item in dict.fromkeys(clean(k) for k in citation_keywords) if item],
        "document_ids": [doc_id],
        "top_k": 12 if difficulty == "hard" else 10,
        "tags": tags,
        "notes": f"source=chroma; doc_id={doc_id}; chunk={source_chunk or ''}; page={page or ''}; table={table or ''}",
    }
    key = {
        "id": "",
        "difficulty": difficulty,
        "question_type": question_type,
        "standard_answer": answer,
        "source_file": info["source_file"],
        "source_page": page,
        "source_table": table,
        "expected_found": True,
        "source_chunk": source_chunk,
    }
    return case, key


def build_row_pair(doc_id: int, fact: dict) -> tuple[dict, dict]:
    info = DOC_INFO[doc_id]
    standard = info["standard"]
    food = compact_food(fact["food"])
    analyte = fact["analyte"]
    value = fact["value"]
    unit = fact["unit"]
    number_count = len(re.findall(r"\d+(?:\.\d+)?", value))
    difficulty = "hard" if len(fact["food"]) > 90 or number_count >= 3 else "medium"
    question_type = "mixed" if difficulty == "hard" else "table_data"
    question = f"{standard}中，{food}的{analyte}限量指标是多少？"
    value_keyword = primary_value(value)
    keywords = [analyte, short(food, 24), value_keyword]
    if unit:
        keywords.append(unit)
    table = fact["table"]
    answer = (
        f"{standard}{table}中，{fact['food']}的{analyte}限量指标为{value}。"
        f"字段为{fact['field']}。"
    )
    return build_pair(
        doc_id=doc_id,
        difficulty=difficulty,
        question_type=question_type,
        question=question,
        keywords=keywords,
        citation_keywords=[standard.split("-")[0], table],
        answer=answer,
        page=fact["page"],
        table=table,
        source_chunk=fact["chunk_index"],
    )


def collect_row_facts(doc_id: int) -> list[dict]:
    from app.rag.vector_store import ChromaVectorStore

    allowed_tables = DOC_INFO[doc_id]["allowed_tables"]
    chunks = ChromaVectorStore().get_document_chunks(document_id=doc_id, limit=1000)
    facts: list[dict] = []
    for item in chunks:
        metadata = dict(item.get("metadata") or {})
        if metadata.get("chunk_type") != "table_row_fact":
            continue
        fact = parse_table_row_fact(str(item.get("text") or ""), metadata)
        if not fact or fact["table"] not in allowed_tables:
            continue
        facts.append(fact)
    return facts


def select_row_pairs(doc_id: int, count: int, used_questions: set[str]) -> list[tuple[dict, dict]]:
    facts = collect_row_facts(doc_id)
    by_table: dict[str, list[dict]] = defaultdict(list)
    for fact in facts:
        by_table[fact["table"]].append(fact)

    selected: list[tuple[dict, dict]] = []
    tables = sorted(by_table, key=lambda value: int(value.removeprefix("表")))
    cursor = 0
    while len(selected) < count and tables:
        table = tables[cursor % len(tables)]
        candidates = by_table[table]
        if candidates:
            fact = candidates.pop(0)
            case, key = build_row_pair(doc_id, fact)
            if case["question"] not in used_questions and not _is_bad_case(case):
                used_questions.add(case["question"])
                selected.append((case, key))
        if not candidates:
            tables.remove(table)
            cursor = 0
        else:
            cursor += 1
    return selected


def _is_bad_case(case: dict) -> bool:
    question = str(case.get("question") or "")
    keywords = " ".join(str(item) for item in case.get("expected_answer_keywords") or [])
    bad_markers = ("注:", "表格第", "相关条目", "无相应限量", "— —", "为总汞", "为总砷")
    return any(marker in question or marker in keywords for marker in bad_markers)


def renumber(pairs: list[tuple[dict, dict]]) -> tuple[list[dict], list[dict]]:
    cases: list[dict] = []
    keys: list[dict] = []
    for index, (case, key) in enumerate(pairs, start=1):
        case_id = f"V2-B02-Q{index:03d}"
        case["id"] = case_id
        key["id"] = case_id
        cases.append(case)
        keys.append(key)
    return cases, keys


def build_batch02() -> tuple[dict, dict, str]:
    pairs = manual_cases()
    used_questions = {case["question"] for case, _key in pairs}
    current_counts = Counter(case["document_ids"][0] for case, _key in pairs)
    for doc_id, target in TARGETS.items():
        needed = target - current_counts[doc_id]
        pairs.extend(select_row_pairs(doc_id, needed, used_questions))

    cases, keys = renumber(pairs)
    testset = {"name": "rag-testset-v2-batch02-contaminants-mycotoxins", "cases": cases}
    answer_key = {
        "name": "rag-testset-v2-batch02-contaminants-mycotoxins-answer-key",
        "version": "v2.0-batch02",
        "created": str(date.today()),
        "description": "GB 2762-2025 污染物限量与 GB 2761-2017 真菌毒素限量批次测试题。基于已入库 Chroma 切块离线生成，尚未运行 RAG 全量评测。",
        "total_questions": len(keys),
        "difficulty_distribution": dict(Counter(item["difficulty"] for item in keys)),
        "type_distribution": dict(Counter(item["question_type"] for item in keys)),
        "document_distribution": dict(Counter(case["document_ids"][0] for case in cases)),
        "questions": keys,
    }
    page_counter = Counter(
        f"{key['source_file'].split()[0]} {key['source_file'].split()[1]} p{key.get('source_page') or 'unknown'}"
        for key in keys
    )
    report = f"""# RAG Testset v2 Batch02 离线生成报告

生成日期: {date.today()}  
测试集: `{BATCH_PATH.as_posix()}`  
答案键: `{ANSWER_KEY_PATH.as_posix()}`  
来源素材: ChromaDB 已入库切块（doc_id 52, 51）

## 结果

| 检查项 | 结果 |
|--------|------|
| 题目数量 | {len(cases)} |
| answer key 数量 | {len(keys)} |
| 重复问题数 | {len(cases) - len({case['question'] for case in cases})} |
| 空答案关键词 | {sum(1 for case in cases if not case.get('expected_answer_keywords'))} |
| 空引用关键词 | {sum(1 for case in cases if not case.get('expected_citation_keywords'))} |
| 文档分布 | {dict(Counter(case['document_ids'][0] for case in cases))} |
| 是否运行 RAG 评测 | 否，本轮只做数据集构建 |

## 难度分布

```json
{json.dumps(answer_key['difficulty_distribution'], ensure_ascii=False, indent=2)}
```

## 题型分布

```json
{json.dumps(answer_key['type_distribution'], ensure_ascii=False, indent=2)}
```

## 页码覆盖 Top 20

```json
{json.dumps(dict(page_counter.most_common(20)), ensure_ascii=False, indent=2)}
```
"""
    return testset, answer_key, report


def update_plan_status() -> None:
    if not PLAN_PATH.exists():
        return
    text = PLAN_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "| batch02 | `rag_testset_v2_batch02_contaminants_mycotoxins.json` | GB 2762 + GB 2761 | 57 | 污染物和真菌毒素限量、食品类别、检验方法 | 待生成 |",
        "| batch02 | `rag_testset_v2_batch02_contaminants_mycotoxins.json` | GB 2762 + GB 2761 | 57 | 污染物和真菌毒素限量、食品类别、检验方法 | 已生成 |",
    )
    PLAN_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    testset, answer_key, report = build_batch02()
    BATCH_PATH.write_text(json.dumps(testset, ensure_ascii=False, indent=2), encoding="utf-8")
    ANSWER_KEY_PATH.write_text(json.dumps(answer_key, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(report, encoding="utf-8")
    update_plan_status()
    print(f"cases={len(testset['cases'])}")
    print(f"difficulty={answer_key['difficulty_distribution']}")
    print(f"types={answer_key['type_distribution']}")
    print(f"documents={answer_key['document_distribution']}")
    print(BATCH_PATH)
    print(ANSWER_KEY_PATH)
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
