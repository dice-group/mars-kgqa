# Sample usage: python -m src.simple_sparql_generator
from src.simple_factoid_solver import extract_triples_data, get_triples_similarity, save_answers_as_tsv
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples
from src.kgqa_tool.llm_request import generate_simple_sparql, filter_common_nodes
from src.const.llm import DEFAULT_CHAT_LLM_CONFIG
from src.const.misc import WIKIDATA_ENDPOINT_URL
from src.util.common import read_json_file
import heapq
from tqdm import tqdm



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
    triple_data_list = []
    visited_nodes = set()
    # Find all one-hop triples for the entities
    for entity_qid in filter_entity_dict.values():
        print(f'Traversing: {entity_qid}')
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid
        visited_nodes.add(entity_qid) # adding all the root nodes which have been extended already    
        # graph traversal tool
        triples = find_1_hop_triples(entity_uri, WIKIDATA_ENDPOINT_URL)
        print(f'Triples found for {entity_uri}: {len(triples)}')
        triple_data_list.extend(extract_triples_data(triples))
    
    print(f'Total triples to process: {len(triple_data_list)}')
    
    priority_queue = get_triples_similarity(aug_qtxt, triple_data_list)
    
    # Use the extracted information to generate a sparql
    context_window_size = 50
    top_triples = heapq.nsmallest(context_window_size, priority_queue, key=lambda x: x[0])
    
    sparql = generate_simple_sparql(question_text, top_triples, [], model_config)
    
    print(f'Generated SPARQL: {sparql}')
        
    return sparql


# Example usage
if __name__ == "__main__":
    #qald_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/aug_gold.json"
    qald_file_path = "data_dir/processed_kgqa_ds/qald10/test/aug_gold.json"
    # Read the qald9 preprocessed file
    qald_json = read_json_file(qald_file_path)
    
    answers_dict = dict()
    # For each question
    for question_item in tqdm(qald_json['questions'],desc='Processed Questions'):
        question_id = question_item['id']
        # extract aug_text, extracted_ents, extracted_rels
        aug_text = question_item['augmented_seq']
        ent_dict = question_item['found_ent']
        rel_dict = question_item['found_rel']
        
         # Extract the English question text
        question_text = next((q['string'] for q in question_item['question'] if q['language'] == 'en'), None)
        # send to process_input_query
        cur_generated_sparql = process_input_query(question_text, DEFAULT_CHAT_LLM_CONFIG, (aug_text, ent_dict, rel_dict))
        
        answers_dict[question_id] = cur_generated_sparql
    
    #output_path = "data_dir/processed_kgqa_ds/qald9plus/test/prediction/tsv/aug_pred_sparql.tsv"
    output_path = "data_dir/processed_kgqa_ds/qald10/test/prediction/tsv/aug_pred_sparql.tsv"
    
    # Save answers dict as tsv
    save_answers_as_tsv(answers_dict, output_path)
    
    