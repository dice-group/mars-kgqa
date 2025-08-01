from src.util.common import read_json_file, create_directory_if_not_exists, execute_sparql_query
from src.const.misc import ANSWER_NOT_FOUND_STR, LITERAL_VAL_PREFIX, WIKIDATA_ENDPOINT_URL
import csv
import json
import ast
from tqdm import tqdm

def get_qald_answer_sparql(sparql, endpoint):
    
    formatted_sparql = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    
    {sparql}
    """
    
    if "limit" not in formatted_sparql.lower():
        # Adding hard limit for the results
        formatted_sparql += "\nLIMIT 100"
    
    sparql_bindings = execute_sparql_query(formatted_sparql, endpoint, get_only_bindings=False)
    return formatted_sparql, sparql_bindings


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
            question_id = row[0]
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
def convert_basic_output(tsv_file_path, qald_file_path, output_file_path, has_tuples):
        
    tsv_dict = load_tsv_answers_dict(tsv_file_path, has_tuples)
    qald_obj = read_json_file(qald_file_path)
    # For each id in the qald_gold
    for question_item in tqdm(qald_obj['questions'], desc='Processing Answers'):
        # Extract answers out of tsv_data and create a qald answer object
        question_id = question_item['id']
        answer_item = None
        if question_id in tsv_dict:
            answer_item = tsv_dict[question_id]
        
        if has_tuples:
            answer_obj = get_qald_answer_obj(answer_item)
            question_item['query'] = {}
        else:
            formatted_sparql, qald_answer = get_qald_answer_sparql(answer_item, WIKIDATA_ENDPOINT_URL)
            answer_obj = [qald_answer]
            question_item['query'] = { 'sparql': formatted_sparql}

        question_item['answers'] = answer_obj    
    
    # Write qald_obj to output_file_path
    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        json.dump(qald_obj, outfile, ensure_ascii=False, indent=4)
    

if __name__ == "__main__":
    ## Sample convert_basic_output call for Graph Traversal approach
    # tsv_file_path = "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent_answers.tsv"
    # output_file_path = "data_dir/processed_kgqa_ds/prediction/pred_qald_linked_augmented_gold_ent.json"
    # has_tuples = True
    
    ## Sample convert_basic_output call for SPARQL Generation approach
    tsv_file_path = "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent_gen_sparqls.tsv"
    output_file_path = "data_dir/processed_kgqa_ds/prediction/pred_sparql_qald_linked_augmented_gold_ent.json"
    has_tuples = False
    
    
    qald_file_path = "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent.json"
    
    create_directory_if_not_exists(output_file_path)
    
    convert_basic_output(tsv_file_path, qald_file_path, output_file_path, has_tuples=has_tuples)