# Common file to store reusable functions for SPARQL generators
from src.util.llm import get_embeddings
from src.const.llm import DEFAULT_EMBED_LLM_CONFIG
from src.const.misc import TRIPLE_VERBALIZATION_LENGTH_LIMIT
from src.util.common import dot, read_json_file, create_directory_if_not_exists, save_json_file
import csv
from tqdm import tqdm
import os
import json
from src.util.process_flow_logger import ProcessFlowLogger


def get_verbalization_similarity(query_text, data_list, verbalizer, batch_size = 512):
    
    print(f'Computing similarity of {len(data_list)} data item(s) with batch size of {batch_size}..')
    
    batched_triple_data = []

    # Split triple_data_list into batches
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        batched_triple_data.append(batch)

    # Fetch embeddings
    triple_data_embd_list = []
    for triple_data_batch in tqdm(batched_triple_data, desc='Processing data batches'):
        # Build text list
        cur_text_batch = [verbalizer(trip_data) for trip_data in triple_data_batch]
        # llm request tool
        cur_embd_batch = get_embeddings(cur_text_batch, DEFAULT_EMBED_LLM_CONFIG)
        triple_data_embd_list.extend(cur_embd_batch)

    query_text = query_text[:TRIPLE_VERBALIZATION_LENGTH_LIMIT] # Truncating the input text to limit to avoid exception during embedding
    # Compute cosine similarity of the verbalized triples to the augmented input
    query_embedding = get_embeddings([query_text], DEFAULT_EMBED_LLM_CONFIG)[0]
    triple_similarity_list = []
    for triple_embd in triple_data_embd_list:
        triple_similarity_list.append(dot(query_embedding, triple_embd)) # as mentioned in https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe-GGUF

    # heapq uses min-heap by default, so we multiply the similarity score by -1
    triple_cossim_list = [(-similarity, triple_data) for similarity, triple_data in zip(triple_similarity_list, data_list)]
    return triple_cossim_list

def save_answers_as_tsv(answers_dict, file_path):
    with open(file_path, 'w', newline='', encoding='utf-8') as tsvfile:
        writer = csv.writer(tsvfile, delimiter='\t')
        # Write header
        writer.writerow(['Question ID', 'Answer'])
        # Write data
        for question_id, answer in answers_dict.items():
            writer.writerow([question_id, answer])
            
def _build_output_path(approach_name: str, input_file_path: str,
                       leaf_dir: str, file_ext: str) -> str:

    # Absolute path of the input file
    input_abs_path = os.path.abspath(input_file_path)

    # Parent directory of the input file
    parent_dir = os.path.dirname(input_abs_path)

    # Base name of the input file (without extension)
    input_file_name = os.path.splitext(os.path.basename(input_abs_path))[0]

    # Build the directory hierarchy:
    #   <parent>/prediction/<input‑file‑name>/<leaf_dir>
    prediction_dir = os.path.join(parent_dir, "prediction")
    file_dir = os.path.join(prediction_dir, input_file_name, leaf_dir)

    # Caller can create the directories if needed:
    # os.makedirs(file_dir, exist_ok=True)

    # Final output file path
    output_file = f"{approach_name}.{file_ext}"
    return os.path.join(file_dir, output_file)


def generate_output_path(approach_name, input_file_path, file_format='tsv'):
    return _build_output_path(approach_name, input_file_path,
                              leaf_dir=file_format, file_ext=file_format)


def generate_gerbil_export_path(approach_name, input_file_path):
    return _build_output_path(approach_name, input_file_path,
                              leaf_dir='gerbil', file_ext='csv')
    
def _build_leaf_dir(input_file_path: str, leaf_dir: str) -> str:

    # Absolute path of the input file
    input_abs_path = os.path.abspath(input_file_path)

    # Parent directory of the input file
    parent_dir = os.path.dirname(input_abs_path)

    # Base name of the input file (without extension)
    input_file_name = os.path.splitext(os.path.basename(input_abs_path))[0]

    # Build the directory hierarchy:
    #   <parent>/prediction/<input‑file‑name>/<leaf_dir>
    prediction_dir = os.path.join(parent_dir, "prediction")
    log_dir = os.path.join(prediction_dir, input_file_name, leaf_dir)

    return log_dir

# Example convenience wrapper (optional)
def get_log_dir(approach_name: str, input_file_path: str) -> str:
    """
    Return a log directory that includes the approach name for extra
    organization, e.g. <...>/prediction/<input‑file>/logs/<approach_name>.
    """
    base_log_dir = _build_leaf_dir(input_file_path, 'logs')
    return os.path.join(base_log_dir, approach_name)

