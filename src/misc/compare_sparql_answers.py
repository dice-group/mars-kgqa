#!/usr/bin/env python3
"""
Utility script to compare gold/reference SPARQL queries and answer sets
against system predictions for KGQA datasets (qald9plus, qald10, etc.).

Compares:
  - SPARQL queries: exact string match, normalized match (prefix/whitespace/var-agnostic)
  - Answer sets: exact match, precision, recall, F1 per question and overall

Usage:
    # Compare single dataset (qald9plus):
    bash pylauncher.sh normal src.misc.compare_sparql_answers \
        --gold data_dir/processed_kgqa_ds/qald9plus/test/gerbil-ready_tentrismain_aug_gold.json \
        --pred data_dir/best_1/processed_kgqa_ds/qald9plus/test/prediction/tentrismain_aug_gold/json/gerbil-ready_en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.json \
        --output data_dir/misc/comparison_qald9plus

    # Compare single dataset (qald10):
    bash pylauncher.sh normal src.misc.compare_sparql_answers \
        --gold data_dir/processed_kgqa_ds/qald10/test/gerbil-ready_tentrismain_aug_gold.json \
        --pred data_dir/best_1/processed_kgqa_ds/qald10/test/prediction/tentrismain_aug_gold/json/gerbil-ready_en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.json \
        --output data_dir/misc/comparison_qald10

    # Compare both datasets at once:
    bash pylauncher.sh normal src.misc.compare_sparql_answers \
        --gold data_dir/processed_kgqa_ds/qald9plus/test/gerbil-ready_tentrismain_aug_gold.json \
        --pred data_dir/best_1/processed_kgqa_ds/qald9plus/test/prediction/tentrismain_aug_gold/json/gerbil-ready_en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.json \
        --gold data_dir/processed_kgqa_ds/qald10/test/gerbil-ready_tentrismain_aug_gold.json \
        --pred data_dir/best_1/processed_kgqa_ds/qald10/test/prediction/tentrismain_aug_gold/json/gerbil-ready_en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.json \
        --output data_dir/misc/comparison_both
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from src.util.common import create_directory_if_not_exists


# Reverse prefix map: prefix_name -> uri_prefix
_PREFIX_TO_URI = {
    "bd": "http://www.bigdata.com/rdf#",
    "cc": "http://creativecommons.org/ns#",
    "dct": "http://purl.org/dc/terms/",
    "geo": "http://www.opengis.net/ont/geosparql#",
    "hint": "http://www.bigdata.com/queryHints#",
    "ontolex": "http://www.w3.org/ns/lemon/ontolex#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "prov": "http://www.w3.org/ns/prov#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "schema": "http://schema.org/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "p": "http://www.wikidata.org/prop/",
    "pq": "http://www.wikidata.org/prop/qualifier/",
    "pqn": "http://www.wikidata.org/prop/qualifier/value-normalized/",
    "pqv": "http://www.wikidata.org/prop/qualifier/value/",
    "pr": "http://www.wikidata.org/prop/reference/",
    "prn": "http://www.wikidata.org/prop/reference/value-normalized/",
    "prv": "http://www.wikidata.org/prop/reference/value/",
    "psv": "http://www.wikidata.org/prop/statement/value/",
    "ps": "http://www.wikidata.org/prop/statement/",
    "psn": "http://www.wikidata.org/prop/statement/value-normalized/",
    "wd": "http://www.wikidata.org/entity/",
    "wdata": "http://www.wikidata.org/wiki/Special:EntityData/",
    "wdno": "http://www.wikidata.org/prop/novalue/",
    "wdref": "http://www.wikidata.org/reference/",
    "wds": "http://www.wikidata.org/entity/statement/",
    "wdt": "http://www.wikidata.org/prop/direct/",
    "wdtn": "http://www.wikidata.org/prop/direct-normalized/",
    "wdv": "http://www.wikidata.org/value/",
    "wikibase": "http://wikiba.se/ontology#",
}


def _expand_prefixed_uris(text: str) -> str:
    """Expand prefixed URIs (e.g. wdt:P421 -> http://www.wikidata.org/prop/direct/P421)."""
    # Sort by prefix length (longest first) to avoid partial matches like 'wd' inside 'wikidata'
    for prefix in sorted(_PREFIX_TO_URI.keys(), key=len, reverse=True):
        uri_base = _PREFIX_TO_URI[prefix]
        # Match prefix:localName where prefix is NOT preceded by a word character or '/'
        # This avoids matching 'wd' inside 'www.wikidata' or 'wdt' inside 'wdtn'
        pattern = re.compile(r'(?:^|(?<=[^a-zA-Z0-9_/]))' + re.escape(prefix) + r':(\S+)')
        text = pattern.sub(lambda m: uri_base + m.group(1), text)
    return text


def normalize_sparql(sparql: str) -> str:
    """
    Normalize a SPARQL query for comparison by:
      - Removing all PREFIX declarations
      - Expanding prefixed URIs to full URIs
      - Normalizing whitespace
      - Anonymizing variable names (?x -> ?v0, ?y -> ?v1, etc.)
      - Removing LIMIT/OFFSET clauses
      - Lowercasing SPARQL keywords
    """
    if not sparql or not sparql.strip():
        return ""

    text = sparql

    # Remove PREFIX lines (collect prefixes for expansion before removing)
    text = re.sub(r'PREFIX\s+\S+\s*:\s*<[^>]*>\s*', '', text, flags=re.IGNORECASE)

    # Remove BASE directive
    text = re.sub(r'BASE\s+<[^>]*>\s*', '', text, flags=re.IGNORECASE)

    # Remove COMMENT blocks (-- and #)
    text = re.sub(r'--[^\n]*', '', text)
    text = re.sub(r'#[^\n]*', '', text)

    # Remove LIMIT clause
    text = re.sub(r'\bLIMIT\s+\d+\s*', '', text, flags=re.IGNORECASE)

    # Remove OFFSET clause
    text = re.sub(r'\bOFFSET\s+\d+\s*', '', text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Expand prefixed URIs to full URIs
    text = _expand_prefixed_uris(text)

    # Collect all variable names in order of appearance
    var_pattern = re.compile(r'\?(?![0-9#])(\w+)')
    vars_found = []
    var_map = {}
    for m in var_pattern.finditer(text):
        var_name = m.group(1)
        if var_name not in var_map:
            var_map[var_name] = f'?v{len(vars_found)}'
            vars_found.append(var_name)

    # Replace variables with anonymized versions
    def replace_var(m):
        var_name = m.group(1)
        return var_map.get(var_name, m.group(0))

    text = var_pattern.sub(replace_var, text)

    # Lowercase SPARQL keywords
    keywords = [
        'SELECT', 'DISTINCT', 'REDUCED', 'CONSTRUCT', 'DESCRIBE', 'ASK',
        'WHERE', 'GRAPH', 'OPTIONAL', 'FILTER', 'ORDER', 'BY', 'ASC', 'DESC',
        'LIMIT', 'OFFSET', 'UNION', 'VALUES', 'GROUP', 'HAVING',
        'BIND', 'SERVICE', 'SILENT', 'USING', 'NAMED', 'DEFAULT',
        'FROM', 'WITH', 'DATA', 'LOAD', 'CLEAR', 'DROP', 'CREATE',
        'INSERT', 'DELETE', 'INTO', 'PREFIX', 'BASE',
        'TRUE', 'FALSE', 'NULL', 'SAMPLE', 'COUNT', 'SUM', 'MIN', 'MAX', 'AVG',
        'EXISTS', 'NOT', 'IN', 'LIKE', 'REGEX', 'BOUND', 'IS', 'LITERAL',
        'URI', 'IRI', 'BLANK', 'NODE', 'TYPE', 'COALESCE', 'IF',
        'STR', 'LANG', 'LANGMATCHES', 'DATATYPE', 'A',
    ]
    for kw in keywords:
        pattern = r'\b' + kw + r'\b'
        text = re.sub(pattern, kw.lower(), text, flags=re.IGNORECASE)

    # Normalize whitespace again after replacements
    text = re.sub(r'\s+', ' ', text).strip()

    # Remove angle brackets around URIs for uniform comparison
    text = text.replace('<', '').replace('>', '')

    # Add spaces around curly braces and parentheses for uniform comparison
    text = text.replace('{', ' { ').replace('}', ' } ')
    text = text.replace('(', ' ( ').replace(')', ' ) ')

    # Remove SPARQL triple-terminating periods (whitespace + . + whitespace/})
    # Don't touch periods inside URIs (no surrounding whitespace)
    text = re.sub(r'\s+\.\s*', ' ', text)
    text = re.sub(r'\.\s*}', ' }', text)
    text = text.rstrip('.')
    text = text.strip()

    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def normalize_sparql_loose(sparql: str) -> str:
    """
    Even more lenient normalization: also strips DISTINCT, WHERE keyword,
    and handles other minor structural differences.
    """
    text = normalize_sparql(sparql)

    # Remove DISTINCT
    text = re.sub(r'\bdistinct\b', '', text, flags=re.IGNORECASE)

    # Remove REDUCED
    text = re.sub(r'\breduced\b', '', text, flags=re.IGNORECASE)

    # Remove WHERE keyword (always implied in SELECT/ASK queries)
    text = re.sub(r'\bwhere\b', '', text, flags=re.IGNORECASE)

    # Clean up extra spaces
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def extract_answer_set(question: dict) -> set[tuple[str, str]]:
    """
    Extract answer set from a QALD question item.
    Returns a set of (type, value) tuples, ignoring variable names.
    """
    answer_set = set()
    for answer_block in question.get('answers', []):
        bindings = answer_block.get('results', {}).get('bindings', [])
        for binding in bindings:
            for var_name, val_obj in binding.items():
                val_type = val_obj.get('type', 'uri')
                val_value = val_obj.get('value', '')
                answer_set.add((val_type, val_value))
    return answer_set


def compute_f1(pred_set: set, gold_set: set) -> tuple[float, float, float]:
    """Compute precision, recall, F1 for two sets."""
    if not pred_set and not gold_set:
        return (1.0, 1.0, 1.0)

    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    return (precision, recall, f1)


def get_en_question(question_item: dict) -> str:
    """Get the English question string, or first available."""
    for q in question_item.get('question', []):
        if q.get('language') == 'en':
            return q.get('string', '')
    if question_item.get('question'):
        return question_item['question'][0].get('string', '')
    return ''


def compare_datasets(gold_path: str, pred_path: str) -> dict:
    """
    Compare gold and prediction files.
    Returns a dict with per-question results and aggregate statistics.
    """
    with open(gold_path, 'r', encoding='utf-8') as f:
        gold_data = json.load(f)
    with open(pred_path, 'r', encoding='utf-8') as f:
        pred_data = json.load(f)

    gold_questions = {str(q['id']): q for q in gold_data.get('questions', [])}
    pred_questions = {str(q['id']): q for q in pred_data.get('questions', [])}

    common_ids = sorted(gold_questions.keys() & pred_questions.keys(), key=lambda x: int(x) if x.isdigit() else x)
    gold_only = sorted(set(gold_questions.keys()) - set(pred_questions.keys()))
    pred_only = sorted(set(pred_questions.keys()) - set(gold_questions.keys()))

    per_question = []
    sparql_exact_count = 0
    sparql_norm_count = 0
    sparql_loose_count = 0
    ans_exact_count = 0
    total_precision = 0.0
    total_recall = 0.0
    total_f1 = 0.0
    answered_count = 0  # questions where both gold and pred have non-empty answers

    # Categories for analysis
    cat_correct_sparql_correct_ans = 0
    cat_correct_sparql_wrong_ans = 0
    cat_wrong_sparql_correct_ans = 0
    cat_wrong_sparql_wrong_ans = 0
    cat_gold_empty_pred_empty = 0
    cat_gold_empty_pred_has = 0
    cat_gold_has_pred_empty = 0

    for qid in common_ids:
        gq = gold_questions[qid]
        pq = pred_questions[qid]

        g_sparql = gq.get('query', {}).get('sparql', '')
        p_sparql = pq.get('query', {}).get('sparql', '')

        g_answers = extract_answer_set(gq)
        p_answers = extract_answer_set(pq)

        # SPARQL comparison
        sparql_exact = g_sparql.strip() == p_sparql.strip()
        sparql_norm = normalize_sparql(g_sparql) == normalize_sparql(p_sparql)
        sparql_loose = normalize_sparql_loose(g_sparql) == normalize_sparql_loose(p_sparql)

        # Answer comparison
        ans_exact = g_answers == p_answers
        precision, recall, f1 = compute_f1(p_answers, g_answers)

        # Categorize
        g_has = len(g_answers) > 0
        p_has = len(p_answers) > 0

        if not g_has and not p_has:
            cat_gold_empty_pred_empty += 1
        elif not g_has and p_has:
            cat_gold_empty_pred_has += 1
        elif g_has and not p_has:
            cat_gold_has_pred_empty += 1
        else:
            answered_count += 1
            if sparql_loose and ans_exact:
                cat_correct_sparql_correct_ans += 1
            elif sparql_loose and not ans_exact:
                cat_correct_sparql_wrong_ans += 1
            elif not sparql_loose and ans_exact:
                cat_wrong_sparql_correct_ans += 1
            else:
                cat_wrong_sparql_wrong_ans += 1

        if sparql_exact:
            sparql_exact_count += 1
        if sparql_norm:
            sparql_norm_count += 1
        if sparql_loose:
            sparql_loose_count += 1
        if ans_exact:
            ans_exact_count += 1

            total_precision += precision
        total_recall += recall
        total_f1 += f1

        en_question = get_en_question(gq)

        per_question.append({
            'id': qid,
            'question_en': en_question,
            'sparql_exact_match': sparql_exact,
            'sparql_normalized_match': sparql_norm,
            'sparql_loose_match': sparql_loose,
            'answer_exact_match': ans_exact,
            'gold_answer_count': len(g_answers),
            'pred_answer_count': len(p_answers),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'gold_answers': sorted(g_answers),
            'pred_answers': sorted(p_answers),
        })

    n = len(common_ids)
    avg_precision = total_precision / n if n else 0.0
    avg_recall = total_recall / n if n else 0.0
    avg_f1 = total_f1 / n if n else 0.0

    # For answered questions only (both have non-empty answers)
    answered_precision = 0.0
    answered_recall = 0.0
    answered_f1 = 0.0
    if answered_count > 0:
        # Recompute for answered questions only
        ap = sum(rq['precision'] for rq in per_question
                 if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] > 0)
        ar = sum(rq['recall'] for rq in per_question
                 if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] > 0)
        af = sum(rq['f1'] for rq in per_question
                 if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] > 0)
        answered_precision = ap / answered_count
        answered_recall = ar / answered_count
        answered_f1 = af / answered_count

    # Collect mismatched questions for detailed inspection
    sparql_mismatches = [rq for rq in per_question if not rq['sparql_loose_match']]
    answer_mismatches = [rq for rq in per_question
                         if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] > 0 and not rq['answer_exact_match']]
    pred_misses = [rq for rq in per_question
                   if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] == 0]
    pred_spurious = [rq for rq in per_question
                     if rq['gold_answer_count'] == 0 and rq['pred_answer_count'] > 0]

    result = {
        'dataset_info': {
            'gold_file': gold_path,
            'pred_file': pred_path,
            'total_common_questions': n,
            'gold_only_ids': gold_only,
            'pred_only_ids': pred_only,
        },
        'sparql_stats': {
            'exact_match_count': sparql_exact_count,
            'exact_match_rate': round(sparql_exact_count / n * 100, 2) if n else 0,
            'normalized_match_count': sparql_norm_count,
            'normalized_match_rate': round(sparql_norm_count / n * 100, 2) if n else 0,
            'loose_match_count': sparql_loose_count,
            'loose_match_rate': round(sparql_loose_count / n * 100, 2) if n else 0,
        },
        'answer_stats': {
            'exact_match_count': ans_exact_count,
            'exact_match_rate': round(ans_exact_count / n * 100, 2) if n else 0,
            'macro_precision': round(avg_precision, 4),
            'macro_recall': round(avg_recall, 4),
            'macro_f1': round(avg_f1, 4),
            'answered_questions': answered_count,
            'macro_precision_answered': round(answered_precision, 4),
            'macro_recall_answered': round(answered_recall, 4),
            'macro_f1_answered': round(answered_f1, 4),
        },
        'categories': {
            'correct_sparql_correct_answer': cat_correct_sparql_correct_ans,
            'correct_sparql_wrong_answer': cat_correct_sparql_wrong_ans,
            'wrong_sparql_correct_answer': cat_wrong_sparql_correct_ans,
            'wrong_sparql_wrong_answer': cat_wrong_sparql_wrong_ans,
            'both_empty': cat_gold_empty_pred_empty,
            'gold_empty_pred_has': cat_gold_empty_pred_has,
            'gold_has_pred_empty': cat_gold_has_pred_empty,
        },
        'mismatches': {
            'sparql_mismatch_count': len(sparql_mismatches),
            'answer_mismatch_count': len(answer_mismatches),
            'pred_miss_count': len(pred_misses),
            'pred_spurious_count': len(pred_spurious),
        },
        'per_question': per_question,
        'sparql_mismatch_ids': [rq['id'] for rq in sparql_mismatches],
        'answer_mismatch_ids': [rq['id'] for rq in answer_mismatches],
        'pred_miss_ids': [rq['id'] for rq in pred_misses],
        'pred_spurious_ids': [rq['id'] for rq in pred_spurious],
    }

    return result


