
# Sample usage: python -m src.cache.wikidata_relation_info_extractor
from src.util.common import execute_sparql_query, create_directory_if_not_exists
from src.const.misc import WIKIDATA_PROP_INFO_CACHE_FILEPATH
from tqdm import tqdm
import json
import os
import time
import src.const.misc as misc_consts
from datetime import datetime

def extract_relation_info(endpoint_url, lang='en', limit=5000, offset=0):
    
    query = f"""
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX wd:       <http://www.wikidata.org/entity/>
    PREFIX wdt:      <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs:     <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX p:        <http://www.wikidata.org/prop/>
    PREFIX ps:       <http://www.wikidata.org/prop/statement/>
    PREFIX pq:       <http://www.wikidata.org/prop/qualifier/>

    SELECT DISTINCT
           ?property ?propertyLabel ?domain ?domainLabel ?range ?rangeLabel
    WHERE {{
      ?property a wikibase:Property .
      ?property p:P2302 ?constraint .
      ?property rdfs:label ?propertyLabel .
      FILTER (LANG(?propertyLabel) = "{lang}")

      OPTIONAL {{  # domain constraints
        ?constraint ps:P2302 wd:Q21503250 .
        ?constraint pq:P2308 ?domain .
        ?domain rdfs:label ?domainLabel .
        FILTER (LANG(?domainLabel) = "{lang}")
      }}
      
      OPTIONAL {{  # range constraints
        ?constraint ps:P2302 wd:Q21510865 .
        ?constraint pq:P2308 ?range .
        ?range rdfs:label ?rangeLabel .
        FILTER (LANG(?rangeLabel) = "{lang}")
      }}
    }}
    ORDER BY ?property   # <‑‑ deterministic ordering
    LIMIT {limit}
    OFFSET {offset}
    """

    # --- retry handling for failed requests ---
    max_retries = 5
    attempt = 0
    while attempt < max_retries:
        bindings, req_failed = execute_sparql_query(
            query, endpoint_url, get_only_bindings=True
        )
        if not req_failed:
            if attempt > 0:
                print(f'Success at attempt #{attempt}')
            break                     # success
        attempt += 1
        time.sleep(10)               # wait before retry
    else:
        # all attempts failed – return empty result
        return []

    # Normalise the result set
    result = []
    for b in bindings:
        result.append({
            "property":      b.get("property",      {}).get("value", ""),
            "propertyLabel": b.get("propertyLabel",{}).get("value", ""),
            "domain":        b.get("domain",       {}).get("value", None),
            "domainLabel":   b.get("domainLabel",  {}).get("value", None),
            "range":         b.get("range",        {}).get("value", None),
            "rangeLabel":    b.get("rangeLabel",   {}).get("value", None),
        })
    return result


def collect_all_relations(endpoint_url, lang='en', batch_size=50000): # 14.08.25: query without limit returns "37395 results in 23221 ms"
    offset = 0
    all_relations = {}
    
    # progress bar – one update per fetched batch
    pbar = tqdm(desc="Fetching relation batches", unit="batch")

    while True:
        batch = extract_relation_info(
            endpoint_url, lang=lang, limit=batch_size, offset=offset
        )
        if not batch:
            break   # no more results

        for rel in batch:
            prop_uri = rel["property"]
            # initialise entry if first time we see this property
            if prop_uri not in all_relations:
                all_relations[prop_uri] = {
                    "label": rel["propertyLabel"],
                    "domains": [],
                    "ranges":  []
                }

            # add domain (if present)
            if rel["domain"]:
                all_relations[prop_uri]["domains"].append({
                    "uri": rel["domain"],
                    "label": rel["domainLabel"]
                })

            # add range (if present)
            if rel["range"]:
                all_relations[prop_uri]["ranges"].append({
                    "uri": rel["range"],
                    "label": rel["rangeLabel"]
                })

        # move to next batch
        offset += batch_size
        pbar.update(1)
    pbar.close()
    return all_relations


def save_relations_to_json(relations_dict, file_path):
    """
    Persist the relations dictionary to ``file_path`` as pretty‑printed JSON.
    """
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(relations_dict, f, ensure_ascii=False, indent=2)



if __name__ == "__main__":
    # endpoint = "https://query.wikidata.org/sparql" # This has to be done on official endpoint, it does not work on Tentris
    endpoint = "http://enexa1.cs.uni-paderborn.de:9080/sparql" # Tentris endpoint with main split
    # init sparql logger
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    sparql_log_fp = os.path.join('./data_dir/sparql_logs', f"wikidata_rel_caching_{timestamp}.txt")
    create_directory_if_not_exists(sparql_log_fp)
    misc_consts.sparql_log_filehandle = open(sparql_log_fp, 'a', buffering=1) # buffering=1 for line-buffering
    # collect everything (the function handles pagination internally)
    relations_dict = collect_all_relations(endpoint, lang='en')
    # store to JSON
    output_file = WIKIDATA_PROP_INFO_CACHE_FILEPATH
    create_directory_if_not_exists(output_file)
    save_relations_to_json(relations_dict, output_file)
    ## Obsolete run (11.08.2025): Saved 7493 properties to wikidata_relations.json
    ## Obsolete run (14.08.2025): Saved 10569 properties to data_dir/cache/wikidata_relations.json
    ## Last run (14.08.2025): Saved 12779 properties to data_dir/cache/wikidata_relations.json
    ## Last run (15.04.2026): Saved 13162 properties to data_dir/cache/wikidata_relations.json
    print(f"Saved {len(relations_dict)} properties to {output_file}")
    misc_consts.sparql_log_filehandle.close()