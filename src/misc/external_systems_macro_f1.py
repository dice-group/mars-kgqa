#!/usr/bin/env python3
"""
Utility script to summarize Macro F1 scores from external system Gerbil results.

Scans all gerbil result CSVs under data_dir/external_systems/,
parses the directory names to extract system, dataset, language, and
native/translated mode, then builds a summary table of Macro F1 scores.

Usage:
    bash pylauncher.sh normal src.misc.external_systems_macro_f1
    bash pylauncher.sh normal src.misc.external_systems_macro_f1 --output-csv data_dir/misc/external_systems_macro_f1.csv --output-md data_dir/misc/external_systems_macro_f1.md
    bash pylauncher.sh normal src.misc.external_systems_macro_f1 --flat
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from collections import defaultdict

from src.util.common import create_directory_if_not_exists

logger = logging.getLogger(__name__)

EXCLUDE_SYSTEMS = {"bkp.deeppavlov2"}


def find_gerbil_csv_dirs(base_dir: Path) -> list[Path]:
    """
    Find all gerbil result directories (directories ending in .csv that
    contain a *.csv result file inside).
    """
    result_dirs: list[Path] = []
    for system_dir in sorted(base_dir.iterdir()):
        if not system_dir.is_dir() or system_dir.name in EXCLUDE_SYSTEMS:
            continue
        for candidate in sorted(system_dir.rglob("*")):
            if not candidate.is_dir():
                continue
            if "output" not in candidate.parts or "gerbil" not in candidate.parts:
                continue
            if not candidate.name.endswith(".csv"):
                continue
            inner_csvs = [f for f in candidate.glob("*.csv") if not _is_placeholder(f)]
            if inner_csvs:
                result_dirs.append(candidate)
    return result_dirs


def _is_placeholder(csv_path: Path) -> bool:
    """Check if a CSV is a placeholder (just experiment ID, no real results)."""
    try:
        lines = csv_path.read_text().strip().splitlines()
        return len(lines) == 2 and "gerbil experiment id" in lines[0]
    except Exception:
        return False


def extract_macro_f1(csv_path: Path) -> float | None:
    """Read the Macro F1 score from a gerbil result CSV."""
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                macro_f1 = row.get("Macro F1")
                if macro_f1:
                    return float(macro_f1)
    except Exception as e:
        logger.warning("Failed to read %s: %s", csv_path, e)
    return None


def parse_dir_name(dir_name: str, system_name: str) -> dict | None:
    """
    Parse a gerbil result directory name to extract dataset, language,
    and native/translated mode.

    Examples:
        deeppavlov2-qald10_test-de_native_qald10_tentrismain_test__qald10_tentrismain_test.csv
        grasp-qald10_test-en_native_qald10_tentrismain_test_output__qald10_tentrismain_test.csv
        mst5-qald10_test-de__qald10_tentrismain_test.csv
        uniqgen-lcquad2_test-en__lcquad2_tentrismain_test.csv
    """
    # Pattern: {system}-{dataset}_test-{lang}[_native|_translated]_...
    m = re.match(
        rf"^{re.escape(system_name)}-(?P<dataset>\w+)_test-(?P<lang>[a-z]{{2,3}})"
        r"(?:_(?P<mode>native|translated))?",
        dir_name,
    )
    if not m:
        return None
    return {
        "dataset": m.group("dataset"),
        "language": m.group("lang"),
        "mode": m.group("mode") or "native",
    }


def discover_system_model(base_dir: Path, system_name: str) -> str:
    """
    For systems like 'grasp' that have a model subdirectory under output/gerbil/,
    return the model name (e.g., 'gpt-oss-120b'). Otherwise return empty string.
    """
    gerbil_dir = base_dir / system_name / "output" / "gerbil"
    if not gerbil_dir.exists():
        return ""
    subdirs = [d for d in gerbil_dir.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        model = subdirs[0].name
        if model not in {"qald10", "qald9plus", "lcquad2"}:
            return model
    return ""


def build_summary(base_dir: Path) -> list[dict]:
    """Build a list of summary rows from all gerbil result CSVs."""
    rows: list[dict] = []
    gerbil_dirs = find_gerbil_csv_dirs(base_dir)

    for gerbil_dir in gerbil_dirs:
        csv_files = [f for f in gerbil_dir.glob("*.csv") if not _is_placeholder(f)]
        if not csv_files:
            continue

        csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
        macro_f1 = extract_macro_f1(csv_path)
        if macro_f1 is None:
            continue

        parts = gerbil_dir.parts
        system_idx = parts.index("external_systems") + 1
        system_name = parts[system_idx]
        model_name = discover_system_model(base_dir, system_name)
        system_label = f"{system_name}/{model_name}" if model_name else system_name

        parsed = parse_dir_name(gerbil_dir.name, system_name)
        if not parsed:
            logger.warning("Could not parse directory name: %s", gerbil_dir.name)
            continue

        rows.append({
            "system": system_label,
            "dataset": parsed["dataset"],
            "language": parsed["language"],
            "mode": parsed["mode"],
            "macro_f1": macro_f1,
        })

    return rows


def format_table(rows: list[dict]) -> str:
    """Format rows as a markdown table."""
    headers = ["System", "Dataset", "Language", "Mode", "Macro F1"]
    col_widths = [len(h) for h in headers]

    formatted_rows: list[list[str]] = []
    for r in rows:
        vals = [
            r["system"],
            r["dataset"],
            r["language"],
            r["mode"],
            f"{r['macro_f1']:.4f}",
        ]
        formatted_rows.append(vals)
        for i, v in enumerate(vals):
            col_widths[i] = max(col_widths[i], len(v))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = [
        " | ".join(v.ljust(col_widths[i]) for i, v in enumerate(row))
        for row in formatted_rows
    ]

    lines = [header_line, sep_line] + data_lines
    return "\n".join(lines)


def save_csv(rows: list[dict], output_path: Path) -> None:
    """Save rows as a CSV file."""
    create_directory_if_not_exists(str(output_path))
    fieldnames = ["system", "dataset", "language", "mode", "macro_f1"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_pivoted_table(rows: list[dict]) -> str:
    """
    Format rows as a pivoted markdown table where:
    - First column groups are dataset names
    - Second column is language+mode
    - Remaining columns are systems with Macro F1 values

    | Dataset | Language | deeppavlov2 | grasp/gpt-oss-120b | mst5 |
    |---------|----------|-------------|-------------------|------|
    | qald10  | de (native) | 0.0052 | 0.5460 | 0.2311 |
    """
    systems = sorted({r["system"] for r in rows})
    datasets = sorted({r["dataset"] for r in rows})

    lookup: dict[tuple[str, str, str, str], str] = {}
    for r in rows:
        key = (r["dataset"], r["language"], r["mode"], r["system"])
        lookup[key] = f"{r['macro_f1']:.4f}"

    headers = ["Dataset", "Language"] + systems
    col_widths = [len(h) for h in headers]

    data_lines: list[list[str]] = []
    current_dataset: str | None = None
    for ds in datasets:
        langs = sorted({(r["language"], r["mode"]) for r in rows if r["dataset"] == ds})
        for lang, mode in langs:
            lang_label = f"{lang} ({mode})"
            vals: list[str] = []
            if ds != current_dataset:
                vals = [ds, lang_label] + [lookup.get((ds, lang, mode, sys_), "-") for sys_ in systems]
            else:
                vals = ["", lang_label] + [lookup.get((ds, lang, mode, sys_), "-") for sys_ in systems]
            data_lines.append(vals)
            current_dataset = ds
            for i, v in enumerate(vals):
                col_widths[i] = max(col_widths[i], len(v))

    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join("-" * col_widths[i] for i in range(len(headers))) + " |"
    row_lines = [
        "| " + " | ".join(v.ljust(col_widths[i]) for i, v in enumerate(row)) + " |"
        for row in data_lines
    ]

    return "\n".join([header_line, sep_line] + row_lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize Macro F1 scores from external system Gerbil results.",
    )
    parser.add_argument(
        "--base-dir",
        default="data_dir/external_systems",
        help="Base directory containing external system results (default: data_dir/external_systems).",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Output CSV file path.",
    )
    parser.add_argument(
        "--output-md",
        default=None,
        help="Output pivoted markdown table file path.",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Print flat table (system per row) instead of pivoted table.",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        logger.error("Base directory does not exist: %s", base_dir)
        sys.exit(1)

    rows = build_summary(base_dir)
    if not rows:
        logger.info("No gerbil result CSVs found under %s.", base_dir)
        return

    if args.flat:
        table = format_table(rows)
    else:
        table = format_pivoted_table(rows)
    print(table)

    if args.output_csv:
        out_path = Path(args.output_csv)
        save_csv(rows, out_path)
        logger.info("CSV saved to %s", out_path)

    if args.output_md:
        md_path = Path(args.output_md)
        create_directory_if_not_exists(str(md_path))
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(format_pivoted_table(rows) + "\n")
        logger.info("Markdown table saved to %s", md_path)


if __name__ == "__main__":
    main()
