#!/usr/bin/env python3
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "backend:native"
os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")

import json
import tempfile
from typing import Dict, Any, List, Optional, Tuple
import torch
from tqdm import tqdm
from src.sbgs_pipeline_v1.model.gnn_retriever_train import CBDJsonDataset, TextEncoder, GNNRetriever, DEFAULT_MODEL

DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

def collate_list(batch):
    return batch

def _dataset_from_data_or_path(
    data_path: Optional[str],
    data_obj: Optional[Dict[str, Any]],
    model_name: str
):
    if data_obj is not None:
        # Prefer an in-memory constructor if your dataset provides it
        if hasattr(CBDJsonDataset, "from_data"):
            return CBDJsonDataset.from_data(data_obj, model_name), None  # no temp path
        # Fallback: spill to a temp file (kept minimal; auto-removed)
        tmp = tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False)
        json.dump(data_obj, tmp, ensure_ascii=False)
        tmp.flush()
        tmp_name = tmp.name
        tmp.close()
        ds = CBDJsonDataset(tmp_name, model_name)
        return ds, tmp_name
    else:
        return CBDJsonDataset(data_path, model_name), None

def load_model_and_dataset(
    data_path: Optional[str],
    ckpt_path: str,
    model_name: str,
    text_emb_dim: int,
    node_feat_dim: int,
    gnn_layers: int,
    data_obj: Optional[Dict[str, Any]] = None
) -> tuple:
    dataset, tmp_path = _dataset_from_data_or_path(data_path, data_obj, model_name)

    text_enc = TextEncoder(model_name, out_dim=text_emb_dim)
    for p in text_enc.parameters():
        p.requires_grad = False
    text_enc.model.eval()

    ckpt = torch.load(ckpt_path, map_location="cpu")
    rel2id_trained = ckpt.get("rel2id", None)
    if rel2id_trained is not None:
        dataset.rel2id = rel2id_trained
        dataset.id2rel = {i: r for r, i in dataset.rel2id.items()}

    model = GNNRetriever(
        text_enc,
        node_feat_dim=node_feat_dim,
        gnn_layers=gnn_layers,
        num_rels=len(dataset.rel2id),
        amp_dtype=(torch.bfloat16 if DEVICE.type == "cuda" else None),
        encode_chunk_size=256,
    )
    state = ckpt.get("model_state", ckpt)
    model.load_state_dict(state, strict=False)
    model.eval().to(DEVICE)
    return model, dataset, tmp_path

@torch.no_grad()
def score_item(model, item: Dict[str, Any]) -> torch.Tensor:
    scores, _ = model(item)
    return scores

def select_edges(scores: torch.Tensor, item: Dict[str, Any], top_k: int = None, threshold: float = None) -> List[int]:
    E = scores.numel()
    if E == 0:
        return []
    if threshold is not None:
        return (scores >= threshold).nonzero(as_tuple=True)[0].tolist()
    k = min(top_k or 0, E) if top_k else E
    return torch.topk(scores, k).indices.tolist()

def edges_to_triples(item: Dict[str, Any], edge_indices: List[int]) -> List[Dict[str, List[str]]]:
    triples = []
    nodes = item["nodes"]
    edges = item["edges"]
    for i in edge_indices:
        e = edges[i]
        s_label = nodes[e["subj"]]["label"]
        s_uri   = nodes[e["subj"]]["uri"]
        p_label = e.get("pred_label", "")
        p_uri   = e.get("pred", "")
        o_label = nodes[e["obj"]]["label"]
        o_uri   = nodes[e["obj"]]["uri"]
        triples.append({
            "s": [s_label, s_uri],
            "p": [p_label, p_uri],
            "o": [o_label, o_uri],
        })
    return triples

def run_inference(
    data_path: Optional[str],
    ckpt_path: str,
    out_path: Optional[str] = None,
    *,
    data_obj: Optional[Dict[str, Any]] = None,  # NEW: in-memory keyed dict {question: {...}}
    model_name: str = DEFAULT_MODEL,
    text_emb_dim: int = 384,
    node_feat_dim: int = 128,
    gnn_layers: int = 2,
    top_k: int = 20,
    threshold: float = None
) -> Dict[str, Any]:
    model, dataset, tmp_path = load_model_and_dataset(
        data_path=data_path,
        data_obj=data_obj,
        ckpt_path=ckpt_path,
        model_name=model_name,
        text_emb_dim=text_emb_dim,
        node_feat_dim=node_feat_dim,
        gnn_layers=gnn_layers,
    )

    # Use provided in-memory data or load from file once
    if data_obj is None:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = data_obj

    for i in tqdm(range(len(dataset)), desc="Predicting"):
        q = dataset.questions[i]      # question text key
        item = dataset[i]
        scores = score_item(model, item)
        sel_idx = select_edges(scores, item, top_k=top_k, threshold=threshold)
        preds = edges_to_triples(item, sel_idx)
        data[q]["predicted_triples"] = preds

    # Optional write
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Cleanup temp spill if used
    if tmp_path:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return data

if __name__ == "__main__":
    import argparse, os
    ap = argparse.ArgumentParser(description="Score CBD edges with a trained GNN and write predicted triples")
    ap.add_argument("--data", required=True, help="Input JSON (questions -> {CBD, ...})")
    ap.add_argument("--ckpt", required=True, help="Path to model_best.pt or model_epochN.pt")
    ap.add_argument("--out", required=True, help="Output JSON with predicted_triples added")
    ap.add_argument("--model_name", default=DEFAULT_MODEL)
    ap.add_argument("--text_emb_dim", type=int, default=384)
    ap.add_argument("--node_feat_dim", type=int, default=128)
    ap.add_argument("--gnn_layers", type=int, default=2)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--top_k", type=int, default=20)
    group.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args()

    _ = run_inference(
        data_path=args.data,
        ckpt_path=args.ckpt,
        out_path=args.out,
        data_obj=None,  # CLI path uses file
        model_name=args.model_name,
        text_emb_dim=args.text_emb_dim,
        node_feat_dim=args.node_feat_dim,
        gnn_layers=args.gnn_layers,
        top_k=args.top_k,
        threshold=args.threshold,
    )