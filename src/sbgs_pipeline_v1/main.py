# main.py
#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from module_extract_qald import extract
from module_cbd_v2 import retrieve_cbd
from model.gnn_retriever_infer import run_inference
# from model.gnn_retriever_infer import run_inference

CKPT_PATH = Path("model/checkpoints/model_epoch10.pt")
CACHE_PATH_DEFAULT = Path("cache/pred_triples.json")

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

def main():
    parser = argparse.ArgumentParser(description="Extract minimal QALD-like data for a specific language.")
    parser.add_argument("--input", help="Path to input JSON file")
    parser.add_argument("--lang", default="en", help="Language (e.g., en, EN, eng, english). Defaults to en")
    parser.add_argument("--out", help="Optional path to write the extracted JSON. Prints to stdout if omitted.")
    parser.add_argument("--hops", type=int, default=1, help="CBD hops (default: 1)")
    # Inference step (optional)
    # parser.add_argument("--infer", action="store_true", help="Run GNN inference to predict/prune triples")
    parser.add_argument("--ckpt", help="Path to trained checkpoint (required if --infer)")
    # parser.add_argument("--pred_out", help="Output JSON path for predictions (default: <out> with _pred suffix)")
    parser.add_argument("--model_name", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--text_emb_dim", type=int, default=384)
    parser.add_argument("--node_feat_dim", type=int, default=128)
    parser.add_argument("--gnn_layers", type=int, default=2)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--top_k", type=int, default=20, help="Keep top-k edges")
    group.add_argument("--threshold", type=float, default=None, help="Keep edges with score >= threshold")
    args = parser.parse_args()

    total_start = time.perf_counter()

    lang = next((k for k, vals in LANG_MAP.items() if args.lang.strip().lower() in set(map(str.lower, vals + [k]))), "en")

    in_path = Path(args.input)
    with in_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    result = extract(data, lang)
    count = 0

    cache_path = CACHE_PATH_DEFAULT
    cache = load_cache(cache_path) if cache_path else {}    

    # Split questions into cached vs pending
    pending = []
    cached_used = 0
    for q in result["questions"]:
        q_text = q.get("question")
        if isinstance(q_text, str) and q_text in cache:
            q["predicted_triples"] = cache[q_text]
            print(f"[cache-hit] Skipping question Q = {q_text[:80]}")
            cached_used += 1
        else:
            pending.append(q)

    if cached_used:
        print(f"Cache hits: {cached_used} | Pending: {len(pending)}")

    # CBD retrieval only for pending questions
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for question in pending:
            start = time.perf_counter()
            entities = question.get("entities") or []
            # dedupe and normalize to Q/P ids
            qids = { e.get("uri") for e in entities if e.get("uri") }

            futures = { pool.submit(retrieve_cbd, qid): qid for qid in qids }
            cbd_all = []
            triples = 0
            for fut in as_completed(futures):
                qid = futures[fut]
                try:
                    cbd_list = fut.result()
                    triples += len(cbd_list or [])
                    if cbd_list:
                        cbd_all.extend(cbd_list)
                except Exception as e:
                    print(f"CBD retrieval failed for {qid}: {e}", file=sys.stderr)

            if cbd_all:
                question["CBD"] = cbd_all
                count += 1
                dur = time.perf_counter() - start
                print(f"{count} of {len(result['questions'])}, triples={triples} done in {dur:.3f}s.")
            
            prediction_start = time.perf_counter()
            keyed = {}
            idx_by_qtxt = {}
            for i, q in enumerate(result["questions"]):
                q_text = q.get("question")  # your extract() should set this to a string
                if q in pending and isinstance(q_text, str) and q_text.strip():
                    keyed[q_text] = {
                        "CBD": q.get("CBD", []),
                        "entities": q.get("entities", []),
                        "relations": q.get("relations", []),
                    }
                    idx_by_qtxt[q_text] = i

            if keyed:
                pred_dict = run_inference(
                    data_path=None,
                    ckpt_path=str(CKPT_PATH),
                    out_path=None,              
                    data_obj=keyed,             
                    model_name=args.model_name,
                    text_emb_dim=args.text_emb_dim,
                    node_feat_dim=args.node_feat_dim,
                    gnn_layers=args.gnn_layers,
                    top_k=args.top_k,
                    threshold=args.threshold,
                )
                # Merge predicted_triples back into result
                merged = 0
                for q_text, payload in pred_dict.items():
                    i = idx_by_qtxt.get(q_text)
                    if i is None:
                        continue
                    preds = payload.get("predicted_triples")
                    if preds is not None:
                        result["questions"][i]["predicted_triples"] = preds
                        cache[q_text] = preds
                        merged += 1
                dur = time.perf_counter() - prediction_start
                print(f"Pruned subgraphs attached for {merged} questions in {dur:.3f}s.")
                if cache_path:
                    save_cache(cache, cache_path)
    total_dur = time.perf_counter() - total_start
    print(f"All questions processed in {total_dur:.3f}s ({total_dur/60:.2f}m/{total_dur/3600:.2f}h).")
            


    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Wrote {len(result['questions'])} items to {out_path}")
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()  # newline


if __name__ == "__main__":
    main()