# Sample usage: python -m src.sparql_gen.simple_sparql_generator
from src.sparql_gen.sparql_gen_common import get_verbalization_similarity, process_dataset, generate_output_path
from src.sparql_gen.simple_factoid_solver import extract_triples_data
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples
from src.kgqa_tool.llm_request import generate_simple_sparql, filter_common_nodes
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL
import heapq
from src.const.dataset import KgqaDataset, DatasetSplit



def process_input_query(question_text, model_config, preprocessed_input, wd_ep, using_gold_entrel, proc_logger):
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
    triple_data_list = []
    visited_nodes = set()
    # Find all one-hop triples for the entities
    for entity_qid in filter_entity_dict.values():
        print(f'Traversing: {entity_qid}')
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid
        visited_nodes.add(entity_qid) # adding all the root nodes which have been extended already    
        # graph traversal tool
        triples = find_1_hop_triples(entity_uri, wd_ep)
        print(f'Triples found for {entity_uri}: {len(triples)}')
        extracted_triples = extract_triples_data(triples)
        triple_data_list.extend(extracted_triples)
        print(f'Filtered triples for {entity_uri}: {len(extracted_triples)}')
    
    print(f'Total triples to process: {len(triple_data_list)}')
    
    priority_queue = get_verbalization_similarity(aug_qtxt, triple_data_list)
    
    # Use the extracted information to generate a sparql
    context_window_size = 50
    top_triples = heapq.nsmallest(context_window_size, priority_queue, key=lambda x: x[0])
    
    sparql = generate_simple_sparql(question_text, top_triples, [], model_config)
    
    print(f'Generated SPARQL: {sparql}')
        
    return sparql


# Example usage
if __name__ == "__main__":
    approach_name = 'ssg'
    
    kgqa_ds = KgqaDataset.QALD9PLUS_UPDATED_TENTRIS.value
    
    wd_ep = kgqa_ds.preferred_wd_endpoint
    
    qald_file_path = kgqa_ds.split_dict[DatasetSplit.TEST]
    
    output_path = generate_output_path(approach_name, qald_file_path)
    
    
    # TODO: This call needs to be updated
    # process_dataset('ssg', qald_file_path, output_path, process_input_query, wd_ep,)
    
    