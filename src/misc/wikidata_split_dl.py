"""
Wikidata Graph Splitter
=======================
Splits a Wikidata RDF dump (N-Triples format) into two subgraphs:
  - main.nt       (everything that is NOT a scholarly article)
  - scholarly.nt   (entities classified as scholarly articles)

The classification rules replicate the official WDQS graph split
(https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split/Rules):

An entity goes into the **scholarly** graph if it has:
  1. A non-deprecated P31 (instance of) whose value is one of the ~49 scholarly QIDs, OR
  2. A non-deprecated P13046 (publication type of scholarly work) statement.

Everything else goes into the **main** graph.

Usage
-----
  # From a gzipped N-Triples Wikidata dump:
  python wikidata_graph_split.py latest-all.nt.gz

  # Or from an uncompressed file / stdin:
  zcat latest-all.nt.gz | python wikidata_graph_split.py -

  # Custom output names:
  python wikidata_graph_split.py latest-all.nt.gz --main out_main.nt --scholarly out_scholarly.nt

Notes
-----
- Wikidata N-Triples dumps group all triples of an entity together.
  The script relies on this ordering: it buffers triples per entity,
  classifies the entity, then flushes the buffer to the right file.
- The script handles both the "truthy" (wdt:) and the full statement
  model (p:/ps:/pq:/pr:) triples.  Classification uses:
    * <http://www.wikidata.org/prop/direct/P31>       (truthy P31)
    * <http://www.wikidata.org/prop/statement/P31>     (full  P31)
    * <http://www.wikidata.org/prop/direct/P13046>     (truthy P13046)
    * <http://www.wikidata.org/prop/statement/P13046>  (full  P13046)
  and it checks for deprecated rank via
    <http://wikiba.se/ontology#rank> <http://wikiba.se/ontology#DeprecatedRank>
"""

import argparse
import gzip
import sys
import os
import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Scholarly QIDs — the 49 types used by the WDQS split (v2.yaml).
# Source: https://ceur-ws.org/Vol-4064/PD-paper3.pdf and the Wikidata Rules page.
# ---------------------------------------------------------------------------
SCHOLARLY_QIDS: set[str] = {
    # -- scholarly article (Q13442814) and its subclasses --
    "Q13442814",   # scholarly article
    "Q7318358",    # review article
    "Q1266946",    # thesis
    "Q187685",     # doctoral thesis
    "Q3331189",    # edition (as used for scholarly editions)
    "Q10870555",   # report
    "Q820655",     # statute
    "Q60797",      # sermon
    "Q35127",      # website
    "Q591041",     # scientific publication
    "Q58632367",   # conference paper
    "Q23927052",   # conference proceedings article
    "Q1348305",    # erratum
    "Q1385450",    # dissertation
    "Q58897583",   # comment (scholarly)
    "Q59387148",   # research report
    "Q1402850",    # field study report
    "Q54670950",   # conference poster
    "Q114613919",  # scientific note
    "Q112585758",  # Bachelor of Literature
    "Q82969330",   # medical scholarly article
    "Q70471362",   # non-randomized controlled trial report
    "Q91901000",   # multicenter study report
    "Q15706459",   # preprint
    "Q3099732",    # monograph (scholarly)
    "Q333291",     # abstract (scholarly)
    "Q55915575",   # scholarly review
    "Q7316896",    # research paper
    "Q47461344",   # written work (scholarly context)
    "Q4502142",    # visual artwork (scholarly context)
    # -- thesis (Q1266946) subclasses --
    "Q798134",     # doctoral dissertation
    "Q2994845",    # habilitation thesis
    "Q21481766",   # bachelor's thesis
    "Q1907875",    # master's thesis
    "Q108590845",  # Diplomarbeit
    "Q108471261",  # Magisterarbeit
    "Q110816155",  # Masterarbeit
    "Q109481039",  # HDR thesis
    "Q110393631",  # Habilitationsschrift variant
    "Q116904692",  # Kandidat nauk dissertation
    "Q116904694",  # Doktor nauk dissertation
    "Q105795032",  # licentiate thesis
    "Q109580988",  # state doctorate thesis
    "Q109529854",  # PhD thesis (specific)
    "Q109569745",  # DEA thesis
    "Q109569761",  # DESS thesis
    "Q109529870",  # MPhil thesis
    # -- other standalone types --
    "Q1233720",    # postdoctoral report / mémoire
    "Q30612",      # clinical trial (when also P31 scholarly article)
}

