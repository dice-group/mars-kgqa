# Sample usage: bash pylauncher.sh normal src.util.qald_io
from src.util.common import read_json_file, create_directory_if_not_exists, execute_sparql_query, save_json_file, get_sparql_timeout
from src.const.misc import ANSWER_NOT_FOUND_STR, LITERAL_VAL_PREFIX, DEFAULT_WIKIDATA_ENDPOINT_URL
import csv
import os
import json
import ast
from tqdm import tqdm
from src.kgqa_tool.graph_traversal import fetch_labels
import re
from src.util.process_flow_logger import ProcessFlowLogger

from src.kgqa_tool.llm_request import mhop_analysis

def convert_lcquad2_to_qald(lcquad2_file_path, output_qald_file_path,
                           sparql_endpoint, use_sleep=False):
    """
    Convert LC‑QuAD2.0 JSON to QALD format.
    """
    lcquad_data = read_json_file(lcquad2_file_path)
    qald_questions = []
    failed_update_items = []          # SPARQL‑execution failures
    missing_question_items = []       # No question text
    copy_keys = ['gold_ent', 'gold_rel']

    for qa_item in tqdm(lcquad_data, desc='Processing Questions'):
        qald_item = {}

        q_id = qa_item['uid']
        sparql = qa_item['sparql_wikidata']

        # Question text handling
        para_text = qa_item.get('paraphrased_question')
        question_text = para_text if para_text else qa_item.get('question')
        if not question_text or not qa_item.get('augmented_seq'): # missing question string or augmented string
            missing_question_items.append(qa_item)
            continue

        # SPARQL execution
        formatted_sparql, sparql_response = get_qald_answer_sparql(
            sparql, sparql_endpoint, use_sleep=use_sleep
        )

        # Detect empty / failed answers (same check as update_qald_answers)
        empty_bind = (
            'results' in sparql_response and
            len(sparql_response['results'].get('bindings', [])) == 0
        )
        if empty_bind:
            failed_update_items.append(qa_item)
            continue

        answer_obj = [sparql_response]

        # Build QALD item
        qald_item['id'] = str(q_id)                     # uniform id type
        qald_item['answers'] = answer_obj
        qald_item['query'] = {'sparql': formatted_sparql}
        qald_item['question'] = [{'language': 'en', 'string': question_text}]

        # Copy augmented / gold fields
        for key_item in copy_keys:
            if key_item in qa_item:
                qald_item[key_item] = qa_item[key_item]

        # Encapsulate augmented sequence and T5‑augmented data
        qald_item['augmented_translations'] = {'en': qa_item['augmented_seq']}
        qald_item['t5_aug'] = {
            'en': {
                'entities': qa_item['entities_aug_t5'],
                'relations': qa_item['relations_aug_t5']
            }
        }

        qald_questions.append(qald_item)

    # Save QALD file
    qald_dict = {'dataset': {'id': 'LC-QuAD2.0'}, 'questions': qald_questions}
    save_json_file(qald_dict, output_qald_file_path)

    # Return both exclusion lists (mirrors update_qald_answers pattern)
    return failed_update_items, missing_question_items
    

