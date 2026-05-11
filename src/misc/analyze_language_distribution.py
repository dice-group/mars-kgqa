#!/usr/bin/env python
"""Analyze language distribution of questions across KGQA datasets."""
import json
import os
import sys
import glob
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_target_files():
    """Find all target dataset files."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..", "data_dir", "processed_kgqa_ds")
    base = os.path.normpath(base)

    files = []

    # All tentrismain_aug_gold.json files
    for f in glob.glob(os.path.join(base, "**", "tentrismain_aug_gold.json"), recursive=True):
        files.append(f)

    # Specific spinach files
    spinach_files = [
        os.path.join(base, "spinach", "test", "qald_test_final_fixed.json"),
        os.path.join(base, "spinach", "train", "qald_dev_final_fixed.json"),
    ]
    for f in spinach_files:
        if os.path.exists(f):
            files.append(f)

    return sorted(set(files))


def extract_languages(question_entry):
    """Extract unique languages from a question's 'question' array.
    A question may have multiple strings for the same language; each language counts once."""
    q_arr = question_entry.get("question", [])
    if isinstance(q_arr, list):
        langs = set()
        for item in q_arr:
            if isinstance(item, dict) and "language" in item:
                langs.add(item["language"])
        return langs
    return set()


def analyze_file(filepath):
    """Analyze all questions in a single file, return language distribution."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    lang_counts = defaultdict(int)
    lang_ids = defaultdict(list)
    no_lang_count = 0
    no_lang_ids = []
    seen_qids = set()

    for q in questions:
        qid = str(q.get("id", "?"))
        langs = extract_languages(q)
        if not langs:
            no_lang_count += 1
            no_lang_ids.append(qid)
            continue
        seen_qids.add(qid)
        for lang in langs:
            lang_counts[lang] += 1
            lang_ids[lang].append(qid)

    return {
        "total_questions": len(questions),
        "unique_questions_with_lang": len(seen_qids),
        "no_language": no_lang_count,
        "no_language_ids": no_lang_ids,
        "language_distribution": dict(sorted(lang_counts.items())),
        "language_ids": {k: v for k, v in sorted(lang_ids.items())},
    }


