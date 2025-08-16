# Based on: https://github.com/dice-group/MST5/blob/master/code/components/Gerbil.py
import io
import json
import logging
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

    def export_results(self, output_file: str, max_retry: int = 10) -> None:
        """
        Download the HTML results page, clean it and write a CSV.
        If the experiment is still running after ``max_retry`` attempts,
        a placeholder CSV containing only the experiment ID is written.
        """
        html = self._poll_experiment_results(max_retry)
        if html:
            df = self._parse_results_html(html)
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_file, index=False)
            logger.info("Experiment results saved to %s", output_file)
        else:
            export_csv(output_file, [["gerbil experiment id"], [self.experiment_id]])
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
    def _parse_results_html(html: str) -> pd.DataFrame:
        """Transform the HTML results table into a clean DataFrame."""
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
    export_file_path: str,
    gerbil_exp_info_path: str,
) -> None:
    """
    End‑to‑end helper:
    1. Prepare a Gerbil client,
    2. Submit the experiment,
    3. Record the experiment URL,
    4. Export the results to CSV.
    """
    gerbil = Gerbil()
    gerbil.add_ref_file(gold_file_label, gold_file_path)
    gerbil.add_pred_file(f"{system_label}-{language}", pred_file_path)

    response = gerbil.submit_experiment(language)
    if response:
        exp_url = f"{EXPERIMENT_URL_PREFIX}{response.text.strip()}"
        create_directory_if_not_exists(gerbil_exp_info_path)
        with open(gerbil_exp_info_path, "a", encoding="utf-8") as f:
            f.write(f"{gold_file_label}\t{language}\t{system_label}\t{exp_url}\n")

    create_directory_if_not_exists(export_file_path)
    gerbil.export_results(export_file_path)