# Sample usage: python -m src.sparql_gen.pattern_based_sparql_generator
from src.sparql_gen.sparql_gen_common import get_verbalization_similarity, process_dataset, generate_output_path, generate_gerbil_export_path, get_log_dir, get_analysis_dir
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_patterns, get_node_label, find_next_hop_patterns
from src.kgqa_tool.llm_request import filter_common_nodes, generate_sparql_from_patterns, sparql_refinement, generate_sparql_or_expansion_indices
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL, WIKIDATA_PROP_INFO_CACHE_FILEPATH, GERBIL_EXPERIMENT_URI_STORE_FILEPATH, TRIPLE_PATTERN_N_TOP, MAX_MULTI_HOP
from src.const.llm import ChatModel
from src.util.common import read_json_file, get_last_uri_fragment, get_prefixed_id
import heapq
from src.util.qald_io import convert_basic_output
from src.analysis.pf_answer_analysis import analyse_mismatches, generate_compiled_analysis

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
        pattern_count: int,
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
        
        self.pattern_count = pattern_count
        
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
        
        # add pattern count as well when IDs are requested
        count_part = f"\tcount={self.pattern_count}" if include_id else ""

        # combine verbalization, optional ID triple, optional count, and class info
        verbalized_str = f"{verbal_part}{id_part}{count_part}\t {class_info}"
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
        pattern_count = pattern_item['count']
        edge_dir = EdgeDirection(direction_str)
        pattern_obj = NodeEdge(root_uri, root_label, prop_uri, prop_id, edge_dir, pattern_count)
        patterns_data_list.append(pattern_obj)
    
    return patterns_data_list, rejected_patterns

def load_property_info(cached_file_path):
    global PROPERTY_INFO_MAP, PROPERTY_ID_MAP
    
    PROPERTY_INFO_MAP = read_json_file(cached_file_path)
    PROPERTY_ID_MAP = {}
    for key in PROPERTY_INFO_MAP:
        prop_id = get_last_uri_fragment(key)
        PROPERTY_ID_MAP[prop_id] = key
        
def initialize_aux_values():
    load_property_info(WIKIDATA_PROP_INFO_CACHE_FILEPATH)
        

def _log_and_extract(question_text, model_config, preprocessed_input,
                     proc_logger):
    """Extract augmented text, entities and relations, logging each step."""
    proc_logger.start_action(
        "entity_relation_extraction",
        {"preprocessed_input_provided": bool(preprocessed_input)}
    )
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_dict = preprocessed_input
    else:
        aug_qtxt, entity_dict, relation_dict = find_entities_and_relations(
            question_text
        )
    proc_logger.add_step(f'Augmented text: {aug_qtxt}')
    proc_logger.add_step(f'Identified/Extracted entities: {entity_dict}')
    proc_logger.add_step(f'Identified/Extracted relations: {relation_dict}')
    proc_logger.complete_action()
    return aug_qtxt, entity_dict, relation_dict


def _filter_entities(entity_dict, using_gold_entrel, model_config,
                    proc_logger):
    """Current implementation keeps the original dict (filtering disabled)."""
    proc_logger.start_action("entity_filtering")
    # -------------------------------------------------------------
    # Original filtering logic (kept commented for easy re‑enable)
    # -------------------------------------------------------------
    # if using_gold_entrel:
    #     filter_entity_dict = entity_dict
    # else:
    #     filter_entity_dict = filter_common_nodes(
    #         question_text, entity_dict, model_config
    #     )
    # -------------------------------------------------------------
    # Filtering disabled – entities are already filtered in the linking step
    filter_entity_dict = entity_dict
    proc_logger.add_step(f'Entities to visit: {filter_entity_dict}')
    proc_logger.complete_action()
    return filter_entity_dict


