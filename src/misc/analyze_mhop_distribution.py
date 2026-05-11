#!/usr/bin/env python
"""Analyze hop-count distribution of SPARQL queries across KGQA datasets."""
import json
import os
import sys
import glob
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rdflib import Graph, Variable
from rdflib.plugins.sparql.processor import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.sparql import Prologue, NamespaceManager

from src.util.common import count_sparql_hops

# --- SPARQL prefix map ---
PREFIX_MAP = {
    "http://www.wikidata.org/prop/direct/": "wdt:",
    "http://www.wikidata.org/entity/": "wd:",
    "http://www.wikidata.org/prop/": "p:",
    "http://www.wikidata.org/prop/statement/": "ps:",
    "http://www.wikidata.org/prop/statement/value/": "psn:",
    "http://www.wikidata.org/prop/statement/value-normalized/": "psv:",
    "http://www.wikidata.org/prop/qualifier/": "pq:",
    "http://www.wikidata.org/prop/qualifier/value/": "pqv:",
    "http://www.wikidata.org/prop/qualifier/value-normalized/": "pqn:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://schema.org/": "schema:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
}


def uri_to_prefixed(uri_str):
    """Convert a full URI to a prefixed form like wd:Q5."""
    for ns, pfx in PREFIX_MAP.items():
        if uri_str.startswith(ns):
            return pfx + uri_str[len(ns):]
    return uri_str


def extract_triples_from_algebra(alg_dict):
    """Recursively extract triple patterns from the SPARQL algebra dict."""
    triples = []
    if isinstance(alg_dict, dict):
        if "triples" in alg_dict:
            for t in alg_dict["triples"]:
                s = t[0]
                o = t[2]
                if isinstance(s, Variable):
                    s = "?" + str(s)
                elif isinstance(s, str) and s.startswith("http"):
                    s = uri_to_prefixed(s)
                if isinstance(o, Variable):
                    o = "?" + str(o)
                elif isinstance(o, str) and o.startswith("http"):
                    o = uri_to_prefixed(o)
                triples.append({"s": s, "p": str(t[1]), "o": o})
        for v in alg_dict.values():
            triples.extend(extract_triples_from_algebra(v))
    elif isinstance(alg_dict, list):
        for item in alg_dict:
            triples.extend(extract_triples_from_algebra(item))
    return triples


def strip_filter_clauses(sparql_str):
    """Remove FILTER clauses from SPARQL to avoid parse errors from malformed expressions.
    FILTER doesn't affect hop count since it only constrains variables, not graph traversal."""
    import re
    # Remove FILTER(...) expressions, handling nested parentheses
    result = sparql_str
    max_iter = 50
    while "FILTER" in result.upper() and max_iter > 0:
        m = re.search(r'(?i)\bFILTER\s*(?:NOT\s*)?\(', result)
        if not m:
            break
        start = m.start()
        depth = 0
        i = m.end() - 1  # position of opening paren
        for j in range(i, len(result)):
            if result[j] == '(':
                depth += 1
            elif result[j] == ')':
                depth -= 1
                if depth == 0:
                    result = result[:start] + result[j + 1:]
                    break
        else:
            break
        max_iter -= 1
    # Clean up double dots left behind after removing FILTER
    result = re.sub(r'\.\s*\.', '.', result)
    return result


