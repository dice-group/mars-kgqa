# Wikidata Preparation Scripts

This directory contains scripts for downloading the latest Wikidata dump and extracting the **main** graph split, as defined by the [Wikidata SPARQL query service graph split](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split).

## Background

Since May 2025, Wikidata's query graph is split into two distinct graphs:

- **Main graph** — all entities except scholarly articles (served at `query.wikidata.org`)
- **Scholarly graph** — entities classified as scholarly articles via `P31` or `P13046` (served at `query-scholarly.wikidata.org`)

MARS uses the **main** split. The scripts below reproduce the same split logic from a raw Wikidata NT dump.

## Quick Start

The pipeline runs in three phases, designed for a SLURM cluster:

### Phase 1 — Download and Pre-split

Download the latest Wikidata NT dump and split it into fixed-size chunks (respecting entity boundaries):

```bash
# Download the dump
sbatch download_latest_wikidata.sh

# Pre-split into chunks
./1_submit_presplit.sh <latest-all.nt.gz> <output_dir> [chunk_size_gb]
```

Example:
```bash
./1_submit_presplit.sh /data/wikidata/latest-all.nt.gz /scratch/wd_split 10
```

This produces `chunk_XXXXX.nt.zst` files in `<output_dir>/chunks/`.

### Phase 2 — Classify Entities

Run a SLURM array job that classifies each entity as either **main** or **scholarly**, based on the official WDQS split rules (v2):

```bash
./2_submit_split.sh <output_dir>
```

This produces `main_XXXX.nt.zst` and `scholarly_XXXX.nt.zst` files in `<output_dir>/split_out/`.

### Phase 3 — Merge

Concatenate all partial files into the final compressed outputs:

```bash
./3_submit_merge.sh <output_dir>
```

This produces:
- `<output_dir>/main.nt.zst` — the main graph split
- `<output_dir>/scholarly.nt.zst` — the scholarly graph split

## Splitting Logic

The classifier (`wikidata_split_worker.py`) follows the official WDQS v2 rules:

An entity goes to the **scholarly** graph if it has a non-deprecated statement of:
- `P31` (instance of) pointing to one of 49 scholarly article types (e.g., `Q13442814` scholarly article, `Q187685` doctoral thesis, etc.)
- `P13046` (publication type of scholarly work)

All remaining entities go to the **main** graph.

The default configuration is built-in. You can also pass a custom `wdqs-subgraph-definitions` YAML file via `--config`.

## Loading Into Tentris

Once you have `main.nt.zst`, you can load it into a Tentris SPARQL endpoint. See the scripts and configuration in [`tentris/`](tentris/) for a reference loading workflow.

## Files

| File | Description |
|------|-------------|
| `download_latest_wikidata.sh` | SLURM script to download the latest Wikidata NT dump with retry logic |
| `wikidata_presplit.py` | Phase 1: splits a large `.nt.gz` into fixed-size chunks at entity boundaries |
| `wikidata_split_worker.py` | Phase 2: classifies each entity as main or scholarly |
| `1_submit_presplit.sh` | SLURM wrapper for Phase 1 |
| `2_submit_split.sh` | SLURM wrapper for Phase 2 (array job) |
| `3_submit_merge.sh` | SLURM wrapper for Phase 3 (merge) |
| `tentris/` | Tentris server config and loading scripts |