def format_markdown_report(res: dict) -> str:
    """Format a single dataset's comparison result as a markdown report."""
    ds_label = Path(res['dataset_info']['gold_file']).parts[-3]
    lines = []
    lines.append(f"# SPARQL & Answer Set Comparison Report: {ds_label}\n")
    lines.append(f"- **Gold file**: `{res['dataset_info']['gold_file']}`")
    lines.append(f"- **Pred file**: `{res['dataset_info']['pred_file']}`")
    lines.append(f"- **Common questions**: {res['dataset_info']['total_common_questions']}")

    if res['dataset_info']['gold_only_ids']:
        lines.append(f"- **Gold-only IDs**: {res['dataset_info']['gold_only_ids']}")
    if res['dataset_info']['pred_only_ids']:
        lines.append(f"- **Pred-only IDs**: {res['dataset_info']['pred_only_ids']}")

    lines.append("")
    lines.append("## SPARQL Comparison")
    lines.append(f"| Metric | Count | Rate |")
    lines.append(f"|--------|-------|------|")
    lines.append(f"| Exact match | {res['sparql_stats']['exact_match_count']} | {res['sparql_stats']['exact_match_rate']}% |")
    lines.append(f"| Normalized match | {res['sparql_stats']['normalized_match_count']} | {res['sparql_stats']['normalized_match_rate']}% |")
    lines.append(f"| Loose match (no DISTINCT) | {res['sparql_stats']['loose_match_count']} | {res['sparql_stats']['loose_match_rate']}% |")

    lines.append("")
    lines.append("## Answer Set Comparison")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Exact match (all questions) | {res['answer_stats']['exact_match_count']} ({res['answer_stats']['exact_match_rate']}%) |")
    lines.append(f"| Macro P (all) | {res['answer_stats']['macro_precision']} |")
    lines.append(f"| Macro R (all) | {res['answer_stats']['macro_recall']} |")
    lines.append(f"| Macro F1 (all) | {res['answer_stats']['macro_f1']} |")
    lines.append(f"| Answered questions | {res['answer_stats']['answered_questions']} |")
    lines.append(f"| Macro P (answered) | {res['answer_stats']['macro_precision_answered']} |")
    lines.append(f"| Macro R (answered) | {res['answer_stats']['macro_recall_answered']} |")
    lines.append(f"| Macro F1 (answered) | {res['answer_stats']['macro_f1_answered']} |")

    lines.append("")
    lines.append("## Categories (answered questions only)")
    lines.append(f"| Category | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Correct SPARQL + Correct Answer | {res['categories']['correct_sparql_correct_answer']} |")
    lines.append(f"| Correct SPARQL + Wrong Answer | {res['categories']['correct_sparql_wrong_answer']} |")
    lines.append(f"| Wrong SPARQL + Correct Answer | {res['categories']['wrong_sparql_correct_answer']} |")
    lines.append(f"| Wrong SPARQL + Wrong Answer | {res['categories']['wrong_sparql_wrong_answer']} |")
    lines.append(f"| Both empty | {res['categories']['both_empty']} |")
    lines.append(f"| Gold empty, Pred has answers | {res['categories']['gold_empty_pred_has']} |")
    lines.append(f"| Gold has answers, Pred empty | {res['categories']['gold_has_pred_empty']} |")

    lines.append("")
    lines.append("## Mismatch Summary")
    lines.append(f"- SPARQL mismatches: {res['mismatches']['sparql_mismatch_count']}")
    lines.append(f"- Answer mismatches (both non-empty): {res['mismatches']['answer_mismatch_count']}")
    lines.append(f"- Pred misses (gold has, pred empty): {res['mismatches']['pred_miss_count']}")
    lines.append(f"- Pred spurious (gold empty, pred has): {res['mismatches']['pred_spurious_count']}")

    lines.append("")
    lines.append("## Pred Miss Details (gold has answers, prediction empty)")
    if res['pred_miss_ids']:
        lines.append("| ID | Question (EN) | Gold Answers |")
        lines.append("|----|---------------|--------------|")
        for rq in res['per_question']:
            if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] == 0:
                q_short = rq['question_en'][:80] + '...' if len(rq['question_en']) > 80 else rq['question_en']
                ans_str = ', '.join(f"{v} ({t})" for t, v in rq['gold_answers'][:5])
                if len(rq['gold_answers']) > 5:
                    ans_str += f" +{len(rq['gold_answers']) - 5} more"
                lines.append(f"| {rq['id']} | {q_short} | {ans_str} |")
    else:
        lines.append("None")

    lines.append("")
    lines.append("## Pred Spurious Details (gold empty, prediction has answers)")
    if res['pred_spurious_ids']:
        lines.append("| ID | Question (EN) | Pred Answers |")
        lines.append("|----|---------------|--------------|")
        for rq in res['per_question']:
            if rq['gold_answer_count'] == 0 and rq['pred_answer_count'] > 0:
                q_short = rq['question_en'][:80] + '...' if len(rq['question_en']) > 80 else rq['question_en']
                ans_str = ', '.join(f"{v} ({t})" for t, v in rq['pred_answers'][:5])
                if len(rq['pred_answers']) > 5:
                    ans_str += f" +{len(rq['pred_answers']) - 5} more"
                lines.append(f"| {rq['id']} | {q_short} | {ans_str} |")
    else:
        lines.append("None")

    lines.append("")
    lines.append("## Answer Mismatch Details (both non-empty, but differ)")
    if res['answer_mismatch_ids']:
        lines.append("| ID | Q (EN) | Gold # | Pred # | P | R | F1 | SPARQL match |")
        lines.append("|----|--------|--------|--------|---|---|-----|-------------|")
        for rq in res['per_question']:
            if rq['gold_answer_count'] > 0 and rq['pred_answer_count'] > 0 and not rq['answer_exact_match']:
                q_short = rq['question_en'][:50] + '...' if len(rq['question_en']) > 50 else rq['question_en']
                lines.append(
                    f"| {rq['id']} | {q_short} | {rq['gold_answer_count']} | "
                    f"{rq['pred_answer_count']} | {rq['precision']} | {rq['recall']} | "
                    f"{rq['f1']} | {'loose' if rq['sparql_loose_match'] else 'no'} |"
                )
    else:
        lines.append("None")

    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(
        description="Compare gold/reference SPARQL and answer sets against predictions."
    )
    parser.add_argument(
        '--gold', action='append', required=True,
        help="Path to gold QALD JSON file (can be specified multiple times)."
    )
    parser.add_argument(
        '--pred', action='append', required=True,
        help="Path to prediction QALD JSON file (can be specified multiple times)."
    )
    parser.add_argument(
        '--output', default='data_dir/misc/comparison',
        help="Output base path for results (JSON + markdown)."
    )
    args = parser.parse_args()

    if len(args.gold) != len(args.pred):
        print("Error: --gold and --pred must be specified the same number of times.", file=sys.stderr)
        sys.exit(1)

    results = []
    for gold_path, pred_path in zip(args.gold, args.pred):
        print(f"Comparing: {gold_path} vs {pred_path}")
        res = compare_datasets(gold_path, pred_path)
        results.append(res)

        # Print summary
        n = res['dataset_info']['total_common_questions']
        print(f"  Questions: {n}")
        print(f"  SPARQL exact: {res['sparql_stats']['exact_match_count']} ({res['sparql_stats']['exact_match_rate']}%)")
        print(f"  SPARQL normalized: {res['sparql_stats']['normalized_match_count']} ({res['sparql_stats']['normalized_match_rate']}%)")
        print(f"  SPARQL loose: {res['sparql_stats']['loose_match_count']} ({res['sparql_stats']['loose_match_rate']}%)")
        print(f"  Answer exact: {res['answer_stats']['exact_match_count']} ({res['answer_stats']['exact_match_rate']}%)")
        print(f"  Macro F1 (all): {res['answer_stats']['macro_f1']}")
        print(f"  Macro F1 (answered): {res['answer_stats']['macro_f1_answered']}")
        print()

    # Save outputs
    output_base = Path(args.output)
    create_directory_if_not_exists(str(output_base.parent))

    # Save JSON (strip per_question for a summary file, keep full in detailed)
    summary_results = []
    for res in results:
        summary_res = {k: v for k, v in res.items() if k != 'per_question'}
        summary_results.append(summary_res)

    json_path = output_base.with_suffix('.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Full JSON saved to: {json_path}")

    # Save summary JSON without per-question details
    summary_path = output_base.with_name(output_base.name + '_summary').with_suffix('.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary_results, f, ensure_ascii=False, indent=2)
    print(f"Summary JSON saved to: {summary_path}")

    # Save per-dataset markdown reports
    md_paths = []
    for i, res in enumerate(results):
        ds_label = Path(res['dataset_info']['gold_file']).parts[-3]
        if len(results) > 1:
            md_path = output_base.with_name(f"{output_base.name}_{ds_label}").with_suffix('.md')
        else:
            md_path = output_base.with_suffix('.md')
        md_content = format_markdown_report(res)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        md_paths.append(str(md_path))
    print(f"Markdown reports saved to: {', '.join(md_paths)}")


if __name__ == "__main__":
    main()
