#!/usr/bin/env python3
"""
wikidata_split_worker.py — Phase 2: Process a single chunk file.
Called by the SLURM array job.  Takes one chunk, produces two output files:
   <outdir>/main_XXXX.nt.zst
   <outdir>/scholarly_XXXX.nt.zst

Usage:
    python wikidata_split_worker.py chunks/chunk_0042.nt.zst --outdir split_out/

    # Use a custom YAML config (e.g. v1 rules without P13046):
    python wikidata_split_worker.py chunks/chunk_0042.nt.zst --outdir split_out/ \
        --config wdqs-subgraph-definitions-v1.yaml

Or via SLURM array:
    SLURM_ARRAY_TASK_ID=42 python wikidata_split_worker.py \
        --chunk-dir chunks/ --outdir split_out/

Requirements:
    pip install tqdm pyyaml
"""

import argparse
import os
import re
import subprocess
import sys

try:
    from tqdm import tqdm
except ImportError:
    print(
        "WARNING: tqdm not installed — no progress bar. "
        "Install with: pip install tqdm",
        file=sys.stderr,
    )
    tqdm = None


# ── Default scholarly QIDs ──
# Taken verbatim from wdqs-subgraph-definitions-v2.yaml in the
# wikidata/query/rdf Gerrit repository (tools/src/main/resources/).

DEFAULT_SCHOLARLY_QIDS: set[str] = {
    "Q13442814",   # scholarly article
    "Q7318358",    # review article
    "Q2782326",    # scientific journal article
    "Q815382",     # meta-analysis
    "Q1348305",    # erratum
    "Q187685",     # doctoral thesis
    "Q1907875",    # master's thesis
    "Q18918145",   # academic journal article
    "Q1266946",    # thesis
    "Q23927052",   # conference proceedings article
    "Q1504425",    # scientific manuscript
    "Q45182324",   # retraction notice
    "Q1402850",    # field study report
    "Q7316896",    # research paper
    "Q580922",     # research article
    "Q30749496",   # clinical trial report
    "Q111475835",  # original article
    "Q92998777",   # editorial note
    "Q114613919",  # scientific note
    "Q798134",     # doctoral dissertation
    "Q1385450",    # dissertation
    "Q10885494",   # scientific conference paper
    "Q51282918",   # research letter
    "Q51282711",   # short communication
    "Q111475860",  # brief communication
    "Q51283092",   # discussion paper
    "Q15706459",   # preprint
    "Q59387148",   # research report
    "Q110716513",  # correction notice
    "Q58897583",   # comment (scholarly)
    "Q51283145",   # case study
    "Q54670950",   # conference poster
    "Q91901000",   # multicenter study report
    "Q111476177",  # correspondence (scholarly)
    "Q51283053",   # brief report
    "Q1414362",    # computer science paper
    "Q51283181",   # rapid communication
    "Q51282999",   # technical note
    "Q51283199",   # preliminary communication
    "Q82969330",   # medical scholarly article
    "Q112585758",  # Bachelor of Literature
    "Q118114827",  # essay in a collection
    "Q106276531",  # scientific preprint
    "Q1884156",    # working paper
    "Q51283362",   # methodological paper
    "Q46629343",   # clinical case report
    "Q100328456",  # registered report
    "Q51283219",   # full paper
    "Q70471362",   # non-randomized controlled trial report
}

# ── Whether P13046 rule is active (v2 = yes, v1 = no) ──
DEFAULT_USE_P13046 = True

WD_ENTITY_PREFIX = b"<http://www.wikidata.org/entity/"

WDT_P31_B     = b"<http://www.wikidata.org/prop/direct/P31>"
PS_P31_B      = b"<http://www.wikidata.org/prop/statement/P31>"
WDT_P13046_B  = b"<http://www.wikidata.org/prop/direct/P13046>"
PS_P13046_B   = b"<http://www.wikidata.org/prop/statement/P13046>"
RANK_PRED_B   = b"<http://wikiba.se/ontology#rank>"
DEPRECATED_B  = b"<http://wikiba.se/ontology#DeprecatedRank>"

# ── Regex to match Q, P, and L entity IDs ──
# Matches the entity ID portion after the Wikidata entity prefix.
# Handles direct entity URIs and statement URIs.
_ENTITY_ID_RE = re.compile(rb"^([QPL]\d+)")