def get_qald_answer_sparql(sparql, endpoint, use_sleep=False):
    
    if sparql is None or not sparql.strip():
        return None, None
    if "prefix" in sparql.lower():
        formatted_sparql = sparql
    else:
        formatted_sparql = f"""
        PREFIX bd: <http://www.bigdata.com/rdf#>
        PREFIX cc: <http://creativecommons.org/ns#>
        PREFIX dct: <http://purl.org/dc/terms/>
        PREFIX geo: <http://www.opengis.net/ont/geosparql#>
        PREFIX hint: <http://www.bigdata.com/queryHints#> 
        PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX prov: <http://www.w3.org/ns/prov#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        PREFIX p: <http://www.wikidata.org/prop/>
        PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
        PREFIX pqn: <http://www.wikidata.org/prop/qualifier/value-normalized/>
        PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
        PREFIX pr: <http://www.wikidata.org/prop/reference/>
        PREFIX prn: <http://www.wikidata.org/prop/reference/value-normalized/>
        PREFIX prv: <http://www.wikidata.org/prop/reference/value/>
        PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
        PREFIX ps: <http://www.wikidata.org/prop/statement/>
        PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/>
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdata: <http://www.wikidata.org/wiki/Special:EntityData/>
        PREFIX wdno: <http://www.wikidata.org/prop/novalue/>
        PREFIX wdref: <http://www.wikidata.org/reference/>
        PREFIX wds: <http://www.wikidata.org/entity/statement/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX wdtn: <http://www.wikidata.org/prop/direct-normalized/>
        PREFIX wdv: <http://www.wikidata.org/value/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        
        {sparql}
        """
    
    if ("ask " not in formatted_sparql.lower()) and ("limit" not in formatted_sparql.lower()):
        # Adding hard limit for the results
        formatted_sparql += "\nLIMIT 1000"
    
    sparql_response, _ = execute_sparql_query(formatted_sparql, endpoint, get_only_bindings=False, use_sleep=use_sleep, timeout=get_sparql_timeout(use_sleep))
    return formatted_sparql, sparql_response

def update_qald_answers(qald_file_path, output_file_path, sparql_endpoint, ignore_ids=[]):
    ignore_ids = [str(item) for item in ignore_ids]
    qald_obj = read_json_file(qald_file_path)
    failed_update_items = []
    ignored_items = []
     # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing questions'):
        q_id = question_item["id"]
        if str(q_id) in ignore_ids:
            ignored_items.append(question_item)
            continue # ignore this item
        # Extract SPARQL query
        gold_sparql = question_item['query']['sparql']
        sparql_response, request_failed = execute_sparql_query(gold_sparql, sparql_endpoint, get_only_bindings=False)
        # Track failed requests
        empty_bind = True if ('results' in  sparql_response and len(sparql_response['results']['bindings']) == 0) else False
        if request_failed or empty_bind:
            failed_update_items.append(question_item)
            continue # cannot update this item
        answer_obj = [sparql_response]
        question_item['answers'] = answer_obj
    
    removed_items = failed_update_items + ignored_items
    # Removing failed items safely
    qald_obj['questions'] = [ q for q in qald_obj['questions'] if q not in removed_items]
    # Save the QALD file
    create_directory_if_not_exists(output_file_path)
    # Write qald_obj to output_file_path
    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        json.dump(qald_obj, outfile, ensure_ascii=False, indent=4)
    # Return failed items
    return failed_update_items, ignored_items

def get_qald_answer_obj(answer_tuples):
    # Generate bindings
    bindings = []
    if answer_tuples:
        for tuple in answer_tuples:
            cossim_score = tuple[0]
            answer_dict = tuple[1]
            if cossim_score == 0 and answer_dict == ANSWER_NOT_FOUND_STR:
                break

            root_uri = answer_dict['root']
            subject = answer_dict['subject']
            object = answer_dict['object']
            object_lbl = answer_dict['objectLabel']
            # default values
            ans_type = 'uri'
            ans_val = subject
            # If root is same as subject, check for object type: literal or uri
            if root_uri == subject:
                if object_lbl.startswith(LITERAL_VAL_PREFIX):
                    ans_type = 'literal'
                ans_val = object
            # Else, answer is subject's uri
            answer_item = {
                "o1": {
                    "type": ans_type,
                    "value": ans_val
                }
            }
            bindings.append(answer_item)
            
    answer_obj = [
        {
            "head": {
                "vars": [
                    "o1"
                ]
            },
            "results": {
                "bindings": bindings
            }
        }
    ]
    return answer_obj

