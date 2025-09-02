# Sample usage: python -m src.pattern_based_sparql_generator
from src.simple_factoid_solver import extract_triples_data, get_verbalization_similarity, process_dataset, generate_output_path, generate_gerbil_export_path, get_log_dir
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples, find_1_hop_patterns, get_node_label, find_next_hop_patterns
from src.kgqa_tool.llm_request import generate_simple_sparql, filter_common_nodes, generate_1hop_pattern_sparql, sparql_refinement, generate_mhop_pattern_sparql
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
        node_id: str,
        node_label: str,
        relation_uri: str,
        relation_id: str,
        direction: EdgeDirection | str,
        var_id: str = None
    ) -> None:
        self.node_id = node_id
        self.node_label = node_label
        self.relation_uri = relation_uri
        self.relation_id = relation_id
        # track if node_uri is already a SPARQL variable (e.g., "?subject1")
        self.node_is_var = isinstance(node_id, str) and node_id.startswith("?")
        # Allow passing either the enum member or its name as a string
        if isinstance(direction, EdgeDirection):
            self.direction = direction
        else:
            self.direction = EdgeDirection[direction.lower()]
        
        self.assign_variable_id(var_id)
    
    def assign_variable_id(self, var_id):
        self.var_id = var_id
        
        # Logic for variable name assignment
        subject_term = '?subject'
        object_term = '?object'
                
        if self.var_id:
            subject_term += f'_{self.var_id}'
            object_term += f'_{self.var_id}'
        
        self.variable_name = None
        
        if self.direction == EdgeDirection.OUTGOING:
            self.variable_name = object_term
        else:  # EdgeDirection.INCOMING
            self.variable_name = subject_term
            
    def get_triple_pattern(self):
        triple_pattern_str = None
        node_repr = self.node_id if self.node_is_var else f'<{self.node_id}>' 
        if self.direction == EdgeDirection.OUTGOING:
            triple_pattern_str = f'{node_repr} <{self.relation_uri}> {self.variable_name} . '
        else:  # EdgeDirection.INCOMING
            triple_pattern_str = f'{self.variable_name} <{self.relation_uri}> {node_repr} . '
        return triple_pattern_str
            
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
        
        node_prefixed_repr = self.node_id if self.node_is_var else get_prefixed_id(self.node_id)
        
        if self.direction == EdgeDirection.OUTGOING:
            # verbal part: "<node_label> <property_label> ?object"
            verbal_part = f"'{self.node_label}' '{prop_label}' {self.variable_name}"
            # ID part (only if requested)
            id_part = f"\t{node_prefixed_repr} {get_prefixed_id(self.relation_uri)} {self.variable_name}" if include_id else ""
        else:  # EdgeDirection.INCOMING
            # verbal part: "?subject <property_label> <node_label>"
            verbal_part = f"{self.variable_name} '{prop_label}' '{self.node_label}'"
            # ID part (only if requested)
            id_part = f"\t{self.variable_name} {get_prefixed_id(self.relation_uri)} {node_prefixed_repr}" if include_id else ""

        # combine verbalization, optional ID triple, and class info
        verbalized_str = f"{verbal_part}{id_part}\t {class_info}"

        return verbalized_str

    def __repr__(self) -> str:
        return (
            f"GraphElement(node_uri={self.node_id!r}, label={self.node_label!r}, "
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


def process_input_query_1hop(question_text, model_config, preprocessed_input,
                            wd_ep, using_gold_entrel, proc_logger):
    """
    One‑hop pattern‑based SPARQL generation
    """
    
    # Log start of the action
    proc_logger.start_action(
        "process_input_query_1hop",
        {"question": question_text, "model_config": model_config.to_dict()}
    ).add_step(f'Processing question: {question_text}')

    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL

    
    # Entity / relation extraction
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_list = preprocessed_input  # unpack
    else:
        aug_qtxt, entity_dict, relation_list = find_entities_and_relations(
            question_text
        )
    proc_logger.add_step(f'Identified entities: {entity_dict}')

    
    # Filtering
    # if using_gold_entrel:
    #     filter_entity_dict = entity_dict
    # else:
    #     filter_entity_dict = filter_common_nodes(question_text, entity_dict, model_config)

    ## Note: Disabling filtering logic, as entities are already getting filtered in entity linking step
    filter_entity_dict = entity_dict
    proc_logger.add_step(f'Entities to visit: {filter_entity_dict}')

    patterns_data_list = []
    visited_nodes = set()
    all_rejected_patterns = []  # Mostly for debugging

    
    # Walk each root entity and collect 1‑hop patterns
    for entity_qid in filter_entity_dict.values():
        proc_logger.add_step(f'Traversing entity: {entity_qid}')
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid
        visited_nodes.add(entity_qid)  # root node already expanded
        entity_label = get_node_label(entity_uri, wd_ep)

        patterns_list = find_1_hop_patterns(entity_uri, wd_ep)
        proc_logger.add_step(
            f'Triple patterns found for {entity_uri}: {len(patterns_list)}'
        )

        extracted_patterns, rejected_patterns = extract_patterns_data(
            entity_uri, entity_label, patterns_list, PROPERTY_ID_MAP
        )
        patterns_data_list.extend(extracted_patterns)
        all_rejected_patterns.extend(rejected_patterns)

        proc_logger.add_step(
            f'Filtered triple patterns for {entity_uri}: {len(extracted_patterns)}'
        )

    
    # Compute verbalization similarity and pick top‑N
    verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP
    )
    proc_logger.add_step('Computing verbalization similarity')
    priority_queue = get_verbalization_similarity(aug_qtxt,
                                                   patterns_data_list,
                                                   verbalizer)

    n_value = 10
    top_triples = heapq.nsmallest(n_value, priority_queue,
                                  key=lambda x: x[0])
    proc_logger.add_step(f'Selected top {n_value} triple patterns')

    id_verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True
    )
    top_id_verbalizations = [id_verbalizer(item[1]) for item in top_triples]

    
    # LLM call – generate SPARQL
    sparql = generate_1hop_pattern_sparql(question_text,
                                          top_id_verbalizations,
                                          model_config)
    proc_logger.add_step(f'Generated SPARQL (raw): {sparql}')

    # ## refine this SPARQL (extra step that is needed for certain models)
    # sparql = sparql_refinement(question_text, sparql, model_config)
    # proc_logger.add_step(f'Refined SPARQL: {sparql}')

    
    # Log final output and complete the action
    proc_logger.set_output({"sparql": sparql}).complete_action()
    return sparql


