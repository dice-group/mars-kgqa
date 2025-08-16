# Sample usage: python -m src.pattern_based_sparql_generator
from src.simple_factoid_solver import extract_triples_data, get_verbalization_similarity, process_dataset, generate_output_path, generate_gerbil_export_path
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples, find_1_hop_patterns, get_node_label
from src.kgqa_tool.llm_request import generate_simple_sparql, filter_common_nodes, generate_1hop_pattern_sparql, sparql_refinement
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL, WIKIDATA_PROP_INFO_CACHE_FILEPATH, GERBIL_EXPERIMENT_URI_STORE_FILEPATH
from src.const.llm import ChatModel
from src.util.common import read_json_file, get_last_uri_fragment, get_prefixed_id
import heapq
from src.util.qald_io import convert_basic_output

from enum import Enum, auto
from src.const.dataset import KgqaDataset, DatasetSplit
from src.util.gerbil import create_export_gerbil_experiment

PROPERTY_INFO_MAP = None
PROPERTY_ID_MAP = None


class EdgeDirection(Enum):
    """Indicates whether a relation is an incoming or outgoing edge."""
    INCOMING = 'in'
    OUTGOING = 'out'

class NodeEdge:
    def __init__(
        self,
        node_uri: str,
        node_label: str,
        relation_uri: str,
        relation_id: str,
        direction: EdgeDirection | str,
    ) -> None:
        self.node_uri = node_uri
        self.node_label = node_label
        self.relation_uri = relation_uri
        self.relation_id = relation_id
        # Allow passing either the enum member or its name as a string
        if isinstance(direction, EdgeDirection):
            self.direction = direction
        else:
            self.direction = EdgeDirection[direction.lower()]
            
    def get_dr_aug_verbalization(self, prop_id_map=PROPERTY_ID_MAP, prop_info_map=PROPERTY_INFO_MAP, include_id=False):
        prop_ent_uri = prop_id_map[self.relation_id]

        # get the property label
        prop_label = prop_info_map[prop_ent_uri]['label']
        # get the domain label(s)
        dom_label_list = [dom_item['label'] for dom_item in prop_info_map[prop_ent_uri]['domains']]
        # get the range label(s)
        range_label_list = [range_item['label'] for range_item in prop_info_map[prop_ent_uri]['ranges']]

        class_info = (
            f"(possible subject classes: {','.join(dom_label_list)}), "
            f"(possible object classes: {','.join(range_label_list)})"
        )
        
        if self.direction == EdgeDirection.OUTGOING:
            # verbal part: "<node_label> <property_label> ?object"
            verbal_part = f"'{self.node_label}' '{prop_label}' ?object"
            # ID part (only if requested)
            id_part = f"\t{get_prefixed_id(self.node_uri)} {get_prefixed_id(self.relation_uri)} ?object" if include_id else ""
        else:  # EdgeDirection.INCOMING
            # verbal part: "?subject <property_label> <node_label>"
            verbal_part = f"?subject '{prop_label}' '{self.node_label}'"
            # ID part (only if requested)
            id_part = f"\t?subject {get_prefixed_id(self.relation_uri)} {get_prefixed_id(self.node_uri)}" if include_id else ""

        # combine verbalization, optional ID triple, and class info
        verbalized_str = f"{verbal_part}{id_part}\t {class_info}"

        return verbalized_str

    def __repr__(self) -> str:
        return (
            f"GraphElement(node_uri={self.node_uri!r}, label={self.node_label!r}, "
            f"relation_uri={self.relation_uri!r}, direction={self.direction.name})"
        )
        
def match_property(truthy_uri, property_uri):
    # Matching the property identifiers since they have different prefixes in Wikidata based on the use-case: https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual/yo
    truthy_prop_id = get_last_uri_fragment(truthy_uri)
    ent_prop_id = get_last_uri_fragment(property_uri)
    return truthy_prop_id == ent_prop_id

def extract_patterns_data(root_uri, root_label, patterns_list, prop_id_map):
    patterns_data_list = []
    rejected_patterns = []
    # For each pattern item
    for pattern_item in patterns_list:
        prop_uri = pattern_item['property']
        # Reject if property is not in our cached info
        prop_id = get_last_uri_fragment(prop_uri)
        if prop_id not in prop_id_map:
            rejected_patterns.append(pattern_item)
            continue
        direction_str = pattern_item['direction']
        edge_dir = EdgeDirection(direction_str)
        pattern_obj = NodeEdge(root_uri, root_label, prop_uri, prop_id, edge_dir)
        patterns_data_list.append(pattern_obj)
    
    return patterns_data_list, rejected_patterns