def load_tsv_answers_dict(file_path, has_tuples=False):
    answers_dict = dict()
    with open(file_path, 'r', newline='', encoding='utf-8') as tsvfile:
        reader = csv.reader(tsvfile, delimiter='\t')
        next(reader)  # Skip the header row
        for row in reader:
            question_id = str(row[0]) # convert to string for uniformity
            answer_str = row[1]
            answer = answer_str
            if has_tuples:
                try:
                    answer = ast.literal_eval(answer_str)
                except (ValueError, SyntaxError):
                     pass  # Fallback to original string if parsing fails
            answers_dict[question_id] = answer
    return answers_dict

# Function to convert the output from basic factiod solver to qald format with answers
def convert_basic_output(tsv_file_path, qald_file_path, output_file_path, has_tuples, wd_ep=DEFAULT_WIKIDATA_ENDPOINT_URL):
        
    tsv_dict = load_tsv_answers_dict(tsv_file_path, has_tuples)
    qald_obj = read_json_file(qald_file_path)
    # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing Answers'):
        # Extract answers out of tsv_data and create a qald answer object
        question_id = str(question_item['id'])
        answer_item = None
        if question_id in tsv_dict:
            answer_item = tsv_dict[question_id]
        
        if has_tuples:
            answer_obj = get_qald_answer_obj(answer_item)
            question_item['query'] = {}
        else:
            if not answer_item:
                answer_obj = []
                question_item['query'] = { 'sparql': ''}
            else:
                formatted_sparql, qald_answer = get_qald_answer_sparql(answer_item, wd_ep)
                answer_obj = [qald_answer]
                question_item['query'] = { 'sparql': formatted_sparql}

        question_item['answers'] = answer_obj  
    
    save_json_file(qald_obj, output_file_path)

# NOTE: This function would not be needed once this is already done in the entity linking part
def encapsulate_qald_aug_info(dataset_label, entrel_linker_name, qald_file_path):
    qald_obj = read_json_file(qald_file_path)
    
    entrel_keys = ['found_ent', 'found_rel', 'augmented_ent', 'augmented_rel', 'filtered_ent', 'filtered_rel']
    aug_seq_key = 'augmented_seq'
    
    question_list = []
     # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing questions'):
        qald_item = {}
        orig_keys = question_item.keys()
        # Copy augmented fields
        for key_item in orig_keys:
            if key_item in entrel_keys:
                if entrel_linker_name not in qald_item:
                    qald_item[entrel_linker_name] = {'en': {}}
                qald_item[entrel_linker_name]['en'][key_item] = question_item[key_item]
            elif key_item == aug_seq_key:
                qald_item[key_item] = {'en': question_item[key_item]}
            else:
                qald_item[key_item] = question_item[key_item]   
        question_list.append(qald_item)
    # Create QALD Dataset    
    qald_dict = {'dataset': {'id': f'{dataset_label} (with ent-rel links)'}, 'questions' : question_list}
    # Backup old file
    if os.path.isfile(qald_file_path):
        dir_name, base_name = os.path.split(qald_file_path)
        backup_path = os.path.join(dir_name, f"old.{base_name}")
        os.rename(qald_file_path, backup_path)   # rename to old.<original>
    # Save json
    save_json_file(qald_dict, qald_file_path)
    
