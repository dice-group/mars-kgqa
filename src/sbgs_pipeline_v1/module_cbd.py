# module_cbd.py
import json
import time
from typing import Dict, List
import requests

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

def retrieve_cbd(
    qid: str,
    retries: int = 3,
    delay: int = 1,
    batch_size: int = 500,
    max_pages: int = 20,
    endpoint: str = SPARQL_ENDPOINT,
    keep_literals: bool = True,   # set False to drop literal objects
) -> Dict[str, List[Dict]]:

    base_query = f"""
    PREFIX wd:  <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX rdfs:<http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?subject ?prop ?object ?subjectLabel ?propertyLabel ?objectLabel WHERE {{
      {{
        wd:{qid} ?prop ?object .
        ?property wikibase:directClaim ?prop .
        BIND(wd:{qid} AS ?subject)
      }}
      UNION
      {{
        ?subject ?prop wd:{qid} .
        ?property wikibase:directClaim ?prop .
        BIND(wd:{qid} AS ?object)
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "CBD-Retriever/1.0 (contact: your_email@example.com)",
    }

    cbd: List[Dict] = []
    seen = set() 

    offset = 0
    page = 0

    session = requests.Session()

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

                    # Object label if it's a URI, otherwise use literal value as label
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
                    if key in seen:
                        continue
                    seen.add(key)

                    # Build CBD entry
                    cbd.append({
                        "s": [s_label, s_uri],
                        "p": [p_label, p_uri],
                        "o": [o_label, o_value],  # o_value may be URI or literal
                    })

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

    return (cbd)

def save_cbd_json(question_text: str, cbd_obj: Dict[str, List[Dict]], out_path: str):

    payload = {
        question_text: {
            
            "CBD": cbd_obj.get("CBD", [])
        }
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# quick manual test
if __name__ == "__main__":
    qid = "Q571"  # book
    cbd_obj = retrieve_cbd(qid, batch_size=200, keep_literals=True)
    print(f"Triples retrieved: {len(cbd_obj['CBD'])}")
    save_cbd_json(f"CBD for {qid}", cbd_obj, f"./cbd_{qid}.json")