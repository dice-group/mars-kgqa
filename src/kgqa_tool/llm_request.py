
from src.util.llm import prompt_chat_llm


def check_if_answer(question_txt, top_triples, model_config):
    # Check if the triple contains the answer to the question

    triples_list = '\n'.join([triple_data.get_verbalization() for _, triple_data in top_triples])

    check_prompt = f"""Look at the following triples and then either use the provided Answer Format if you find one triple that directly answers the question or use Next Triple Format if no answer is found. Do not write anything else, use only single format.

    Question: {question_txt}

    Triples list:
    {triples_list}

    ---

    Answer Format:

    Answer: <place the index of the answer triple here, use 0-indexing>

    ---

    Next Triple Format:

    Next Triple Index: <place the index of the next triple to consider here, use 0-indexing>

    """
    llm_resp_text = prompt_chat_llm(check_prompt, None, model_config.get_static_instance(), model_config.model_id)

    # Parse the LLM response
    if "Answer:" in llm_resp_text:
        answer_triple = llm_resp_text.split("Answer:")[1].strip()
        return answer_triple, None
    elif "Next Triple Index:" in llm_resp_text:
        next_triple_index = int(llm_resp_text.split("Next Triple Index:")[1].strip())
        return None, next_triple_index
    else:
        # If the response doesn't match either format, return None for both
        return None, None
    
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