def _collect_root_patterns(filter_entity_dict, wd_ep, proc_logger):
    """Collect 1‑hop patterns for each root entity."""
    proc_logger.start_action("root_entity_pattern_collection")
    patterns_data_list, visited_nodes, all_rejected_patterns = [], set(), []
    for entity_qid in filter_entity_dict.values():
        proc_logger.add_step(f'Traversing entity: {entity_qid}')
        entity_uri = f'http://www.wikidata.org/entity/{entity_qid}'
        visited_nodes.add(entity_qid)
        entity_label = get_node_label(entity_uri, wd_ep)

        patterns_list = find_1_hop_patterns(entity_uri, wd_ep)
        proc_logger.add_step(
            f'Triple patterns found for {entity_uri}: {len(patterns_list)}'
        )

        extracted, rejected = extract_patterns_data(
            entity_uri, entity_label, patterns_list, PROPERTY_ID_MAP
        )
        patterns_data_list.extend(extracted)
        all_rejected_patterns.extend(rejected)

        proc_logger.add_step(
            f'Filtered triple patterns for {entity_uri}: {len(extracted)}'
        )
    proc_logger.complete_action()
    return patterns_data_list, visited_nodes, all_rejected_patterns


def _score_and_select_top(aug_qtxt, patterns_data_list, proc_logger,
                         top_n=TRIPLE_PATTERN_N_TOP):
    """Compute verbalisation similarity and return the top‑N triples."""
    proc_logger.start_action("similarity_scoring")
    verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP
    )
    proc_logger.add_step('Computing verbalization similarity')
    priority_queue = get_verbalization_similarity(
        aug_qtxt, patterns_data_list, verbalizer
    )
    top_triples = heapq.nsmallest(top_n, priority_queue, key=lambda x: x[0])
    proc_logger.add_step(f'Selected top {len(priority_queue)} triple patterns (top-n: {top_n})')
    proc_logger.complete_action()
    return top_triples


def _generate_final_sparql(question_text, top_triples, entity_dict, relation_dict, model_config,
                          proc_logger, extra_verbalizations=None):
    """Generate SPARQL (1‑hop or after expansion)."""
    id_verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True
    )
    if extra_verbalizations is None:
        # 1‑hop case – use the selected triples only
        verbalizations = [id_verbalizer(item[1]) for item in top_triples]
    else:
        # Multi‑hop expansion – combine previously‑expanded verbalizations
        # with the newly‑selected ones.
        verbalizations = [
            id_verbalizer(item[1]) for item in top_triples
        ] +  extra_verbalizations
        
    entity_dict_str = '\n'.join([f"{k}: {v}" for k, v in entity_dict.items()])
    relation_dict_str = '\n'.join([f"{k}: {v}" for k, v in relation_dict.items()])

    sparql = generate_sparql_from_patterns(
        question_text, verbalizations, entity_dict_str, relation_dict_str, model_config, proc_logger
    )
    return sparql


def process_input_query_1hop(question_text, model_config, preprocessed_input,
                            wd_ep, using_gold_entrel, proc_logger):
    """
    One‑hop pattern‑based SPARQL generation
    """
    proc_logger.start_action(
        "process_input_query_1hop",
        {"question": question_text, "model_config": model_config.to_dict()}
    ).add_step(f'Processing question: {question_text}')

    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL

    # extraction & filtering
    aug_qtxt, entity_dict, relation_dict = _log_and_extract(
        question_text, model_config, preprocessed_input, proc_logger
    )
    filter_entity_dict = _filter_entities(
        entity_dict, using_gold_entrel, model_config, proc_logger
    )

    # pattern collection
    patterns_data_list, _, _ = _collect_root_patterns(
        filter_entity_dict, wd_ep, proc_logger
    )

    # scoring & SPARQL generation
    top_triples = _score_and_select_top(aug_qtxt, patterns_data_list, proc_logger)

    sparql = _generate_final_sparql(
        question_text, top_triples, filter_entity_dict, relation_dict, model_config, proc_logger
    )
    # -------------------------------------------------------------
    # SPARQL refinement step (commented out – enable if needed)
    # -------------------------------------------------------------
    # sparql = sparql_refinement(question_text, sparql, model_config)
    # proc_logger.add_step(f'Refined SPARQL: {sparql}')
    # -------------------------------------------------------------
    proc_logger.add_step(f'Generated SPARQL (raw): {sparql}')
    proc_logger.set_output({"sparql": sparql}).complete_action()
    return sparql