def extract_patterns(sparql_str):
    """Parse SPARQL and extract triple patterns as dicts with 's' and 'o' keys."""
    # Strip FILTER clauses first to avoid parse errors from malformed expressions
    cleaned = strip_filter_clauses(sparql_str)
    try:
        parsed = parseQuery(cleaned)
    except Exception:
        return []

    ns = NamespaceManager(Graph())
    for item in parsed:
        if isinstance(item, dict) and "prefix" in item:
            ns.bind(str(item["prefix"]), item["iri"])

    prologue = Prologue()
    prologue.bindings = ns
    try:
        alg = translateQuery(parsed, prologue)
    except Exception:
        return []

    triples = extract_triples_from_algebra(alg.algebra)
    seen = set()
    unique = []
    for t in triples:
        key = (t["s"], t["o"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def get_sparql_from_question(q):
    """Extract the SPARQL string from a QALD-format question dict."""
    return q.get("query", {}).get("sparql", "")


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


def analyze_file(filepath):
    """Analyze all queries in a single file, return hop-count distribution with query IDs."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    hop_counts = defaultdict(int)
    hop_ids = defaultdict(list)
    parse_errors = 0
    skipped_ids = []

    for q in questions:
        qid = q.get("id", "?")
        sparql = get_sparql_from_question(q)
        if not sparql:
            skipped_ids.append(str(qid))
            continue

        # Accept queries with WHERE clause (case-insensitive) or SELECT/ASK/CONSTRUCT/DESCRIBE + graph pattern
        upper = sparql.upper().strip()
        has_where = "WHERE" in upper
        has_sparql_query = any(kw in upper for kw in ["SELECT", "ASK", "CONSTRUCT", "DESCRIBE"])
        has_graph_pattern = "{" in sparql
        if not (has_where or (has_sparql_query and has_graph_pattern)):
            skipped_ids.append(str(qid))
            continue

        patterns = extract_patterns(sparql)
        if not patterns:
            parse_errors += 1
            continue

        try:
            max_hops, _ = count_sparql_hops(sparql, patterns)
            hop_counts[max_hops] += 1
            hop_ids[max_hops].append(str(qid))
        except Exception:
            parse_errors += 1

    return {
        "total_queries": len(questions),
        "analyzed": sum(hop_counts.values()),
        "parse_errors": parse_errors,
        "skipped": len(skipped_ids),
        "skipped_ids": skipped_ids,
        "hop_distribution": dict(sorted(hop_counts.items())),
        "hop_ids": {str(k): v for k, v in sorted(hop_ids.items())},
    }


def group_hops(dist):
    """Group hop counts: 0+1 -> '1', 2 -> '2', >=3 -> '3+', '*' -> '*'.
    0-hop and 1-hop are combined because both represent simple queries:
    0-hop is a single triple lookup, and 1-hop traverses one edge.
    Both require no multi-hop chaining, unlike 2-hop+ queries."""
    g = {"1": 0, "2": 0, "3+": 0, "*": 0}
    for k, v in dist.items():
        if k == "*":
            g["*"] += v
        else:
            n = int(k)
            if n <= 1:  # 0-hop + 1-hop combined as "simple" queries
                g["1"] += v
            elif n == 2:
                g["2"] += v
            else:
                g["3+"] += v
    return g


def build_latex_table(results):
    """Build a LaTeX table from analysis results."""
    col_order = ["1", "2", "3+"]
    col_labels = [r"\textbf{1-hop}", r"\textbf{2-hop}", r"$>\,\text{\textbf{3-hop}}$"]

    ds_map = {
        "qald9plus/test": r"\dataset{QALD-9plus}",
        "qald10/test": r"\dataset{QALD-10}",
        "lcquad2/test": r"\dataset{LC-QuAD2.0}",
    }
    ds_order = ["qald9plus/test", "qald10/test", "lcquad2/test"]

    lookup = {r["dataset_name"]: r for r in results}
    rows = []
    for key in ds_order:
        r = lookup.get(key)
        if r is None:
            continue
        g = group_hops(r["hop_distribution"])
        total = sum(g[c] for c in col_order) or 1
        cells = []
        for col in col_order:
            cnt = g[col]
            pct = cnt / total * 100
            if cnt == 0:
                cells.append("0")
            else:
                cells.append(f"{cnt} ({pct:.2f}\\%)")
        rows.append((ds_map[key], key, r["hop_distribution"], r.get("skipped", 0),
                      r.get("parse_errors", 0), cells))

    lines = []
    lines.append(r"\begin{table}")
    lines.append(r"\caption{Proportion of multi-hop queries across datasets.}")
    lines.append(r"\label{tab:mhop_analysis}")
    lines.append(r"\centering")
    lines.append(r"\resizebox{0.75\textwidth}{!}{%")
    lines.append(r"\rowcolors{2}{white}{gray!20}")
    lines.append(r"\setlength{\tabcolsep}{5pt}")
    cols = "l " + " ".join(["r"] * len(col_order))
    lines.append(f"\\begin{{tabular}}{{{cols}}}")
    lines.append(r"\toprule")
    header = r"\textbf{Dataset} & " + " & ".join(col_labels)
    lines.append(f"{header}  \\")
    lines.append(r"\midrule")
    for ds_label, key, dist, skipped, errors, cells in rows:
        dist_str = str(dist).replace("'", "\\'")
        has_zero = "0" in dist
        comment = f"% {key} mhop map: {dist_str}"
        if has_zero:
            comment += " % 0 and 1 can be interpreted the same"
        lines.append(comment)
        line = f"{ds_label} & " + " & ".join(cells) + "  \\\\"
        lines.append(line)
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}%")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def build_table(results):
    """Build a markdown table from analysis results."""
    # Collect all unique hop values
    all_hops = set()
    for r in results:
        all_hops.update(r["hop_distribution"].keys())
    hop_cols = sorted(all_hops)

    lines = []
    lines.append("# Multi-Hop Query Analysis")
    lines.append("")
    lines.append("| Dataset | Total Qs | Analyzed | Skipped | Errors |")
    lines.append("|---------|----------|----------|---------|--------|")

    for r in results:
        ds = r["dataset_name"]
        lines.append(f"| {ds} | {r['total_queries']} | {r['analyzed']} | {r['skipped']} | {r['parse_errors']} |")

    lines.append("")
    lines.append("## Hop Distribution")
    lines.append("")
    header = "| Dataset |" + " | ".join(f"{h}-hop" for h in hop_cols) + " | Total |"
    sep = "|---------|" + "|".join("---" for _ in hop_cols) + "|-------|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        ds = r["dataset_name"]
        dist = r["hop_distribution"]
        vals = " | ".join(f"{dist.get(h, 0)}" for h in hop_cols)
        total = sum(dist.values())
        lines.append(f"| {ds} | {vals} | {total} |")

    # Summary row
    totals = defaultdict(int)
    for r in results:
        for h, c in r["hop_distribution"].items():
            totals[h] += c
    vals = " | ".join(f"{totals.get(h, 0)}" for h in hop_cols)
    grand = sum(totals.values())
    lines.append(f"| **Total** | {vals} | {grand} |")

    lines.append("")
    lines.append("## Percentage Distribution")
    lines.append("")
    header = "| Dataset |" + " | ".join(f"{h}-hop (%)" for h in hop_cols) + " |"
    sep = "|---------|" + "|".join("---" for _ in hop_cols) + "|"
    lines.append(header)
    lines.append(sep)

    for r in results:
        ds = r["dataset_name"]
        dist = r["hop_distribution"]
        total = sum(dist.values()) or 1
        vals = " | ".join(f"{dist.get(h, 0) / total * 100:.1f}" for h in hop_cols)
        lines.append(f"| {ds} | {vals} |")

    # Summary percentages
    vals = " | ".join(f"{totals.get(h, 0) / grand * 100:.1f}" for h in hop_cols)
    lines.append(f"| **Total** | {vals} |")
    lines.append("")

    return "\n".join(lines)


def main():
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
        #short = short.replace("/qald_test_final_fixed.json", "").replace("/qald_dev_final_fixed.json", "")
        print(f"\nAnalyzing: {short} ...")
        stats = analyze_file(filepath)
        stats["dataset_name"] = short
        print(f"  Total: {stats['total_queries']}, Analyzed: {stats['analyzed']}, "
               f"Skipped: {stats['skipped']}, Errors: {stats['parse_errors']}")
        print(f"  Distribution: {stats['hop_distribution']}")
        for h, ids in stats.get("hop_ids", {}).items():
            print(f"    {h}-hop: {len(ids)} queries")
        results.append(stats)

    # Write output
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "..", "data_dir", "misc")
    out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    md_path = os.path.join(out_dir, "mhop_analysis.md")
    json_path = os.path.join(out_dir, "mhop_analysis.json")
    tex_path = os.path.join(out_dir, "mhop_analysis.tex")

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