def process_input_query_mhop(question_text, model_config, preprocessed_input,
                            wd_ep, using_gold_entrel, proc_logger):
    """
    Multi‑hop pattern‑based SPARQL generation
    """
    
    # Log start of the multi‑hop action
    proc_logger.start_action(
        "process_input_query_mhop",
        {"question": question_text, "model_config": model_config.to_dict()}
    ).add_step(f'Processing question: {question_text}')

    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL

    
    # Entity / relation extraction
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_list = preprocessed_input  # unpack
    else:
        aug_qtxt, entity_dict, relation_list = find_entities_and_relations(
            question_text
        )
    proc_logger.add_step(f'Identified entities: {entity_dict}')

    
    # Filtering
    # if using_gold_entrel:
    #     filter_entity_dict = entity_dict
    # else:
    #     filter_entity_dict = filter_common_nodes(question_text, entity_dict, model_config)

    ## Note: Disabling filtering logic, as entities are already getting filtered in entity linking step
    filter_entity_dict = entity_dict
    proc_logger.add_step(f'Entities to visit: {filter_entity_dict}')

    patterns_data_list = []
    visited_nodes = set()
    all_rejected_patterns = []  # Mostly for debugging

    
    # Walk each root entity and collect 1‑hop patterns
    for entity_qid in filter_entity_dict.values():
        proc_logger.add_step(f'Traversing entity: {entity_qid}')
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid
        visited_nodes.add(entity_qid)  # root node already expanded
        entity_label = get_node_label(entity_uri, wd_ep)

        patterns_list = find_1_hop_patterns(entity_uri, wd_ep)
        proc_logger.add_step(
            f'Triple patterns found for {entity_uri}: {len(patterns_list)}'
        )

        extracted_patterns, rejected_patterns = extract_patterns_data(
            entity_uri, entity_label, patterns_list, PROPERTY_ID_MAP
        )
        patterns_data_list.extend(extracted_patterns)
        all_rejected_patterns.extend(rejected_patterns)

        proc_logger.add_step(
            f'Filtered triple patterns for {entity_uri}: {len(extracted_patterns)}'
        )

    
    # Compute similarity and pick top‑N (same as 1‑hop)
    verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP
    )
    proc_logger.add_step('Computing verbalization similarity')
    priority_queue = get_verbalization_similarity(aug_qtxt,
                                                   patterns_data_list,
                                                   verbalizer)

    n_value = 10
    top_triples = heapq.nsmallest(n_value, priority_queue,
                                  key=lambda x: x[0])
    proc_logger.add_step(f'Selected top {n_value} triple patterns')

    id_verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True
    )
    top_id_verbalizations = [id_verbalizer(item[1]) for item in top_triples]

    
    # First LLM call – ask for expansion indices
    sparql, indices = generate_mhop_pattern_sparql(question_text,
                                                   top_id_verbalizations,
                                                   model_config)
    proc_logger.add_step(f'LLM returned SPARQL: {sparql}')
    proc_logger.add_step(f'LLM requested expansion for indices: {indices}')

    
    # If the model asks for further expansion, walk the requested edges
    if indices and not sparql:
        proc_logger.add_step('Entering expansion loop')
        next_hop_patterns_data_list = []
        next_hop_reject_patterns = []
        expanded_triple_tuples = []

        i = 1
        for index_item in indices:
            index_item = int(index_item)
            if index_item < 0 or index_item >= len(top_triples):
                continue

            cur_triple_tuple = top_triples[index_item]
            expanded_triple_tuples.append(cur_triple_tuple)

            cur_id = i
            cur_edge = cur_triple_tuple[1]
            cur_edge.assign_variable_id(cur_id)

            proc_logger.add_step(
                f'Expanding edge #{i}: {id_verbalizer(cur_edge)}'
            )

            cur_var_name = cur_edge.variable_name
            cur_constraint_tp = cur_edge.get_triple_pattern()
            cur_patterns_list = find_next_hop_patterns(
                cur_constraint_tp, cur_var_name, wd_ep
            )
            proc_logger.add_step(
                f'Triple patterns found for {cur_var_name}: {len(cur_patterns_list)}'
            )

            extracted_patterns, rejected_patterns = extract_patterns_data(
                cur_var_name, cur_var_name, cur_patterns_list, PROPERTY_ID_MAP
            )
            next_hop_patterns_data_list.extend(extracted_patterns)
            next_hop_reject_patterns.extend(rejected_patterns)

            proc_logger.add_step(
                f'Filtered triple patterns for {cur_var_name}: {len(extracted_patterns)}'
            )
            i += 1

        
        # Rank next‑hop patterns and generate final SPARQL
        next_priority_queue = get_verbalization_similarity(
            aug_qtxt, next_hop_patterns_data_list, verbalizer
        )
        next_top_triples = heapq.nsmallest(
            n_value, next_priority_queue, key=lambda x: x[0]
        )
        top_id_verbalizations = [
            id_verbalizer(item[1]) for item in next_top_triples
        ]

        final_verbalizations = [
            id_verbalizer(item[1]) for item in expanded_triple_tuples
        ]
        final_verbalizations.extend(top_id_verbalizations)

        sparql = generate_1hop_pattern_sparql(question_text,
                                             final_verbalizations,
                                             model_config)
        proc_logger.add_step(f'Generated final SPARQL after expansion: {sparql}')

    
    # Log final output and complete the action
    proc_logger.set_output({"sparql": sparql}).complete_action()
    return sparql