def load_config(yaml_path: str) -> tuple[set[str], bool]:
    """
    Load scholarly QIDs and rules from a wdqs-subgraph-definitions YAML file.
    Returns (scholarly_qids, use_p13046).
    """
    try:
        import yaml
    except ImportError:
        print(
            "ERROR: pyyaml is required for --config. "
            "Install with: pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    qids = set()
    for entry in data.get("bindings", {}).get("scholarly_type", []):
        # "wd:Q13442814" → "Q13442814"
        qid = entry.split(":")[-1] if ":" in entry else entry
        qids.add(qid)

    # Detect whether the scholarly_articles subgraph uses P13046
    use_p13046 = False
    for sg in data.get("subgraphs", []):
        if sg.get("name") == "scholarly_articles":
            for rule in sg.get("rules", []):
                if "P13046" in rule:
                    use_p13046 = True
                    break

    return qids, use_p13046


def build_uri_set(qids: set[str]) -> set[bytes]:
    return {f"<http://www.wikidata.org/entity/{q}>".encode() for q in qids}


def owning_entity_bytes(line: bytes) -> bytes | None:
    """
    Extract the owning entity ID (Q/P/L) from a subject URI.

    Handles:
      <http://www.wikidata.org/entity/Q123>          → Q123
      <http://www.wikidata.org/entity/statement/Q123-...> → Q123
      <http://www.wikidata.org/entity/P31>            → P31
      <http://www.wikidata.org/entity/L123>           → L123

    Returns None for non-entity subjects (values, references, ontology, etc).
    """
    if not line.startswith(WD_ENTITY_PREFIX):
        return None
    rest = line[len(WD_ENTITY_PREFIX):]
    # Strip the statement/ prefix to get to the entity ID
    if rest.startswith(b"statement/"):
        rest = rest[10:]
    m = _ENTITY_ID_RE.match(rest)
    return m.group(1) if m else None


def make_classifier(scholarly_uris: set[bytes], use_p13046: bool):
    """Return an is_scholarly(triples) function closed over the config."""

    def is_scholarly_fast(triples: list[bytes]) -> bool:
        # Pass 1: collect deprecated statement subjects using field-based parsing
        deprecated: set[bytes] = set()
        for line in triples:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            s, p, rest = parts
            if p == RANK_PRED_B and rest.rstrip().rstrip(b".").strip() == DEPRECATED_B:
                deprecated.add(s)

        # Pass 2: check classification predicates
        for line in triples:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            s, p, rest = parts

            # Truthy P31
            if p == WDT_P31_B:
                obj = rest.rstrip().rstrip(b".").strip()
                if obj in scholarly_uris:
                    return True

            # Full-model P31 (non-deprecated)
            elif p == PS_P31_B and s not in deprecated:
                obj = rest.rstrip().rstrip(b".").strip()
                if obj in scholarly_uris:
                    return True

            # P13046 rules (v2 only)
            elif use_p13046 and p == WDT_P13046_B:
                return True
            elif use_p13046 and p == PS_P13046_B and s not in deprecated:
                return True

        return False

    return is_scholarly_fast


def estimate_chunk_size(path: str) -> int | None:
    try:
        disk_size = os.path.getsize(path)
    except OSError:
        return None

    if path.endswith(".zst"):
        try:
            r = subprocess.run(
                ["zstd", "-l", "--no-progress", path],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0].endswith(".zst"):
                    return int(parts[2])
        except Exception:
            pass
        return disk_size * 3
    elif path.endswith(".gz"):
        return disk_size * 5
    else:
        return disk_size


def open_zstd_writer(path: str):
    proc = subprocess.Popen(
        ["zstd", "-T0", "-3", "--no-progress", "-o", path],
        stdin=subprocess.PIPE,
    )
    return proc.stdin, proc


def open_reader(path: str):
    if path.endswith(".zst"):
        proc = subprocess.Popen(
            ["zstd", "-d", "--stdout", "--no-progress", path],
            stdout=subprocess.PIPE,
        )
        return proc.stdout, proc
    elif path.endswith(".gz"):
        import gzip
        return gzip.open(path, "rb"), None
    else:
        return open(path, "rb"), None


def process_chunk(chunk_path: str, outdir: str, is_scholarly):
    os.makedirs(outdir, exist_ok=True)

    basename = os.path.basename(chunk_path)
    idx = basename.split("_")[1].split(".")[0]

    main_path = os.path.join(outdir, f"main_{idx}.nt.zst")
    scholarly_path = os.path.join(outdir, f"scholarly_{idx}.nt.zst")

    infile, in_proc = open_reader(chunk_path)
    main_out, main_proc = open_zstd_writer(main_path)
    sch_out, sch_proc = open_zstd_writer(scholarly_path)

    current_entity: bytes | None = None
    buffer: list[bytes] = []
    stats = {"main": 0, "scholarly": 0, "triples": 0, "shared": 0}

    # ── Progress bar ──
    est_total = estimate_chunk_size(chunk_path)
    pbar = None
    if tqdm is not None:
        pbar = tqdm(
            total=est_total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"Chunk {idx}",
            miniters=1,
            smoothing=0.05,
        )

    def flush():
        if not buffer:
            return
        if is_scholarly(buffer):
            for line in buffer:
                sch_out.write(line)
            stats["scholarly"] += 1
        else:
            for line in buffer:
                main_out.write(line)
            stats["main"] += 1
        stats["triples"] += len(buffer)
        buffer.clear()

    for raw_line in infile:
        if pbar is not None:
            pbar.update(len(raw_line))

        stripped = raw_line.strip()
        if not stripped or stripped.startswith(b"#"):
            continue

        entity = owning_entity_bytes(stripped)

        if entity is None:
            if current_entity is not None:
                # Still part of the current entity (sitelinks, EntityData metadata)
                buffer.append(raw_line)
            else:
                # Preamble before any entity (ontology/dump header) — shared
                main_out.write(raw_line)
                sch_out.write(raw_line)
                stats["triples"] += 1
                stats["shared"] += 1
            continue

        if entity != current_entity:
            flush()
            current_entity = entity

            if pbar is not None and (stats["main"] + stats["scholarly"]) % 50_000 == 0:
                pbar.set_postfix(
                    main=f"{stats['main']:,}",
                    scholarly=f"{stats['scholarly']:,}",
                    refresh=False,
                )

        buffer.append(raw_line)

    flush()

    main_out.close()
    sch_out.close()
    if main_proc:
        main_proc.wait()
    if sch_proc:
        sch_proc.wait()
    if in_proc:
        in_proc.wait()
    infile.close()

    if pbar is not None:
        pbar.set_postfix(
            main=f"{stats['main']:,}",
            scholarly=f"{stats['scholarly']:,}",
        )
        pbar.close()

    print(
        f"Chunk {idx}: {stats['triples']:,} triples, "
        f"{stats['main']:,} main entities, "
        f"{stats['scholarly']:,} scholarly entities, "
        f"{stats['shared']:,} shared triples (duplicated to both)",
        file=sys.stderr,
    )


def main():
    p = argparse.ArgumentParser(description="Process one chunk of the Wikidata split.")
    p.add_argument("chunk", nargs="?", help="Path to a single chunk file")
    p.add_argument("--chunk-dir",
                    help="Directory of chunks (used with SLURM_ARRAY_TASK_ID)")
    p.add_argument("--outdir", default="split_out",
                    help="Output directory (default: split_out/)")
    p.add_argument("--config",
                    help="Path to wdqs-subgraph-definitions YAML file. "
                         "If omitted, uses the built-in v2 defaults (49 QIDs + P13046).")
    args = p.parse_args()

    # ── Load config ──
    if args.config:
        qids, use_p13046 = load_config(args.config)
        print(f"Config: {args.config} ({len(qids)} QIDs, P13046={'yes' if use_p13046 else 'no'})",
              file=sys.stderr)
    else:
        qids = DEFAULT_SCHOLARLY_QIDS
        use_p13046 = DEFAULT_USE_P13046
        print(f"Config: built-in v2 defaults ({len(qids)} QIDs, P13046=yes)",
              file=sys.stderr)

    scholarly_uris = build_uri_set(qids)
    is_scholarly = make_classifier(scholarly_uris, use_p13046)

    # ── Resolve chunk path ──
    if args.chunk:
        chunk_path = args.chunk
    elif args.chunk_dir:
        task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
        chunks = sorted(
            f for f in os.listdir(args.chunk_dir) if f.startswith("chunk_")
        )
        chunk_path = os.path.join(args.chunk_dir, chunks[task_id])
    else:
        p.error("Provide either a chunk path or --chunk-dir with SLURM_ARRAY_TASK_ID")

    print(f"Processing: {chunk_path}", file=sys.stderr)
    process_chunk(chunk_path, args.outdir, is_scholarly)


if __name__ == "__main__":
    main()