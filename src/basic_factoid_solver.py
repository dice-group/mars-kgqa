from src.kgqa_tool.entity_retrieval import find_entities_and_relations
from src.kgqa_tool.graph_traversal import find_1_hop_triples
from src.util.llm import get_embeddings
from src.const.misc import WIKIDATA_ENDPOINT_URL

def extract_triples_data(triples_dict):
    # TODO: Process the dictionary and create a list of triple objects with verbalization function
    raise NotImplementedError()

def process_input_query(question_txt):
    # Retrieve entities and relations for the input question
    aug_qtxt, entity_list, relation_list = find_entities_and_relations(question_txt)

    triple_data_list = []
    # Find all one-hop triples for the entities
    for entity_uri in entity_list:    
        # graph traversal tool
        triples = find_1_hop_triples(entity_uri, WIKIDATA_ENDPOINT_URL)
        triple_data_list.extend(extract_triples_data(triples))
    
    batch_size = 20
    batched_triple_data = []

    # Split triple_data_list into batches
    for i in range(0, len(triple_data_list), batch_size):
        batch = triple_data_list[i:i + batch_size]
        batched_triple_data.append(batch)
    
    # Fetch embeddings
    triple_data_embd_list = []
    for triple_data_batch in batched_triple_data:
        # TODO: build text list
        cur_text_batch = [trip_data.get_verbalization() for trip_data in triple_data_batch]
        # llm request tool
        cur_embd_batch = get_embeddings(cur_text_batch)
        triple_data_embd_list.extend(cur_embd_batch)
    # Compute cosine similarity of the verbalized triples to the augmented input
    
    # Sort the triples based on similarity in a priority-queue
        # util function

    # Test the if the answer is in top triples (context window), if not, expand it, compute similarity and add to the queue
        # llm request
        # graph traversal
        # util

    # Repeat until the answer is found