# Sample usage: python -m src.sparql_gen.simple_factoid_solver
from src.sparql_gen.sparql_gen_common import get_verbalization_similarity, generate_output_path
from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples
from src.kgqa_tool.llm_request import check_if_answer, filter_common_nodes
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL, ADD_NODES_EXPANSION_LIMIT, MAX_TRIES, EXTENDED_ANSWER_SEARCH_LIMIT, ANSWER_NOT_FOUND_STR, LITERAL_VAL_PREFIX, TRIPLE_VERBALIZATION_LENGTH_LIMIT
import heapq
from src.const.dataset import KgqaDataset, DatasetSplit
from src.util.process_flow_logger import ProcessFlowLogger


class TripleData:
    def __init__(self, root, subject, predicate, object, propLabel, subjectLabel, objectLabel):
        self.root = root
        self.subject = subject
        self.predicate = predicate
        self.object = object
        self.propLabel = propLabel
        self.subjectLabel = subjectLabel
        if len(objectLabel) > 0: # To handle cases where no object label is retrieved because object is literal
            self.objectLabel = objectLabel
        else:
            self.objectLabel = LITERAL_VAL_PREFIX + object

    def get_verbalization(self):
        return f"{self.subjectLabel} {self.propLabel} {self.objectLabel}"
    
    def __str__(self):
        return str({
            'root': self.root,
            'subject': self.subject,
            'predicate': self.predicate,
            'object': self.object,
            'propLabel': self.propLabel,
            'subjectLabel': self.subjectLabel,
            'objectLabel': self.objectLabel
        })
        
    def __repr__(self):
        return self.__str__()

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
        # Reject triples with very long verbalization
        if len(triple_data.get_verbalization()) > TRIPLE_VERBALIZATION_LENGTH_LIMIT:
            continue
        triple_data_list.append(triple_data)
    return triple_data_list

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
    
    verbalizer=lambda obj: obj.get_verbalization()
    
    priority_queue = get_verbalization_similarity(aug_qtxt, triple_data_list, verbalizer)
    
    
    # Test the if the answer is in top triples (context window), if not, expand it, compute similarity and add to the queue
    context_window_size = 10
    finish_search = False
    answer_tuples = []
    current_imp_context = []
    expand_count = 0
    loop_count = 0
    extended_answer_search = 0
    # Repeat until the answer is found
    while not finish_search and priority_queue:
        if expand_count > ADD_NODES_EXPANSION_LIMIT or loop_count > MAX_TRIES:
            print(f'Cannot find answer within the set traversal limit. Expanded Node Limit: {expand_count}/{ADD_NODES_EXPANSION_LIMIT}, Max Tries Limit: {loop_count}/{MAX_TRIES}')
            answer_tuples.append((0, ANSWER_NOT_FOUND_STR))
            break
        
        loop_count += 1
        # Get the top triples
        top_triples = heapq.nsmallest(context_window_size, priority_queue, key=lambda x: x[0]) # Sorts the triples based on similarity in a priority-queue
        # Ask LLM if it can find an answer in these triples
        answer_triple_index_list, next_triple_index, additional_context = check_if_answer(question_text, top_triples, current_imp_context, model_config)
        # If answers found, add them to the list
        if answer_triple_index_list is not None and len(answer_triple_index_list) > 0:
            answer_triple_index_list = [int(item) for item in answer_triple_index_list]
            # Remove out-of-index entries
            valid_indices = [idx for idx in answer_triple_index_list if 0 <= idx < len(top_triples)]
            answer_tuples.extend([(-top_triples[item][0], top_triples[item][1]) for item in valid_indices])  # removing the negative sign from before
            # remove seen entries
            [priority_queue.remove(item) for item in top_triples]
        # If no answers are found
        # But previously they were found, keep looking in the top triples and ignore everything else for now
        elif len(answer_tuples) > 0:
            # continue search in the existing triples
            loop_count=0
            if extended_answer_search > EXTENDED_ANSWER_SEARCH_LIMIT:
                print(f'Answer found: {answer_tuples}')
                break
            extended_answer_search+=1
        else :
            print(f'Answer not found in top ten')
            print(f'LLM suggested additional context: {additional_context}')
            if next_triple_index is None:
                print(f'No top ten triples worthy of expansion.')
                for item in top_triples:
                    priority_queue.remove(item)
                continue
            if next_triple_index < 0 or next_triple_index >= len(top_triples):
                print(f'LLM suggested out-of-index triple: {next_triple_index}')
                continue
            print(f'LLM suggests expanding: {top_triples[next_triple_index]}')
            # Extend the current context
            current_imp_context.extend(additional_context)
            # Expand the preferred node next and add it's triples to the list
            next_triple_tuple = top_triples[next_triple_index]
            priority_queue.remove(next_triple_tuple)
            
            triple_val = next_triple_tuple[1]
            root_uri = triple_val.root
            next_node_uri = triple_val.subject if root_uri == triple_val.object else triple_val.object
            if next_node_uri in visited_nodes:
                continue
            visited_nodes.add(next_node_uri)
            expand_count+=1
            new_triples = find_1_hop_triples(next_node_uri, wd_ep)
            new_trip_data_list = extract_triples_data(new_triples)
            new_trip_sim_list = get_verbalization_similarity(aug_qtxt, new_trip_data_list, verbalizer)
            priority_queue.extend(new_trip_sim_list)
        
    return answer_tuples


# Example usage
if __name__ == "__main__":
    
    approach_name = 'sfs'
    
    kgqa_ds = KgqaDataset.QALD9PLUS_UPDATED_TENTRIS.value
    
    wd_ep = kgqa_ds.preferred_wd_endpoint
    
    qald_file_path = kgqa_ds.split_dict[DatasetSplit.TEST]
    
    output_path = generate_output_path(approach_name, qald_file_path)
    
    # TODO: This call needs to be updated
    # process_dataset(approach_name, qald_file_path, output_path, process_input_query, wd_ep)
    