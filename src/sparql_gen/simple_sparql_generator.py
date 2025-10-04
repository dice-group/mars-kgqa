# Sample usage: python -m src.sparql_gen.simple_sparql_generator
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.llm_request import generate_simple_sparql

def process_input_query(
    question_text, model_config, preprocessed_input,
    wd_ep, filter_entities, proc_logger, *args, **kwargs
):
    # start logging this query
    proc_logger.start_action(
        "process_input_query",
        {"question": question_text, "model_config": model_config.to_dict()}
    )

    # Entity & relation extraction (no hop logic)
    proc_logger.start_action("entity_relation_extraction")
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_dict = preprocessed_input
    else:
        aug_qtxt, entity_dict, relation_dict = find_entities_and_relations(question_text)
    proc_logger.add_step(f"Augmented text: {aug_qtxt}")
    proc_logger.add_step(f"Extracted entities: {entity_dict}")
    proc_logger.add_step(f"Extracted relations: {relation_dict}")
    proc_logger.complete_action()
    
    if kwargs.get('use_aug_sim'):
        proc_logger.add_step(f"Using augmented text instead of question.")
        question_text = aug_qtxt

    # Direct SPARQL generation from question, entities & relations
    proc_logger.start_action("sparql_generation")
    # The baseline generator only needs the question, the entity dict and the
    # relation dict. No triple collection or similarity scoring is performed.
    sparql = generate_simple_sparql(
        question_text,
        '\n'.join([f"{k}: {v}" for k, v in entity_dict.items()]),
        '\n'.join([f"{k}: {v}" for k, v in relation_dict.items()]),
        model_config,
        proc_logger
    )
    proc_logger.add_step(f"Generated SPARQL: {sparql}")
    proc_logger.complete_action()

    # finish logging for this query
    proc_logger.complete_action()
    return sparql
    
    