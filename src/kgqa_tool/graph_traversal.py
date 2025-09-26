# Sample usage: python -m src.kgqa_tool.graph_traversal
import requests
from src.const.misc import SPARQL_HARD_LIMIT
from src.util.common import execute_sparql_query

# Find all the 1-hop triples for a node (given URI), alongside the labels for relations and nodes using SPARQL
def find_1_hop_triples(node_uri, endpoint_url, lang_list=[], use_sleep=False):
    formatted_lang_list = ''
    if lang_list:
        formatted_lang_list = ',' + ', '.join(f"'{item}'" for item in lang_list)

    query = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    
    SELECT DISTINCT ?subject ?predicate ?object ?subjectLabel ?propLabel ?objectLabel
    WHERE {{
        {{
            VALUES ?object {{ <{node_uri}> }} 
            ?subject ?predicate <{node_uri}> .
            
            ?subject rdfs:label ?subjectLabel . FILTER (lang(?subjectLabel) in ('en'{formatted_lang_list}) )
            
            ?object rdfs:label ?objectLabel . FILTER (lang(?objectLabel) in ('en'{formatted_lang_list}) )
            
        }}
        UNION
        {{ 
            VALUES ?subject {{ <{node_uri}> }}
            <{node_uri}> ?predicate ?object .
            
            OPTIONAL {{ ?object rdfs:label ?objectLabel . FILTER (lang(?objectLabel) in ('en'{formatted_lang_list}) ) }}
            
            ?subject rdfs:label ?subjectLabel . FILTER (lang(?subjectLabel) in ('en'{formatted_lang_list}) )
            
            FILTER(!isURI(?object) || EXISTS {{ ?object rdfs:label ?objectLabel . FILTER (lang(?objectLabel) in ('en'{formatted_lang_list})) }})
            
        }}
        
        FILTER(STRSTARTS(STR(?subject), "http://www.wikidata.org/entity/") && !STRSTARTS(STR(?subject), "http://www.wikidata.org/entity/statement/") ) # Filtering out statements
        FILTER(?predicate NOT IN (<http://schema.org/description>, <http://www.w3.org/2004/02/skos/core#altLabel>, <http://www.w3.org/2004/02/skos/core#prefLabel>, <http://www.w3.org/2000/01/rdf-schema#label>))  # Excluding specific predicates
        OPTIONAL {{ ?prop wikibase:directClaim ?predicate . ?prop rdfs:label ?propLabel. FILTER (lang(?propLabel) = 'en') }} # English labels are sufficient for the properties
        
    }} LIMIT {SPARQL_HARD_LIMIT}
    """
    
    bindings, _ = execute_sparql_query(query, endpoint_url, use_sleep=use_sleep)

    triples = []
    for binding_item in bindings:
        triple = {
            'root': node_uri,
            'subject': binding_item.get('subject', {}).get('value', ''),
            'predicate': binding_item.get('predicate', {}).get('value', ''),
            'object': binding_item.get('object', {}).get('value', ''),
            'propLabel': binding_item.get('propLabel', {}).get('value', ''),
            'subjectLabel': binding_item.get('subjectLabel', {}).get('value', ''),
            'objectLabel': binding_item.get('objectLabel', {}).get('value', '')
        }
        triples.append(triple)

    return triples

def find_1_hop_patterns(node_uri, endpoint_url, use_sleep=False):
    
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?direction ?property (COUNT(*) AS ?count)
    WHERE {{
        
        {{   # outgoing statements
            BIND ("out" AS ?direction)
            <{node_uri}> ?property ?object .
        }}
        UNION
        {{   # incoming statements
            BIND ("in" AS ?direction)
            ?subject ?property <{node_uri}> .
        }}
    }}
    GROUP BY ?direction ?property
    """
    timeout = 60 if use_sleep else 10
    bindings, _ = execute_sparql_query(query, endpoint_url, True, timeout, use_sleep=use_sleep)

    patterns = []
    for b in bindings:
        patterns.append({
            "direction": b.get("direction", {}).get("value", ""),
            "property":  b.get("property",  {}).get("value", ""),
            "count":     int(b.get("count", {}).get("value", "0"))
        })
    return patterns

def find_next_hop_patterns(triple_constraint, var_name, endpoint_url, use_sleep=False):
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?direction ?property (COUNT(*) AS ?count)
    WHERE {{
        {triple_constraint}
        {{   # outgoing statements
            BIND ("out" AS ?direction)
            {var_name} ?property ?object .
        }}
        UNION
        {{   # incoming statements
            BIND ("in" AS ?direction)
            ?subject ?property {var_name} .
        }}
    }}
    GROUP BY ?direction ?property
    """
    timeout = 60 if use_sleep else 10
    bindings, _ = execute_sparql_query(query, endpoint_url, True, timeout, use_sleep=use_sleep)

    patterns = []
    for b in bindings:
        patterns.append({
            "direction": b.get("direction", {}).get("value", ""),
            "property":  b.get("property", {}).get("value", ""),
            "count":     int(b.get("count", {}).get("value", "0"))
        })
    return patterns


def get_node_label(node_uri, endpoint_url, lang = "en", use_sleep=False):
    # A query that prefers the requested language, falling back to any label.
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

    SELECT ?label WHERE {{
        {{ <{node_uri}> rdfs:label ?label FILTER (lang(?label) = "{lang}") }}
        UNION
        {{ <{node_uri}> skos:prefLabel ?label FILTER (lang(?label) = "{lang}") }}
        UNION
        {{ <{node_uri}> rdfs:label ?label FILTER (lang(?label) = "" ) }}
        UNION
        {{ <{node_uri}> skos:prefLabel ?label FILTER (lang(?label) = "" ) }}
    }}
    LIMIT 1
    """

    bindings, _ = execute_sparql_query(query, endpoint_url, use_sleep=use_sleep)

    if bindings:
        return bindings[0].get("label", {}).get("value", "")
    return ""

def fetch_labels(id_list, endpoint_url, pref, use_sleep=False):
    """
    Fetch English labels for a list of Wikidata IDs.
    """
    if not id_list:
        return []

    # Build the VALUES clause – each full URI is wrapped in <>.
    values_block = " ".join(f"<{pref}{qid}>" for qid in id_list)

    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?uri ?label WHERE {{
        VALUES ?uri {{ {values_block} }}
        OPTIONAL {{
            ?uri rdfs:label ?label .
            FILTER (lang(?label) = 'en')
        }}
    }}
    """

    bindings, _ = execute_sparql_query(query, endpoint_url, use_sleep=use_sleep)

    # Transform SPARQL results into the desired list of dicts.
    results = []
    # Initialize with empty labels in case some IDs have no label.
    for qid in id_list:
        results.append({"uri": qid, "label": ""})

    # Fill in the labels that were returned.
    for b in bindings:
        full_uri = b.get('uri', {}).get('value')
        label = b.get('label', {}).get('value', '')
        if full_uri:
            # Strip the prefix to get the plain ID.
            qid = full_uri.replace(pref, "")
            # Find the corresponding dict and set the label.
            for entry in results:
                if entry["uri"] == qid:
                    entry["label"] = label
                    break

    return results

# Example usage
if __name__ == "__main__":
    node_uri = "http://www.wikidata.org/entity/Q567"
    endpoint_url = "https://wikidata.data.dice-research.org/sparql"
    triples = find_1_hop_triples(node_uri, endpoint_url, ['de'])
    for triple in triples:
        print(triple)