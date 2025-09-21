# Sample usage: bash pylauncher.sh normal src.util.external_kgqa
import json
import csv
from pathlib import Path
from typing import Iterable, Dict, Any
import re
from typing import Pattern
from src.kgqa_tool.llm_request import sparql_filter

_LANG_FILTER_RE: Pattern = re.compile(
    r"""
    FILTER\s*\(\s*LANG\s*\(\s*\?\w+\s*\)\s*=\s*['"]\w{2}['"]\s*\)
    """,
    re.IGNORECASE | re.VERBOSE,
)

def has_language_filter(sparql_snippet: str) -> bool:
    return bool(_LANG_FILTER_RE.search(sparql_snippet))

def qald_to_grasp_jsonl(qald_file: str, jsonl_out: str):
    qald_path = Path(qald_file)
    out_path = Path(jsonl_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with qald_path.open(encoding="utf‑8") as f:
        data = json.load(f)

    questions: Iterable[Dict[str, Any]] = data.get("questions", [])
    with out_path.open("w", encoding="utf‑8") as out_f:
        for q in questions:
            q_text = ""
            if isinstance(q.get("question"), list):
                for entry in q["question"]:
                    if entry.get("language") == "en":
                        q_text = entry.get("string", "")
                        break
            q_text = q_text or q.get("string", "") or q.get("question", "")
            q_id = str(q.get("id"))

            entry = {
                "id": q_id,
                "question": q_text,
                "sparql": "", # Keeping this empty on purpose
                "paraphrases": [],
                "info": {}
            }
            out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def grasp_output_to_tsv(grasp_out: str, tsv_out: str, refine_sparql: bool):
    
    inp_path = Path(grasp_out)
    out_path = Path(tsv_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with inp_path.open(encoding="utf‑8") as in_f, \
         out_path.open("w", encoding="utf‑8", newline="") as out_f:
        writer = csv.writer(out_f, delimiter="\t")
        # header
        header = ["Question ID", "Answer"]
        writer.writerow(header)

        for line in in_f:
            if not line.strip():
                continue
            obj = json.loads(line)
            qid = obj.get("id")
            output_section = obj.get("output") or {} # setting default get value does not work if the data has "null" mapped to the key
            ans = output_section.get("sparql") or ""
            # Ensure the SPARQL query is a single‑line string (remove newlines and extra whitespace)
            ans = " ".join(ans.split())
            ans = ans.strip()
            if refine_sparql and len(ans) > 0: 
                ans = refine_output_sparql(ans)
            row = [qid, ans]
            writer.writerow(row)

def evaluate_external_system(system_name, kgqa_dataset, split, external_qald_file, lang):
    pass

def refine_output_sparql(sparql_str):
    if has_language_filter(sparql_str):
        # TODO: Refine the input sparql to remove the selected labels if any
        pass
    # NOTE: More refinement cases to be added here if needed
    return sparql_str
            
# Example usage
if __name__ == "__main__":
    # from src.const.dataset import KgqaDataset, DatasetSplit
    
    # ds_obj = KgqaDataset.QALD10
    # ds_split = DatasetSplit.TEST
    
    # ds_path = ds_obj.value.split_dict[ds_split]
    # qald_to_grasp_jsonl(ds_path, f'data_dir/external_systems/grasp/input/{ds_obj.value.dataset_id}_{ds_split.name.lower()}.jsonl')
    
    grasp_output_to_tsv('data_dir/external_systems/grasp/output/original/gpt-oss-120b/qald9plus_updt_curwd_test_output.jsonl', 'data_dir/external_systems/grasp/output/tsv/gpt-oss-120b/qald9plus_updt_curwd_test_output.tsv')