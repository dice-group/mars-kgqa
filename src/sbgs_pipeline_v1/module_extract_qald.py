# simple_qald_extract.py
#!/usr/bin/env python3
from typing import Any, Dict, List


def extract(data: Dict[str, Any], lang: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "questions" : []
    }
    questions = data.get("questions", [])
    if not isinstance(questions, list):
        return out

    for id, q in enumerate(questions, start=1):
        # print(q)
        if not isinstance(q, dict):
            continue
        # qid = str(q.get("id", idx))

        # q_text = pick_question_text(q.get("question"), lang)
        q_text = next((it["string"] for it in (q.get("question") or []) if isinstance(it, dict) and str(it.get("language", "")).lower() == lang and isinstance(it.get("string"), str)), None)
        if not q_text:
            # Skip if no question in the requested language
            continue

        sparql = None
        q_query = q.get("query")
        if isinstance(q_query, dict) and isinstance(q_query.get("sparql"), str):
            sparql = q_query["sparql"]

        ents: List[Dict[str, Any]] = []
        rels: List[Dict[str, Any]] = []
        t5_aug = q.get("t5_aug")
        if isinstance(t5_aug, dict):
            lang_block = t5_aug.get(lang)
            if isinstance(lang_block, dict):
                if isinstance(lang_block.get("entities"), list):
                    ents = [e for e in lang_block["entities"] if isinstance(e, dict)]
                if isinstance(lang_block.get("relations"), list):
                    rels = [r for r in lang_block["relations"] if isinstance(r, dict)]

        dict_values= {
            "question": q_text,
            "sparql": sparql,
            "entities": ents,
            "relations": rels,
        }
        out["questions"].append(dict_values)

    return out


if __name__ == "__main__":
    result = extract( "../../data_dir/processed_kgqa_ds/qald9plus/test/tentrisq10_aug_gold.json", "en")
