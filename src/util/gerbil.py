# Based on: https://github.com/dice-group/MST5/blob/master/code/components/Gerbil.py
import io
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from src.util.common import create_directory_if_not_exists, export_csv

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

GERBIL_BASE_URL = "https://gerbil-qa.aksw.org/gerbil"
UPLOAD_URL = f"{GERBIL_BASE_URL}/file/upload"
EXECUTE_URL_PREFIX = f"{GERBIL_BASE_URL}/execute?experimentData="
EXPERIMENT_URL_PREFIX = f"{GERBIL_BASE_URL}/experiment?id="

# Common request headers (both upload and submit use the same set)
GERBIL_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Connection": "keep-alive",
    "Cookie": "JSESSIONID=265042E6F0ECFC6AEEA55C409FB7168F",
    "Origin": "https://gerbil-qa.aksw.org",
    "Referer": "https://gerbil-qa.aksw.org/gerbil/config",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.58"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Chromium";v="112", "Microsoft Edge";v="112", "Not:A-Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

# Set up module‑level logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --------------------------------------------------------------------------- #
# Helper data container
# --------------------------------------------------------------------------- #
class PredFile:
    """Container for a single prediction file."""
    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path


# --------------------------------------------------------------------------- #
# Main Gerbil client
# --------------------------------------------------------------------------- #
class Gerbil:
    """
    Minimal client for the Gerbil QA benchmark.
    Supports **exactly one** reference file and **one** prediction file.
    """

    def __init__(self) -> None:
        self.ref_name: Optional[str] = None
        self.ref_path: Optional[Path] = None
        self.pred_file: Optional[PredFile] = None
        self.experiment_id: Optional[str] = None

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #
    def add_ref_file(self, name: str, file_path: str) -> None:
        """Set the reference (gold) dataset."""
        self.ref_name = name
        self.ref_path = Path(file_path)
        logger.debug("Reference file set: %s -> %s", name, self.ref_path)

    def add_pred_file(self, name: str, file_path: str) -> None:
        """Set the prediction file (only one allowed)."""
        self.pred_file = PredFile(name, Path(file_path))
        logger.debug("Prediction file set: %s -> %s", name, self.pred_file.path)

    def submit_experiment(self, lang: str = "en") -> Optional[requests.Response]:
        """Upload reference + prediction, then start the experiment."""
        if not all([self.ref_name, self.ref_path, self.pred_file]):
            logger.error("Reference and prediction files must be provided before submission.")
            return None

        self._upload_ref()
        self._upload_pred()
        experiment_data = self._build_experiment_payload(lang)
        exec_url = EXECUTE_URL_PREFIX + experiment_data

        try:
            response = requests.get(exec_url, headers=GERBIL_HEADERS, timeout=30)
            response.raise_for_status()
            self.experiment_id = response.text.strip()
            logger.info("Gerbil experiment submitted successfully – ID: %s", self.experiment_id)
            return response
        except requests.RequestException as err:
            logger.error("Failed to submit experiment: %s", err)
            return None

    def export_results(self, output_dir: str, max_retry: int = 10) -> None:
        """
        Download the HTML results page, extract the JSON-LD object,
        parse it into a DataFrame and write a CSV named after the
        experiment ID.

        If the experiment is still running after ``max_retry`` attempts,
        a placeholder CSV containing only the experiment ID is written.
        """
        html = self._poll_experiment_results(max_retry)
        if html:
            jsonld = self._extract_jsonld(html)
            if jsonld is not None:
                out_dir = Path(output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)

                # Save raw JSON-LD
                jsonld_path = out_dir / f"{self.experiment_id}.jsonld"
                with open(jsonld_path, "w", encoding="utf-8") as f:
                    json.dump(jsonld, f, indent=2, ensure_ascii=False)
                logger.info("JSON-LD saved to %s", jsonld_path)

                # Save CSV
                df = self._parse_jsonld_results(jsonld)
                csv_path = out_dir / f"{self.experiment_id}.csv"
                df.to_csv(csv_path, index=False)
                logger.info("Experiment results saved to %s", csv_path)
            else:
                logger.warning("No JSON-LD found in experiment page; falling back to HTML table parsing.")
                df = self._parse_results_html(html)
                output_path = Path(output_dir) / f"{self.experiment_id}.csv"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(output_path, index=False)
                logger.info("Experiment results saved to %s", output_path)
        else:
            output_path = Path(output_dir) / f"{self.experiment_id}.csv"
            export_csv(str(output_path), [["gerbil experiment id"], [self.experiment_id]])
            logger.warning("Could not retrieve results; placeholder CSV written.")

    # ------------------------------------------------------------------- #
    # Internal helpers
    # ------------------------------------------------------------------- #
    def _upload_ref(self) -> None:
        data = {
            "name": self.ref_name,
            "URI": "",
            "multiselect": "",
            "qlang": "",
        }
        # TODO: Write logic to re-use already uploaded gold files
        file_obj = self._prepare_file(self.ref_path)
        self._post_file(data, file_obj, "reference")

    def _upload_pred(self) -> None:
        pred = self.pred_file
        ref_file_name = self.ref_path.name
        data = {
            "name": pred.name,
            "URI": "",
            "multiselect": f"AFDS_{ref_file_name}",
            "qlang": "",
        }
        file_obj = self._prepare_file(pred.path)
        self._post_file(data, file_obj, "prediction")

    @staticmethod
    def _prepare_file(path: Path) -> dict:
        """Read a file and return the dict suitable for ``requests.files``."""
        with path.open("rb") as f:
            content = f.read()
        file_like = io.BytesIO(content)
        return {"files[]": (path.name, file_like, "application/json")}

    @staticmethod
    def _post_file(data: dict, files: dict, role: str) -> None:
        try:
            resp = requests.post(UPLOAD_URL, headers=GERBIL_HEADERS, data=data, files=files, timeout=30)
            resp.raise_for_status()
            logger.debug("Uploaded %s file successfully.", role)
        except requests.RequestException as err:
            logger.error("Failed to upload %s file: %s", role, err)
            raise

    def _build_experiment_payload(self, lang: str) -> str:
        """Create the URL‑encoded JSON payload for the experiment."""
        ref_file_name = self.ref_path.name
        answer_file = (
            f"AF_{self.pred_file.name}({self.pred_file.path.name})(undefined)"
            f"(AFDS_{ref_file_name})"
        )
        payload = {
            "type": "QA",
            "matching": "STRONG_ENTITY_MATCH",
            "annotator": [],
            "dataset": [f"NIFDS_{self.ref_name}({ref_file_name})"],
            "answerFiles": [answer_file],
            "questionLanguage": lang,
        }
        return urllib.parse.quote(json.dumps(payload))

    def _poll_experiment_results(self, max_retry: int) -> Optional[str]:
        if not self.experiment_id:
            logger.error("No experiment ID available – cannot fetch results.")
            return None

        url = EXPERIMENT_URL_PREFIX + self.experiment_id
        for attempt in range(1, max_retry + 1):
            try:
                resp = requests.get(url, headers=GERBIL_HEADERS, timeout=30)
                resp.raise_for_status()
                content = resp.text
                if self._is_error(content):
                    logger.error("Experiment %s failed: %s", self.experiment_id, content)
                    return None
                if self._is_running(content):
                    logger.info("Attempt %d/%d – experiment still running, waiting...", attempt, max_retry)
                    time.sleep(30)
                    continue
                return content
            except requests.RequestException as err:
                logger.warning("Attempt %d – request error: %s", attempt, err)
                time.sleep(30)

        logger.error("Experiment %s did not finish after %d attempts.", self.experiment_id, max_retry)
        return None

    @staticmethod
    def _is_error(content: str) -> bool:
        return any(phrase in content for phrase in [
            "The annotator caused too many single errors.",
            "The dataset couldn't be loaded."
        ])

    @staticmethod
    def _is_running(content: str) -> bool:
        return "The experiment is still running." in content

    @staticmethod
    def _extract_jsonld(html: str) -> Optional[dict]:
        """
        Extract the JSON-LD object embedded in a
        ``<script type="application/ld+json">`` tag from the Gerbil
        experiment results page.
        """
        pattern = r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>'
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            return None
        raw = match.group(1).strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as err:
            logger.error("Failed to parse JSON-LD from experiment page: %s", err)
            return None

    @staticmethod
    def _parse_jsonld_results(jsonld: dict) -> pd.DataFrame:
        """
        Convert a Gerbil JSON-LD object into a tidy DataFrame.

        The ``@graph`` contains:
        * One ``gerbil:Experiment`` node (experiment metadata).
        * Several ``qb:Observation`` nodes – the *task-level* results
          that have ``qb:dataset`` pointing back at the experiment, plus
          metric values like ``microF1``, ``macroF1``, etc.
        * Per-question ``qb:Observation`` nodes that additionally carry
          a ``datasetElement`` key – these are fine-grained and are
          **excluded** from the summary CSV.

        Annotator / dataset / language IRIs are shortened to their
        local names for readability.
        """
        nodes = jsonld.get("@graph", [jsonld] if isinstance(jsonld, dict) else jsonld)

        # ---- Identify task-level observation nodes ----
        # Task-level observations have metric keys (e.g. microF1) and
        # belong to the experiment (qb:dataset) but do NOT have a
        # ``datasetElement`` key (which marks per-question rows).
        _metric_keys = {
            "microF1", "microPrecision", "microRecall",
            "macroF1", "macroPrecision", "macroRecall",
            "Macro_F1_QALD",
        }

        # Helper: extract the local name from an IRI and turn the
        # ``_(uploaded)`` suffix into `` (uploaded)`` for readability.
        def _strip_iri(iri: str) -> str:
            local = iri.rsplit("/", 1)[-1] if "/" in iri else iri
            return local.replace("_(uploaded)", " (uploaded)")

        rows: list[dict] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            # Skip per-question observations
            if "datasetElement" in node:
                continue
            # Must have at least one metric key to be a result row
            if not _metric_keys.intersection(node.keys()):
                continue

            row: dict = {}

            # --- Annotator (strip IRI prefix) ---
            # NOTE: In the JSON-LD the ``annotator`` IRI points to
            # the answer/prediction file while ``dataset`` points to
            # the gold corpus – the reverse of the HTML table.  We
            # swap them here so the CSV matches the HTML display.
            ds_iri = node.get("annotator", "")
            ann_iri = node.get("dataset", "")
            row["Annotator"] = _strip_iri(ann_iri)
            row["Dataset"] = _strip_iri(ds_iri)

            # --- Language ---
            lang = node.get("language", "")
            row["Language"] = lang.rsplit("/", 1)[-1] if "/" in lang else lang

            # --- Sub-experiment type (from @id suffix like _0 = C2KB) ---
            node_id = node.get("@id", "")
            # The main task has no underscore suffix after the task id;
            # sub-tasks have _0, _1, _2, etc.
            id_tail = node_id.rsplit("experimentTask_", 1)[-1] if "experimentTask_" in node_id else ""
            row["Benchmark"] = id_tail if "_" in id_tail else ""

            # --- Metrics ---
            row["Micro F1"] = node.get("microF1")
            row["Micro Precision"] = node.get("microPrecision")
            row["Micro Recall"] = node.get("microRecall")
            row["Macro F1"] = node.get("macroF1")
            row["Macro Precision"] = node.get("macroPrecision")
            row["Macro Recall"] = node.get("macroRecall")
            row["Macro F1 QALD"] = node.get("Macro_F1_QALD")
            row["Error Count"] = node.get("errorCount")
            row["Timestamp"] = node.get("timestamp")

            rows.append(row)
            break # we only need the first result

        if not rows:
            logger.warning("No task-level observation nodes found in JSON-LD.")
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Convert metric columns to float where possible
        metric_cols = [
            "Micro F1", "Micro Precision", "Micro Recall",
            "Macro F1", "Macro Precision", "Macro Recall",
            "Macro F1 QALD", "Error Count",
        ]
        for col in metric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    @staticmethod
    def _parse_results_html(html: str) -> pd.DataFrame:
        """
        Fallback: transform the HTML results table into a clean
        DataFrame (legacy behaviour kept for robustness).
        """
        df = pd.read_html(html)[0].rename(columns={"Unnamed: 3": "Benchmark"})
        # Keep only rows without a benchmark (these are the actual result rows)
        df = df[df["Benchmark"].isna()] if "Benchmark" in df.columns else df

        # Extract language from the annotator column (last two letters before the closing ')')
        if "Annotator" in df.columns:
            df["Language"] = df["Annotator"].str[-13:-11]

        # Drop columns that are not needed for downstream processing
        drop_cols = [
            "Dataset", "Annotator", "Error Count",
            "avg millis/doc", "Timestamp", "GERBIL version", "Benchmark"
        ]
        df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        return df


# --------------------------------------------------------------------------- #
# Convenience wrapper used by the rest of the code base
# --------------------------------------------------------------------------- #
def create_export_gerbil_experiment(
    gold_file_label: str,
    gold_file_path: str,
    system_label: str,
    pred_file_path: str,
    language: str,
    export_dir: str,
    gerbil_exp_info_path: str,
) -> None:
    """
    End‑to‑end helper:
    1. Prepare a Gerbil client,
    2. Submit the experiment,
    3. Record the experiment URL,
    4. Export the results to a CSV named ``<experiment_id>.csv``
       inside *export_dir*.
    """
    gerbil = Gerbil()
    gerbil.add_ref_file(gold_file_label, gold_file_path)
    gerbil.add_pred_file(f"{system_label}", pred_file_path)

    response = gerbil.submit_experiment(language)
    if response:
        exp_url = f"{EXPERIMENT_URL_PREFIX}{response.text.strip()}"
        create_directory_if_not_exists(gerbil_exp_info_path)
        with open(gerbil_exp_info_path, "a", encoding="utf-8") as f:
            f.write(f"{gold_file_label}\t{language}\t{system_label}\t{exp_url}\n")

    create_directory_if_not_exists(export_dir)
    gerbil.export_results(export_dir)