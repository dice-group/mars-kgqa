
from src.util.llm import prompt_chat_llm


def old_generate_baseline_sparql(question_txt, model_config):

    check_prompt = f"""Given a question generate a Wikidata SPARQL to answer the question. Strictly follow the provided "Answer Format", do not write anything else. 

    Question: {question_txt}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    llm_resp_text, _ = prompt_chat_llm(check_prompt, None, model_config.get_static_instance(), model_config.model_id, model_config.postfix)
    
    print(f'LLM Response: {llm_resp_text}')
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        
    return answer_sparql

def generate_simple_sparql(question_txt, entity_dict_str, relation_dict_str, model_config, proc_logger):
    proc_logger.start_action(
        "generate_simple_sparql",
        {
            "question": question_txt,
            "entity_dict_str": entity_dict_str,
            "relation_dict_str": relation_dict_str,
        }
    ).add_step("Building prompt for simple SPARQL generation")
    
    llm_prompt = f"""Given a question and a set of extracted Wikdata entities and relations alongside their labels, generate a SPARQL to answer the question. Do not try to retrieve labels unless explicitly asked. Strictly follow ONLY one of the provided "Answer Format", do not write anything else. 

    Question: {question_txt}

    ### Identified Question Entities:
    {entity_dict_str}
    
    ### Identified Question Relations:
    {relation_dict_str}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    # Log the full prompt before sending it to the LLM
    proc_logger.add_step({"prompt": llm_prompt})
    
    proc_logger.add_step("Calling LLM")
    llm_resp_text, _ = prompt_chat_llm(
        llm_prompt,
        None,
        model_config.get_static_instance(),
        model_config.model_id,
        model_config.postfix,
    )
    
    # Log the raw LLM output
    proc_logger.add_step({"LLM Response": llm_resp_text})
    
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        proc_logger.add_step("Extracted SPARQL from LLM output")
    
    # Finish logging and return the result
    proc_logger.set_output({"sparql": answer_sparql}).complete_action()
    return answer_sparql

