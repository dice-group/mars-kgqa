import os
from typing import Dict, List, Tuple

from src.sparql_gen.sparql_gen_common import get_question_pf_name
from src.util.process_flow_logger import ProcessFlowLogger
from src.kgqa_tool.llm_request import analyse_gen_sparql

from src.util.common import read_json_file
from tqdm import tqdm

def _extract_normalised_answer(answer_obj: dict) -> str:
    """
    Normalise a single ``answers`` entry from a QALD file.

    Handles three known shapes:
      1. ``answers[0]["results"]["bindings"]`` – a list of bindings.
      2. ``answers[0]["boolean"]`` – a boolean result.
      3. Empty ``head`` with a single binding (same as #1).

    Returns a space‑separated string of the extracted values (lower‑cased,
    whitespace‑collapsed) **sorted** so ordering does not affect comparisons.
    """
    # Boolean result
    if "boolean" in answer_obj:
        return str(answer_obj["boolean"]).lower()

    # Results with bindings
    results = answer_obj.get("results", {})
    bindings = results.get("bindings", [])
    values: List[str] = []

    for binding in bindings:
        # each binding maps a variable name (e.g. "o1") to a dict with a "value"
        for var_info in binding.values():
            if isinstance(var_info, dict) and "value" in var_info:
                values.append(str(var_info["value"]))

    # Sort values to make the representation order‑independent
    values.sort()
    # If no bindings were found (unlikely) fall back to an empty string
    return " ".join(values).lower()


def _find_mismatches(
    gold_qald_path: str,
    pred_qald_path: str,
) -> List[Tuple[str, str, str]]:
    """
    Compare gold answers with predictions.

    Returns:
        List of tuples ``(question_id, gold_answer, pred_answer)`` for all
        mismatching IDs.
    """
    
    # Load gold data
    gold_data = read_json_file(gold_qald_path)

    gold_answers: Dict[str, str] = {}
    for q in gold_data.get("questions", []):
        qid = str(q.get("id"))
        answers_list = q.get("answers", [])
        if answers_list:
            # Normalise **all** answer entries and build a canonical string
            norm_set = { _extract_normalised_answer(a) for a in answers_list }
            gold_answers[qid] = " ".join(sorted(norm_set))

    # Load prediction data
    pred_data = read_json_file(pred_qald_path)

    pred_answers: Dict[str, str] = {}
    for q in pred_data.get("questions", []):
        qid = str(q.get("id"))
        answers_list = q.get("answers", [])
        if answers_list:
            norm_set = { _extract_normalised_answer(a) for a in answers_list }
            pred_answers[qid] = " ".join(sorted(norm_set))

    # Compare
    mismatches: List[Tuple[str, str, str]] = []
    for qid, pred_norm in pred_answers.items():
        gold_norm = gold_answers.get(qid, "")
        if pred_norm != gold_norm:
            mismatches.append((qid, gold_norm, pred_norm))

    return mismatches


def _load_log(logs_dir: str, question_id: str) -> str:
    """Read the log file produced for *question_id* (if it exists)."""
    pf_name = get_question_pf_name(question_id)
    log_file_path = ProcessFlowLogger.gen_log_file_path(pf_name, logs_dir)
    if os.path.isfile(log_file_path):
        with open(log_file_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _write_analysis(
    output_dir: str,
    question_id: str,
    analysis_text: str,
    think_content: str
) -> None:
    """Persist the LLM analysis along with the original think content."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{question_id}_analysis.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        # Write think content first
        f.write("=== THINK CONTENT START ===\n")
        f.write(think_content.rstrip() + "\n")
        f.write("=== THINK CONTENT END ===\n")
        # Unique separator for visual clarity
        f.write("\n---===---\n\n")
        # Write LLM analysis next
        f.write("=== ANALYSIS START ===\n")
        f.write(analysis_text.rstrip() + "\n")
        f.write("=== ANALYSIS END ===\n")

def analyse_mismatches(
    gold_qald_path: str,
    pred_qald_path: str,
    logs_dir: str,
    output_dir: str,
    llm_config,
) -> None:
    """
    End‑to‑end driver that discovers mismatching answers and creates an LLM
    analysis for each of them.
    """
    mismatches = _find_mismatches(gold_qald_path, pred_qald_path)

    if not mismatches:
        print("All predictions match the gold answers – nothing to analyse.")
        return

    print(f"Found {len(mismatches)} mismatching question(s).")
    for qid, gold_ans, pred_ans in tqdm(mismatches, 'Analysing Mismatches'):
        log_txt = _load_log(logs_dir, qid)
        analysis, think_content = analyse_gen_sparql(gold_ans, pred_ans, log_txt, llm_config)
        _write_analysis(output_dir, qid, analysis, think_content)
        print(f"\t - {qid}: analysis written.")