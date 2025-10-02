# Sample usage: python -m src.sparql_gen.pattern_based_sparql_generator
from src.sparql_gen.sparql_gen_common import get_verbalization_similarity, process_dataset, generate_output_path, generate_gerbil_export_path, get_log_dir, get_analysis_dir
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_patterns, get_node_label, find_next_hop_patterns, find_concrete_examples
from src.kgqa_tool.llm_request import filter_common_nodes, generate_sparql_from_patterns, sparql_refinement, generate_sparql_or_expansion_indices, estimate_mhop
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL, WIKIDATA_PROP_INFO_CACHE_FILEPATH, GERBIL_EXPERIMENT_URI_STORE_FILEPATH, TRIPLE_PATTERN_N_TOP, MAX_MULTI_HOP
from src.const.llm import ChatModel
from src.util.common import read_json_file, get_last_uri_fragment, get_prefixed_id
import heapq
from src.util.qald_io import convert_basic_output
from src.analysis.pf_answer_analysis import analyse_mismatches, generate_compiled_analysis

from enum import Enum, auto
from src.const.dataset import KgqaDataset, DatasetSplit
from src.util.gerbil import create_export_gerbil_experiment
from src.util.process_flow_logger import ProcessFlowLogger
import re
import copy
import json

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
            
    def get_dr_aug_verbalization(self, prop_id_map=PROPERTY_ID_MAP, prop_info_map=PROPERTY_INFO_MAP, include_id=False, include_count=False, conc_ex_map = {}, include_concrete_ex=False, include_class_info=False):
        
        prop_ent_uri = prop_id_map[self.relation_id]

        # get the property label
        prop_label = prop_info_map[prop_ent_uri]['label']
        # get the domain label(s)
        dom_label_list = [dom_item['label'] for dom_item in prop_info_map[prop_ent_uri]['domains']]
        # get the range label(s)
        range_label_list = [range_item['label'] for range_item in prop_info_map[prop_ent_uri]['ranges']]
        
        node_prefixed_repr = self.node_id if self.node_is_var else get_prefixed_id(self.node_id)
        
        if self.direction == EdgeDirection.OUTGOING:
            # verbal part: "<node_label> <property_label> ?object"
            verbal_part = f"'{self.node_label}' '{prop_label}' {self.variable_name}"
            # ID part (only if requested)
            id_part = f"\t{node_prefixed_repr} {get_prefixed_id(self.relation_uri)} {self.variable_name}" if include_id else ""
            subject_var = node_prefixed_repr
            object_var = self.variable_name
        else:  # EdgeDirection.INCOMING
            # verbal part: "?subject <property_label> <node_label>"
            verbal_part = f"{self.variable_name} '{prop_label}' '{self.node_label}'"
            # ID part (only if requested)
            id_part = f"\t{self.variable_name} {get_prefixed_id(self.relation_uri)} {node_prefixed_repr}" if include_id else ""
            subject_var = self.variable_name
            object_var = node_prefixed_repr
        
        class_info = ''
        # Assigning variable name besides subject and object for better clarity 
        if include_class_info:
            class_info = (
                f"\t (possible DOMAIN ({subject_var}) classes: {','.join(dom_label_list)}), "
                f"(possible RANGE ({object_var}) classes: {','.join(range_label_list)})"
            )
        
        # add pattern count if requested
        count_part = f"\tcount={self.pattern_count}" if include_count else ""
        
        # add concrete example if requested
        concrete_examples_part = ''
        if include_concrete_ex:
            edge_key = _build_cache_key(self)
            conc_examples = conc_ex_map[edge_key][0]
            example_dict_list = []
            for item in conc_examples:
                ex_id = item[self.variable_name]
                ex_label = item['displayLabel']
                is_literal = ex_id == ex_label
                if is_literal:
                    example_dict_list.append({'value': ex_id})
                else:
                    example_dict_list.append({'id': get_prefixed_id(ex_id), 'label': ex_label})
            concrete_examples_part = f'\t{self.variable_name} examples: {','.join(json.dumps(d) for d in example_dict_list)}'

        # combine verbalization, optional ID triple, optional count, and class info
        verbalized_str = f"{verbal_part}{id_part}{count_part}{concrete_examples_part}{class_info}"
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


