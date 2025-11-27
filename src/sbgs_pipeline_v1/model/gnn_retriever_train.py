#!/usr/bin/env python3
"""
Train a GNN-based retriever that scores CBD edges for a question.
Input JSON format (per question):
{
  "Question text": {
    "entities": [{"uri":"Q123","label":"Foo"}, ...],
    "relations": [{"uri":"Pxxx","label":"..."}, ...],
    "sparql": "...",
    "triple_patterns": [...],
    "gold_triples": [
        {"s": ["Label","URI"], "p": ["Label","URI"], "o": ["Label","URI"]},
        ...
    ],
    "CBD": [
        {"s": ["Label","URI"], "p": ["Label","URI"], "o": ["Label","URI"]},
        ...
    ]
  }
}
This script:
 - builds per-question local graph from CBD (nodes = unique URIs in CBD; edges = CBD triples)
 - builds gold edge mask by matching gold_triples to CBD edges by URI
 - uses HF transformer to embed node labels and question
 - runs a small GAT stack and an MLP scoring head to score each edge
 - training uses margin ranking loss (push positives above negatives)
"""

import argparse
import json
import math
import os
import random
import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple
from contextlib import nullcontext

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "backend:native"
os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")

# PyG conv
try:
    from torch_geometric.nn import GATConv
except Exception as e:
    raise RuntimeError("torch_geometric (GATConv) not available. Install torch_geometric for this script.") from e

# Huggingface transformer
from transformers import AutoTokenizer, AutoModel

# -------- Config / defaults --------
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # small & fast; swap for multilingual (e.g., "xlm-roberta-base")
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
AMP_DTYPE = torch.bfloat16 if DEVICE.type == "cuda" else None


# ---------------------------
# Utility functions
# ---------------------------
def uri_to_qid(uri: str) -> str:
    """Extract QID/PID from a full URI or return unchanged if not recognized."""
    if not uri:
        return ""
    if "/" in uri:
        return uri.rstrip("/").split("/")[-1]
    return uri


def normalize_uri(uri: str) -> str:
    """Return canonical full URI (best-effort). If it's already a full URI, return it."""
    if not uri:
        return ""
    if uri.startswith("http"):
        return uri
    # support Qxxx or Pxxx
    if uri.startswith("Q") or uri.startswith("P"):
        if uri[0] == "Q":
            return f"http://www.wikidata.org/entity/{uri}"
        else:
            return f"http://www.wikidata.org/prop/direct/{uri}"
    return uri