def load_property_info(cached_file_path):
    global PROPERTY_INFO_MAP, PROPERTY_ID_MAP
    
    PROPERTY_INFO_MAP = read_json_file(cached_file_path)
    PROPERTY_ID_MAP = {}
    for key in PROPERTY_INFO_MAP:
        prop_id = get_last_uri_fragment(key)
        PROPERTY_ID_MAP[prop_id] = key


def process_input_query(question_text, model_config, preprocessed_input=None, wd_ep=None):
    print(f'Processing question: {question_text}')
    
    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL
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
    
    all_rejected_patterns = [] # Mostly for debugging
    # For each entity, find all the triple patterns that exist
    for entity_qid in filter_entity_dict.values():
        print(f'Traversing: {entity_qid}')
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid
        visited_nodes.add(entity_qid) # adding all the root nodes which have been extended already
        entity_label = get_node_label(entity_uri, wd_ep)
        patterns_list = find_1_hop_patterns(entity_uri, wd_ep)
        print(f'Triple patterns found for {entity_uri}: {len(patterns_list)}')
        extracted_patterns, rejected_patterns = extract_patterns_data(entity_uri, entity_label, patterns_list, PROPERTY_ID_MAP)
        patterns_data_list.extend(extracted_patterns)
        all_rejected_patterns.extend(rejected_patterns)
        print(f'Filtered triple patterns for {entity_uri}: {len(extracted_patterns)}')
    
    # TODO: Implement
    # Compute similarity of the patterns to the (augmented) query
    verbalizer=lambda obj: obj.get_dr_aug_verbalization(PROPERTY_ID_MAP, PROPERTY_INFO_MAP)
    # Sort the patterns
    priority_queue = get_verbalization_similarity(aug_qtxt, patterns_data_list, verbalizer)
    # For top N patterns
    n_value = 10
    top_triples = heapq.nsmallest(n_value, priority_queue, key=lambda x: x[0])
    
    id_verbalizer=lambda obj: obj.get_dr_aug_verbalization(PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True)
    top_id_verbalizations = [id_verbalizer(item[1]) for item in top_triples]
    
    sparql = generate_1hop_pattern_sparql(question_text, top_id_verbalizations, model_config)
    print(f'First SPARQL: {sparql}')
    ## refine this SPARQL (extra step that is needed for certain models)
    #sparql = sparql_refinement(question_text, sparql, model_config)
    #print(f'Refined SPARQL: {sparql}')
    
    # TODO: Implementation pending
    # Ask the LLM if we should consider further hops
    # If yes, then expand the chosen triples and add them to the new list
        # compute similarity
        # Show the next top patterns and repeat
    # If not, then retrieve the triples for the chosen patterns and rank them
    
    # Choose top F triples from each chosen path
    # Ask LLM to generate a SPARQL based on this context
        
    return sparql


# Example usage
if __name__ == "__main__":
    
    approach_name = 'pbsg'
    
    llm_config = ChatModel.DEEPSEEK_R1_QWEN3_8B.value
    
    run_name = f'{approach_name}__{llm_config.model_id}'
    
    kgqa_ds = KgqaDataset.QALD9PLUS_UPDATED.value
    #kgqa_ds = KgqaDataset.QALD10.value
    
    wd_ep = kgqa_ds.preferred_wd_endpoint
    
    split_conf = DatasetSplit.TEST
    
    qald_file_path = kgqa_ds.split_dict[split_conf]
    
    tsv_output_path = generate_output_path(run_name, qald_file_path, 'tsv')
    
    # Load the cached property info map
    load_property_info(WIKIDATA_PROP_INFO_CACHE_FILEPATH)
    
    # Generates TSV (for readability)
    process_dataset(run_name, qald_file_path, tsv_output_path, process_input_query, wd_ep, llm_config)
    
    json_output_path = generate_output_path(run_name, qald_file_path, 'json')
    # Converts TSV to JSON (for evaluation)
    convert_basic_output(tsv_output_path, qald_file_path, json_output_path, has_tuples=False)
    
    # Evaluating results on GERBIL
    gold_dataset_label = f'{kgqa_ds.dataset_id}_{split_conf.name.lower()}'
    system_label = f'{run_name}'
    gerbil_result_path = generate_gerbil_export_path(run_name, qald_file_path)
    
    create_export_gerbil_experiment(gold_dataset_label, qald_file_path, system_label, json_output_path, 'en', gerbil_result_path, GERBIL_EXPERIMENT_URI_STORE_FILEPATH)