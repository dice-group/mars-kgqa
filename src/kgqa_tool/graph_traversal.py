# Sample usage: python -m src.kgqa_tool.graph_traversal
import requests

# Find all the 1-hop triples for a node (given URI), alongside the labels for relations and nodes using SPARQL
def find_1_hop_triples(node_uri, endpoint_url, lang_list=[]):
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
    SELECT ?subject ?predicate ?object ?subjectLabel ?propLabel ?objectLabel
    WHERE {{
        {{ 
            ?subject ?predicate <{node_uri}> .
            OPTIONAL {{ ?subject rdfs:label ?subjectLabel . FILTER (lang(?subjectLabel) in ('en'{formatted_lang_list}) ) }}
            
        }}
        UNION
        {{ 
            <{node_uri}> ?predicate ?object . 
            OPTIONAL {{ ?object rdfs:label ?objectLabel . FILTER (lang(?objectLabel) in ('en'{formatted_lang_list}) ) }}
        }}
        OPTIONAL {{ ?prop wikibase:directClaim ?predicate . ?prop rdfs:label ?propLabel. FILTER (lang(?propLabel) = 'en') }} # English labels are sufficient for the properties
        FILTER(?predicate NOT IN (<http://schema.org/description>, <http://www.w3.org/2004/02/skos/core#altLabel>, <http://www.w3.org/2004/02/skos/core#prefLabel>, <http://www.w3.org/2000/01/rdf-schema#label>))  # Excluding specific predicates
    }}
    """
    
    #print(query)
    
    headers = {
        "Accept": "application/sparql-results+json"
    }
    

    try:
        response = requests.get(endpoint_url, params={'query': query, 'format': 'json'}, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
        return []

    triples = []
    for binding in data['results']['bindings']:
        triple = {
            'subject': binding.get('subject', {}).get('value', ''),
            'predicate': binding.get('predicate', {}).get('value', ''),
            'object': binding.get('object', {}).get('value', ''),
            'propLabel': binding.get('propLabel', {}).get('value', ''),
            'subjectLabel': binding.get('subjectLabel', {}).get('value', ''),
            'objectLabel': binding.get('objectLabel', {}).get('value', '')
        }
        triples.append(triple)

    return triples

# Example usage
if __name__ == "__main__":
    node_uri = "http://www.wikidata.org/entity/Q567"
    endpoint_url = "https://wikidata.data.dice-research.org/sparql"
    triples = find_1_hop_triples(node_uri, endpoint_url, ['de'])
    for triple in triples:
        print(triple)