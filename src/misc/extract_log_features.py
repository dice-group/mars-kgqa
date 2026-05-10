"""Extract prediction times and feature flags from cluster log files."""
import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path


FEATURE_KEYS = [
    "top_n",
    "max_hops",
    "include_pattern_count",
    #"refine_sparql",
    "use_aug_sim",
    #"use_sleep",
    "conc_ex_limit",
    "use_class_info",
    "verify_update_sparql",
]

PREDICTION_TIME_RE = re.compile(
    r"\[TIME\]\s*Prediction on dataset took\s+([\d.]+)s"
)

ALL_JSON_KEYS = FEATURE_KEYS + ["filter_entities"]
JSON_VALUE_RE = {
    k: re.compile(r'"' + re.escape(k) + r'"\s*:\s*([^\n,]+)') for k in ALL_JSON_KEYS
}

TOKEN_COUNT_RE = re.compile(r"Total tokens in the message:\s*(\d+)")


def extract_prediction_time(lines: list[str]) -> float | None:
    for line in lines:
        m = PREDICTION_TIME_RE.search(line)
        if m:
            return float(m.group(1))
    return None


def _parse_value(raw: str):
    raw = raw.strip().rstrip(",")
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def extract_features(lines: list[str]) -> dict:
    result: dict = {}
    for key in ALL_JSON_KEYS:
        for line in lines:
            m = JSON_VALUE_RE[key].search(line)
            if m:
                result[key] = _parse_value(m.group(1))
                break
    return result


def find_log_files(base_dir: str) -> list[str]:
    found: list[str] = []
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            found.append(os.path.join(root, fname))
    return sorted(found)


def process_file(filepath: str) -> dict | None:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            lines = content.splitlines(True)
    except OSError:
        return None

    pred_time = extract_prediction_time(lines)
    if pred_time is None:
        return None

    features = extract_features(lines)

    token_values = [int(m.group(1)) for m in TOKEN_COUNT_RE.finditer(content)]
    num_requests = len(token_values)
    avg_tokens = sum(token_values) / num_requests if num_requests else 0.0

    return {
        "file": filepath,
        "prediction_time_s": pred_time,
        **features,
        "num_llm_requests": num_requests,
        "avg_tokens": round(avg_tokens, 2),
    }


def build_gerbil_config(features: dict) -> str:
    """Build the gerbil config suffix string from feature flags."""
    parts: list[str] = []
    top_n = features.get("top_n")
    if top_n is not None:
        parts.append(f"t{top_n}")
    max_hops = features.get("max_hops")
    if max_hops is not None:
        parts.append(f"h{max_hops}")
    if features.get("filter_entities"):
        parts.append("enfil")
    if features.get("include_pattern_count"):
        parts.append("pc")
    if features.get("refine_sparql"):
        parts.append("sref")
    if features.get("use_aug_sim"):
        parts.append("ausm")
    if features.get("use_gold"):
        parts.append("gld-enrl")
    else:
        parts.append("grasp-el")
    conc_ex = features.get("conc_ex_limit", 0)
    if conc_ex and conc_ex > 0:
        parts.append(f"exlim{conc_ex}")
    if features.get("use_class_info"):
        parts.append("clsinf")
    if features.get("verify_update_sparql"):
        parts.append("verupdt")
    return "-".join(parts)


def extract_macro_f1_from_gerbil(csv_path: Path) -> float | None:
    """Read the Macro F1 score from a gerbil result CSV."""
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                macro_f1 = row.get("Macro F1")
                if macro_f1:
                    return float(macro_f1)
    except Exception:
        pass
    return None


def find_gerbil_macro_f1(gerbil_base: str, features: dict) -> float | None:
    """Find the macro F1 score for a given feature config in the gerbil directory."""
    if not gerbil_base or not os.path.isdir(gerbil_base):
        return None

    config_str = build_gerbil_config(features)
    if not config_str:
        return None

    gerbil_path = Path(gerbil_base)
    for subdir in gerbil_path.iterdir():
        if not subdir.is_dir():
            continue
        if config_str not in subdir.name:
            continue
        csv_files = list(subdir.glob("*.csv"))
        if not csv_files:
            continue
        csv_file = max(csv_files, key=lambda p: p.stat().st_mtime)
        f1 = extract_macro_f1_from_gerbil(csv_file)
        if f1 is not None:
            return f1
    return None