def generate_sparql_from_patterns(question_txt, top_verbalized_patterns, entity_dict_str, rel_dict_str, model_config, proc_logger):
    
    proc_logger.start_action(
        "generate_sparql_from_patterns",
        {"num_patterns": len(top_verbalized_patterns)}
    ).add_step("Building prompt for single‑hop SPARQL generation")
    
    patterns_str = '\n'.join(top_verbalized_patterns)

    gen_prompt = f"""Given a natural language question, identified entities and a set of Wikidata triple patterns (subject, predicate, object) including entity IDs and domain/range type restrictions, generate a valid wikidata SPARQL query utilizing the relevant provided IDs that answers the question. Prioritize triple patterns where the entity IDs appear relevant to the question and the domain/range types align with the expected answer type. Discard any triple patterns that do not contribute to answering the question. Do not try to retrieve labels unless explicitly asked.
    Strictly follow the provided "Answer Format", do not write anything else.

    Question: {question_txt}
    
    ### Identified Question Entities:
    {entity_dict_str}

    ### Triple Patterns:
    {patterns_str}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    
    # Log the full prompt before sending it to the LLM
    proc_logger.add_step({"prompt": gen_prompt})

    proc_logger.add_step("Calling LLM")
    
    llm_resp_text, think_content = prompt_chat_llm(gen_prompt, model_config.sysprompt, model_config.get_static_instance(), model_config.model_id, model_config.postfix)
    
    if think_content:
        proc_logger.add_step({"LLM Reasoning": think_content})
    
    # Log the raw LLM output
    proc_logger.add_step({"LLM Response": llm_resp_text})
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        proc_logger.add_step("Extracted SPARQL from LLM output")
    
    # Record final output and finish the action
    proc_logger.complete_action()
        
    return answer_sparql

def generate_sparql_or_expansion_indices(question_txt, top_verbalized_patterns, entity_dict_str, rel_dict_str,
                                 model_config, proc_logger):
    
    proc_logger.start_action(
        "generate_sparql_or_expansion_indices",
        {"num_patterns": len(top_verbalized_patterns)}
    ).add_step("Building prompt for multi‑hop SPARQL generation")
    
    patterns_str = '\n'.join(top_verbalized_patterns)

    gen_prompt = f"""Given a natural language question, identified entities and a set of Wikidata triple patterns (subject, predicate, object) including entity IDs and domain/range type restrictions, tell if you need to look further into the paths to generate a Wikidata SPARQL for the question. If yes, list the index based on the 0-indexing, of the patterns. If not, then generate a valid wikidata SPARQL query utilizing the relevant provided IDs that answers the question. Prioritize triple patterns where the entity IDs appear relevant to the question and the domain/range types align with the expected answer type. Discard any triple patterns that do not contribute to answering the question. Do not try to retrieve labels unless explicitly asked.
    Strictly follow ONLY one of the provided "Answer Format" depending upon your response, do not write anything else.

    Question: {question_txt}
    
    ### Identified Question Entities:
    {entity_dict_str}

    ### Triple Patterns:
    {patterns_str}

    ---

    Answer Format (SPARQL Generation):

    SPARQL: <place the generated SPARQL here in a single line>
    
    ---

    Answer Format (Path Expansion Selection):

    Indices: <place the comma-separated 0-index values of the paths to expand further for the answers, put atleast one value. Do not pick too many.>

    """
    
    # Log the prompt (full text) before sending it to the LLM
    #proc_logger.add_step("Prompt built – logging prompt")
    proc_logger.add_step({"prompt": gen_prompt})
    
    proc_logger.add_step("Calling LLM")
    
    llm_resp_text, think_content = prompt_chat_llm(gen_prompt, model_config.sysprompt,
                                    model_config.get_static_instance(),
                                    model_config.model_id, model_config.postfix)
    
    # proc_logger.add_step("LLM response received")
    if think_content:
        proc_logger.add_step({"LLM Reasoning": think_content})
        
    proc_logger.add_step({"LLM Response": llm_resp_text})
    
    sparql = None
    indices = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        sparql = llm_resp_text.split("SPARQL:")[1].strip()
        proc_logger.add_step("Extracted SPARQL from LLM output")
    if "Indices:" in llm_resp_text:
        indices = llm_resp_text.split("Indices:")[1].strip()
        if len(indices) > 0:
            indices = [item.strip() for item in indices.split(',')]
        else:
            indices = []
        proc_logger.add_step(f"Extracted expansion indices: {indices}")

    proc_logger.set_output({"sparql": sparql, "indices": indices}).complete_action()
    return sparql, indices

def sparql_refinement(question_txt, sparql_str, model_config, proc_logger):
    
    # Log the start of the refinement step
    proc_logger.start_action(
        "sparql_refinement",
        {"question": question_txt, "original_sparql": sparql_str}
    ).add_step("Building refinement prompt")
    
    check_prompt = f"""For the given question, FIX the provided SPARQL for Wikidata. Write it as it is, if the SPARQL requires no fix. Strictly follow the provided "Answer Format", do not write anything else. 

    Question: {question_txt}

    SPARQL: {sparql_str}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    # Log the full prompt
    proc_logger.add_step({"prompt": check_prompt})
    
    llm_resp_text, _ = prompt_chat_llm(
        check_prompt,
        None,
        model_config.get_static_instance(),
        model_config.model_id,
        model_config.postfix
    )
    
    # Log the raw LLM output
    proc_logger.add_step({"LLM Response": llm_resp_text})
    
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        proc_logger.add_step("Extracted refined SPARQL")
    
    # Finish logging
    proc_logger.set_output({"refined_sparql": answer_sparql}).complete_action()
    
    return answer_sparql

def estimate_mhop(question_txt,  entity_dict_str, rel_dict_str, model_config, proc_logger):
    
    # Log the start of the refinement step
    proc_logger.start_action(
        "estimate_mhop",
        {"question": question_txt, "entity_dict_str": entity_dict_str,  "rel_dict_str": rel_dict_str}
    ).add_step("Building mhop estimation prompt")
    
    llm_prompt = f"""For the given question alongwith augmented context, recognized entities and relations. Estimate the number of hops required in the graph from these entities to generate a SPARQL that answers this question. Strictly follow the provided "Answer Format", do not write anything else. 

    Question: {question_txt}

    ### Identified Question Entities:
    {entity_dict_str}
    
    ### Identified Relations:
    {entity_dict_str}

    ---

    Answer Format:

    MHOP: <place the estimated MHOP integer here, minimum value is 1>

    """
    # Log the full prompt
    proc_logger.add_step({"prompt": llm_prompt})
    
    llm_resp_text, _ = prompt_chat_llm(
        llm_prompt,
        None,
        model_config.get_static_instance(),
        model_config.model_id,
        model_config.postfix
    )
    
    # Log the raw LLM output
    proc_logger.add_step({"LLM Response": llm_resp_text})
    
    estimated_mhop = 1
    # Extract the generated MHOP
    if "MHOP:" in llm_resp_text:
        try:
            estimated_mhop = int(llm_resp_text.split("MHOP:")[1].strip())
        except ValueError:
            # keep the default value if the cast fails
            proc_logger.add_step(f'Could not parse LLM response to integer, going forward with the default value: {estimate_mhop}')
    # Finish logging
    proc_logger.set_output({"mhop": estimated_mhop}).complete_action()
    
    return estimated_mhop

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
    llm_resp_text, _ = prompt_chat_llm(check_prompt, None, model_config.get_static_instance(), model_config.model_id, model_config.postfix)
    

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
    llm_resp_text, _ = prompt_chat_llm(model_prompt, None, model_config.get_static_instance(), model_config.model_id, model_config.postfix)
    
    return llm_resp_text