def build_latex_table(results):
    """Build a LaTeX table from analysis results."""
    ds_map = {
        "qald9plus/test": r"\dataset{QALD-9plus}",
        "qald10/test": r"\dataset{QALD-10}",
        "lcquad2/test": r"\dataset{LC-QuAD2.0}",
    }
    ds_order = ["qald9plus/test", "qald10/test", "lcquad2/test"]

    # Collect top languages across all results
    all_langs = set()
    for r in results:
        all_langs.update(r["language_distribution"].keys())
    top_langs = sorted(all_langs, key=lambda l: sum(
        r["language_distribution"].get(l, 0) for r in results
    ), reverse=True)

    # Limit columns to top languages for readability
    col_langs = top_langs[:10]
    other_langs = [l for l in top_langs if l not in col_langs]

    lookup = {r["dataset_name"]: r for r in results}
    rows = []
    for key in ds_order:
        r = lookup.get(key)
        if r is None:
            continue
        dist = r["language_distribution"]
        total = r["unique_questions_with_lang"] or 1
        cells = []
        for lang in col_langs:
            cnt = dist.get(lang, 0)
            if cnt == 0:
                cells.append("0")
            else:
                cells.append(f"{cnt} ({cnt / total * 100:.1f}\\%)")
        other_cnt = sum(dist.get(l, 0) for l in other_langs)
        if other_cnt > 0:
            cells.append(f"{other_cnt} ({other_cnt / total * 100:.1f}\\%)")
        else:
            cells.append("0")
        rows.append((ds_map[key], key, dist, cells))

    lines = []
    lines.append(r"\begin{table}")
    lines.append(r"\caption{Language distribution of questions across datasets.}")
    lines.append(r"\label{tab:lang_analysis}")
    lines.append(r"\centering")
    lines.append(r"\resizebox{\textwidth}{!}{%")
    lines.append(r"\rowcolors{2}{white}{gray!20}")
    lines.append(r"\setlength{\tabcolsep}{4pt}")
    n_cols = len(col_langs) + (1 if other_langs else 0)
    cols = "l " + " ".join(["r"] * n_cols)
    lines.append(f"\\begin{{tabular}}{{{cols}}}")
    lines.append(r"\toprule")
    col_labels = [f"\\textbf{{{l}}}" for l in col_langs]
    if other_langs:
        col_labels.append(r"\textbf{Other}")
    header = r"\textbf{Dataset} & " + " & ".join(col_labels)
    lines.append(f"{header}  \\")
    lines.append(r"\midrule")
    for ds_label, key, dist, cells in rows:
        dist_str = str(dist).replace("'", "\\'")
        lines.append(f"% {key} lang map: {dist_str}")
        line = f"{ds_label} & " + " & ".join(cells) + "  \\\\"
        lines.append(line)
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}%")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def build_table(results):
    """Build a markdown table from analysis results."""
    all_langs = set()
    for r in results:
        all_langs.update(r["language_distribution"].keys())
    lang_cols = sorted(all_langs, key=lambda l: sum(
        r["language_distribution"].get(l, 0) for r in results
    ), reverse=True)

    lines = []
    lines.append("# Language Distribution Analysis")
    lines.append("")
    lines.append("## Language Distribution")
    lines.append("")
    header = "| Dataset |" + " | ".join(f"{l}" for l in lang_cols) + " | Total |"
    sep = "|---------|" + "|".join("---" for _ in lang_cols) + "|-------|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        ds = r["dataset_name"]
        dist = r["language_distribution"]
        vals = " | ".join(f"{dist.get(l, 0)}" for l in lang_cols)
        total = sum(dist.values())
        lines.append(f"| {ds} | {vals} | {total} |")

    # Summary row
    totals = defaultdict(int)
    for r in results:
        for l, c in r["language_distribution"].items():
            totals[l] += c
    vals = " | ".join(f"{totals.get(l, 0)}" for l in lang_cols)
    grand = sum(totals.values())
    lines.append(f"| **Total** | {vals} | {grand} |")

    lines.append("")
    lines.append("## Percentage Distribution")
    lines.append("")
    header = "| Dataset |" + " | ".join(f"{l} (%)" for l in lang_cols) + " |"
    sep = "|---------|" + "|".join("---" for _ in lang_cols) + "|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        ds = r["dataset_name"]
        dist = r["language_distribution"]
        total = r["unique_questions_with_lang"] or 1
        vals = " | ".join(f"{dist.get(l, 0) / total * 100:.1f}" for l in lang_cols)
        lines.append(f"| {ds} | {vals} |")

    grand_unique = sum(r["unique_questions_with_lang"] for r in results) or 1
    vals = " | ".join(f"{totals.get(l, 0) / grand_unique * 100:.1f}" for l in lang_cols)
    lines.append(f"| **Total** | {vals} |")
    lines.append("")

    return "\n".join(lines)


def main():
    # Filter: only analyze these datasets (set to None for all)
    DATASET_FILTER = {"qald9plus/test", "qald10/test"}

    files = find_target_files()
    if not files:
        print("No target files found.")
        sys.exit(1)

    print(f"Found {len(files)} files to analyze:")
    for f in files:
        print(f"  {f}")

    results = []
    for filepath in files:
        rel = os.path.relpath(filepath,
                              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          ".."))
        short = rel.replace("data_dir/processed_kgqa_ds/", "").replace("/tentrismain_aug_gold.json", "")
        short = short.replace("/qald_test_final_fixed.json", "").replace("/qald_dev_final_fixed.json", "")

        if DATASET_FILTER and short not in DATASET_FILTER:
            print(f"\nSkipping: {short}")
            continue

        print(f"\nAnalyzing: {short} ...")
        stats = analyze_file(filepath)
        stats["dataset_name"] = short
        print(f"  Total: {stats['total_questions']}, Unique w/ Lang: {stats['unique_questions_with_lang']}, No Lang: {stats['no_language']}")
        dist = stats["language_distribution"]
        top5 = sorted(dist.items(), key=lambda x: -x[1])[:5]
        print(f"  Top languages: {dict(top5)}")
        results.append(stats)

    # Write output
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "..", "data_dir", "misc")
    out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    md_path = os.path.join(out_dir, "lang_analysis.md")
    json_path = os.path.join(out_dir, "lang_analysis.json")
    tex_path = os.path.join(out_dir, "lang_analysis.tex")

    table = build_table(results)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(table)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    latex_table = build_latex_table(results)
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(latex_table)

    print(f"\nOutput written to:")
    print(f"  {md_path}")
    print(f"  {json_path}")
    print(f"  {tex_path}")


if __name__ == "__main__":
    main()