# Example usage
if __name__ == "__main__":
    
    ## Constants
    pbsg_variants = {
        'pbsg': process_input_query_1hop,
        'pbsg_mhop': process_input_query_mhop
    }
    
    ## Configurable variables
    use_goldentrel = False # Whether to use gold entities and relations
    approach_id = 'pbsg_mhop' # identifier of the approach

    llm_config = ChatModel.GPTOSS120B.value # LLM to use
    
    kgqa_ds = KgqaDataset.QALD9PLUS_UPDATED_CURWD.value # Dataset to use (includes filepaths and wikidata endpoint information)
    
    split_conf = DatasetSplit.TRAIN # Dataset split to use
    
    ## Rest of the logic
    approach_name = approach_id # copying id for modification if needed
    if use_goldentrel:
        approach_name+='_gold-entrel'
    
    run_name = f'{approach_name}__{llm_config.model_id}'
    
    wd_ep = kgqa_ds.preferred_wd_endpoint
    
    qald_file_path = kgqa_ds.split_dict[split_conf]
    
    tsv_output_path = generate_output_path(run_name, qald_file_path, 'tsv')
    
    # Generate a log directory path
    log_dir = get_log_dir(run_name, qald_file_path)
    # Load the cached property info map
    load_property_info(WIKIDATA_PROP_INFO_CACHE_FILEPATH)
    
    # Generates TSV (for readability)
    process_dataset(run_name, qald_file_path, tsv_output_path, pbsg_variants[approach_id], wd_ep, llm_config, use_goldentrel, log_dir)
    
    json_output_path = generate_output_path(run_name, qald_file_path, 'json')
    # Converts TSV to JSON (for evaluation)
    convert_basic_output(tsv_output_path, qald_file_path, json_output_path, False, wd_ep)
    
    # Evaluating results on GERBIL
    gold_dataset_label = f'{kgqa_ds.dataset_id}_{split_conf.name.lower()}'
    system_label = f'{run_name}'
    gerbil_result_path = generate_gerbil_export_path(run_name, qald_file_path)
    
    create_export_gerbil_experiment(gold_dataset_label, qald_file_path, system_label, json_output_path, 'en', gerbil_result_path, GERBIL_EXPERIMENT_URI_STORE_FILEPATH)