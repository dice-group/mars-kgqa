#!/usr/bin/env python
"""Analyze hop-count distribution of SPARQL queries across KGQA datasets."""
import json
import os
import sys
import glob
from collections import defaultdict
from datetime import datetime

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


def extract_patterns(sparql_str):
    """Parse SPARQL and extract triple patterns as dicts with 's' and 'o' keys."""
    try:
        parsed = parseQuery(sparql_str)
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

    for q in questions:
        qid = q.get("id", "?")
        sparql = get_sparql_from_question(q)
        if not sparql or "WHERE" not in sparql:
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
        "hop_distribution": dict(sorted(hop_counts.items())),
        "hop_ids": {str(k): v for k, v in sorted(hop_ids.items())},
    }


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
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("| Dataset | Total Qs | Analyzed | Errors |")
    lines.append("|---------|----------|----------|--------|")

    for r in results:
        ds = r["dataset_name"]
        lines.append(f"| {ds} | {r['total_queries']} | {r['analyzed']} | {r['parse_errors']} |")

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
        short = short.replace("/qald_test_final_fixed.json", "").replace("/qald_dev_final_fixed.json", "")
        print(f"\nAnalyzing: {short} ...")
        stats = analyze_file(filepath)
        stats["dataset_name"] = short
        print(f"  Total: {stats['total_queries']}, Analyzed: {stats['analyzed']}, "
              f"Errors: {stats['parse_errors']}")
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

    table = build_table(results)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(table)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nOutput written to:")
    print(f"  {md_path}")
    print(f"  {json_path}")


if __name__ == "__main__":
    main()