# ---------------------------
# Dataset
# ---------------------------
class CBDJsonDataset(Dataset):
    """
    Wrap JSON file. Each item is one question with:
      - question_text: str
      - nodes: list of {"label":..., "uri":...}
      - edges: list of {"subj": idx, "obj": idx, "pred_uri":..., "pred_label":...}
      - pos_edge_mask: tensor[E] boolean marking gold edges
    """

    def __init__(self, json_path: str, tokenizer_name: str, max_node_tokens: int = 32):
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.questions = list(raw.keys())
        self.raw = raw
        self.tok_name = tokenizer_name
        self.tokenizer = AutoTokenizer.from_pretrained(self.tok_name)
        self.max_node_tokens = max_node_tokens

        # Build global relation vocabulary from CBD + gold (URI strings)
        rels = set()
        for q in self.questions:
            obj = raw[q]
            for t in obj.get("CBD", []):
                p_uri = t["p"][1] if isinstance(t.get("p"), list) and len(t["p"])>1 else t.get("p")
                rels.add(str(p_uri))
            for gt in obj.get("gold_triples", []):
                p_uri = gt["p"][1] if isinstance(gt.get("p"), list) and len(gt["p"])>1 else gt.get("p")
                rels.add(str(p_uri))
        self.rel2id = {r: i for i, r in enumerate(sorted(list(rels)))}
        self.id2rel = {i: r for r, i in self.rel2id.items()}

    def __len__(self):
        return len(self.questions)

    def _build_graph_from_cbd(self, cbd_list: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Build nodes (unique uris) and edges from the CBD triples list.
        node dict: {"label":..., "uri":...}
        edge dict: {"subj": idx, "obj": idx, "pred": pred_uri, "pred_label": pred_label}
        """
        uri_to_idx = {}
        nodes = []
        edges = []

        for t in cbd_list:
            # expected t["s"] = [label, uri], t["p"] = [label, uri], t["o"] = [label, uri]
            try:
                s_label, s_uri = t["s"]
                p_label, p_uri = t["p"]
                o_label, o_uri = t["o"]
            except Exception:
                # tolerate slightly different input shapes
                continue

            s_uri_norm = normalize_uri(s_uri)
            o_uri_norm = normalize_uri(o_uri)
            p_uri_norm = normalize_uri(p_uri)

            for uri, lab in ((s_uri_norm, s_label), (o_uri_norm, o_label)):
                if uri not in uri_to_idx:
                    uri_to_idx[uri] = len(nodes)
                    nodes.append({"label": lab if lab else uri.rsplit("/", 1)[-1], "uri": uri})

            s_idx = uri_to_idx[s_uri_norm]
            o_idx = uri_to_idx[o_uri_norm]
            edges.append({
                "subj": s_idx,
                "obj": o_idx,
                "pred": p_uri_norm,
                "pred_label": p_label if p_label else p_uri_norm.rsplit("/",1)[-1]
            })
        return nodes, edges

    def _build_gold_mask(self, edges: List[Dict], gold_triples: List[Dict]) -> torch.Tensor:
        """
        For each edge in edges, mark True if it matches any gold triple by URI.
        Matching: (s_uri, p_uri, o_uri)
        """
        gold_set = set()
        for gt in gold_triples:
            try:
                s_uri = normalize_uri(gt["s"][1])
                p_uri = normalize_uri(gt["p"][1])
                o_uri = normalize_uri(gt["o"][1])
                gold_set.add((s_uri, p_uri, o_uri))
            except Exception:
                continue

        mask = torch.zeros(len(edges), dtype=torch.bool)
        for i, e in enumerate(edges):
            s_uri = normalize_uri(e["subj_uri"]) if "subj_uri" in e else None
            # we stored subj_idx not uri; reconstruct below simpler
            # Instead compare via nodes list outside - but we don't have node uris here.
            # We'll change: in caller, after nodes built, populate subj_uri and obj_uri
            pass
        # we will set mask in __getitem__ where nodes exist; return placeholder here
        return mask

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        q = self.questions[idx]
        raw_item = self.raw[q]

        cbd_list = raw_item.get("CBD", [])
        gold_triples = raw_item.get("gold_triples", [])
        # Build nodes & edges
        nodes, edges = self._build_graph_from_cbd(cbd_list)

        # add subj_uri and obj_uri for easier matching
        for e in edges:
            e["subj_uri"] = nodes[e["subj"]]["uri"]
            e["obj_uri"] = nodes[e["obj"]]["uri"]

        # Build pos mask by exact URI match to gold triples
        gold_set = set()
        for gt in gold_triples:
            try:
                s_uri = normalize_uri(gt["s"][1])
                p_uri = normalize_uri(gt["p"][1])
                o_uri = normalize_uri(gt["o"][1])
                gold_set.add((s_uri, p_uri, o_uri))
            except Exception:
                continue

        pos_mask = torch.zeros(len(edges), dtype=torch.bool)
        for i, e in enumerate(edges):
            if (e["subj_uri"], normalize_uri(e["pred"]), e["obj_uri"]) in gold_set:
                pos_mask[i] = True

        # Edge relation ids
        rel_ids = []
        for e in edges:
            rel_ids.append(self.rel2id.get(str(e["pred"]), 0))
        rel_ids = torch.tensor(rel_ids, dtype=torch.long)

        # Text fields: node labels and question
        node_texts = [n["label"] for n in nodes] if nodes else []
        question_text = q

        # Tokenize node texts and question (we keep tokenized dicts)
        # Node tokenization: produce per-node tokens (we will flatten before encoder)
        if node_texts:
            node_tok = self.tokenizer(node_texts,
                                      padding=True,
                                      truncation=True,
                                      max_length=self.max_node_tokens,
                                      return_tensors="pt")
        else:
            # empty placeholders
            node_tok = {"input_ids": torch.empty((0,1), dtype=torch.long),
                        "attention_mask": torch.empty((0,1), dtype=torch.long)}

        q_tok = self.tokenizer(question_text, padding=True, truncation=True, return_tensors="pt")

        return {
            "question": q,
            "nodes": nodes,
            "edges": edges,
            "node_tok": node_tok,
            "q_tok": q_tok,
            "edge_rel_ids": rel_ids,
            "pos_mask": pos_mask,
        }


# ---------------------------
# Model
# ---------------------------
class TextEncoder(nn.Module):
    def __init__(self, model_name: str, out_dim: int = 384):
        super().__init__()
        self.model = AutoModel.from_pretrained(model_name)
        hidden_size = self.model.config.hidden_size
        self.out_dim = out_dim
        if hidden_size != out_dim:
            self.proj = nn.Linear(hidden_size, out_dim)
        else:
            self.proj = None

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        # input shape: (B, L)
        outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
        last = outputs.last_hidden_state  # (B, L, H)
        mask = attention_mask.unsqueeze(-1).float()
        summed = (last * mask).sum(dim=1)
        lengths = mask.sum(dim=1).clamp(min=1e-6)
        pooled = summed / lengths
        if self.proj:
            pooled = self.proj(pooled)
        return pooled  # (B, out_dim)


class GNNRetriever(nn.Module):
    def __init__(self, text_encoder: TextEncoder, node_feat_dim: int = 128, gnn_layers: int = 2, num_rels: int = 64, amp_dtype=None, encode_chunk_size: int = 256):
        super().__init__()
        self.text_encoder = text_encoder
        self.node_proj = nn.Linear(text_encoder.out_dim, node_feat_dim)
        self.gnn_layers = nn.ModuleList([GATConv(node_feat_dim, node_feat_dim, heads=2, concat=False) for _ in range(gnn_layers)])
        self.rel_emb = nn.Embedding(num_rels, node_feat_dim)
        # NEW: project question embedding into node feature space (early fusion)
        self.q_proj = nn.Linear(text_encoder.out_dim, node_feat_dim)
        self.dropout = nn.Dropout(p=0.1)

        # scoring MLP stays the same
        self.edge_mlp = nn.Sequential(
            nn.Linear(node_feat_dim * 3 + text_encoder.out_dim, 512),
            nn.ReLU(),
            nn.Linear(512, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )
        self.amp_dtype = amp_dtype 
        self.encode_chunk_size = encode_chunk_size

    def forward_graph(self, node_feats: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = node_feats
        for conv in self.gnn_layers:
            x = conv(x, edge_index)
            x = torch.relu(x)
        return x

    def score_edges(self, node_emb: torch.Tensor, edge_index: torch.Tensor, rel_ids: torch.Tensor, q_emb: torch.Tensor) -> torch.Tensor:
        # edge_index: [2, E]
        subj_idx = edge_index[0]
        obj_idx = edge_index[1]
        subj_emb = node_emb[subj_idx]
        obj_emb = node_emb[obj_idx]
        rel_emb = self.rel_emb(rel_ids.to(node_emb.device))
        # q_emb: [d_q]
        q_rep = q_emb.unsqueeze(0).repeat(subj_emb.size(0), 1)
        triple_feat = torch.cat([subj_emb, rel_emb, obj_emb, q_rep], dim=-1)
        scores = self.edge_mlp(triple_feat).squeeze(-1)
        return scores


    def forward(self, batch_item):
        device = next(self.parameters()).device
        node_tok = batch_item["node_tok"]
        if node_tok["input_ids"].numel() == 0 or len(batch_item["edges"]) == 0:
            return torch.tensor([], device=device), batch_item["pos_mask"].to(device)

        amp_ctx = torch.autocast(device_type='cuda', dtype=self.amp_dtype) if (self.amp_dtype and device.type == 'cuda') else nullcontext()
        enc_frozen = not any(p.requires_grad for p in self.text_encoder.parameters())
        grad_ctx = torch.no_grad() if enc_frozen else nullcontext()

        # 1) Encode question first
        q_ids = batch_item["q_tok"]["input_ids"].to(device, non_blocking=True)
        q_attn = batch_item["q_tok"]["attention_mask"].to(device, non_blocking=True)
        with grad_ctx:
            with amp_ctx:
                q_emb = self.text_encoder(q_ids.view(-1, q_ids.size(-1)),
                                        q_attn.view(-1, q_attn.size(-1))).squeeze(0)
        q_emb = q_emb.float()
        q_bias = self.q_proj(q_emb).unsqueeze(0)  # [1, d_node]

        # 2) Encode node texts in chunks
        input_ids = node_tok["input_ids"].to(device, non_blocking=True)
        attn = node_tok["attention_mask"].to(device, non_blocking=True)
        N = input_ids.size(0)
        C = max(1, self.encode_chunk_size)
        node_emb_chunks = []
        with grad_ctx:
            for i in range(0, N, C):
                ids_i = input_ids[i:i+C]
                attn_i = attn[i:i+C]
                with amp_ctx:
                    emb_i = self.text_encoder(ids_i, attn_i)
                node_emb_chunks.append(emb_i)
        node_embs = torch.cat(node_emb_chunks, dim=0).float()   # [N, text_dim]
        node_feats = self.node_proj(node_embs)                  # [N, d_node]
        node_feats = self.dropout(node_feats + q_bias.expand(N, -1))

        # 3) Graph tensors
        edge_index = torch.tensor([[e["subj"] for e in batch_item["edges"]],
                                [e["obj"] for e in batch_item["edges"]]],
                                dtype=torch.long, device=device)
        rel_ids = batch_item["edge_rel_ids"].to(device, non_blocking=True)

        # 4) GNN
        node_final = self.forward_graph(node_feats, edge_index)

        # 5) Score edges (use original q_emb too)
        scores = self.score_edges(
            node_final, edge_index,
            rel_ids if rel_ids.numel() > 0 else torch.zeros(edge_index.size(1), dtype=torch.long, device=device),
            q_emb
        )
        return scores, batch_item["pos_mask"].to(device, non_blocking=True)

 

@torch.no_grad()
def init_rel_from_text(dataset: CBDJsonDataset, model: GNNRetriever, tokenizer, device):
    model.eval()
    # Build a label for each relation id from CBD/gold (prefer human label, fallback to URI tail)
    id2label = {}
    for rid in range(len(dataset.rel2id)):
        id2label[rid] = None
    for q in dataset.questions:
        for t in dataset.raw[q].get("CBD", []):
            try:
                p_label, p_uri = t["p"]
            except Exception:
                continue
            rid = dataset.rel2id.get(normalize_uri(p_uri))
            if rid is not None and id2label[rid] is None and p_label:
                id2label[rid] = p_label
        for gt in dataset.raw[q].get("gold_triples", []):
            try:
                p_label, p_uri = gt["p"]
            except Exception:
                continue
            rid = dataset.rel2id.get(normalize_uri(p_uri))
            if rid is not None and id2label[rid] is None and p_label:
                id2label[rid] = p_label
    for rid in range(len(dataset.rel2id)):
        if id2label[rid] is None:
            uri = dataset.id2rel[rid]
            id2label[rid] = uri.rsplit("/", 1)[-1]

    texts = [id2label[i] for i in range(len(id2label))]
    tok = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
    tok = {k: v.to(device) for k, v in tok.items()}

    # Encode with the same text encoder; project to node_feat_dim
    out_chunks = []
    C = 256
    for i in range(0, len(texts), C):
        with torch.autocast(device_type='cuda', dtype=torch.bfloat16) if device.type == 'cuda' else nullcontext():
            emb = model.text_encoder(tok["input_ids"][i:i+C], tok["attention_mask"][i:i+C])
        out_chunks.append(emb.float())
    rel_text_emb = torch.cat(out_chunks, dim=0)                              # [R, text_dim]
    rel_node_emb = model.node_proj(rel_text_emb.to(next(model.parameters()).device))  # [R, node_dim]

    # Load into embedding (clip if mismatch)
    R = model.rel_emb.num_embeddings
    model.rel_emb.weight[:R].copy_(rel_node_emb[:R])

# ---------------------------
# Training utilities
# ---------------------------
def collate_list(batch):
    """We keep batch as a list of items; internal processing loops per-item."""
    return batch


def train_epoch(model: GNNRetriever, dataloader: DataLoader, optimizer, epoch: int, margin: float = 1.0):
    model.train()
    running = 0.0
    steps = 0
    pbar = tqdm(dataloader, desc=f"Train E{epoch}")
    criterion = nn.MarginRankingLoss(margin=margin)

    for batch in pbar:
        item_losses = []
        for item in batch:
            scores, pos_mask = model(item)
            if scores.numel() == 0:
                continue
            pos_idx = torch.where(pos_mask)[0]
            neg_mask = ~pos_mask
            if pos_idx.numel() == 0 or neg_mask.sum().item() == 0:
                continue

            # Hard negative pool: share subject or predicate with positives
            device = scores.device
            edges = item["edges"]
            subj = torch.tensor([e["subj"] for e in edges], device=device)
            rel_ids = item["edge_rel_ids"].to(device)

            hard_pool = torch.zeros_like(neg_mask)
            for pi in pos_idx.tolist():
                hard_pool |= ((subj == subj[pi]) | (rel_ids == rel_ids[pi])) & neg_mask

            # If hard pool too small, fall back to all negatives
            neg_pool = hard_pool if hard_pool.any() else neg_mask
            neg_indices = torch.where(neg_pool)[0]

            pos_scores = scores[pos_idx]
            # sample up to 5x negatives per positive
            mult = 5
            k = min(neg_indices.size(0), mult * pos_idx.size(0))
            if k == 0:
                continue
            sel = neg_indices[torch.randperm(neg_indices.size(0), device=device)[:k]]
            neg_sample = scores[sel]

            # repeat positives to match k
            pos_rep = pos_scores.repeat((k + pos_scores.size(0) - 1) // pos_scores.size(0))[:k]
            target = torch.ones_like(neg_sample)
            loss = criterion(pos_rep, neg_sample, target)
            item_losses.append(loss)

        if not item_losses:
            continue

        batch_loss = torch.stack(item_losses).mean()
        optimizer.zero_grad(set_to_none=True)
        batch_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        running += batch_loss.item()
        steps += 1
        pbar.set_postfix({"loss": running / steps if steps else 0.0})

    return running / max(1, steps)


def evaluate(model: GNNRetriever, dataloader: DataLoader, ks=(5, 20, 50)):
    model.eval()

    # For original hit-rate recall@k
    totals_hit = {k: 0 for k in ks}
    hits = {k: 0 for k in ks}

    # Macro accumulators (average per question with at least one positive)
    macro_p_sum = {k: 0.0 for k in ks}
    macro_r_sum = {k: 0.0 for k in ks}
    macro_f_sum = {k: 0.0 for k in ks}
    macro_count = {k: 0 for k in ks}  # count of questions with >=1 gold

    # Micro accumulators (pool across all questions)
    micro_tp = {k: 0 for k in ks}
    micro_pred = {k: 0 for k in ks}
    micro_pos = {k: 0 for k in ks}

    with torch.no_grad():
        for batch in dataloader:
            for item in batch:
                scores, pos_mask = model(item)
                if scores.numel() == 0:
                    continue

                E = scores.size(0)
                pos_total = int(pos_mask.sum().item())

                for k in ks:
                    kk = min(k, E)
                    topk_idx = torch.topk(scores, kk).indices

                    # Original hit-rate recall@k
                    totals_hit[k] += 1
                    hits[k] += int(pos_mask[topk_idx].any())

                    # TP for this question at k
                    tp = int(pos_mask[topk_idx].sum().item())
                    pred_k = kk

                    # Macro (only if there is at least one gold edge in CBD)
                    if pos_total > 0:
                        p_i = tp / pred_k if pred_k > 0 else 0.0
                        r_i = tp / pos_total if pos_total > 0 else 0.0
                        f_i = (2 * p_i * r_i / (p_i + r_i)) if (p_i + r_i) > 0 else 0.0

                        macro_p_sum[k] += p_i
                        macro_r_sum[k] += r_i
                        macro_f_sum[k] += f_i
                        macro_count[k] += 1

                    # Micro (pool across all questions)
                    micro_tp[k] += tp
                    micro_pred[k] += pred_k
                    micro_pos[k] += pos_total

    # Assemble metrics
    metrics = {}
    # Original recall@k (hit-rate)
    for k in ks:
        metrics[f"recall_at_{k}"] = hits[k] / max(1, totals_hit[k])

    # Macro averages
    for k in ks:
        cnt = max(1, macro_count[k])  # avoid div-by-zero
        metrics[f"macro_precision@{k}"] = macro_p_sum[k] / cnt
        metrics[f"macro_recall@{k}"] = macro_r_sum[k] / cnt
        # Compute macro F1 from averaged P and R (or average of per-question F1; here we used average of F1 above)
        metrics[f"macro_f1@{k}"] = macro_f_sum[k] / cnt

    # Micro averages
    for k in ks:
        p_den = max(1, micro_pred[k])
        r_den = max(1, micro_pos[k])
        p = micro_tp[k] / p_den
        r = micro_tp[k] / r_den
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        metrics[f"micro_precision@{k}"] = p
        metrics[f"micro_recall@{k}"] = r
        metrics[f"micro_f1@{k}"] = f1

    return metrics
# ---------------------------
# Main
# ---------------------------
def main(args):
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        # H100 speedups
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")

    print("Loading dataset...")
    dataset = CBDJsonDataset(args.data, args.model_name, max_node_tokens=args.max_node_tokens)

    # Split train/val
    n = len(dataset)
    idxs = list(range(n))
    random.shuffle(idxs)
    split = int((1 - args.val_ratio) * n)
    train_idx, val_idx = idxs[:split], idxs[split:]
    train_subset = torch.utils.data.Subset(dataset, train_idx)
    val_subset = torch.utils.data.Subset(dataset, val_idx)

    # DataLoaders
    train_loader = DataLoader(
        train_subset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_list,
        num_workers=0,
        pin_memory=(DEVICE.type == "cuda"),
    )
    val_loader = DataLoader(
        val_subset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate_list,
        num_workers=0,
        pin_memory=(DEVICE.type == "cuda"),
    )

    print("Creating model...")
    text_enc = TextEncoder(args.model_name, out_dim=args.text_emb_dim)

    for p in text_enc.parameters():
        p.requires_grad = False
    text_enc.model.eval() 
    
    model = GNNRetriever(
        text_enc,
        node_feat_dim=args.node_feat_dim,
        gnn_layers=args.gnn_layers,
        num_rels=len(dataset.rel2id),
        amp_dtype=(torch.bfloat16 if DEVICE.type == "cuda" else None),
        encode_chunk_size=args.encode_chunk_size,
    )

    # Move entire model to device (works with backend:native)
    model = model.to(DEVICE)

    # Initialize relation embeddings from text (once)
    tokenizer_for_init = dataset.tokenizer  # reuse the dataset tokenizer
    init_rel_from_text(dataset, model, tokenizer_for_init, DEVICE)

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=1e-3, weight_decay=1e-4
    )

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=2, verbose=True)

    # optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    os.makedirs(args.out_dir, exist_ok=True)
    best_val = -1.0

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss = train_epoch(model, train_loader, optimizer, epoch, margin=args.margin)
        val_metrics = evaluate(model, val_loader, ks=(5, 20, 50))
        t1 = time.time()
        print(f"Epoch {epoch} — train_loss={train_loss:.4f} — val={val_metrics} — time={(t1-t0):.1f}s")
        # Scheduler on your primary signal (recall@5)
        scheduler.step(val_metrics["recall_at_5"])
        # val_metrics = evaluate(model, val_loader, k=args.eval_k)
        # t1 = time.time()
        # print(f"Epoch {epoch} — train_loss={train_loss:.4f} — val={val_metrics} — time={(t1-t0):.1f}s")

        # Save checkpoint
        ckpt = os.path.join(args.out_dir, f"model_epoch{epoch}.pt")
        torch.save({
            "epoch": epoch,
            "model_state": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "rel2id": dataset.rel2id
        }, ckpt)
        print(f"Saved {ckpt}")

        metric = list(val_metrics.values())[0]
        if metric > best_val:
            best_val = metric
            torch.save(model.state_dict(), os.path.join(args.out_dir, "model_best.pt"))

    print("Training finished. Best val:", best_val)





if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train GNN Retriever on CBD->gold mapping")
    parser.add_argument("--data", required=True, help="Path to dataset json")
    parser.add_argument("--out_dir", default="./checkpoints", help="Checkpoint output dir")
    parser.add_argument("--model_name", default=DEFAULT_MODEL, help="HF model name")
    parser.add_argument("--node_feat_dim", type=int, default=128)
    parser.add_argument("--text_emb_dim", type=int, default=384)
    parser.add_argument("--gnn_layers", type=int, default=2)
    parser.add_argument("--batch_size", type=int, default=4, help="Number of questions processed per batch (each example processed internally)")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--margin", type=float, default=0.5)
    parser.add_argument("--eval_k", type=int, default=5)
    parser.add_argument("--val_ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max_node_tokens", type=int, default=32)
    parser.add_argument("--encode_chunk_size", type=int, default=256)
    args = parser.parse_args()
    main(args)
