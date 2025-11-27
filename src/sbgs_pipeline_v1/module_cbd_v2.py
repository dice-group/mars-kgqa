# module_cbd_v2.py
import json
import time
from typing import Dict, List, Set, Tuple, Optional
import requests

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


def retrieve_cbd(
    qid: str,
    retries: int = 3,
    delay: int = 1,
    batch_size: int = 500,
    max_pages: int = 20,
    endpoint: str = SPARQL_ENDPOINT,
    keep_literals: bool = True,
    hops: int = 1,
) -> List[Dict]:
    """
    Retrieve a Concise Bounded Description around a Wikidata entity (qid).
    If hops > 1, recursively expands neighbors up to 'hops' distance (BFS).
    Returns a flat list of triples: [{"s": [label, uri], "p": [label, uri], "o": [label, value]}, ...]
    """
    session = requests.Session()
    all_triples: List[Dict] = []
    seen_triples: Set[Tuple[str, str, str]] = set()  # dedupe across pages, nodes, and hops
    visited_nodes: Set[str] = set()
    frontier: Set[str] = set()

    def one_hop(
        node_qid: str,
        session: requests.Session,
    ) -> Tuple[List[Dict], Set[str]]:
        """
        Fetch one-hop CBD around node_qid. Returns (triples, neighbor_qids).
        """
        base_query = f"""
        PREFIX wd:  <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX rdfs:<http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?subject ?prop ?object ?subjectLabel ?propertyLabel ?objectLabel WHERE {{
          {{
            wd:{node_qid} ?prop ?object .
            ?property wikibase:directClaim ?prop .
            BIND(wd:{node_qid} AS ?subject)
          }}
          UNION
          {{
            ?subject ?prop wd:{node_qid} .
            ?property wikibase:directClaim ?prop .
            BIND(wd:{node_qid} AS ?object)
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """

        headers = {
            "Accept": "application/sparql-results+json",
            "User-Agent": "CBD-Retriever/1.0 (contact: your_email@example.com)",
        }

        triples: List[Dict] = []
        neighbors: Set[str] = set()
        subject_wd_uri = f"http://www.wikidata.org/entity/{node_qid}"

        offset = 0
        page = 0
        while page < max_pages:
            paged_query = f"{base_query}\nLIMIT {batch_size} OFFSET {offset}"
            success = False
            for attempt in range(1, retries + 1):
                try:
                    resp = session.get(
                        endpoint,
                        params={"query": paged_query, "format": "json"},
                        headers=headers,
                        timeout=60,
                    )
                    if resp.status_code != 200:
                        time.sleep(delay * attempt)
                        continue

                    data = resp.json()
                    bindings = data.get("results", {}).get("bindings", [])
                    if not bindings:
                        success = True
                        page = max_pages  # stop outer loop
                        break

                    for b in bindings:
                        s_uri = b.get("subject", {}).get("value", "")
                        p_uri = b.get("prop", {}).get("value", "")
                        o_binding = b.get("object", {})
                        o_type = o_binding.get("type", "")
                        o_value = o_binding.get("value", "")

                        s_label = b.get("subjectLabel", {}).get("value", s_uri.rsplit("/", 1)[-1])
                        p_label = b.get("propertyLabel", {}).get("value", p_uri.rsplit("/", 1)[-1])
                        if o_type == "uri":
                            o_label = b.get("objectLabel", {}).get("value", o_value.rsplit("/", 1)[-1])
                        else:
                            o_label = o_value  # literal text/number/date as label

                        # Optionally drop literals
                        if not keep_literals and o_type != "uri":
                            continue
                        if not (s_uri and p_uri and o_value):
                            continue

                        key = (s_uri, p_uri, o_value)
                        if key in seen_triples:
                            continue
                        seen_triples.add(key)

                        triples.append({
                            "s": [s_label, s_uri],
                            "p": [p_label, p_uri],
                            "o": [o_label, o_value],  # o_value may be URI or literal
                        })

                        # Collect neighbor nodes (URIs only)
                        # - From outgoing edges: object URI different from self
                        if o_type == "uri" and o_value.startswith("http://www.wikidata.org/entity/"):
                            tail = o_value.rsplit("/", 1)[-1]
                            if tail and tail != node_qid:
                                neighbors.add(tail)
                        # - From incoming edges: subject is neighbor, self bound as object
                        if s_uri and s_uri != subject_wd_uri and s_uri.startswith("http://www.wikidata.org/entity/"):
                            tail_s = s_uri.rsplit("/", 1)[-1]
                            if tail_s and tail_s != node_qid:
                                neighbors.add(tail_s)

                    offset += batch_size
                    page += 1
                    success = True
                    break
                except requests.RequestException:
                    time.sleep(delay * attempt)
                except ValueError:
                    # JSON decode error
                    time.sleep(delay * attempt)

            if not success:
                # Skip this page to avoid getting stuck
                offset += batch_size
                page += 1

        return triples, neighbors

    # BFS up to 'hops'
    frontier.add(qid)
    visited_nodes.add(qid)

    for _depth in range(max(1, hops)):  # ensure at least one pass (hops=1)
        next_frontier: Set[str] = set()
        for node in list(frontier):
            triples, new_neighbors = one_hop(node, session)
            if triples:
                all_triples.extend(triples)
            for nb in new_neighbors:
                if nb not in visited_nodes:
                    visited_nodes.add(nb)
                    next_frontier.add(nb)
        frontier = next_frontier
        if not frontier:
            break

    return all_triples


def save_cbd_json(question_text: str, cbd_list: List[Dict], out_path: str):
    payload = {
        question_text: {
            "CBD": cbd_list
        }
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# quick manual test
if __name__ == "__main__":
    qid = "Q571"  # book
    cbd_list = retrieve_cbd(qid, batch_size=200, keep_literals=True, hops=1)
    print(f"Triples retrieved (1-hop): {len(cbd_list)}")
    save_cbd_json(f"CBD for {qid}", cbd_list, f"./cbd_{qid}_1hop.json")

    # 2 hops example
    cbd_list_2 = retrieve_cbd(qid, batch_size=200, keep_literals=True, hops=2)
    print(f"Triples retrieved (2-hop): {len(cbd_list_2)}")
    save_cbd_json(f"CBD for {qid}", cbd_list_2, f"./cbd_{qid}_2hop.json")