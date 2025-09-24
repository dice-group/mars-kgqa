from src.util.common import read_json_file, create_directory_if_not_exists, execute_sparql_query, save_json_file
from src.const.misc import ANSWER_NOT_FOUND_STR, LITERAL_VAL_PREFIX, DEFAULT_WIKIDATA_ENDPOINT_URL
import csv
import os
import json
import ast
from tqdm import tqdm

def convert_lcquad2_to_qald(lcquad2_file_path, output_qald_file_path, sparql_endpoint):
    lcquad_data = read_json_file(lcquad2_file_path)
    qald_questions = []
    copy_keys = ['augmented_seq', 'found_ent', 'found_rel', 'gold_ent', 'gold_rel', 'augmented_ent', 'augmented_rel', 'filtered_ent', 'filtered_rel']
    for qa_item in tqdm(lcquad_data, desc='Processing Questions'):
        qald_item = {}
        
        id = qa_item['uid']
        sparql = qa_item['sparql_wikidata']
        # Fetch the answer
        para_text = qa_item['paraphrased_question']
        question_text = para_text if para_text else qa_item['question']
        if not question_text:
            continue
        formatted_sparql, sparql_response = get_qald_answer_sparql(sparql, sparql_endpoint)
        answer_obj = [sparql_response]
        # Build QALD item dictionary
        qald_item['id'] = str(id) # For uniformity
        qald_item['answers'] = answer_obj
        qald_item['query'] = { 'sparql': formatted_sparql}
        qald_item['question'] = [{ "language": "en", "string": question_text}]
        # Copy augmented fields
        for key_item in copy_keys:
            if key_item in qa_item:
                qald_item[key_item] = qa_item[key_item]
            
        qald_questions.append(qald_item)
    # Create QALD Dataset    
    qald_dict = {'dataset': {'id': 'LC-QuAD2.0'}, 'questions' : qald_questions}
    # Save json
    save_json_file(qald_dict, output_qald_file_path)
    

def get_qald_answer_sparql(sparql, endpoint, use_sleep=False):
    
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
    
    sparql_response, _ = execute_sparql_query(formatted_sparql, endpoint, get_only_bindings=False, use_sleep=use_sleep)
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
    # TODO: Implement
    # For each file in qald9_dir
    # Read them into json, then iterate over 'questions'
    # For each question, open the 'question' list of dict with items like {'language': <langcode>, 'string': <question_string>}
    # Find the 'en' string and then save it to dictionary like <english_question_string>: <question_list_of_dict>
    # Raise error if a repeated english entry is found
    
    # Once the string dictionary is ready, now iterate over all the the qald_9plus_filepaths
    # Check if the English question is in the dictionary
    # if yes, then add every language string that is not there
    
    # replace the current files with one with old_multi. prefix
    # write the new files with the current name
    pass

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
    from src.const.dataset import KgqaDataset, DatasetSplit
    from src.util.qald_io import convert_spinach_to_qald

    spinach_ds = KgqaDataset.SPINACH_TENTRISQ10.value

    wd_ep = spinach_ds.preferred_wd_endpoint

    split_conf = DatasetSplit.TEST
    input_path = 'data_dir/processed_kgqa_ds/spinach/test/test.json'

    out_dir = os.path.dirname(input_path)
    out_file_name = 'qald_' + os.path.basename(input_path)

    output_file_path = os.path.join(out_dir, out_file_name)

    dataset_name = f'{spinach_ds.dataset_name} - {split_conf.name}'

    convert_spinach_to_qald(dataset_name, input_path, output_file_path, wd_ep)