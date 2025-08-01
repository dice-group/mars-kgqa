
from src.util.llm import prompt_chat_llm


def generate_baseline_sparql(question_txt, model_config):

    check_prompt = f"""Given a question generate a Wikidata SPARQL to answer the question. Strictly follow the provided "Answer Format", do not write anything else. 

    Question: {question_txt}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    llm_resp_text = prompt_chat_llm(check_prompt, None, model_config.get_static_instance(), model_config.model_id)
    print(f'LLM Response: {llm_resp_text}')
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        
    return answer_sparql

def generate_simple_sparql(question_txt, top_triples, context_list, model_config):
    # Check if the triple contains the answer to the question
    triples_str = ''
    for triple_tuple in top_triples:
        triple_item = triple_tuple[1]
        # Subject details
        sub_uri = triple_item.subject
        # Predicate details
        pred_uri = triple_item.predicate
        # Object details
        obj_val = triple_item.object
        
        triple_line = f'{sub_uri}\t {pred_uri}\t {obj_val}\t "{triple_item.get_verbalization()}"\n'
        triples_str+=triple_line
    
    context_str = '\n'.join(context_list)

    check_prompt = f"""Given a question and a table of extracted related triples alongside their verbalization from Wikidata, generate a SPARQL to answer the question. Strictly follow the provided "Answer Format", do not write anything else. 

    Question: {question_txt}

    ### Triples table:
    subject\t predicate\t object\t verbalization
    {triples_str}
    
    ### Important context:
    
    {context_str}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    llm_resp_text = prompt_chat_llm(check_prompt, None, model_config.get_static_instance(), model_config.model_id)
    print(f'LLM Response: {llm_resp_text}')
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        
    return answer_sparql

def check_if_answer(question_txt, top_triples, context_list, model_config):
    # Check if the triple contains the answer to the question

    triples_str = '\n'.join([triple_data.get_verbalization() for _, triple_data in top_triples])
    context_str = '\n'.join(context_list)

    check_prompt = f"""Look at the following triples and added important context and then either use the provided Answer Format if you find one or more triples that directly answer the question or use Next Triple Format if no answer is found. Only choose the triples that actually fit as an answer, do not write anything else, use only single format.

    Question: {question_txt}

    Triples list:
    {triples_str}
    
    Important context:
    
    {context_str}

    ---

    Answer Format:

    Answer: <place the comma-separated index of the answer triples here, use 0-indexing>

    ---

    Next Triple Format:

    Next Triple Index: <place the index of the best next triple to consider here, use 0-indexing, the object must not be a literal, put '-1' if no triples fit the criteria>
    New Important Context: <if there are triples that might be very helpful for future context, write them in a comma separated manner here. Be mindful of only choosing triples that are really important.>

    """
    llm_resp_text = prompt_chat_llm(check_prompt, None, model_config.get_static_instance(), model_config.model_id)

    # Parse the LLM response
    if "Answer:" in llm_resp_text:
        answer_triple_list = llm_resp_text.split("Answer:")[1].strip().split(',')
        return answer_triple_list, None, None
    elif "Next Triple Index:" in llm_resp_text:
        resp_items = llm_resp_text.split('\n')
        # find the next triple index
        next_trip_resp = resp_items[0]
        next_triple_index = int(next_trip_resp.split("Next Triple Index:")[1].strip())
        if next_triple_index == -1:
            next_triple_index = None
        # extracting additional context
        add_context_resp = resp_items[1]
        additional_context = add_context_resp.split("New Important Context:")[1].strip().split(',')
        return None, next_triple_index, additional_context
    else:
        # If the response doesn't match either format, return None for both
        return None, None, None
    
def recognize_entities_and_relations(question_txt, model_config):
    model_prompt = f"""
    Your task is to help to link Information from Questions to Knowledge Graphs. 
    Please generate a list with all Entities, relations and Types for the following Question.
    Please generate one list with all entities. Do not format the json output.
    Question: \\textbf{{{question_txt}}}
    """
    llm_resp_text = prompt_chat_llm(model_prompt, None, model_config.get_static_instance(), model_config.model_id)
    return llm_resp_text

def filter_common_nodes(question_txt, entity_dict, model_config):
    # Return filtered dict of entities to explore further
    filter_prompt = f"""For the following question, strictly pick and list a comma separated list of entity ids to explore further, the ids should provide a good starting point to start looking for an answer. The ids ideally should not lead to too many child nodes otherwise the search becomes too expensive, be careful in choosing expensive ids. Choose at least one id. Do not write anything else.

    Question: {question_txt}

    Entity Dict: {entity_dict}
    """
    llm_resp_text = prompt_chat_llm(filter_prompt, None, model_config.get_static_instance(), model_config.model_id)
    
    qid_set = set([item.strip() for item in llm_resp_text.split(',')])
    filtered_dict = dict()
    for key, val in entity_dict.items():
        if val in qid_set:
            filtered_dict[key] = val
    
    return filtered_dict