def process_input_query_2hop(question_text, model_config, preprocessed_input,
                            wd_ep, using_gold_entrel, proc_logger):
    """
    2‑hop pattern‑based SPARQL generation
    """
    proc_logger.start_action(
        "process_input_query_2hop",
        {"model_config": model_config.to_dict()}
    )

    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL

    # extraction & filtering
    aug_qtxt, entity_dict, relation_dict = _log_and_extract(
        question_text, model_config, preprocessed_input, proc_logger
    )
    filter_entity_dict = _filter_entities(
        entity_dict, using_gold_entrel, model_config, proc_logger
    )

    # pattern collection
    patterns_data_list, _, _ = _collect_root_patterns(
        filter_entity_dict, wd_ep, proc_logger
    )

    # scoring
    top_triples = _score_and_select_top(aug_qtxt, patterns_data_list, proc_logger)

    # first LLM call
    sparql, indices = generate_sparql_or_expansion_indices(
        question_text,
        [item[1].get_dr_aug_verbalization(
            PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True) for item in top_triples],
        filter_entity_dict,
        relation_dict,
        model_config, proc_logger
    )

    # expansion loop (only if needed)
    if indices and not sparql:
        proc_logger.start_action("expansion_loop")
        expanded_triple_tuples = []
        new_patterns = []

        for i, idx in enumerate(map(int, indices), start=1):
            if idx < 0 or idx >= len(top_triples):
                continue

            cur_triple = top_triples[idx]
            expanded_triple_tuples.append(cur_triple)

            edge = cur_triple[1]
            edge.assign_variable_id(i)
            proc_logger.add_step(
                f'Expanding edge #{i}: {edge.get_dr_aug_verbalization(PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True)}'
            )

            var_name = edge.variable_name
            constraint_tp = edge.get_triple_pattern()
            next_patterns = find_next_hop_patterns(constraint_tp, var_name, wd_ep)

            proc_logger.add_step(
                f'Triple patterns found for {var_name}: {len(next_patterns)}'
            )

            extracted, _ = extract_patterns_data(
                var_name, var_name, next_patterns, PROPERTY_ID_MAP
            )
            
            proc_logger.add_step(
                f'Filtered triple patterns for {var_name}: {len(extracted)}'
            )
            
            new_patterns.extend(extracted)
        
        # rank next‑top patterns
        next_top = _score_and_select_top(aug_qtxt, new_patterns, proc_logger)
        extra_verbalizations = [
            edge.get_dr_aug_verbalization(
                PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True
            ) for edge in [t[1] for t in next_top]
        ]    
            
        proc_logger.add_step(
            f'Expanded triples: {len(expanded_triple_tuples)}'
        )
        proc_logger.add_step(
            f'Extra verbalizations: {len(extra_verbalizations)}'
        )
        # generate final SPARQL using both the expanded and newly‑selected triples
        sparql = _generate_final_sparql(
            question_text,
            expanded_triple_tuples,
            filter_entity_dict,
            relation_dict,
            model_config,
            proc_logger,
            extra_verbalizations=extra_verbalizations
        )
        #proc_logger.add_step(f'Generated final SPARQL after expansion: {sparql}')
        proc_logger.complete_action()

    proc_logger.complete_action()
    return sparql

def _build_verbalizations(edges):
    """Return a list of verbalized patterns (with IDs) for the given edges."""
    id_verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True
    )
    return [id_verbalizer(e) for e in edges]