def convert_spinach_to_qald(dataset_label, input_spinach_filepath, output_qald_filepath, sparql_endpoint, use_sleep=False):
    spinach_question_list = read_json_file(input_spinach_filepath)
    qald_question_list = []
    ignored_items = []
    for question_item in tqdm(spinach_question_list, desc='Processing questions'):
        qald_item = {}
        q_id = question_item['id']
        question_text = question_item['question']
        sparql = question_item['sparql']
        if not question_text:
            print(f'Missing question text for ID: {q_id}')
            ignored_items.append(question_item)
            continue
        formatted_sparql, sparql_response = get_qald_answer_sparql(sparql, sparql_endpoint, use_sleep)
        if not sparql_response:
            print(f'Missing answer for ID: {q_id}\tQuestion: {question_text}')
            ignored_items.append(question_item)
            continue
        answer_obj = [sparql_response]
        # Build QALD item dictionary
        qald_item['id'] = str(q_id) # For uniformity
        qald_item['answers'] = answer_obj
        qald_item['query'] = { 'sparql': formatted_sparql}
        qald_item['question'] = [{ "language": "en", "string": question_text}]
        
        qald_question_list.append(qald_item)
    # Create QALD Dataset    
    qald_dict = {'dataset': {'id': f'{dataset_label} (QALD Format)'}, 'questions' : qald_question_list}
    # Save json
    save_json_file(qald_dict, output_qald_filepath)
    
    ignored_ids = [q['id'] for q in ignored_items]
    
    print(f'Following questions ignored: {f'{','.join(ignored_ids)}'}')
    
    print(f'Total {len(ignored_items)} out of {len(spinach_question_list)} ignored.')
    print(f'Total {len(qald_question_list)} out of {len(spinach_question_list)} saved.')
    
def fetch_qald9_multilingual_strings(qald9_dir, *qald_9plus_filepaths):
    # Build English‑to‑multilingual dictionary from the original QALD‑9 set
    eng_to_questions = {}

    # iterate over all JSON files in the supplied directory
    for fname in os.listdir(qald9_dir):
        if not fname.lower().endswith('.json'):
            continue
        file_path = os.path.join(qald9_dir, fname)
        qald_obj = read_json_file(file_path)

        for q_item in qald_obj.get('questions', []):
            # find the English entry in the ``question`` list
            en_entry = next(
                (entry for entry in q_item.get('question', [])
                 if entry.get('language') == 'en'), None)

            if en_entry is None:
                # no English string – skip this question
                continue

            eng_q = en_entry.get('string')
            if eng_q in eng_to_questions:
                print(f'Duplicate English question found across QALD‑9 files: "{eng_q}"')
                continue
            # store the whole list of language entries for later merging
            eng_to_questions[eng_q] = q_item.get('question', [])

    # Enrich each QALD‑9‑plus file using the mapping
    for target_path in qald_9plus_filepaths:
        qald_plus = read_json_file(target_path)

        total_q = len(qald_plus.get('questions', []))
        updated_q = 0
        unmerged_questions = []
        
        for q_item in qald_plus.get('questions', []):
            # locate English string in the target item
            en_entry = next(
                (entry for entry in q_item.get('question', [])
                 if entry.get('language') == 'en'), None)

            if en_entry is None:
                # nothing to match – skip
                unmerged_questions.append(eng_q)
                continue

            eng_q = en_entry.get('string')
            # get multilingual list from the original QALD‑9 data (if present)
            multi_list = eng_to_questions.get(eng_q)
            if not multi_list:
                # No multilingual data for this question – skip
                unmerged_questions.append(eng_q)
                continue

            # Merge missing language entries
            existing_langs = {
                entry.get('language') for entry in q_item.get('question', [])
            }
            merged = False
            for lang_entry in multi_list:
                if lang_entry.get('language') not in existing_langs:
                    q_item.setdefault('question', []).append(lang_entry)
                    merged = True
            if merged:
                updated_q += 1
            else:
                unmerged_questions.append(eng_q)

        print(f'[{os.path.basename(target_path)}] Updated {updated_q} / {total_q} questions')
        if unmerged_questions:
            print('Unmerged questions:')
            for uq in unmerged_questions:
                print(f'  - {uq}')
        # Backup original file and write the enriched version
        if os.path.isfile(target_path):
            dir_name, base_name = os.path.split(target_path)
            backup_path = os.path.join(dir_name, f"old_multi.{base_name}")
            os.rename(target_path, backup_path)   # rename to old.<original>

        # ensure output directory exists
        create_directory_if_not_exists(target_path)
        save_json_file(qald_plus, target_path)
        