def get_analysis_dir(approach_name: str, input_file_path: str) -> str:
    """
    Return an analysis directory that includes the approach name for extra
    organization, e.g. <...>/prediction/<input‑file>/analysis/<approach_name>.
    """
    base_analysis_dir = _build_leaf_dir(input_file_path, 'analysis')
    return os.path.join(base_analysis_dir, approach_name)

def get_question_pf_name(question_id):
    return f"question_{question_id}"
            
def process_dataset(proc_name, qald_file_path, output_path, process_fn, wd_ep,
                    llm_config, use_gold_entrel, log_dir, filter_entities, topn_count,
                    mhop_limit, include_pattern_count, refine_sparql, ent_annot, use_aug_sim, q_lang, use_sleep):
    # Output directory
    output_path = os.path.abspath(output_path)
    out_dir = os.path.dirname(output_path)
    create_directory_if_not_exists(out_dir)

    # Log directory
    create_directory_if_not_exists(log_dir)
    # Handle cache file
    cache_file = os.path.join(out_dir, f'{proc_name}_cache.json')

    # Read cache if it exists
    answers_cache = {}
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            answers_cache = json.load(f)

    cur_answers_dict = {}

    # Read the qald preprocessed file
    qald_json = read_json_file(qald_file_path)
    
    ent_linker = ent_annot.value

    # For each question
    for question_item in tqdm(qald_json['questions'], desc='Processing Questions'):
        question_id = question_item['id']

        # Extract the English question text
        question_text = next(
            (q['string'] for q in question_item['question'] if q['language'] == q_lang), None
        )
        
        # Initialise a logger for this question
        proc_logger = ProcessFlowLogger(
            process_name=get_question_pf_name(question_id),
            output_dir=log_dir
        ).start_action(
            "process_question",
            {"question_id": question_id, "question_text": question_text, "language": q_lang}
        )
        
        proc_logger.add_step(f"Wikidata Endpoint: {wd_ep}")
        if use_gold_entrel:
            proc_logger.add_step(f"NOTE: The model will have access to the provided gold entities.")
        else:
            proc_logger.add_step(f"NOTE: The model will not have access to the provided gold entities. It must use the predicted/extracted entities.")
        
        cache_id = f"{question_id}_{question_text}"

        
        # Cache lookup
        if cache_id in answers_cache:
            proc_logger.add_step(f"Using cached answer for cache ID: {cache_id}")
            cur_answers_dict[question_id] = answers_cache[cache_id]
            proc_logger.set_output({"cached_answer": answers_cache[cache_id]}).complete_action()
            continue

        
        # Verify required pre‑processed fields are present
        if not use_gold_entrel and not all(
            key in question_item for key in ['augmented_translations', ent_linker]
        ):
            proc_logger.add_step("Missing augmented data; skipping question").complete_action()
            continue  # skip if augmented data is missing

        
        # Load augmented text / entities / relations
        aug_text = question_item['augmented_translations'][q_lang]
        
        # Log the gold entities, relations and SPARQL
        proc_logger.add_step(f"Gold Entities: {question_item['gold_ent']}")
        proc_logger.add_step(f"Gold Relations: {question_item['gold_rel']}")
        proc_logger.add_step(f"Gold SPARQL: {question_item['query']['sparql']}")

        if use_gold_entrel:
            ent_dict = {e['label']: e['uri'] for e in question_item['gold_ent']}
            rel_dict = {r['label']: r['uri'] for r in question_item['gold_rel']}
        else:
            proc_logger.add_step(f'Entity/Relation Linker: {ent_linker}')
            ent_dict = {e['label']: e['uri'] for e in question_item[ent_linker][q_lang]['entities']}
            rel_dict = {r['label']: r['uri'] for r in question_item[ent_linker][q_lang]['relations']}

        proc_logger.add_step(
            f"Prepared input – aug_text length: {len(aug_text)}, "
            f"entities: {len(ent_dict)}, relations: {len(rel_dict)}"
        )
        
        
        # Call the actual query generation / solving function
        cur_generated_output = process_fn(
            question_text,
            llm_config,
            (aug_text, ent_dict, rel_dict),
            wd_ep,
            filter_entities,
            proc_logger,
            topn_count,
            mhop_limit,
            include_pattern_count,
            refine_sparql,
            use_aug_sim,
            use_sleep
        )
        
        # Cache the generated output
        answers_cache[cache_id] = cur_generated_output
        save_json_file(answers_cache, cache_file)

        
        # Store result & finish logging for this question
        cur_answers_dict[question_id] = cur_generated_output
        proc_logger.set_output({'Generated output': cur_generated_output}).complete_action()

    # Save answers dict as tsv
    save_answers_as_tsv(cur_answers_dict, output_path)