def process_input_query_multi_hop(question_text, model_config, preprocessed_input,
                                 wd_ep, using_gold_entrel, proc_logger):
    """
    Multi‑hop pattern‑based SPARQL generation
    """
    proc_logger.start_action(
        "process_input_query_multi_hop",
        {"question": question_text, "model_config": model_config.to_dict()}
    )
    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL

    # Extraction & filtering (same as the 1‑hop flow)
    aug_qtxt, entity_dict, relation_dict = _log_and_extract(
        question_text, model_config, preprocessed_input, proc_logger
    )
    filter_entity_dict = _filter_entities(
        entity_dict, using_gold_entrel, model_config, proc_logger
    )

    # Collect initial 1‑hop patterns
    patterns_data_list, _, _ = _collect_root_patterns(
        filter_entity_dict, wd_ep, proc_logger
    )
    top_triples = _score_and_select_top(aug_qtxt, patterns_data_list, proc_logger)

    # Keep a flat list of all edges that have been “accepted” so far.
    selected_edges = [t[1] for t in top_triples]

    # Iterative expansion loop (max MAX_MULTI_HOP iterations)
    for hop in range(1, MAX_MULTI_HOP + 1):
        proc_logger.start_action("hop_iteration", {"hop": hop})

        # Ask LLM whether we already have enough info or need more hops.
        verbalizations = _build_verbalizations(selected_edges)
        sparql, indices = generate_sparql_or_expansion_indices(
            question_text,
            verbalizations,
            entity_dict,
            relation_dict,
            model_config,
            proc_logger
        )

        # If LLM produced a SPARQL, stop here.
        if sparql:
            proc_logger.add_step(f"LLM returned final SPARQL at hop {hop}")
            proc_logger.complete_action()   # close hop_iteration
            proc_logger.complete_action()   # close process_input_query_multi_hop
            return sparql

        # No SPARQL yet, we must expand the requested edges.
        if not indices:
            proc_logger.add_step("LLM returned no indices – stopping expansion")
            proc_logger.complete_action()
            break   # safety‑break (should not happen, but guards against loops)

        # Expand each indexed edge
        new_patterns = []
        i = 1
        for idx_str in indices:
            idx = int(idx_str)
            if idx < 0 or idx >= len(selected_edges):
                continue

            edge = selected_edges[idx]
            cur_edge_id = i
            i = i+1
            # give the edge a fresh variable name for the next hop
            edge.assign_variable_id(cur_edge_id)

            proc_logger.add_step(
                f"Expanding edge #{idx_str}: "
                f"{edge.get_dr_aug_verbalization(PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True)}"
            )

            # Build a constraint triple (e.g. "?subject wdt:P31 ?obj .")
            constraint_tp = edge.get_triple_pattern()
            var_name = edge.variable_name

            # Retrieve next‑hop patterns from the KG.
            next_patterns = find_next_hop_patterns(constraint_tp, var_name, wd_ep)
            proc_logger.add_step(
                f"Found {len(next_patterns)} next‑hop patterns for var {var_name}"
            )

            # Extract & filter them.
            extracted, _ = extract_patterns_data(
                var_name, var_name, next_patterns, PROPERTY_ID_MAP
            )
            new_patterns.extend(extracted)

        # Rank the newly discovered patterns and add the top N
        if new_patterns:
            next_top = _score_and_select_top(aug_qtxt, new_patterns, proc_logger)
            # add only the edge objects (not the score tuples) to the pool
            selected_edges.extend([t[1] for t in next_top])
            proc_logger.add_step(
                f"Added {len(next_top)} new edges after hop {hop}"
            )
        else:
            proc_logger.add_step("No new patterns discovered – breaking")
            proc_logger.complete_action()
            break

        proc_logger.complete_action()   # close hop_iteration

    # Force SPARQL generation after reaching the hop limit
    proc_logger.add_step(
        f"Reached hop limit ({MAX_MULTI_HOP}) – forcing final SPARQL generation"
    )
    final_verbalizations = _build_verbalizations(selected_edges)

    # Use the same helper that builds the SPARQL from patterns.
    final_sparql = generate_sparql_from_patterns(
        question_text,
        final_verbalizations,
        '\n'.join([f"{k}: {v}" for k, v in entity_dict.items()]),
        '\n'.join([f"{k}: {v}" for k, v in relation_dict.items()]),
        model_config,
        proc_logger
    )
    proc_logger.set_output({"sparql": final_sparql}).complete_action()
    return final_sparql


# Example usage
if __name__ == "__main__":
    
    ## Constants
    pbsg_variants = {
        'pbsg_1hop': process_input_query_1hop,
        'pbsg_2hop': process_input_query_2hop
    }
    
    ## Configurable variables
    use_goldentrel = False # Whether to use gold entities and relations
    approach_id = 'pbsg_2hop' # identifier of the approach

    llm_config = ChatModel.GPTOSS120B.value # LLM to use
    
    kgqa_ds = KgqaDataset.QALD9PLUS_UPDATED_CURWD.value # Dataset to use (includes filepaths and wikidata endpoint information)
    
    split_conf = DatasetSplit.TEST # Dataset split to use
    
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
    
    # Analyse answers
    analysis_dir = get_analysis_dir(run_name, qald_file_path)
    
    analyse_mismatches(qald_file_path, json_output_path, log_dir, analysis_dir, llm_config)
    generate_compiled_analysis(analysis_dir, llm_config)