def _get_gerbil_ready_filepath(json_filepath):
    dir_name, base_name = os.path.split(json_filepath)
    output_filepath = os.path.join(dir_name, f"gerbil-ready_{base_name}")
    return output_filepath

def clean_qald_gerbil_json(qald_json_filepath):
    qald_obj = read_json_file(qald_json_filepath)
    
    copy_keys = {'id', 'question', 'query', 'answers'}
    
    question_list = []
     # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing questions'):
        qald_item = {}
        orig_keys = question_item.keys()
        # Copy augmented fields
        for key_item in orig_keys: 
            if key_item in copy_keys:
                qald_item[key_item] = question_item[key_item]
        question_list.append(qald_item)
    # Create QALD Dataset
    qald_dict = {}
    if 'dataset' in qald_obj:
        qald_dict['dataset'] = qald_obj['dataset']    
    qald_dict['questions'] = question_list
    
    output_qald_file_path = _get_gerbil_ready_filepath(qald_json_filepath)
    
    # Save json
    save_json_file(qald_dict, output_qald_file_path)
    
    print(f'Cleaned file stored at: {output_qald_file_path}')
    return output_qald_file_path

def _extract_identifiers(sparql):
    # \b = word boundary, [QP] = Q or P, \d+ = one‑or‑more digits, \b = trailing word boundary
    pattern = r'\b[QP]\d+\b'
    identifiers = set(re.findall(pattern, sparql))

    # Separate Q‑identifiers (entities) from P‑identifiers (relations)
    entities = {id_ for id_ in identifiers if id_.startswith('Q')}
    relations = {id_ for id_ in identifiers if id_.startswith('P')}

    return entities, relations

def update_qald_gold_info(qald_file_path, wd_ep, prop_cache_path, use_sleep=False):
    qald_obj = read_json_file(qald_file_path)
    
    ent_pref = "http://www.wikidata.org/entity/"
    # getting cached property data
    from src.sparql_gen.pattern_based_sparql_generator import load_property_info
    load_property_info(prop_cache_path)
    # import variable after it has been initialized
    from src.sparql_gen.pattern_based_sparql_generator import PROPERTY_ID_MAP, PROPERTY_INFO_MAP

    # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing questions'):
        gold_sparql = question_item['query']['sparql']
        gold_ents, gold_rels = _extract_identifiers(gold_sparql)
        # Fetch labels
        gold_ent_ld = fetch_labels(gold_ents, wd_ep, ent_pref, use_sleep=use_sleep)
        question_item['gold_ent'] = gold_ent_ld
        
        gold_rel_ld = [{'uri': p_id, 'label': PROPERTY_INFO_MAP.get(PROPERTY_ID_MAP.get(p_id, ''), {}).get('label', '')} for p_id in gold_rels]
        question_item['gold_rel'] = gold_rel_ld

    # Backup old file
    if os.path.isfile(qald_file_path):
        dir_name, base_name = os.path.split(qald_file_path)
        backup_path = os.path.join(dir_name, f"nogold.{base_name}")
        os.rename(qald_file_path, backup_path)
    # Save json
    save_json_file(qald_obj, qald_file_path)
    
def reformat_spinach_qald(qald_file_path):
    qald_obj = read_json_file(qald_file_path)
    # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing questions'):
        question_item['augmented_translations'] = {'en': question_item['augmented_seq']}
        question_item['t5_aug'] = {'en': question_item['t5_aug']}
        # Remove the original sequence to avoid duplication
        question_item.pop('augmented_seq', None)
    
    # Backup old file
    if os.path.isfile(qald_file_path):
        dir_name, base_name = os.path.split(qald_file_path)
        backup_path = os.path.join(dir_name, f"badlyformatted.{base_name}")
        os.rename(qald_file_path, backup_path)
    # Save json
    save_json_file(qald_obj, qald_file_path)
    
