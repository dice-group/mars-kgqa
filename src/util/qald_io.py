from src.util.common import read_json_file, create_directory_if_not_exists
from src.const.misc import ANSWER_NOT_FOUND_STR, LITERAL_VAL_PREFIX
import csv
import json
import ast

def get_qald_answer_sparql(sparql, endpoint):
    pass


def get_qald_answer_obj(answer_tuples):
    # Generate bindings
    bindings = []
    
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

def load_tsv_answers_dict(file_path):
    answers_dict = dict()
    with open(file_path, 'r', newline='', encoding='utf-8') as tsvfile:
        reader = csv.reader(tsvfile, delimiter='\t')
        next(reader)  # Skip the header row
        for row in reader:
            question_id = row[0]
            answer_str = row[1]
            try:
                answer = ast.literal_eval(answer_str)
            except (ValueError, SyntaxError):
                answer = answer_str  # Fallback to original string if parsing fails
            answers_dict[question_id] = answer
    return answers_dict

# Function to convert the output from basic factiod solver to qald format with answers
def convert_bfs_output(tsv_file_path, qald_file_path, output_file_path):
    tsv_dict = load_tsv_answers_dict(tsv_file_path)
    qald_obj = read_json_file(qald_file_path)
    # For each id in the qald_gold
    for question_item in qald_obj['questions']:
        # Extract answers out of tsv_data and create a qald answer object
        question_id = question_item['id']
        answer_tuple = []
        if question_id in tsv_dict:
            answer_tuple = tsv_dict[question_id]
        answer_obj = get_qald_answer_obj(answer_tuple)
        question_item['answers'] = answer_obj
        question_item['query'] = {}    
    
    # Write qald_obj to output_file_path
    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        json.dump(qald_obj, outfile, ensure_ascii=False, indent=4)
    

if __name__ == "__main__":
    # Sample convert_bfs_output call
    tsv_file_path = "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent_answers.tsv"
    qald_file_path = "data_dir/processed_kgqa_ds/qald_linked_augmented_gold_ent.json"
    output_file_path = "data_dir/processed_kgqa_ds/prediction/pred_qald_linked_augmented_gold_ent.json"
    create_directory_if_not_exists(output_file_path)
    
    convert_bfs_output(tsv_file_path, qald_file_path, output_file_path)