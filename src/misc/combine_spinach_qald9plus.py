#!/usr/bin/env python
"""Combine train sets of spinach and qald9plus into a single dataset."""

import json
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.util.common import read_json_file, save_json_file, create_directory_if_not_exists


def combine_datasets(spinach_path, qald9plus_path, output_path, dry_run=True):
    spinach_data = read_json_file(spinach_path)
    qald9plus_data = read_json_file(qald9plus_path)

    spinach_questions = spinach_data.get("questions", [])
    qald9plus_questions = qald9plus_data.get("questions", [])

    existing_ids = set(str(q["id"]) for q in spinach_questions)

    merged = list(spinach_questions)
    for q in qald9plus_questions:
        qid = str(q["id"])
        if qid in existing_ids:
            new_id = f"qald9plus_{qid}"
            print(f"  ID collision '{qid}' -> renamed to '{new_id}'")
            q = dict(q)
            q["id"] = new_id
            existing_ids.add(new_id)
        else:
            existing_ids.add(qid)
        merged.append(q)

    result = {
        "dataset": {
            "id": "SPINACH + QALD9PLUS Combined Train (QALD Format)"
        },
        "questions": merged
    }

    print(f"Spinach questions: {len(spinach_questions)}")
    print(f"QALD9plus questions: {len(qald9plus_questions)}")
    print(f"Combined questions: {len(merged)}")
    print(f"Output: {output_path}")

    if not dry_run:
        save_json_file(result, output_path)
        print(f"Saved to {output_path}")
    else:
        print("(dry_run=True -- set to False to write)")


if __name__ == "__main__":
    base = "data_dir/processed_kgqa_ds"
    spinach_path = os.path.join(base, "spinach", "train", "tentrismain_aug_gold.json")
    qald9plus_path = os.path.join(base, "qald9plus", "train", "tentrismain_aug_gold.json")
    output_path = os.path.join(base, "spinach_qald9plus_combined", "train", "tentrismain_aug_gold.json")
    combine_datasets(spinach_path, qald9plus_path, output_path, dry_run=False)