# URIs used to detect classification-relevant triples
WDT_P31 = "<http://www.wikidata.org/prop/direct/P31>"
PS_P31  = "<http://www.wikidata.org/prop/statement/P31>"
WDT_P13046 = "<http://www.wikidata.org/prop/direct/P13046>"
PS_P13046  = "<http://www.wikidata.org/prop/statement/P13046>"
P_P31   = "<http://www.wikidata.org/prop/P31>"
P_P13046 = "<http://www.wikidata.org/prop/P13046>"
RANK_PRED  = "<http://wikiba.se/ontology#rank>"
DEPRECATED = "<http://wikiba.se/ontology#DeprecatedRank>"

WD_ENTITY_PREFIX = "http://www.wikidata.org/entity/"
WD_STATEMENT_PREFIX = "http://www.wikidata.org/entity/statement/"

# Build the set of full URIs for fast lookup
SCHOLARLY_URIS: set[str] = {
    f"<{WD_ENTITY_PREFIX}{q}>" for q in SCHOLARLY_QIDS
}


def extract_entity_id(subject: str) -> str | None:
    """Return the Q-id (e.g. 'Q42') from a subject URI, or None."""
    if subject.startswith(f"<{WD_ENTITY_PREFIX}Q"):
        qid = subject[len(f"<{WD_ENTITY_PREFIX}"):-1]
        # Only bare entity URIs (Q…), not statement nodes
        if qid.startswith("Q") and "/" not in qid:
            return qid
    return None


def owning_entity(subject: str) -> str | None:
    """
    Given any subject URI from a Wikidata NT dump, return the 'owning'
    entity QID.  Wikidata triples are grouped by entity; auxiliary nodes
    (statements, references, values) belong to the entity whose Q-id
    appears first in the URI path.

    Examples:
      <…/entity/Q42>                       -> Q42
      <…/entity/statement/Q42-…>           -> Q42
      <…/entity/value/…>                   -> None  (shared, goes to both? — actually grouped with entity)
    """
    if not subject.startswith(f"<{WD_ENTITY_PREFIX}"):
        return None
    rest = subject[len(f"<{WD_ENTITY_PREFIX}"):-1]
    # Q42, Q42-xxxx (statement), statement/Q42-xxx
    m = re.match(r"(?:statement/)?(Q\d+)", rest)
    return m.group(1) if m else None


def is_scholarly_entity(triples: list[str]) -> bool:
    """
    Given all raw N-Triple lines belonging to one entity, decide whether
    the entity belongs to the scholarly graph.

    Rules (mirroring WDQS):
      - Has a non-deprecated P31 whose object is in SCHOLARLY_URIS, OR
      - Has a non-deprecated P13046 statement.
    """
    # Quick pass: collect statement node IDs that have deprecated rank
    deprecated_statements: set[str] = set()
    for line in triples:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        s, p, rest = parts
        if p == RANK_PRED and DEPRECATED in rest:
            deprecated_statements.add(s)

    # Now check P31 and P13046
    # For truthy (wdt:) triples, deprecated statements are already excluded
    # by Wikidata's export. But we also check the full model (ps:) and skip
    # those whose statement node is deprecated.

    # Collect statement nodes for P31 and P13046
    # <entity> p:P31 <statement-node>  — gives us the statement node
    p31_statement_nodes: set[str] = set()
    p13046_statement_nodes: set[str] = set()
    for line in triples:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        s, p, rest = parts
        if p == P_P31:
            obj = rest.strip().rstrip(".")
            p31_statement_nodes.add(obj.strip())
        elif p == P_P13046:
            obj = rest.strip().rstrip(".")
            p13046_statement_nodes.add(obj.strip())

    # Check 1: truthy P31 in scholarly set
    for line in triples:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        s, p, rest = parts
        if p == WDT_P31:
            obj = rest.strip().rstrip(".").strip()
            if obj in SCHOLARLY_URIS:
                return True

    # Check 2: full-model P31 (ps:P31) with non-deprecated statement
    for line in triples:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        s, p, rest = parts
        if p == PS_P31:
            if s not in deprecated_statements:
                obj = rest.strip().rstrip(".").strip()
                if obj in SCHOLARLY_URIS:
                    return True

    # Check 3: truthy P13046 exists
    for line in triples:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        s, p, rest = parts
        if p == WDT_P13046:
            return True

    # Check 4: full-model P13046 (ps:P13046) with non-deprecated statement
    for line in triples:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        s, p, rest = parts
        if p == PS_P13046:
            if s not in deprecated_statements:
                return True

    return False