def analyse_qald_mhop(qald_file_path, log_dir, model_config):
    create_directory_if_not_exists(log_dir)

    qald_obj = read_json_file(qald_file_path)
    log_file = os.path.splitext(os.path.basename(qald_file_path))[0]
    print(f'log will be saved to: {log_dir} with name {log_file}')
    proc_logger = ProcessFlowLogger(f"log_{log_file}", log_dir, enable_print=False)

    # Log input information
    proc_logger.log_input_info({
        "input_file": qald_file_path,
    })
    prog_path = os.path.join(log_dir, f"progress_{log_file}.json")
    if os.path.exists(prog_path):
        with open(prog_path, "r") as f:
            prog_data = json.load(f)
        mhop_map = prog_data.get("mhop_map", {})
        processed_ids = set(prog_data.get("processed_ids", []))
    else:
        mhop_map = {}
        processed_ids = set()

    proc_logger.start_action("Analysis QALD file for Multi-Hop Questions")
    _counter = 0

    for question_item in tqdm(qald_obj['questions'], desc='Processing questions'):
        q_id = question_item.get('id')
        if q_id in processed_ids:
            continue

        en_entry = next(
            (entry for entry in question_item.get('question', [])
             if entry.get('language') == 'en'), None)
        gold_sparql = question_item['query']['sparql']
        ent_dict = {e['label']: e['uri'] for e in question_item['gold_ent']}
        ent_dict_str = '\n'.join([f"{k}: {v}" for k, v in ent_dict.items()])
        mhop_value = mhop_analysis(en_entry, gold_sparql, ent_dict_str,
                                   model_config, proc_logger)

        mhop_map[mhop_value] = mhop_map.get(mhop_value, 0) + 1
        processed_ids.add(q_id)
        _counter += 1

        # save every 10 questions
        if _counter % 10 == 0:
            with open(prog_path, "w") as f:
                json.dump({
                    "mhop_map": mhop_map,
                    "processed_ids": list(processed_ids)
                }, f)
    # final save in case total questions isn’t a multiple of 10
    if _counter % 10 != 0:
        with open(prog_path, "w") as f:
            json.dump({
                "mhop_map": mhop_map,
                "processed_ids": list(processed_ids)
            }, f)

    return mhop_map