def filter_common_nodes(question_txt, entity_dict, model_config, proc_logger):
    # Log the start of the filtering step
    proc_logger.start_action(
        "filter_common_nodes",
        {"question": question_txt, "entity_dict": entity_dict}
    ).add_step("Building filter prompt")
    
    filter_prompt = f"""For the following question, strictly pick and list a comma separated list of entity ids to explore further, the ids should provide a good starting point to start looking for an answer. The ids ideally should not lead to too many child nodes otherwise the search becomes too expensive, be careful in choosing expensive ids. Choose at least one id. Do not write anything else.

    Question: {question_txt}

    Entity Dict: {entity_dict}
    """
    # Log the prompt
    proc_logger.add_step({"prompt": filter_prompt})
    
    llm_resp_text, _ = prompt_chat_llm(
        filter_prompt,
        None,
        model_config.get_static_instance(),
        model_config.model_id,
        model_config.postfix
    )
    
    # Log the raw LLM output
    proc_logger.add_step({"LLM Response": llm_resp_text})
    
    qid_set = set([item.strip() for item in llm_resp_text.split(',')])
    filtered_dict = dict()
    for key, val in entity_dict.items():
        if val in qid_set:
            filtered_dict[key] = val
    
    # Log the final filtered dictionary
    proc_logger.set_output({"filtered_entity_dict": filtered_dict}).complete_action()
    
    return filtered_dict

def analyse_gen_sparql(gold_answer, pred_answer, log_content, model_config, use_answers=False):
    
    if use_answers:
        start_sec = f"""For a question, you are given gold answer(s) together with the system's predicted answer. Additionally you have the full process‑flow log for this question.
        
        Gold answer: {gold_answer}
        Predicted answer: {pred_answer}."""
    else:
        start_sec = f"""For a question, you have the full process‑flow log of the system."""
    
    prompt = f"""{start_sec}
    
    --- LOG START ---
    {log_content}
    --- LOG END ---

    Please provide a short analysis (2‑3 sentences) explaining what likely went wrong
    in the SPARQL generation pipeline that caused the mismatch and what could be the solution."""
    
    llm_resp_text, think_content = prompt_chat_llm(prompt, None, model_config.get_static_instance(), model_config.model_id, model_config.postfix)
    
    return llm_resp_text, think_content

def compile_analyses(analyses_content, model_config):
    
    prompt = f"""You are given a collection of analysis excerpts from mismatched questions. Summarise the main failure patterns and suggest possible improvements.
    \n\n
    {analyses_content}"""
    
    llm_resp_text, think_content = prompt_chat_llm(prompt, None, model_config.get_static_instance(), model_config.model_id, model_config.postfix)
    
    return llm_resp_text, think_content


def sparql_filter(sparql_str, has_lang_filter, model_config, proc_logger):
    
    # Log the start of the refinement step
    proc_logger.start_action(
        "sparql_filter",
        {"original_sparql": sparql_str}
    ).add_step("Building refinement prompt")
    
    tasks_list = []
    i = 1
    if has_lang_filter:
        tasks_list.append(f'{i}. Remove the logic to select a label.')
    
    tasks_str = '\n'.join(tasks_list)
    
    model_prompt = f"""For the given SPARQL, look at the tasks to perform, and produce a single final SPARQL that accomodates all of the requested changes. Write it as it is, if nothing to do. Strictly follow the provided "Answer Format", do not write anything else. 
    
    Input SPARQL: {sparql_str}

    TASKS:
    {tasks_str}

    ---

    Answer Format:

    SPARQL: <place the generated SPARQL here in a single line>

    """
    # Log the full prompt
    proc_logger.add_step({"prompt": model_prompt})
    
    llm_resp_text, _ = prompt_chat_llm(
        model_prompt,
        None,
        model_config.get_static_instance(),
        model_config.model_id,
        model_config.postfix
    )
    
    # Log the raw LLM output
    proc_logger.add_step({"LLM Response": llm_resp_text})
    
    answer_sparql = None
    # Extract the generated SPARQL
    if "SPARQL:" in llm_resp_text:
        answer_sparql = llm_resp_text.split("SPARQL:")[1].strip()
        proc_logger.add_step("Extracted refined SPARQL")
    
    # Finish logging
    proc_logger.set_output({"refined_sparql": answer_sparql}).complete_action()
    
    return answer_sparql