# Sample usage: python -m src.kgqa_tool.graph_traversal
import requests
from src.const.misc import SPARQL_HARD_LIMIT
from src.util.common import execute_sparql_query

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
    
    bindings = execute_sparql_query(query, endpoint_url)

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

# Example usage
if __name__ == "__main__":
    node_uri = "http://www.wikidata.org/entity/Q567"
    endpoint_url = "https://wikidata.data.dice-research.org/sparql"
    triples = find_1_hop_triples(node_uri, endpoint_url, ['de'])
    for triple in triples:
        print(triple)