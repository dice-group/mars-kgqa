# Sample usage: python -m src.basic_factoid_solver
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples
from src.kgqa_tool.llm_request import check_if_answer, filter_common_nodes
from src.util.llm import get_embeddings
from src.const.llm import DEFAULT_CHAT_LLM_CONFIG
from src.const.misc import WIKIDATA_ENDPOINT_URL
from src.util.common import dot, read_dataset
import heapq
import csv


class TripleData:
    def __init__(self, root, subject, predicate, object, propLabel, subjectLabel, objectLabel):
        self.root = root
        self.subject = subject
        self.predicate = predicate
        self.object = object
        self.propLabel = propLabel
        self.subjectLabel = subjectLabel
        self.objectLabel = objectLabel

    def get_verbalization(self):
        return f"{self.subjectLabel} {self.propLabel} {self.objectLabel}"

def extract_triples_data(triples_dict):
    # Process the dictionary and create a list of triple objects with verbalization function
    triple_data_list = []
    for triple in triples_dict:
        root = triple['root']
        subject = triple['subject']
        predicate = triple['predicate']
        object = triple['object']
        propLabel = triple['propLabel']
        subjectLabel = triple['subjectLabel']
        objectLabel = triple['objectLabel']
        triple_data = TripleData(root, subject, predicate, object, propLabel, subjectLabel, objectLabel)
        triple_data_list.append(triple_data)
    return triple_data_list


def get_triples_similarity(aug_qtxt, triple_data_list, batch_size = 20):
    batched_triple_data = []

    # Split triple_data_list into batches
    for i in range(0, len(triple_data_list), batch_size):
        batch = triple_data_list[i:i + batch_size]
        batched_triple_data.append(batch)

    # Fetch embeddings
    triple_data_embd_list = []
    for triple_data_batch in batched_triple_data:
        # Build text list
        cur_text_batch = [trip_data.get_verbalization() for trip_data in triple_data_batch]
        # llm request tool
        cur_embd_batch = get_embeddings(cur_text_batch)
        triple_data_embd_list.extend(cur_embd_batch)

    # Compute cosine similarity of the verbalized triples to the augmented input
    query_embedding = get_embeddings([aug_qtxt])[0]
    triple_similarity_list = []
    for triple_embd in triple_data_embd_list:
        triple_similarity_list.append(dot(query_embedding, triple_embd)) # as mentioned in https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe-GGUF

    # heapq uses min-heap by default, so we multiply the similarity score by -1
    triple_cossim_list = [(-similarity, triple_data) for similarity, triple_data in zip(triple_similarity_list, triple_data_list)]
    return triple_cossim_list

def process_input_query(question_txt, model_config, preprocessed_input=None):
    # Retrieve entities and relations for the input question
    if preprocessed_input:
        aug_qtxt, entity_dict, relation_list = preprocessed_input # unpack
    else:
        aug_qtxt, entity_dict, relation_list = find_entities_and_relations(question_txt)
        
    # Filter entity dictionary to remove entities that will lead to too many child nodes
    filter_entity_dict = filter_common_nodes(question_txt, entity_dict, model_config)

    triple_data_list = []
    
    visited_nodes = set()
    # Find all one-hop triples for the entities
    for entity_qid in filter_entity_dict.values():
        entity_uri = 'http://www.wikidata.org/entity/' + entity_qid    
        # graph traversal tool
        triples = find_1_hop_triples(entity_uri, WIKIDATA_ENDPOINT_URL)
        triple_data_list.extend(extract_triples_data(triples))
        visited_nodes.add(entity_uri)
    
    priority_queue = get_triples_similarity(aug_qtxt, triple_data_list)
    

    # Test the if the answer is in top triples (context window), if not, expand it, compute similarity and add to the queue
    context_window_size = 10
    found_answer = False
    while not found_answer and priority_queue:
        # Get the top triples
        top_triples = heapq.nsmallest(context_window_size, priority_queue) # Sorts the triples based on similarity in a priority-queue
        # Ask LLM if it can find an answer in these triples
        answer_triple, next_triple_index = check_if_answer(question_txt, top_triples, model_config)
        
        if answer_triple:
            found_answer = True
        else :
            # Expand the preferred node next and add it's triples to the list
            next_triple = top_triples[next_triple_index]
            priority_queue.remove(next_triple)
            next_node_uri = next_triple.root
            if next_node_uri in visited_nodes:
                continue
            
            new_triples = find_1_hop_triples(next_node_uri, WIKIDATA_ENDPOINT_URL)
            new_trip_sim_list = get_triples_similarity(aug_qtxt, new_triples)
            priority_queue.extend(new_trip_sim_list)
      
    # Repeat until the answer is found
    return answer_triple


def save_answers_as_tsv(answers_dict, file_path):
    with open(file_path, 'w', newline='', encoding='utf-8') as tsvfile:
        writer = csv.writer(tsvfile, delimiter='\t')
        # Write header
        writer.writerow(['Question ID', 'Answer'])
        # Write data
        for question_id, answer in answers_dict.items():
            writer.writerow([question_id, answer])

# Example usage
if __name__ == "__main__":
    qald_file_path = "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent.json"
    # Read the qald9 preprocessed file
    qald_json = read_dataset(qald_file_path)
    
    answers_dict = dict()
    # For each question
    for question_item in qald_json['questions']:
        question_id = question_item['id']
        # extract aug_text, extracted_ents, extracted_rels
        aug_text = question_item['augmented_seq']
        ent_dict = question_item['found_ent']
        rel_dict = question_item['found_rel']
        
         # Extract the English question text
        question_text = next((q['string'] for q in question_item['question'] if q['language'] == 'en'), None)
        # send to process_input_query
        cur_answer = process_input_query(aug_text, DEFAULT_CHAT_LLM_CONFIG, (aug_text, ent_dict, rel_dict))
        
        answers_dict[question_id] = cur_answer
    
    # Save answers dict as tsv
    save_answers_as_tsv(answers_dict, "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent_answers.tsv")
    
    