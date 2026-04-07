#!/usr/bin/env python3
"""
wikidata_graph_split.py — Single-threaded Wikidata graph splitter.
===================================================================
Splits a Wikidata RDF dump (N-Triples) into two subgraphs:
  - main.nt       (everything NOT a scholarly article)
  - scholarly.nt   (entities classified as scholarly articles)

Rules replicate the official WDQS graph split (v2):
  An entity is scholarly if it has:
    1. A non-deprecated P31 whose value is one of the 49 scholarly QIDs, OR
    2. A non-deprecated P13046 (publication type of scholarly work) statement.

Usage:
    python wikidata_graph_split.py latest-all.nt.gz
    python wikidata_graph_split.py latest-all.nt.gz --main out_main.nt --scholarly out_scholarly.nt
    python wikidata_graph_split.py latest-all.nt.gz --config wdqs-subgraph-definitions-v1.yaml

Requirements:
    pip install tqdm pyyaml
"""

import argparse
import gzip
import os
import re
import sys
import subprocess

try:
    from tqdm import tqdm
except ImportError:
    print(
        "WARNING: tqdm not installed — no progress bar. "
        "Install with: pip install tqdm",
        file=sys.stderr,
    )
    tqdm = None


# ── Default scholarly QIDs (from wdqs-subgraph-definitions-v2.yaml) ──

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

DEFAULT_USE_P13046 = True

# ── URI constants ──

WD_ENTITY_PREFIX = "http://www.wikidata.org/entity/"

WDT_P31    = "<http://www.wikidata.org/prop/direct/P31>"
PS_P31     = "<http://www.wikidata.org/prop/statement/P31>"
WDT_P13046 = "<http://www.wikidata.org/prop/direct/P13046>"
PS_P13046  = "<http://www.wikidata.org/prop/statement/P13046>"
RANK_PRED  = "<http://wikiba.se/ontology#rank>"
DEPRECATED = "<http://wikiba.se/ontology#DeprecatedRank>"


def load_config(yaml_path: str) -> tuple[set[str], bool]:
    """Load scholarly QIDs and rules from a wdqs-subgraph-definitions YAML."""
    try:
        import yaml
    except ImportError:
        print("ERROR: pyyaml required for --config. Install: pip install pyyaml",
              file=sys.stderr)
        sys.exit(1)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    qids = set()
    for entry in data.get("bindings", {}).get("scholarly_type", []):
        qid = entry.split(":")[-1] if ":" in entry else entry
        qids.add(qid)

    use_p13046 = False
    for sg in data.get("subgraphs", []):
        if sg.get("name") == "scholarly_articles":
            for rule in sg.get("rules", []):
                if "P13046" in rule:
                    use_p13046 = True
                    break

    return qids, use_p13046


def build_uri_set(qids: set[str]) -> set[str]:
    return {f"<{WD_ENTITY_PREFIX}{q}>" for q in qids}


def owning_entity(subject: str) -> str | None:
    """Return the owning QID from a subject URI."""
    if not subject.startswith(f"<{WD_ENTITY_PREFIX}"):
        return None
    rest = subject[len(f"<{WD_ENTITY_PREFIX}"):-1]
    m = re.match(r"(?:statement/)?(Q\d+)", rest)
    return m.group(1) if m else None


def make_classifier(scholarly_uris: set[str], use_p13046: bool):
    """Return an is_scholarly(triples) function closed over the config."""

    def is_scholarly(triples: list[str]) -> bool:
        deprecated_stmts: set[str] = set()
        for line in triples:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            if parts[1] == RANK_PRED and DEPRECATED in parts[2]:
                deprecated_stmts.add(parts[0])

        for line in triples:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            s, p, rest = parts

            if p == WDT_P31:
                obj = rest.strip().rstrip(".").strip()
                if obj in scholarly_uris:
                    return True
            elif p == PS_P31 and s not in deprecated_stmts:
                obj = rest.strip().rstrip(".").strip()
                if obj in scholarly_uris:
                    return True
            elif use_p13046 and p == WDT_P13046:
                return True
            elif use_p13046 and p == PS_P13046 and s not in deprecated_stmts:
                return True

        return False

    return is_scholarly


def estimate_uncompressed_size(path: str) -> int | None:
    try:
        disk_size = os.path.getsize(path)
    except OSError:
        return None
    if path.endswith(".gz"):
        return disk_size * 5
    elif path.endswith(".bz2"):
        return disk_size * 6
    elif path.endswith(".zst"):
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
    else:
        return disk_size