def detect_use_gold(filepath: str) -> bool:
    """Detect whether gold entities were used by checking the log filename."""
    return "gold_ent" in os.path.basename(filepath)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract prediction times and feature flags from cluster logs."
    )
    parser.add_argument(
        "base_dir",
        help="Base directory containing log files (e.g. data_dir/ablation_4/cluster_logs)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output JSON path (default: <out_dir>/mars_all_feature_scale_analysis.json)",
    )
    parser.add_argument(
        "--csv-out",
        default=None,
        help="Output CSV path (default: <out_dir>/mars_all_feature_scale_analysis.csv)",
    )
    parser.add_argument(
        "--md-out",
        default=None,
        help="Output Markdown path (default: <out_dir>/mars_all_feature_scale_analysis.md)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for JSON/CSV/MD files (default: data_dir/misc)",
    )
    parser.add_argument(
        "--gerbil-dir",
        default=None,
        help="Gerbil results directory for Macro F1 lookup",
    )
    args = parser.parse_args()

    base_dir = args.base_dir
    if args.out_dir:
        out_dir = args.out_dir
    else:
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..",
            "data_dir",
            "misc",
        )
        out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    if not os.path.isdir(base_dir):
        print(f"Error: '{base_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    log_files = find_log_files(base_dir)
    if not log_files:
        print(f"No files found in '{base_dir}'.")
        sys.exit(0)

    print(f"Found {len(log_files)} files in '{base_dir}'.")

    results: list[dict] = []
    skipped = 0
    no_f1 = 0
    for fp in log_files:
        row = process_file(fp)
        if row is None:
            skipped += 1
            rel = os.path.relpath(fp, base_dir)
            print(f"  SKIP (no prediction time): {rel}")
            continue

        row["use_gold"] = detect_use_gold(fp)
        if args.gerbil_dir:
            f1 = find_gerbil_macro_f1(args.gerbil_dir, row)
            row["macro_f1"] = f1
            if f1 is not None:
                rel = os.path.relpath(fp, base_dir)
                print(f"  {rel}: {row['prediction_time_s']:.2f}s  Macro F1: {f1:.4f}")
            else:
                no_f1 += 1
                rel = os.path.relpath(fp, base_dir)
                print(f"  {rel}: {row['prediction_time_s']:.2f}s  (no Macro F1)")
        else:
            rel = os.path.relpath(fp, base_dir)
            print(f"  {rel}: {row['prediction_time_s']:.2f}s")

        results.append(row)

    if skipped:
        print(f"\nSkipped {skipped} file(s) without prediction time.")
    if no_f1:
        print(f"Could not find Macro F1 for {no_f1} file(s).")
    print(f"Processed {len(results)} file(s) successfully.")

    if args.gerbil_dir:
        results.sort(key=lambda r: r.get("macro_f1") or 0, reverse=True)

    out_json = args.out or os.path.join(out_dir, "mars_all_feature_scale_analysis.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nJSON output written to: {out_json}")

    if args.csv_out:
        out_csv = args.csv_out
    else:
        out_csv = os.path.join(out_dir, "mars_all_feature_scale_analysis.csv")
    fieldnames = ["file", "prediction_time_s"] + FEATURE_KEYS + ["num_llm_requests", "avg_tokens"]
    if args.gerbil_dir:
        fieldnames.append("macro_f1")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV output written to: {out_csv}")

    # Markdown output
    if args.md_out:
        out_md = args.md_out
    else:
        out_md = os.path.join(out_dir, "mars_all_feature_scale_analysis.md")

    lines: list[str] = []
    lines.append("# Extracted Log Features\n")
    lines.append(f"**Base directory:** `{base_dir}`  ")
    lines.append(f"**Files processed:** {len(results)}  ")
    if skipped:
        lines.append(f"**Files skipped:** {skipped} (no prediction time found)  ")
    lines.append("")

    has_f1 = args.gerbil_dir and any(r.get("macro_f1") is not None for r in results)
    header_cols = ["File", "Prediction (s)"]
    for k in FEATURE_KEYS:
        header_cols.append(f"`{k}`")
    header_cols.append("Num LLM Req")
    header_cols.append("Avg Tokens")
    if has_f1:
        header_cols.append("Macro F1")
    sep_cols = ["---------", "-----------------"] + ["---"] * len(FEATURE_KEYS)
    sep_cols += ["-----------", "-----------"]
    if has_f1:
        sep_cols.append("---------")
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("|" + "|".join(sep_cols) + "|")

    for row in results:
        rel = os.path.relpath(row["file"], base_dir)
        cells = [
            f"`{rel}`",
            f"{row['prediction_time_s']:.2f}",
        ]
        for k in FEATURE_KEYS:
            cells.append(str(row.get(k, "")))
        cells.append(str(row.get("num_llm_requests", "")))
        cells.append(f"{row.get('avg_tokens', 0):.1f}")
        if has_f1:
            f1 = row.get("macro_f1")
            cells.append(f"{f1:.4f}" if f1 is not None else "-")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Markdown output written to: {out_md}")


if __name__ == "__main__":
    main()