def _filter_entities(question_text, entity_dict, filter_entities, model_config, proc_logger):
    proc_logger.start_action("entity_filtering")
    
    if filter_entities:
        filter_entity_dict = filter_common_nodes(question_text, entity_dict, model_config, proc_logger)
    else:
        filter_entity_dict = entity_dict
        
    filter_entity_dict = entity_dict
    proc_logger.add_step(f'Entities to visit: {filter_entity_dict}')
    proc_logger.complete_action()
    return filter_entity_dict


def _collect_root_patterns(filter_entity_dict, wd_ep, proc_logger, use_sleep=False):
    """Collect 1‑hop patterns for each root entity."""
    proc_logger.start_action("root_entity_pattern_collection")
    patterns_data_list, visited_nodes, all_rejected_patterns = [], set(), []
    for entity_qid in filter_entity_dict.values():
        proc_logger.add_step(f'Traversing entity: {entity_qid}')
        entity_uri = f'http://www.wikidata.org/entity/{entity_qid}'
        visited_nodes.add(entity_qid)
        entity_label = get_node_label(entity_uri, wd_ep, use_sleep=use_sleep)

        patterns_list = find_1_hop_patterns(entity_uri, wd_ep, use_sleep=use_sleep)
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
                         top_n=TRIPLE_PATTERN_N_TOP, use_class_info=False):
    """Compute verbalisation similarity and return the top‑N triples."""
    proc_logger.start_action("similarity_scoring")
    verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP, include_class_info=use_class_info
    )
    proc_logger.add_step('Computing verbalization similarity')
    priority_queue = get_verbalization_similarity(
        aug_qtxt, patterns_data_list, verbalizer
    )
    top_triples = heapq.nsmallest(top_n, priority_queue, key=lambda x: x[0])
    proc_logger.add_step(f'Selected top {len(top_triples)} triple patterns (top-n: {top_n})')
    proc_logger.complete_action()
    return top_triples

def _construct_paths(edge_list):
    """
    Build ordered paths (lists of Edge objects) from a flat list of edges.
    """
    # Categorise edges
    root_edges = []
    intermediate_map = {}
    leaf_map = {}

    var_with_idx_pat = re.compile(r'^\?\w+_\d+$')
    var_no_idx_pat    = re.compile(r'^\?\w+$')

    for edge in edge_list:
        var_name = edge.variable_name
        node_is_var = isinstance(edge.node_id, str) and edge.node_id.startswith("?")

        # Root node
        if var_with_idx_pat.match(var_name) and not node_is_var:
            root_edges.append(edge)

        # Intermediate node
        elif var_with_idx_pat.match(var_name) and node_is_var:
            parent = edge.node_id
            intermediate_map.setdefault(parent, []).append((var_name, edge))

        # Leaf node
        elif var_no_idx_pat.match(var_name):
            parent = edge.node_id
            leaf_map.setdefault(parent, []).append((var_name, edge))

        else:
            raise ValueError(
                f"Unrecognised edge pattern: var={var_name}, node_id={edge.node_id}"
            )

    # Initialise paths with root edges
    paths = [[root] for root in root_edges]

    # Expand intermediate nodes iteratively
    while intermediate_map:
        extended = False
        new_paths = []

        for path in paths:
            last_edge = path[-1]
            children = intermediate_map.get(last_edge.variable_name, [])

            if children:
                extended = True
                for child_var, child_edge in children:
                    new_paths.append(path + [child_edge])
                # Mark this parent as processed
                del intermediate_map[last_edge.variable_name]
            else:
                new_paths.append(path)

        paths = new_paths

        if not extended:
            # No further expansion possible – break to avoid infinite loop
            break

    if intermediate_map:
        # If anything is left we couldn’t resolve a parent → raise early
        raise RuntimeError(
            f"Unresolved intermediate nodes remain: {list(intermediate_map.keys())}"
        )

    # Attach leaf nodes
    for parent_var, leaf_entries in list(leaf_map.items()):
        matching_paths = [p for p in paths if p[-1].variable_name == parent_var]

        if matching_paths:
            # Extend each matching path with every leaf child (branching if needed)
            for path in matching_paths:
                for leaf_var, leaf_edge in leaf_entries:
                    paths.append(path + [leaf_edge])
                # Remove the original path (will be superseded by extensions)
                paths.remove(path)
        else:
            # No parent found → treat leaf as a root‑only path
            for leaf_var, leaf_edge in leaf_entries:
                paths.append([leaf_edge])

        del leaf_map[parent_var]

    return paths

