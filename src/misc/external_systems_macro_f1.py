#!/usr/bin/env python3
"""
Utility script to summarize Macro F1 scores from external system Gerbil results.

Scans all gerbil result CSVs under data_dir/external_systems/ and mars results
under data_dir/processed_kgqa_ds/, parses directory names to extract system,
dataset, language, and native/translated mode, then builds a summary table.

For mars: selects the best configuration per dataset based on 'en' language
Macro F1, then uses that config for all languages (reported as native).

Filters: grasp/mst5 use native only; deeppavlov2 uses translated only.

Usage:
    bash pylauncher.sh normal src.misc.external_systems_macro_f1
    bash pylauncher.sh normal src.misc.external_systems_macro_f1 --output-csv data_dir/misc/external_systems_macro_f1.csv --output-md data_dir/misc/external_systems_macro_f1.md
 bash pylauncher.sh normal src.misc.external_systems_macro_f1 --flat
    bash pylauncher.sh normal src.misc.external_systems_macro_f1 --no-mars

Scan gerbil directory and rank subdirectories by Macro F1:
    bash pylauncher.sh normal src.misc.external_systems_macro_f1 --scan-gerbil-dir data_dir/processed_kgqa_ds/qald9plus/train/prediction/tentrismain_aug_gold/gerbil
    bash pylauncher.sh normal src.misc.external_systems_macro_f1 --scan-gerbil-dir data_dir/processed_kgqa_ds/qald9plus/train/prediction/tentrismain_aug_gold/gerbil --scan-output-md data_dir/misc/gerbil_ranking.md
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

MARS_SYSTEM_LABEL = "mars/gptoss120b"
MARS_BASE_DIR_DEFAULT = "data_dir/processed_kgqa_ds"
MARS_DATASETS = {"qald9plus", "qald10", "lcquad2"}
NATIVE_ONLY_SYSTEMS = {"grasp/gpt-oss-120b", "mst5"}
TRANSLATED_ONLY_SYSTEMS = {"deeppavlov2"}

SYSTEM_ORDER = [
    "deeppavlov2",
    "mst5",
    "uniqgen",
    "grasp/gpt-oss-120b",
    "mars/gptoss120b",
]

SYSTEM_LATEX_MAP = {
    "deeppavlov2": r"\tool{DeepPavlov}",
    "mst5": r"\tool{MST5}",
    "uniqgen": r"\tool{UniQ-Gen}",
    "grasp/gpt-oss-120b": r"\tool{GRASP}",
    "mars/gptoss120b": r"\tool{\approach}",
}

LATEX_SYSTEM_ORDER = [
    "deeppavlov2",
    "mst5",
    "uniqgen",
    "grasp/gpt-oss-120b",
    "mars/gptoss120b",
]

LATEX_HEADER_ORDER = [
    "deeppavlov2",
    "mst5",
    "uniqgen",
    "grasp/gpt-oss-120b",
]

DATASET_LATEX_MAP = {
    "qald9plus": "QALD-9plus",
    "qald10": "QALD-10",
    "lcquad2": "LC-QuAD2.0",
}

DATASET_DISPLAY_ORDER = ["qald9plus", "qald10", "lcquad2"]

EXCLUDED_LANGS: dict[str, set[str]] = {
    "qald10": {"ja"},
    "qald9plus": {"zh", "lt", "ja"},
}


def find_gerbil_csvs(base_dir: Path) -> list[tuple[Path, str]]:
    """
    Find all gerbil result CSVs. Returns list of (csv_path, name_to_parse) tuples.
    Handles both directory-style (dir.csv/timestamp.csv) and flat file style.
    """
    results: list[tuple[Path, str]] = []
    for system_dir in sorted(base_dir.iterdir()):
        if not system_dir.is_dir() or system_dir.name in EXCLUDE_SYSTEMS:
            continue
        for candidate in sorted(system_dir.rglob("*")):
            if "output" not in candidate.parts or "gerbil" not in candidate.parts:
                continue
            if not candidate.name.endswith(".csv"):
                continue
            if candidate.is_dir():
                inner_csvs = [f for f in candidate.glob("*.csv") if not _is_placeholder(f)]
                if inner_csvs:
                    csv_path = max(inner_csvs, key=lambda p: p.stat().st_mtime)
                    results.append((csv_path, candidate.name))
            elif candidate.is_file() and not _is_placeholder(candidate):
                # Skip files inside .csv directories (those are handled above)
                if candidate.parent.name.endswith(".csv"):
                    continue
                results.append((candidate, candidate.name))
    return results


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


def scan_gerbil_directory(gerbil_dir: Path) -> list[dict]:
    """
    Scan a gerbil result directory and return a descending list of subdirectories
    ranked by Macro F1 score.

    Each subdirectory is expected to contain a .csv file with gerbil results.
    Returns list of dicts with keys: name, macro_f1, gerbil_id, gerbil_url.
    Sorted by macro_f1 in descending order.

    Example path: data_dir/processed_kgqa_ds/qald9plus/train/prediction/tentrismain_aug_gold/gerbil
    """
    if not gerbil_dir.exists() or not gerbil_dir.is_dir():
        logger.warning("Gerbil directory does not exist: %s", gerbil_dir)
        return []

    results: list[dict] = []
    for subdir in sorted(gerbil_dir.iterdir()):
        if not subdir.is_dir():
            continue

        csv_files = [f for f in subdir.glob("*.csv") if not _is_placeholder(f)]
        if not csv_files:
            continue

        csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
        macro_f1 = extract_macro_f1(csv_path)
        if macro_f1 is None:
            continue

        gerbil_id = csv_path.stem
        gerbil_url = f"https://gerbil-qa.aksw.org/gerbil/experiment?id={gerbil_id}"

        results.append({
            "name": subdir.name,
            "macro_f1": macro_f1,
            "gerbil_id": gerbil_id,
            "gerbil_url": gerbil_url,
        })

    results.sort(key=lambda x: x["macro_f1"], reverse=True)
    return results


def format_gerbil_ranking(rows: list[dict]) -> str:
    """Format gerbil ranking rows as a markdown table sorted by Macro F1 descending."""
    if not rows:
        return "No gerbil results found."

    headers = ["Rank", "Name", "Macro F1", "Gerbil ID", "Gerbil URL"]
    col_widths = [len(h) for h in headers]

    lines: list[str] = []
    for idx, r in enumerate(rows, start=1):
        vals = [
            str(idx),
            r["name"],
            f"{r['macro_f1']:.4f}",
            r["gerbil_id"],
            r["gerbil_url"],
        ]
        for i, v in enumerate(vals):
            col_widths[i] = max(col_widths[i], len(v))
        lines.append(" | ".join(v.ljust(col_widths[i]) for i, v in enumerate(vals)))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))

    return "\n".join([header_line, sep_line] + lines)


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


def parse_mars_filename(filename: str) -> dict | None:
    """
    Parse a mars gerbil directory name to extract language and config.

    Example:
        en__otus__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.csv
    """
    m = re.match(
        r"^(?P<lang>[a-z]{2,3})__otus__(?P<config>PBSG_MHOP__[^_]+)__gptoss120b\.csv$",
        filename,
    )
    if not m:
        return None
    return {
        "language": m.group("lang"),
        "config": m.group("config"),
    }


def find_mars_gerbil_dirs(mars_base_dir: Path) -> list[Path]:
    """
    Find all mars gerbil result directories under processed_kgqa_ds.
    Only include test directories for known datasets.
    """
    result_dirs: list[Path] = []
    if not mars_base_dir.exists():
        return result_dirs

    for dataset_dir in sorted(mars_base_dir.iterdir()):
        if not dataset_dir.is_dir() or dataset_dir.name not in MARS_DATASETS:
            continue
        test_dir = dataset_dir / "test"
        if not test_dir.exists():
            continue
        gerbil_dir = (
            test_dir / "prediction" / "tentrismain_aug_gold" / "gerbil"
        )
        if not gerbil_dir.exists():
            continue
        for candidate in sorted(gerbil_dir.iterdir()):
            if not candidate.is_dir():
                continue
            if not candidate.name.endswith(".csv"):
                continue
            parsed = parse_mars_filename(candidate.name)
            if not parsed:
                continue
            inner_csvs = [f for f in candidate.glob("*.csv") if not _is_placeholder(f)]
            if inner_csvs:
                result_dirs.append(candidate)
    return result_dirs


def build_mars_summary(mars_base_dir: Path) -> list[dict]:
    """
    Build mars summary rows. For each dataset, select the best configuration
    based on the highest Macro F1 for 'en' language, then use that config
    for all languages in the dataset.
    """
    gerbil_dirs = find_mars_gerbil_dirs(mars_base_dir)
    if not gerbil_dirs:
        return []

    # Collect all (dataset, language, config, macro_f1, gerbil_id) tuples
    all_results: list[tuple[str, str, str, float, str]] = []
    for gerbil_dir in gerbil_dirs:
        dataset = gerbil_dir.parts[0]  # First part after base_dir is dataset name
        # Actually need to extract from path parts
        try:
            base_idx = gerbil_dir.parts.index(mars_base_dir.name)
        except ValueError:
            continue
        dataset = gerbil_dir.parts[base_idx + 1]

        parsed = parse_mars_filename(gerbil_dir.name)
        if not parsed:
            continue

        csv_files = [f for f in gerbil_dir.glob("*.csv") if not _is_placeholder(f)]
        if not csv_files:
            continue
        csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
        macro_f1 = extract_macro_f1(csv_path)
        if macro_f1 is None:
            continue

        all_results.append((dataset, parsed["language"], parsed["config"], macro_f1, csv_path.stem))

    # For each dataset, find the best config based on 'en' language Macro F1
    best_config_per_dataset: dict[str, str] = {}
    for dataset in MARS_DATASETS:
        en_results = [
            (config, f1)
            for ds, lang, config, f1, _ in all_results
            if ds == dataset and lang == "en"
        ]
        if en_results:
            best_config = max(en_results, key=lambda x: x[1])[0]
            best_config_per_dataset[dataset] = best_config

    # Build final rows using the best config for each dataset
    rows: list[dict] = []
    for dataset, best_config in best_config_per_dataset.items():
        for ds, lang, config, f1, gid in all_results:
            if ds == dataset and config == best_config:
                rows.append({
                    "system": MARS_SYSTEM_LABEL,
                    "dataset": dataset,
                    "language": lang,
                    "mode": "native",
                    "macro_f1": f1,
                    "gerbil_id": gid,
                })

    return rows


def filter_rows_by_mode(rows: list[dict]) -> list[dict]:
    """
    Filter rows based on system-specific mode preferences:
    - grasp/gpt-oss-120b and mst5: native only
    - deeppavlov2: translated only, except 'en' which is always native
    - mars: native only (already set)
    """
    filtered: list[dict] = []
    for r in rows:
        system = r["system"]
        mode = r["mode"]
        lang = r["language"]

        if system in NATIVE_ONLY_SYSTEMS:
            if mode != "native":
                continue
        elif system in TRANSLATED_ONLY_SYSTEMS:
            if lang == "en":
                if mode != "native":
                    continue
            else:
                if mode != "translated":
                    continue
        elif system == MARS_SYSTEM_LABEL:
            if mode != "native":
                continue

        filtered.append(r)
    return filtered


def filter_excluded_langs(rows: list[dict]) -> list[dict]:
    """Remove rows for excluded dataset+language combinations."""
    return [
        r for r in rows
        if r["language"] not in EXCLUDED_LANGS.get(r["dataset"], set())
    ]


def build_summary(base_dir: Path) -> list[dict]:
    """Build a list of summary rows from all gerbil result CSVs."""
    rows: list[dict] = []
    gerbil_csvs = find_gerbil_csvs(base_dir)

    for csv_path, parse_name in gerbil_csvs:
        macro_f1 = extract_macro_f1(csv_path)
        if macro_f1 is None:
            continue

        parts = csv_path.parts
        system_idx = parts.index("external_systems") + 1
        system_name = parts[system_idx]
        model_name = discover_system_model(base_dir, system_name)
        system_label = f"{system_name}/{model_name}" if model_name else system_name

        parsed = parse_dir_name(parse_name, system_name)
        if not parsed:
            logger.warning("Could not parse name: %s", parse_name)
            continue

        rows.append({
            "system": system_label,
            "dataset": parsed["dataset"],
            "language": parsed["language"],
            "mode": parsed["mode"],
            "macro_f1": macro_f1,
            "gerbil_id": csv_path.stem,
        })

    return filter_excluded_langs(filter_rows_by_mode(rows))


def format_table(rows: list[dict]) -> str:
    """Format rows as a markdown table."""
    headers = ["System", "Dataset", "Language", "Mode", "Macro F1", "Gerbil ID"]
    col_widths = [len(h) for h in headers]

    formatted_rows: list[list[str]] = []
    for r in rows:
        vals = [
            r["system"],
            r["dataset"],
            r["language"],
            r["mode"],
            f"{r['macro_f1']:.4f}",
            r.get("gerbil_id", ""),
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
    fieldnames = ["system", "dataset", "language", "mode", "macro_f1", "gerbil_id"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_pivoted_table(rows: list[dict]) -> str:
    """
    Format rows as a pivoted markdown table where:
    - First column groups are dataset names
    - Second column is language (mode is implicit per system filter)
    - Remaining columns are systems with Macro F1 values

    | Dataset | Language | deeppavlov2 | grasp/gpt-oss-120b | mars/gptoss120b | mst5 |
    |---------|----------|-------------|-------------------|-----------------|------|
    | qald10  | de       | 0.1455      | 0.5460            | 0.6085          | 0.2311 |
    """
    all_systems = {r["system"] for r in rows}
    systems = [s for s in SYSTEM_ORDER if s in all_systems] + sorted(
        s for s in all_systems if s not in SYSTEM_ORDER
    )
    datasets = sorted({r["dataset"] for r in rows})

    lookup: dict[tuple[str, str, str], str] = {}
    for r in rows:
        key = (r["dataset"], r["language"], r["system"])
        lookup[key] = f"{r['macro_f1']:.4f}"

    headers = ["Dataset", "Language"] + systems
    col_widths = [len(h) for h in headers]

    data_lines: list[list[str]] = []
    current_dataset: str | None = None
    for ds in datasets:
        langs = sorted({r["language"] for r in rows if r["dataset"] == ds})
        for lang in langs:
            vals: list[str] = []
            if ds != current_dataset:
                vals = [ds, lang] + [lookup.get((ds, lang, sys_), "-") for sys_ in systems]
            else:
                vals = ["", lang] + [lookup.get((ds, lang, sys_), "-") for sys_ in systems]
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


def format_latex_table(rows: list[dict]) -> str:
    """
    Format rows as a LaTeX table matching the provided template.
    Systems: DeepPavlov, MST5, UniQ-Gen, GRASP, SSG, \\approach.
    Values as percentage to two decimal places. Best per row bolded.
    """
    lookup: dict[tuple[str, str, str], float] = {}
    gerbil_lookup: dict[tuple[str, str, str], str] = {}
    for r in rows:
        key = (r["dataset"], r["language"], r["system"])
        lookup[key] = r["macro_f1"]
        gerbil_lookup[key] = r.get("gerbil_id", "")

    datasets = [ds for ds in DATASET_DISPLAY_ORDER if ds in {r["dataset"] for r in rows}]

    # Collect all rows in dataset order for global row indexing
    all_rows: list[tuple[str, str]] = []
    for ds in datasets:
        langs = sorted({r["language"] for r in rows if r["dataset"] == ds})
        for lang in langs:
            all_rows.append((ds, lang))

    lines: list[str] = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"\caption{Macro F1 scores (in [\%]) of all systems across datasets.}")
    lines.append(r"\label{tab:f1_combined}")
    lines.append(r"\centering")
    lines.append(r"\resizebox{\textwidth}{!}{%")
    lines.append(r"\setlength{\tabcolsep}{3pt}")
    lines.append(r"\begin{tabular}{l l c c c c | c}")
    lines.append(r"\toprule")
    hdr_cells = [
        r"\textbf{Dataset}",
        r"\textbf{Lang.}",
    ] + [f"\\textbf{{{SYSTEM_LATEX_MAP[s]}}}" for s in LATEX_HEADER_ORDER] + [
        rf"\textbf{{{SYSTEM_LATEX_MAP['mars/gptoss120b']}}}",
    ]
    lines.append(" & ".join(hdr_cells) + r" \\")
    lines.append(r"\midrule")

    global_row = 0
    for ds_idx, ds in enumerate(datasets):
        ds_label = DATASET_LATEX_MAP.get(ds, ds)
        langs = sorted({r["language"] for r in rows if r["dataset"] == ds})
        n_langs = len(langs)

        for li, lang in enumerate(langs):
            is_gray = global_row % 2 == 0
            is_last = li == n_langs - 1

            # Build value cells for all systems
            latex_systems = LATEX_HEADER_ORDER + ["mars/gptoss120b"]
            vals: list[str | None] = []
            gerbil_ids: list[str] = []
            for sk in latex_systems:
                v = lookup.get((ds, lang, sk))
                vals.append(f"{v * 100:.2f}" if v is not None else None)
                gerbil_ids.append(gerbil_lookup.get((ds, lang, sk), ""))

            # Find best value index
            best_idx = -1
            best_val = -1.0
            for vi, vc in enumerate(vals):
                if vc is not None:
                    if float(vc) > best_val:
                        best_val = float(vc)
                        best_idx = vi

            def _link(text: str, gid: str, bold: bool = False) -> str:
                if gid:
                    url = rf"https://gerbil-qa.aksw.org/gerbil/experiment?id={gid}"
                    inner = rf"\textbf{{{text}}}" if bold else text
                    return rf"\href{{{url}}}{{{inner}}}"
                else:
                    return rf"\textbf{{{text}}}" if bold else text

            cells: list[str] = []
            for vi, vc in enumerate(vals):
                if vc is None:
                    cells.append("-")
                elif vi == best_idx:
                    cells.append(_link(vc, gerbil_ids[vi], bold=True))
                else:
                    cells.append(_link(vc, gerbil_ids[vi], bold=False))

            # Build first cell (dataset column)
            if n_langs == 1:
                first_cell = rf"\dataset{{{ds_label}}}"
            elif is_last:
                first_cell = rf"\cellcolor{{white}}\multirow{{-{n_langs}}}{{*}}{{\dataset{{{ds_label}}}}}"
            elif is_gray:
                first_cell = r"\cellcolor{white}"
            else:
                first_cell = ""

            row_cells = [first_cell, lang] + cells
            row_str = " & ".join(row_cells) + r" \\"

            if is_gray:
                lines.append(r"\rowcolor{gray!20}")
            if is_gray or n_langs == 1 or is_last:
                lines.append(row_str)
            else:
                lines.append(" " + row_str)

            global_row += 1

        if ds_idx < len(datasets) - 1:
            lines.append(r"\midrule")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}%")
    lines.append(r"\end{table}")

    return "\n".join(lines)


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
        "--mars-base-dir",
        default=MARS_BASE_DIR_DEFAULT,
        help="Base directory containing mars results (default: data_dir/processed_kgqa_ds).",
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
    parser.add_argument(
        "--no-mars",
        action="store_true",
        help="Exclude mars system from results.",
    )
    parser.add_argument(
        "--output-latex",
        default=None,
        help="Output LaTeX table file path.",
    )
    parser.add_argument(
        "--scan-gerbil-dir",
        default=None,
        help="Scan a gerbil directory and print subdirectories ranked by Macro F1 descending.",
    )
    parser.add_argument(
        "--scan-output-md",
        default=None,
        help="Output markdown file path for --scan-gerbil-dir results.",
    )
    args = parser.parse_args()

    if args.scan_gerbil_dir:
        gerbil_dir = Path(args.scan_gerbil_dir)
        rows = scan_gerbil_directory(gerbil_dir)
        table = format_gerbil_ranking(rows)
        print(table)
        if args.scan_output_md:
            out_path = Path(args.scan_output_md)
            create_directory_if_not_exists(str(out_path))
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(table + "\n")
            logger.info("Ranking saved to %s", out_path)
        return

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        logger.error("Base directory does not exist: %s", base_dir)
        sys.exit(1)

    rows = build_summary(base_dir)

    if not args.no_mars:
        mars_base_dir = Path(args.mars_base_dir)
        mars_rows = build_mars_summary(mars_base_dir)
        rows.extend(filter_excluded_langs(mars_rows))

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

    if args.output_latex:
        latex_path = Path(args.output_latex)
        create_directory_if_not_exists(str(latex_path))
        with open(latex_path, "w", encoding="utf-8") as f:
            f.write(format_latex_table(rows) + "\n")
        logger.info("LaTeX table saved to %s", latex_path)


if __name__ == "__main__":
    main()