if __name__ == "__main__":
    ## Sample convert_basic_output call for Graph Traversal approach
    # tsv_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/prediction/tsv/aug_pred_gt.tsv"
    # output_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/prediction/json/aug_pred_gt.json"
    # has_tuples = True
    
    ## Sample convert_basic_output call for SPARQL Generation approach
    # tsv_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/prediction/tsv/aug_pred_sparql.tsv"
    # output_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/prediction/json/aug_pred_sparql.json"
    # has_tuples = False
    
    
    # qald_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/aug_gold.json"
    
    # convert_basic_output(tsv_file_path, qald_file_path, output_file_path, has_tuples=has_tuples)
    
    ## Convert SPINACH dataset to QALD-format
    # from src.const.dataset import KgqaDataset, DatasetSplit
    # from src.util.qald_io import convert_spinach_to_qald

    # spinach_ds = KgqaDataset.SPINACH_TENTRISQ10.value

    # wd_ep = spinach_ds.preferred_wd_endpoint

    # split_conf = DatasetSplit.TEST
    # input_path = 'data_dir/processed_kgqa_ds/spinach/test/test.json'

    # out_dir = os.path.dirname(input_path)
    # out_file_name = 'qald_' + os.path.basename(input_path)

    # output_file_path = os.path.join(out_dir, out_file_name)

    # dataset_name = f'{spinach_ds.dataset_name} - {split_conf.name}'

    # convert_spinach_to_qald(dataset_name, input_path, output_file_path, wd_ep)
    
    ## Enrich QALD9Plus with QALD9 multilingual questions
    # qald9_dir = 'data_dir/kgqa_datasets/qald9'
    # qald9plus_test = 'data_dir/processed_kgqa_ds/qald9plus/test/tentrisq10_aug_gold.json'
    # qald9plus_train = 'data_dir/processed_kgqa_ds/qald9plus/train/tentrisq10_updt_aug_gold.json'
    
    # fetch_qald9_multilingual_strings(qald9_dir, qald9plus_test, qald9plus_train)
    
    # from src.const.dataset import KgqaDataset, DatasetSplit
    # qald_dict = {
    #     # Train dataset not needed - ent-rel linkers might have bias
    #     # 'qald9plus_train': {
    #     #     'file_path': 'data_dir/processed_kgqa_ds/qald9plus/train/qald_9_filtered.json',
    #     #     'name': 'QALD-9-plus - Train',
    #     #     'kgqa_ds': KgqaDataset.QALD9PLUS_UPDATED_TENTRISQ10,
    #     #     'split': DatasetSplit.TRAIN
    #     # },
    #     'qald9plus_test': {
    #         'file_path': 'data_dir/processed_kgqa_ds/qald9plus/test/qald_9_augmented_final.json',
    #         'name': 'QALD-9-plus - Test',
    #         'kgqa_ds': KgqaDataset.QALD9PLUS_UPDATED_TENTRISQ10,
    #         'split': DatasetSplit.TEST
    #     },
    #     'qald10_test': {
    #         'file_path': 'data_dir/processed_kgqa_ds/qald10/test/qald_10_augmented_final.json',
    #         'name': 'QALD-10 - Test',
    #         'kgqa_ds': KgqaDataset.QALD10_UPDATED_TENTRISQ10,
    #         'split': DatasetSplit.TEST,
    #         'ignore_ids': [92, 203] # qald10 question that crashes tentris endpoint (better to avoid queries with sum)
    #     }
    # }
        
    # from src.util.qald_io import update_qald_gold_info
    # from src.const.misc import WIKIDATA_PROP_INFO_CACHE_FILEPATH
    # for qald_ds in qald_dict:
    #     print(f'Processing: {qald_ds}')
    #     ds_dict = qald_dict[qald_ds]
    #     kgqa_ds_obj = ds_dict['kgqa_ds'].value
    #     update_qald_gold_info(ds_dict['file_path'], kgqa_ds_obj.preferred_wd_endpoint, WIKIDATA_PROP_INFO_CACHE_FILEPATH)
    
    from src.const.dataset import KgqaDataset, DatasetSplit
    from src.const.llm import ChatModel
    
    llm_config = ChatModel.GPTOSS120B.value # LLM to use
    ds_info_dict = {
        'qald10_test': {
            'ds': KgqaDataset.QALD10_UPDATED_TENTRISQ10,
            'split' : DatasetSplit.TEST,
            'log_dir': 'data_dir/analysis/mhop/qald10',
        },
        'qald9plus_test': {
            'ds': KgqaDataset.QALD9PLUS_UPDATED_TENTRISQ10,
            'split' : DatasetSplit.TEST,
            'log_dir': 'data_dir/analysis/mhop/qald9plus'
        },
        'lcquad2_test': {
            'ds': KgqaDataset.LCQUAD2_UPDATED_TENTRISQ10,
            'split' : DatasetSplit.TEST,
            'log_dir': 'data_dir/analysis/mhop/lcquad2'
        },
    }
    
    for key, ds_info in ds_info_dict.items():
        print(f'Processing {key}')
        ds_obj = ds_info['ds'].value
        ds_split = ds_info['split']
        # extract the gold qald file path
        gold_qald_fp = ds_obj.split_dict[ds_split]
        log_dir = ds_info['log_dir']
        mhop_map = analyse_qald_mhop(gold_qald_fp, log_dir, llm_config)
        print(f'{key} mhop map: {mhop_map}')