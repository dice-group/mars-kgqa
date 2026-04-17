import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from tqdm import tqdm

import src.const.misc as misc_consts
from src.const.dataset import DatasetSplit, KgqaDataset
from src.util.common import create_directory_if_not_exists, sparql_one_line
from src.util.external_kgqa import deeppavlov2_output_to_tsv, qald_to_deeppavlov2_jsonl


DEEPPAVLOV_URL = "http://kgqa.cs.upb.de:40196/respond"
HEADERS = {"Content-Type": "application/json"}
REQUEST_TIMEOUT = 180  # seconds

SPARQL_LOG_DIR = "data_dir/sparql_logs"

DEEPPAVLOV2_INFO: Dict[str, Dict[str, Any]] = {
    "qald10_test": {
        "ds": KgqaDataset.QALD10_UPDATED_TENTRISMAIN,
        "split": DatasetSplit.TEST,
        "input_dir":     "data_dir/external_systems/deeppavlov2/input/qald10",
        "tsv_out_dir":   "data_dir/external_systems/deeppavlov2/output/tsv/qald10",
        "gerbil_out_dir":"data_dir/external_systems/deeppavlov2/output/gerbil/qald10",
        "native_langs":     ["en", "de", "ru"],
        "translated_langs": ["de", "ru", "zh"],
    },
    "qald9plus_test": {
        "ds": KgqaDataset.QALD9PLUS_UPDATED_TENTRISMAIN,
        "split": DatasetSplit.TEST,
        "input_dir":     "data_dir/external_systems/deeppavlov2/input/qald9plus",
        "tsv_out_dir":   "data_dir/external_systems/deeppavlov2/output/tsv/qald9plus",
        "gerbil_out_dir":"data_dir/external_systems/deeppavlov2/output/gerbil/qald9plus",
        "native_langs":     ["en", "de", "ru"],
        "translated_langs": ["de", "fr", "ba", "be", "es", "hy", "ru", "uk"],
    },
    "lcquad2_test": {
        "ds": KgqaDataset.LCQUAD2_UPDATED_TENTRISMAIN,
        "split": DatasetSplit.TEST,
        "input_dir":     "data_dir/external_systems/deeppavlov2/input/lcquad2",
        "tsv_out_dir":   "data_dir/external_systems/deeppavlov2/output/tsv/lcquad2",
        "gerbil_out_dir":"data_dir/external_systems/deeppavlov2/output/gerbil/lcquad2",
        "native_langs":     ["en"],
        "translated_langs": [],
    },
}



def init_sparql_logger() -> None:
    """Open a timestamped SPARQL log file and attach it to the global handle."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sparql_log_fp = os.path.join(SPARQL_LOG_DIR, f"external_systems_{timestamp}.txt")
    create_directory_if_not_exists(sparql_log_fp)
    # buffering=1 -> line-buffered so tail -f works during long runs
    misc_consts.sparql_log_filehandle = open(sparql_log_fp, "a", buffering=1)


def close_sparql_logger() -> None:
    handle = getattr(misc_consts, "sparql_log_filehandle", None)
    if handle is not None and not handle.closed:
        handle.close()

def query_deeppavlov2(question: str) -> Any:
    """Send a single question to DeepPavlov2 and return the parsed JSON response."""
    payload = json.dumps({"questions": [question]})
    resp = requests.post(
        DEEPPAVLOV_URL, headers=HEADERS, data=payload, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def build_lang_configs(
    native_langs: List[str], translated_langs: List[str]
) -> List[Tuple[str, bool]]:
    """Return a flat list of (lang, use_translation) pairs to iterate over."""
    return (
        [(l, False) for l in native_langs]
        + [(l, True)  for l in translated_langs]
    )


def fetch_responses(jsonl_in: str, responses_out: str, desc: str = "questions") -> None:
    """Query DeepPavlov2 for every question in `jsonl_in`, writing raw responses."""
    with open(jsonl_in, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    with open(responses_out, "w", encoding="utf-8") as out_f:
        for entry in tqdm(
            entries,
            desc=desc,
            unit="q",
            leave=False,
        ):
            q_id, q_text = entry["id"], entry["question"]
            try:
                resp_data = query_deeppavlov2(q_text)
            except Exception as e:
                tqdm.write(f"    ! Error for id={q_id}: {e}")
                resp_data = None

            out_f.write(
                json.dumps(
                    {"id": q_id, "question": q_text, "response": resp_data},
                    ensure_ascii=False,
                )
                + "\n"
            )


def process_language(
    gold_qald_fp: str,
    file_base_name: str,
    lang: str,
    use_translation: bool,
    jsonl_dir: str,
    tsv_out_dir: str,
) -> None:
    """Run the full jsonl -> responses -> tsv pipeline for one (lang, mode)."""
    lang_type = "translated" if use_translation else "native"
    stem = f"{lang}_{lang_type}_{file_base_name}"

    jsonl_fp     = os.path.join(jsonl_dir,   f"{stem}.jsonl")
    responses_fp = os.path.join(jsonl_dir,   f"{stem}_responses.jsonl")
    tsv_fp       = os.path.join(tsv_out_dir, f"{stem}.tsv")

    # 1. Gold QALD -> DeepPavlov2 input jsonl
    qald_to_deeppavlov2_jsonl(
        gold_qald_fp, jsonl_fp, lang, use_translation=use_translation
    )

    # 2. Input jsonl -> raw responses jsonl
    fetch_responses(jsonl_fp, responses_fp, desc=f"  {lang} ({lang_type}) questions")

    # 3. Raw responses -> tsv
    deeppavlov2_output_to_tsv(responses_fp, tsv_fp)


def process_dataset(key: str, ds_info: Dict[str, Any]) -> None:
    """Process all languages (native + translated) for a single dataset."""
    ds_obj   = ds_info["ds"].value
    ds_split = ds_info["split"]

    gold_qald_fp   = ds_obj.split_dict[ds_split]
    jsonl_dir      = ds_info["input_dir"]
    tsv_out_dir    = ds_info["tsv_out_dir"]
    file_base_name = f"{ds_obj.dataset_id}_{ds_split.name.lower()}"

    Path(jsonl_dir).mkdir(parents=True, exist_ok=True)
    Path(tsv_out_dir).mkdir(parents=True, exist_ok=True)

    lang_configs = build_lang_configs(
        ds_info["native_langs"], ds_info.get("translated_langs", [])
    )

    for lang, use_translation in tqdm(
        lang_configs,
        desc=f"Dataset {key}: processing languages",
        unit="lang",
        leave=False,
    ):
        process_language(
            gold_qald_fp=gold_qald_fp,
            file_base_name=file_base_name,
            lang=lang,
            use_translation=use_translation,
            jsonl_dir=jsonl_dir,
            tsv_out_dir=tsv_out_dir,
        )


def main() -> None:
    init_sparql_logger()
    try:
        for key, ds_info in tqdm(
            DEEPPAVLOV2_INFO.items(),
            desc="Processing all datasets",
            unit="ds",
            total=len(DEEPPAVLOV2_INFO),
        ):
            process_dataset(key, ds_info)
    finally:
        close_sparql_logger()


if __name__ == "__main__":
    main()