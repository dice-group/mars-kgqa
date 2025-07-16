
from src.util.llm import prompt_chat_llm


def check_if_answer(question_txt, top_triples, model_config):
    # Check if the triple contains the answer to the question

    triples_list = '\n'.join([triple_data.get_verbalization() for triple_data in top_triples])

    check_prompt = f"""Look at the following triples and then either use the provided Answer Format if you find one triple that directly answers the question or use Next Triple Format if no answer is found. Do not write anything else, use only single format.

    Question: {question_txt}

    Triples list:
    {triples_list}

    ---

    Answer Format:

    Answer: <place the answer triple here>

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