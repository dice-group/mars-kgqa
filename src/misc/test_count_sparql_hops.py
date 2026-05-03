#!/usr/bin/env python
"""Test count_sparql_hops on real dataset queries."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rdflib import Graph, URIRef, Variable
from rdflib.plugins.sparql.processor import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.sparql import Prologue, NamespaceManager

from src.util.common import count_sparql_hops

# --- SPARQL prefix map ---
PREFIX_MAP = {
    "http://www.wikidata.org/prop/direct/": "wdt:",
    "http://www.wikidata.org/entity/": "wd:",
    "http://www.wikidata.org/prop/": "p:",
    "http://www.wikidata.org/prop/statement/": "ps:",
    "http://www.wikidata.org/prop/statement/value/": "psn:",
    "http://www.wikidata.org/prop/statement/value-normalized/": "psv:",
    "http://www.wikidata.org/prop/qualifier/": "pq:",
    "http://www.wikidata.org/prop/qualifier/value/": "pqv:",
    "http://www.wikidata.org/prop/qualifier/value-normalized/": "pqn:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://schema.org/": "schema:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
}

PREFIX_DECL = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX psn: <http://www.wikidata.org/prop/statement/value/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value-normalized/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
PREFIX pqn: <http://www.wikidata.org/prop/qualifier/value-normalized/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


def uri_to_prefixed(uri_str):
    """Convert a full URI to a prefixed form like wd:Q5."""
    for ns, pfx in PREFIX_MAP.items():
        if uri_str.startswith(ns):
            return pfx + uri_str[len(ns):]
    return uri_str


def extract_triples_from_algebra(alg_dict):
    """Recursively extract triple patterns from the SPARQL algebra dict."""
    triples = []
    if isinstance(alg_dict, dict):
        if "triples" in alg_dict:
            for t in alg_dict["triples"]:
                s = t[0]
                p = t[1]
                o = t[2]
                # Convert Variable objects to ?var strings
                if isinstance(s, Variable):
                    s = "?" + str(s)
                elif isinstance(s, str) and s.startswith("http"):
                    s = uri_to_prefixed(s)
                if isinstance(o, Variable):
                    o = "?" + str(o)
                elif isinstance(o, str) and o.startswith("http"):
                    o = uri_to_prefixed(o)
                triples.append({"s": s, "p": p, "o": o})
        # Recurse into nested structures
        for v in alg_dict.values():
            triples.extend(extract_triples_from_algebra(v))
    elif isinstance(alg_dict, list):
        for item in alg_dict:
            triples.extend(extract_triples_from_algebra(item))
    return triples


def extract_patterns(sparql_str):
    """Parse SPARQL and extract triple patterns as dicts with 's' and 'o' keys."""
    full_query = PREFIX_DECL + sparql_str
    parsed = parseQuery(full_query)

    ns = NamespaceManager(Graph())
    for item in parsed:
        if isinstance(item, dict) and "prefix" in item:
            ns.bind(str(item["prefix"]), item["iri"])

    prologue = Prologue()
    prologue.bindings = ns
    alg = translateQuery(parsed, prologue)

    triples = extract_triples_from_algebra(alg.algebra)
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for t in triples:
        key = (t["s"], t["o"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


# --- Test queries from datasets ---
TEST_QUERIES = [
    {
        "name": "1-hop: simple type query",
        "sparql": "SELECT ?uri WHERE { ?uri wdt:P31 wd:Q5 . }",
        "expected_hops": 1,
    },
    {
        "name": "2-hop: chain through ?x",
        "sparql": "SELECT ?uri WHERE { wd:Q5 wdt:P279 ?x . ?x wdt:P279 ?uri . }",
        "expected_hops": 2,
    },
    {
        "name": "3-hop: chain through ?x, ?y",
        "sparql": "SELECT ?uri WHERE { wd:Q5 wdt:P279 ?x . ?x wdt:P279 ?y . ?y wdt:P279 ?uri . }",
        "expected_hops": 3,
    },
    {
        "name": "2-hop: two properties from same entity",
        "sparql": "SELECT ?uri WHERE { wd:Q5 wdt:P279 ?x . ?x wdt:P31 ?uri . }",
        "expected_hops": 2,
    },
    {
        "name": "1-hop: answer variable in object position",
        "sparql": "SELECT ?x WHERE { wd:Q5 wdt:P279 ?x . }",
        "expected_hops": 1,
    },
    {
        "name": "2-hop: answer variable in middle",
        "sparql": "SELECT ?x WHERE { wd:Q5 wdt:P279 ?x . ?x wdt:P31 wd:Q1 . }",
        "expected_hops": 1,  # ?x is at depth 1 from anchor wd:Q5
    },
    {
        "name": "1-hop: ?uri as subject",
        "sparql": "SELECT ?uri WHERE { ?uri wdt:P279 wd:Q5 . }",
        "expected_hops": 1,
    },
    {
        "name": "2-hop: answer is ?result",
        "sparql": "SELECT ?result WHERE { wd:Q5 wdt:P279 ?x . ?x wdt:P31 ?result . }",
        "expected_hops": 2,
    },
    # --- Real dataset queries ---
    {
        "name": "spinach: 2-hop election query",
        "sparql": "SELECT DISTINCT ?item WHERE { ?election wdt:P31 wd:Q93306595 . ?election wdt:P726 ?item . }",
        "expected_hops": 2,  # wd:Q93306595 -> ?election -> ?item
    },
    {
        "name": "spinach: 2-hop province query",
        "sparql": "SELECT ?province ?state WHERE { ?province wdt:P17 ?state . ?province wdt:P31 wd:Q34876 . }",
        "expected_hops": 1,  # anchor ?province, wd:Q34876 at depth 1
    },
    {
        "name": "spinach: 1-hop book query",
        "sparql": "SELECT DISTINCT ?book WHERE { ?book wdt:P50 wd:Q35610 . }",
        "expected_hops": 1,  # wd:Q35610 -> ?book
    },
    {
        "name": "spinach: 3-hop author birthplace",
        "sparql": "SELECT ?item ?auteur ?lieunaissance WHERE { ?item wdt:P170 ?auteur . ?auteur wdt:P19 ?lieunaissance . ?lieunaissance wdt:P131 wd:Q12130 . }",
        "expected_hops": 3,  # wd:Q12130 -> ?lieunaissance -> ?auteur -> ?item
    },
    {
        "name": "spinach: 2-hop country language",
        "sparql": "SELECT ?language WHERE { ?country wdt:P31 wd:Q6256 . ?country wdt:P37 ?language . }",
        "expected_hops": 2,  # wd:Q6256 -> ?country -> ?language
    },
    {
        "name": "spinach: 3-hop script query",
        "sparql": "SELECT ?language WHERE { ?country wdt:P31 wd:Q6256 . ?country wdt:P37 ?language . ?language wdt:P282 ?script . ?script wdt:P279 wd:Q8229 . }",
        "expected_hops": 2,  # anchor ?language, wd:Q6256 and wd:Q8229 at depth 2
    },
    {
        "name": "spinach: 2-hop item with property",
        "sparql": "SELECT ?item WHERE { ?item p:P528 ?statement . ?statement pq:P972 wd:Q51278630 . }",
        "expected_hops": 2,  # wd:Q51278630 -> ?statement -> ?item
    },
]


def run_tests():
    passed = 0
    failed = 0
    for tc in TEST_QUERIES:
        patterns = extract_patterns(tc["sparql"])
        max_hops, entity_depths = count_sparql_hops(tc["sparql"], patterns)

        status = "PASS" if max_hops == tc["expected_hops"] else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1

        print(f"\n{'='*60}")
        print(f"{status}: {tc['name']}")
        print(f"  Query:    {tc['sparql']}")
        print(f"  Patterns: {json.dumps(patterns, indent=2)}")
        print(f"  Expected: {tc['expected_hops']} hops")
        print(f"  Got:      {max_hops} hops")
        if entity_depths:
            print(f"  Entity depths: {entity_depths}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TEST_QUERIES)}")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
