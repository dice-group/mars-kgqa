# Sample usage: python -m src.simple_sparql_generator
from src.simple_factoid_solver import extract_triples_data, get_triples_similarity, process_dataset, generate_output_path
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples, find_1_hop_patterns
from src.kgqa_tool.llm_request import generate_simple_sparql, filter_common_nodes
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL
from src.util.common import read_json_file
import heapq

from enum import Enum, auto

PROPERTY_INFO_MAP = None


class EdgeDirection(Enum):
    """Indicates whether a relation is an incoming or outgoing edge."""
    INCOMING = auto()
    OUTGOING = auto()

class GraphElement:
    def __init__(
        self,
        node_uri: str,
        label: str,
        relation_uri: str,
        direction: EdgeDirection | str,
    ) -> None:
        self.node_uri = node_uri
        self.label = label
        self.relation_uri = relation_uri
        # Allow passing either the enum member or its name as a string
        if isinstance(direction, EdgeDirection):
            self.direction = direction
        else:
            self.direction = EdgeDirection[direction.upper()]

    def __repr__(self) -> str:
        return (
            f"GraphElement(node_uri={self.node_uri!r}, label={self.label!r}, "
            f"relation_uri={self.relation_uri!r}, direction={self.direction.name})"
        )

def extract_patterns_data(patterns_list):
    # TODO: Implement
    pass

def load_property_info(cached_file_path):
    global PROPERTY_INFO_MAP
    PROPERTY_INFO_MAP = read_json_file(cached_file_path)


def process_input_query(question_text, model_config, preprocessed_input=None):
    print(f'Processing question: {question_text}')
    # Retrieve entities and relations for the input question
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_list = preprocessed_input # unpack
    else:
        aug_qtxt, entity_dict, relation_list = find_entities_and_relations(question_text)
        
    # Filter entity dictionary to remove entities that will lead to too many child nodes
    filter_entity_dict = filter_common_nodes(question_text, entity_dict, model_config)
    print(f'Entities to visit: {filter_entity_dict}')
    
    patterns_data_list = []
    visited_nodes = set()
    
    # For each entity, find all the triple patterns that exist
    for entity_qid in filter_entity_dict.values():
        print(f'Traversing: {entity_qid}')
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid
        visited_nodes.add(entity_qid) # adding all the root nodes which have been extended already
        patterns_list = find_1_hop_patterns(entity_uri, DEFAULT_WIKIDATA_ENDPOINT_URL)
        print(f'Triple patterns found for {entity_uri}: {len(patterns_list)}')
        extracted_patterns = extract_patterns_data(patterns_list)
        patterns_data_list.extend(extracted_patterns)
        print(f'Filtered triple patterns for {entity_uri}: {len(extracted_patterns)}')
    
    # TODO: Implement
    # Extract domain and range for each relation to use as augmented information
    
    # Compute similarity of the patterns to the query
    
    # Sort the patterns
    
    # For top N patterns
    # Ask the LLM if we should consider further hops
    # If yes, then expand the chosen triples and add them to the new list
        # compute similarity
        # Show the next top patterns and repeat
    # If not, then retrieve the triples for the chosen patterns and rank them
    
    # Choose top F triples from each chosen path
    # Ask LLM to generate a SPARQL based on this context
    
    sparql = None
    
    print(f'Generated SPARQL: {sparql}')
        
    return sparql


# Example usage
if __name__ == "__main__":
    
    approach_name = 'pbsg'
    
    qald_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/aug_gold.json"
    #qald_file_path = "data_dir/processed_kgqa_ds/qald10/test/aug_gold.json"
    #qald_file_path = "data_dir/processed_kgqa_ds/lcquad2/test/updt_qald_aug_gold.json"
    
    output_path = generate_output_path(approach_name, qald_file_path)
    #output_path = "data_dir/processed_kgqa_ds/qald9plus/test/prediction/tsv/aug_pred_sparql.tsv"
    #output_path = "data_dir/processed_kgqa_ds/qald10/test/prediction/tsv/aug_pred_sparql.tsv"
    #output_path = "data_dir/processed_kgqa_ds/lcquad2/test/prediction/tsv/aug_pred_sparql.tsv"
    
    # Load the cached property info map
    load_property_info("data_dir/cache/wikidata_relations.json")
    
    process_dataset(approach_name, qald_file_path, output_path, process_input_query)