def _build_cache_key(edge):
    cache_key = (
        edge.node_id,
        edge.relation_uri,
        edge.variable_name,
        edge.direction,
    )
    return cache_key

def _update_con_ex_and_contraints_cache(paths_list, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=False):
    # Iterate over every path (list of Edge objects)
    for path in paths_list:
        # Keep track of the constraint triples
        accumulated_constraints = []

        for edge in path:
            # Build a hashable cache key for the edge
            cache_key = _build_cache_key(edge)

            # If we already have examples for this edge, just reuse them
            if cache_key in conc_ex_and_constraints_cache:
                # Append cached examples to the accumulated constraints for later edges
                accumulated_constraints.append(conc_ex_and_constraints_cache[cache_key][1])
                continue

            # Build a constraint triple (e.g. "?subject wdt:P31 ?obj .")
            triple_pattern = edge.get_triple_pattern()

            # Combine with constraints from preceding edges in the path.
            if accumulated_constraints:
                # Pre‑pend previous constraints so the KG query respects the full path
                constraints_str = " \n ".join(accumulated_constraints + [triple_pattern])
            else:
                constraints_str = triple_pattern

            # Query the KG for a few concrete examples.
            examples = []
            if conc_ex_limit > 0:
                examples = find_concrete_examples(
                    constraints_str,
                    edge.variable_name,
                    wd_ep,
                    limit=conc_ex_limit,
                    use_sleep=use_sleep
                )

            conc_ex_and_constraints_cache[cache_key] = (examples, constraints_str, copy.deepcopy(accumulated_constraints))

            accumulated_constraints.append(triple_pattern)

def _update_edge_cache(edges, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=False):
    # Build paths
    paths = _construct_paths(edges)
    # Build concrete examples for each edge in path (maintain cache for previously seen edges)
    _update_con_ex_and_contraints_cache(paths, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=use_sleep)

def _build_verbalizations(edges, include_pattern_count, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=False, use_class_info=False):
    """Return a list of verbalized patterns (with IDs) for the given edges."""
    # Update the edge cache in case something is missing
    _update_edge_cache(edges, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=use_sleep)
    use_conc_ex = conc_ex_limit > 0
    
    id_verbalizer = lambda obj: obj.get_dr_aug_verbalization(
        PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True, include_pattern_count, 
        conc_ex_map=conc_ex_and_constraints_cache, include_concrete_ex=use_conc_ex, include_class_info=use_class_info
    )
    return [id_verbalizer(e) for e in edges]