def split_dump(input_path: str, main_path: str, scholarly_path: str) -> None:
    """Stream through an N-Triples dump and split it."""

    # Open input
    if input_path == "-":
        infile = sys.stdin.buffer
    elif input_path.endswith(".gz"):
        infile = gzip.open(input_path, "rb")
    elif input_path.endswith(".bz2"):
        import bz2
        infile = bz2.open(input_path, "rb")
    else:
        infile = open(input_path, "rb")

    main_out = open(main_path, "wb")
    scholarly_out = open(scholarly_path, "wb")

    current_entity: str | None = None
    buffer: list[bytes] = []
    stats = {"main": 0, "scholarly": 0, "triples_main": 0, "triples_scholarly": 0}

    def flush():
        nonlocal current_entity, buffer
        if not buffer:
            return
        decoded = [line.decode("utf-8", errors="replace") for line in buffer]
        if is_scholarly_entity(decoded):
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

    line_count = 0
    for raw_line in infile:
        line_count += 1
        if line_count % 10_000_000 == 0:
            total_ent = stats["main"] + stats["scholarly"]
            print(
                f"  [{line_count:>13,} lines] "
                f"entities: {total_ent:,}  "
                f"(main: {stats['main']:,}, scholarly: {stats['scholarly']:,})",
                file=sys.stderr,
            )

        line_str = raw_line.decode("utf-8", errors="replace")
        # Skip blank / comment lines
        stripped = line_str.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Determine owning entity of this triple
        parts = stripped.split(None, 1)
        if not parts:
            continue
        subject = parts[0]
        entity = owning_entity(subject)

        if entity is None:
            # Non-entity triple (schema:, owl:, etc.) — goes to both graphs
            main_out.write(raw_line)
            scholarly_out.write(raw_line)
            continue

        if entity != current_entity:
            flush()
            current_entity = entity

        buffer.append(raw_line)

    # Flush last entity
    flush()

    # Cleanup
    if input_path != "-":
        infile.close()
    main_out.close()
    scholarly_out.close()

    print("\n=== Wikidata Graph Split Complete ===", file=sys.stderr)
    print(f"  Main graph:      {stats['main']:>12,} entities, {stats['triples_main']:>14,} triples  -> {main_path}", file=sys.stderr)
    print(f"  Scholarly graph:  {stats['scholarly']:>12,} entities, {stats['triples_scholarly']:>14,} triples  -> {scholarly_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Split a Wikidata N-Triples dump into main and scholarly subgraphs."
    )
    parser.add_argument(
        "input",
        help="Path to the N-Triples dump (.nt, .nt.gz, .nt.bz2) or '-' for stdin.",
    )
    parser.add_argument(
        "--main", default="main.nt",
        help="Output path for the main graph (default: main.nt)",
    )
    parser.add_argument(
        "--scholarly", default="scholarly.nt",
        help="Output path for the scholarly graph (default: scholarly.nt)",
    )
    args = parser.parse_args()

    print(f"Splitting: {args.input}", file=sys.stderr)
    print(f"  -> main:      {args.main}", file=sys.stderr)
    print(f"  -> scholarly:  {args.scholarly}", file=sys.stderr)
    print(f"  Scholarly QIDs tracked: {len(SCHOLARLY_QIDS)}", file=sys.stderr)
    print(file=sys.stderr)

    split_dump(args.input, args.main, args.scholarly)


if __name__ == "__main__":
    main()