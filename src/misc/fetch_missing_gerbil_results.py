#!/usr/bin/env python3
"""
Utility script to fetch missing Gerbil experiment results.

Scans all gerbil result CSVs under data_dir/processed_kgqa_ds/,
checks which ones are placeholders or missing JSON-LD, and fetches
the actual results from the Gerbil API.

Usage:
    bash pylauncher.sh normal src.misc.fetch_missing_gerbil_results [--max-retries N] [--dry-run]
    bash pylauncher.sh normal src.misc.fetch_missing_gerbil_results --base-dir data_dir/external_systems --dry-run
"""

import argparse
import json
import logging
from pathlib import Path

from src.util.gerbil import (
    Gerbil,
    EXPERIMENT_URL_PREFIX,
    GERBIL_HEADERS,
)

logger = logging.getLogger(__name__)


def fetch_and_save(experiment_id: str, output_dir: Path, max_retries: int) -> bool:
    """
    Use the existing Gerbil client to poll and save results.
    Returns True if results were saved, False otherwise.
    """
    g = Gerbil()
    g.experiment_id = experiment_id
    html = g._poll_experiment_results(max_retries)
    if html is None:
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    jsonld = g._extract_jsonld(html)
    if jsonld is not None:
        jsonld_path = output_dir / f"{experiment_id}.jsonld"
        with open(jsonld_path, "w", encoding="utf-8") as f:
            json.dump(jsonld, f, indent=2, ensure_ascii=False)
        logger.info("  JSON-LD saved to %s", jsonld_path)

        df = g._parse_jsonld_results(jsonld)
        csv_path = output_dir / f"{experiment_id}.csv"
        df.to_csv(csv_path, index=False)
        logger.info("  CSV saved to %s", csv_path)
    else:
        logger.warning("  No JSON-LD found, falling back to HTML table parsing.")
        df = g._parse_results_html(html)
        csv_path = output_dir / f"{experiment_id}.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        logger.info("  CSV saved to %s", csv_path)

    return True


def is_still_running(experiment_id: str) -> bool:
    """Quick check whether an experiment is still running on Gerbil."""
    url = EXPERIMENT_URL_PREFIX + experiment_id
    try:
        resp = __import__("requests").get(url, headers=GERBIL_HEADERS, timeout=30)
        resp.raise_for_status()
        return Gerbil._is_running(resp.text)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Discovery: find all gerbil result CSVs and extract experiment IDs
# --------------------------------------------------------------------------- #


def is_placeholder_csv(csv_path: Path) -> bool:
    """
    A placeholder CSV has exactly 2 lines:
        gerbil experiment id
        <experiment_id>
    """
    try:
        lines = csv_path.read_text().strip().splitlines()
        return len(lines) == 2 and "gerbil experiment id" in lines[0]
    except Exception:
        return False


def extract_exp_id_from_placeholder(csv_path: Path) -> str | None:
    """Read the experiment ID from the second line of a placeholder CSV."""
    try:
        lines = csv_path.read_text().strip().splitlines()
        if len(lines) >= 2:
            return lines[1].strip()
    except Exception:
        pass
    return None


def find_all_gerbil_csvs(base_dir: str) -> list[Path]:
    """
    Recursively find all {experiment_id}.csv files under gerbil directories.
    These are inside {system}.csv/ subdirectories.
    """
    base = Path(base_dir)
    if not base.exists():
        logger.warning("Base directory does not exist: %s", base)
        return []
    return sorted(base.rglob("gerbil/**/*/*.csv"))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch missing Gerbil experiment results.",
    )
    parser.add_argument(
        "--base-dir",
        nargs="+",
        default=["data_dir/processed_kgqa_ds", "data_dir/external_systems"],
        help="Base directories containing gerbil result CSVs (can specify multiple).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=15,
        help="Max polling attempts per experiment (default: 15).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be fetched, without making API calls.",
    )
    args = parser.parse_args()

    csv_files: list[Path] = []
    for base_dir in args.base_dir:
        csv_files.extend(find_all_gerbil_csvs(base_dir))
    if not csv_files:
        logger.info("No gerbil result CSVs found under %s.", args.base_dir)
        return

    logger.info("Found %d gerbil result CSV file(s).", len(csv_files))

    # Classify each CSV
    placeholders: list[tuple[str, Path, Path]] = []  # (exp_id, csv_path, parent_dir)
    has_results: int = 0

    for csv_path in csv_files:
        parent_dir = csv_path.parent
        exp_id = csv_path.stem  # filename without .csv extension

        if is_placeholder_csv(csv_path):
            pid = extract_exp_id_from_placeholder(csv_path)
            if pid:
                placeholders.append((pid, csv_path, parent_dir))
            else:
                logger.warning("Could not extract experiment ID from placeholder: %s", csv_path)
        else:
            has_results += 1

    logger.info("Placeholder CSVs (need fetching): %d", len(placeholders))
    logger.info("Already have results:             %d", has_results)

    if not placeholders:
        logger.info("All experiments already have results. Nothing to do.")
        return

    # Check which placeholders also have JSON-LD
    missing: list[tuple[str, Path, Path]] = []
    complete: int = 0
    for exp_id, csv_path, parent_dir in placeholders:
        jsonld_path = parent_dir / f"{exp_id}.jsonld"
        if jsonld_path.exists():
            complete += 1
        else:
            missing.append((exp_id, csv_path, parent_dir))

    logger.info("Placeholder + JSON-LD exists:     %d", complete)
    logger.info("Placeholder, missing JSON-LD:     %d", len(missing))

    if not missing:
        logger.info("All experiments already have JSON-LD. Nothing to do.")
        return

    if args.dry_run:
        logger.info("--- DRY RUN ---")
        for exp_id, csv_path, parent_dir in missing:
            logger.info("  [%s] %s", exp_id, parent_dir)
        return

    # Fetch missing results
    succeeded = 0
    failed = 0
    still_running_count = 0

    for i, (exp_id, csv_path, parent_dir) in enumerate(missing, 1):
        logger.info("[%d/%d] Fetching experiment %s ...", i, len(missing), exp_id)
        ok = fetch_and_save(exp_id, parent_dir, args.max_retries)
        if ok:
            succeeded += 1
        elif is_still_running(exp_id):
            still_running_count += 1
            logger.warning("  Experiment %s still running on Gerbil. Skip.", exp_id)
        else:
            failed += 1
            logger.error("  Failed to fetch experiment %s.", exp_id)

    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info("  Total CSV files scanned:        %d", len(csv_files))
    logger.info("  Already had results:            %d", has_results + complete)
    logger.info("  Successfully fetched:           %d", succeeded)
    logger.info("  Still running on Gerbil:        %d", still_running_count)
    logger.info("  Failed / errored:               %d", failed)
    logger.info("=" * 60)

    if still_running_count > 0:
        logger.info(
            "Tip: Run again later to pick up the %d still-running experiment(s).",
            still_running_count,
        )


if __name__ == "__main__":
    main()
