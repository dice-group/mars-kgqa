# Sample usage: python -m src.sparql_gen.simple_sparql_generator
from src.sparql_gen.sparql_gen_common import get_verbalization_similarity
from src.sparql_gen.simple_factoid_solver import extract_triples_data
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples
from src.kgqa_tool.llm_request import generate_simple_sparql, filter_common_nodes
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL
import heapq

def process_input_query(
    question_text, model_config, preprocessed_input,
    wd_ep, filter_entities, proc_logger, topn_count: int, *args, **kwargs
):
    # start logging this query
    proc_logger.start_action(
        "process_input_query",
        {"question": question_text, "model_config": model_config.to_dict()}
    )

    wd_ep = wd_ep if wd_ep else DEFAULT_WIKIDATA_ENDPOINT_URL

    # entity & relation extraction 
    proc_logger.start_action("entity_relation_extraction")
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_list = preprocessed_input
    else:
        aug_qtxt, entity_dict, relation_list = find_entities_and_relations(question_text)
    proc_logger.add_step(f"Augmented text: {aug_qtxt}")
    proc_logger.add_step(f"Extracted entities: {entity_dict}")
    proc_logger.add_step(f"Extracted relations: {relation_list}")
    proc_logger.complete_action()

    # entity filtering 
    proc_logger.start_action("entity_filtering")
    if filter_entities:
        filter_entity_dict = filter_common_nodes(question_text, entity_dict, model_config, proc_logger)
    else:
        filter_entity_dict = entity_dict
    proc_logger.add_step(f"Entities to visit: {filter_entity_dict}")
    proc_logger.complete_action()

    triple_data_list = []
    visited_nodes = set()

    # 1‑hop triple collection 
    proc_logger.start_action("triple_collection")
    for entity_qid in filter_entity_dict.values():
        proc_logger.add_step(f"Traversing entity: {entity_qid}")
        entity_uri = f'http://www.wikidata.org/entity/{entity_qid}'
        visited_nodes.add(entity_qid)

        triples = find_1_hop_triples(entity_uri, wd_ep)
        proc_logger.add_step(f"Found {len(triples)} raw triples for {entity_uri}")

        extracted_triples = extract_triples_data(triples)
        proc_logger.add_step(f"Kept {len(extracted_triples)} triples after extraction")
        triple_data_list.extend(extracted_triples)
    proc_logger.add_step(f"Total triples gathered: {len(triple_data_list)}")
    proc_logger.complete_action()

    # similarity scoring 
    proc_logger.start_action("similarity_scoring")
    priority_queue = get_verbalization_similarity(aug_qtxt, triple_data_list)
    proc_logger.add_step(f"Computed similarity scores for {len(triple_data_list)} triples")
    proc_logger.complete_action()

    # select top‑N triples 
    proc_logger.start_action("select_top_triples")
    
    top_triples = heapq.nsmallest(topn_count, priority_queue,
                                  key=lambda x: x[0])
    proc_logger.add_step(f"Selected top {len(top_triples)} triples")
    proc_logger.complete_action()

    # SPARQL generation 
    proc_logger.start_action("sparql_generation")
    sparql = generate_simple_sparql(question_text, top_triples, [], model_config)
    proc_logger.add_step(f"Generated SPARQL: {sparql}")
    proc_logger.complete_action()

    # finish logging for this query
    proc_logger.complete_action()
    return sparql
    
    