def split_dump(input_path: str, main_path: str, scholarly_path: str,
               is_scholarly) -> None:
    if input_path == "-":
        infile = sys.stdin.buffer
    elif input_path.endswith(".gz"):
        infile = gzip.open(input_path, "rb")
    elif input_path.endswith(".bz2"):
        import bz2
        infile = bz2.open(input_path, "rb")
    elif input_path.endswith(".zst"):
        infile = subprocess.Popen(
            ["zstd", "-d", "--stdout", "--no-progress", input_path],
            stdout=subprocess.PIPE,
        ).stdout
    else:
        infile = open(input_path, "rb")

    main_out = open(main_path, "wb")
    scholarly_out = open(scholarly_path, "wb")

    est_total = estimate_uncompressed_size(input_path) if input_path != "-" else None
    pbar = None
    if tqdm is not None:
        pbar = tqdm(
            total=est_total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Splitting",
            miniters=1,
            smoothing=0.05,
        )

    current_entity: str | None = None
    buffer: list[bytes] = []
    stats = {"main": 0, "scholarly": 0, "triples_main": 0, "triples_scholarly": 0}

    def flush():
        nonlocal current_entity, buffer
        if not buffer:
            return
        decoded = [line.decode("utf-8", errors="replace") for line in buffer]
        if is_scholarly(decoded):
            for line in buffer:
                scholarly_out.write(line)
            stats["scholarly"] += 1
            stats["triples_scholarly"] += len(buffer)
        else:
            for line in buffer:
                main_out.write(line)
            stats["main"] += 1
            stats["triples_main"] += len(buffer)
        buffer = []

    for raw_line in infile:
        if pbar is not None:
            pbar.update(len(raw_line))

        line_str = raw_line.decode("utf-8", errors="replace")
        stripped = line_str.strip()
        if not stripped or stripped.startswith("#"):
            continue

        parts = stripped.split(None, 1)
        if not parts:
            continue
        subject = parts[0]
        entity = owning_entity(subject)

        if entity is None:
            main_out.write(raw_line)
            scholarly_out.write(raw_line)
            continue

        if entity != current_entity:
            flush()
            current_entity = entity

            total_ent = stats["main"] + stats["scholarly"]
            if pbar is not None and total_ent % 100_000 == 0:
                pbar.set_postfix(
                    main=f"{stats['main']:,}",
                    scholarly=f"{stats['scholarly']:,}",
                    refresh=False,
                )

        buffer.append(raw_line)

    flush()

    if input_path != "-":
        infile.close()
    main_out.close()
    scholarly_out.close()

    if pbar is not None:
        pbar.set_postfix(
            main=f"{stats['main']:,}",
            scholarly=f"{stats['scholarly']:,}",
        )
        pbar.close()

    print("\n=== Wikidata Graph Split Complete ===", file=sys.stderr)
    print(f"  Main:      {stats['main']:>12,} entities, "
          f"{stats['triples_main']:>14,} triples  -> {main_path}", file=sys.stderr)
    print(f"  Scholarly:  {stats['scholarly']:>12,} entities, "
          f"{stats['triples_scholarly']:>14,} triples  -> {scholarly_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Split a Wikidata N-Triples dump into main and scholarly subgraphs."
    )
    parser.add_argument(
        "input",
        help="Path to the N-Triples dump (.nt, .nt.gz, .nt.bz2, .nt.zst) or '-' for stdin.",
    )
    parser.add_argument("--main", default="main.nt",
                        help="Output path for the main graph (default: main.nt)")
    parser.add_argument("--scholarly", default="scholarly.nt",
                        help="Output path for the scholarly graph (default: scholarly.nt)")
    parser.add_argument("--config",
                        help="Path to wdqs-subgraph-definitions YAML file. "
                             "If omitted, uses the built-in v2 defaults.")
    args = parser.parse_args()

    if args.config:
        qids, use_p13046 = load_config(args.config)
        print(f"Config: {args.config} ({len(qids)} QIDs, "
              f"P13046={'yes' if use_p13046 else 'no'})", file=sys.stderr)
    else:
        qids = DEFAULT_SCHOLARLY_QIDS
        use_p13046 = DEFAULT_USE_P13046
        print(f"Config: built-in v2 defaults ({len(qids)} QIDs, P13046=yes)",
              file=sys.stderr)

    scholarly_uris = build_uri_set(qids)
    is_scholarly = make_classifier(scholarly_uris, use_p13046)

    print(f"Splitting: {args.input}", file=sys.stderr)
    print(f"  -> main:      {args.main}", file=sys.stderr)
    print(f"  -> scholarly:  {args.scholarly}", file=sys.stderr)

    split_dump(args.input, args.main, args.scholarly, is_scholarly)


if __name__ == "__main__":
    main()