def process_input_query_multi_hop(
    question_text: str,
    model_config: ChatModel,
    preprocessed_input: any,
    wd_ep: str,
    filter_entities: bool,
    proc_logger: ProcessFlowLogger,
    topn_count: int,
    mhop_limit: int,
    include_pattern_count: bool,
    refine_sparql: bool,
    use_aug_sim: bool,
    use_sleep:bool,
    conc_ex_limit: int,
    use_class_info: bool,
):
    """Multi‑hop pattern‑based SPARQL generation with configurable limits."""
    
    # start logging for this query
    proc_logger.start_action(
        "process_input_query_multi_hop",
        {
            "question": question_text,
            "model_config": model_config.to_dict(),
            "wd_endpoint": wd_ep,
            "filter_entities": filter_entities,
            "top_n": topn_count,
            "max_hops": mhop_limit,
            "include_pattern_count": include_pattern_count,
            "refine_sparql": refine_sparql,
            "use_aug_sim": use_aug_sim,
            "use_sleep": use_sleep,
            "conc_ex_limit": conc_ex_limit,
            "use_class_info": use_class_info,
        }
    )
    
    use_conc_ex = False
    if conc_ex_limit > 0:
        use_conc_ex = True
    
    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL
    # To introduce concrete examples from patterns
    conc_ex_and_constraints_cache = dict() # This needs to be refreshed for every new question
    # extraction & filtering
    aug_qtxt, entity_dict, relation_dict = _log_and_extract(
        question_text, model_config, preprocessed_input, proc_logger
    )
    filter_entity_dict = _filter_entities(
        question_text, entity_dict, filter_entities, model_config, proc_logger
    )
    
    # resolve mhop-limit
    if mhop_limit < 0:
        # call llm for mhop estimation
        mhop_limit = estimate_mhop(aug_qtxt, 
            '\n'.join([f"{k}: {v}" for k, v in entity_dict.items()]),
            '\n'.join([f"{k}: {v}" for k, v in relation_dict.items()]),
            model_config, proc_logger)
        proc_logger.add_step(f"Estimate mhop_limit: {mhop_limit}")
    
    
    if not use_aug_sim:
        aug_qtxt = question_text # overwrite augmented text if it is not required

    # collect initial 1‑hop patterns
    patterns_data_list, _, _ = _collect_root_patterns(
        filter_entity_dict, wd_ep, proc_logger, use_sleep=use_sleep
    )
    top_triples = _score_and_select_top(
        aug_qtxt, patterns_data_list, proc_logger, top_n=topn_count, use_class_info=False # No need for class info here
    )
    # postfix number for variables to make it unique
    var_post_num = 1
    # keep accepted edges
    selected_edges = []
    for t in top_triples:
        cur_edge = t[1]
        cur_edge.assign_variable_id(var_post_num)
        var_post_num += 1
        selected_edges.append(cur_edge)
    
    
    if mhop_limit == 1:
        proc_logger.add_step("mhop_limit=1 – generating final SPARQL directly")
        final_verbalizations = _build_verbalizations(selected_edges, include_pattern_count, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=use_sleep, use_class_info=use_class_info)
        final_sparql = generate_sparql_from_patterns(
            question_text,
            final_verbalizations,
            '\n'.join([f"{k}: {v}" for k, v in entity_dict.items()]),
            '\n'.join([f"{k}: {v}" for k, v in relation_dict.items()]),
            model_config,
            proc_logger,
        )
        if refine_sparql:
            final_sparql = sparql_refinement(question_text, final_sparql, model_config, proc_logger)
        proc_logger.complete_action()
        return final_sparql
    
    # Track edges that have already been expanded (by their variable name)
    expanded_edges = set()
    # i = 1
    # iterative expansion (max mhop_limit iterations)
    for hop in range(1, mhop_limit + 1):
        proc_logger.start_action("hop_iteration", {"hop": hop})

        verbalizations = _build_verbalizations(selected_edges, include_pattern_count, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=use_sleep, use_class_info=use_class_info)
        sparql, indices = generate_sparql_or_expansion_indices(
            question_text,
            verbalizations,
            entity_dict,
            relation_dict,
            model_config,
            proc_logger,
        )

        # if LLM returns final SPARQL, optionally refine and finish
        if sparql:
            if refine_sparql:
                sparql = sparql_refinement(question_text, sparql, model_config, proc_logger)
            proc_logger.add_step(f"LLM returned final SPARQL at hop {hop}")
            proc_logger.complete_action()   # close hop_iteration
            proc_logger.complete_action()   # close process_input_query_multi_hop
            return sparql

        # No SPARQL yet, we must expand the requested edges.
        if not indices:
            proc_logger.add_step("LLM returned no indices – stopping expansion")
            proc_logger.complete_action()   # close hop_iteration
            break   # safety‑break (should not happen, but guards against loops)

        # Expand each indexed edge
        new_patterns = []
        
        for idx_str in indices:
            try:
                idx = int(idx_str)
            except ValueError:
                # Skip malformed index strings
                proc_logger.add_step(f"Skipping malformed index {idx_str}")
                continue
            if idx < 0 or idx >= len(selected_edges):
                proc_logger.add_step(f"Skipping invalid index {idx_str}")
                continue
            
            edge = selected_edges[idx]

            # Skip edges that were already expanded
            if edge.variable_name in expanded_edges:
                proc_logger.add_step(
                    f"Skipping already‑expanded edge #{idx_str} (var {edge.variable_name})"
                )
                continue
            
            # cur_edge_id = i
            # i = i+1
            # # give the edge a fresh variable name for the next hop
            # edge.assign_variable_id(cur_edge_id)

            # Build constraint with the full path followed so far
            _update_edge_cache(selected_edges, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=use_sleep)
            cache_key = _build_cache_key(edge)
            constraint_tp = conc_ex_and_constraints_cache[cache_key][1]
            
            var_name = edge.variable_name
            
            proc_logger.add_step(
                f"Expanding edge #{idx_str}: {edge.get_dr_aug_verbalization(PROPERTY_ID_MAP, PROPERTY_INFO_MAP, True, True, conc_ex_map=conc_ex_and_constraints_cache, include_concrete_ex=use_conc_ex, include_class_info=use_class_info)}"
            )

            # Retrieve next‑hop patterns from the KG.
            next_patterns = find_next_hop_patterns(constraint_tp, var_name, wd_ep, use_sleep=use_sleep)
            
            proc_logger.add_step(
                f'Triple patterns found for {var_name}: {len(next_patterns)}'
            )
            # Mark as expanded before we start the next‑hop search
            expanded_edges.add(edge.variable_name)

            # Extract & filter them.
            extracted, _ = extract_patterns_data(
                var_name, var_name, next_patterns, PROPERTY_ID_MAP
            )
            proc_logger.add_step(
                f'Filtered triple patterns for {var_name}: {len(extracted)}'
            )
            new_patterns.extend(extracted)

        # Rank the newly discovered patterns and add the top N
        if new_patterns:
            next_top = _score_and_select_top(
                aug_qtxt, new_patterns, proc_logger, top_n=topn_count, use_class_info=False # No need for class info here
            )
            for nt in next_top:
                cur_edge = nt[1]
                cur_edge.assign_variable_id(var_post_num)
                var_post_num += 1
                selected_edges.append(cur_edge)
            #selected_edges.extend([t[1] for t in next_top])
            proc_logger.add_step(
                f"Added {len(next_top)} new edges after hop {hop}"
            )
        else:
            proc_logger.add_step("No new patterns discovered – breaking")
            proc_logger.complete_action()    # close hop_iteration
            break

        proc_logger.complete_action()   # close hop_iteration

    # forced final SPARQL after reaching hop limit
    proc_logger.add_step(
        f"Reached hop limit ({mhop_limit}) – generating final SPARQL"
    )
    final_verbalizations = _build_verbalizations(selected_edges, include_pattern_count, conc_ex_limit, conc_ex_and_constraints_cache, wd_ep, use_sleep=use_sleep, use_class_info=use_class_info)
    final_sparql = generate_sparql_from_patterns(
        question_text,
        final_verbalizations,
        '\n'.join([f"{k}: {v}" for k, v in entity_dict.items()]),
        '\n'.join([f"{k}: {v}" for k, v in relation_dict.items()]),
        model_config,
        proc_logger,
    )
    if refine_sparql:
        final_sparql = sparql_refinement(question_text, final_sparql, model_config, proc_logger)
    proc_logger.complete_action() # close process_input_query_multi_hop
    return final_sparql


# Example usage
if __name__ == "__main__":
    
    ## Constants
    pbsg_variants = {
        'pbsg_1hop': lambda *args, **kw: process_input_query_multi_hop(*args, mhop_limit=1, **kw),
        'pbsg_2hop': lambda *args, **kw: process_input_query_multi_hop(*args, mhop_limit=2, **kw),
        'pbsg_mhop': lambda *args, **kw: process_input_query_multi_hop(*args, mhop_limit=MAX_MULTI_HOP, **kw),   
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