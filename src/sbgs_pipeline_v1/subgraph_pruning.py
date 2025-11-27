# subgraph_pruning.py
#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from src.sbgs_pipeline_v1.module_extract_qald import extract
from src.sbgs_pipeline_v1.module_cbd_v2 import retrieve_cbd
from src.sbgs_pipeline_v1.model.gnn_retriever_infer import run_inference
# from model.gnn_retriever_infer import run_inference

CKPT_PATH = Path("src/sbgs_pipeline_v1/model/checkpoints/model_epoch10.pt")
CACHE_PATH_DEFAULT = Path("src/sbgs_pipeline_v1/cache/pred_triples.json")

# Map canonical language codes to acceptable variants
LANG_MAP: Dict[str, List[str]] = {
    "en": ["en", "EN", "eng", "english"],
    "de": ["de", "DE", "ger", "deu", "german", "deutsch"],
    "es": ["es", "ES", "spa", "spanish", "español"],
    "fr": ["fr", "FR", "fra", "fre", "french", "français"],
    "ru": ["ru", "RU", "rus", "russian"],
    "uk": ["uk", "UK", "ukr", "ukraine"],
    "lt": ["lt", "LT", "ltn", "latin"],
    "be": ["be", "BE", "blr", "belarusian"],
    "ba": ["ba", "BA", "bashkir"],
    "hy": []
}

MAX_WORKERS = 8 
_qid_re = re.compile(r"(?:^|/|wd:)([QP]\d+)$")

def _qid_of(val: Optional[str]) -> Optional[str]:
    if not isinstance(val, str):
        return None
    m = _qid_re.search(val.strip())
    return m.group(1) if m else None

def _as_entity_list(entity_dict: Dict[str, str]) -> List[Dict[str, str]]:
    # Convert {"label": "Q123"} or {"label": "http://.../Q123"} to [{"label": ..., "uri": "http://.../Q123"}]
    out: List[Dict[str, str]] = []
    for label, uri_or_id in (entity_dict or {}).items():
        qid = _qid_of(uri_or_id)
        if not qid:
            continue
        out.append({"label": label, "uri": f"http://www.wikidata.org/entity/{qid}"})
    return out

def _as_relation_list(relation_dict: Dict[str, str]) -> List[Dict[str, str]]:
    # Minimal pass-through to [{"label": ..., "uri": "Pxxx"}]; adjust if your inference expects full URIs
    out: List[Dict[str, str]] = []
    for label, pid_or_uri in (relation_dict or {}).items():
        pid = _qid_of(pid_or_uri)
        if not pid:
            continue
        out.append({"label": label, "uri": pid})
    return out


def load_cache(path: Path) -> Dict[str, List[Dict]]:
    if not path or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache: Dict[str, List[Dict]], path: Path):
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def prune_subgraph(
        question_text: str,
        entity_dict: Dict[str, str],
        relation_dict: Dict[str, str],
        *,
        hops: int = 1,
        keep_literals: bool = False,
        top_k: int = 20,
        threshold: Optional[float] = None,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        text_emb_dim: int = 384,
        node_feat_dim: int = 128,
        gnn_layers: int = 2,
    ) -> List[Dict[str, List[str]]]:

    entities = _as_entity_list(entity_dict)
    relations = _as_relation_list(relation_dict)

    qids = { _qid_of(e["uri"]) for e in entities if _qid_of(e.get("uri")) }
    cbd_all: List[Dict[str, List[str]]] = []

    triples = 0

    cache_path = CACHE_PATH_DEFAULT
    cache = load_cache(cache_path) if cache_path else {}    

    # Split questions into cached vs pending

    if isinstance(question_text, str) and question_text in cache:
        pruned = cache[question_text] if isinstance(cache[question_text], list) else []
        print(f"[cache-hit] Skipping question Q = {question_text[:80]}")
        return pruned

    else:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = { pool.submit(retrieve_cbd, qid, keep_literals=keep_literals, hops=hops): qid for qid in qids }
            for fut in as_completed(futures):
                qid = futures[fut]
                try:
                    cbd_list = fut.result()
                    triples += len(cbd_list or [])
                    if cbd_list:
                        cbd_all.extend(cbd_list)
                except Exception as e:
                    print(f"CBD retrieval failed for {qid}: {e}", file=sys.stderr)
                
        dur = time.perf_counter() - start
        print(f"{question_text}: triples={triples} done in {dur:.3f}s.")

        keyed = {
            question_text: {
                "CBD": cbd_all,
                "entities": entities,
                "relations": relations,
            }
        }

        try:
            pred_dict = run_inference(
                data_path=None,
                ckpt_path=str(CKPT_PATH),
                out_path=None,
                data_obj=keyed,
                model_name=model_name,
                text_emb_dim=text_emb_dim,
                node_feat_dim=node_feat_dim,
                gnn_layers=gnn_layers,
                top_k=top_k,
                threshold=threshold,
            )
            payload = pred_dict.get(question_text, {}) if isinstance(pred_dict, dict) else {}
            pruned = payload.get("predicted_triples", []) or []
            cache[question_text] = pruned
            save_cache(cache, cache_path)
            return pruned

        except Exception as e:
            print(f"Subgraph pruning failed for {question_text}: {e}", file=sys.stderr)
            return []


        
    


if __name__ == "__main__":
    prune_subgraph()