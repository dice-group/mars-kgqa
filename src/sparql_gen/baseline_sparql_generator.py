# Sample usage: python -m src.sparql_gen.baseline_sparql_generator
from src.sparql_gen.sparql_gen_common import save_answers_as_tsv
from src.kgqa_tool.llm_request import generate_baseline_sparql
from src.const.llm import DEFAULT_CHAT_LLM_CONFIG
from src.util.common import read_json_file
from tqdm import tqdm



def process_input_query(question_txt, model_config):
    print(f'Processing question: {question_text}')
    
    sparql = generate_baseline_sparql(question_txt, model_config)
    
    print(f'Generated SPARQL: {sparql}')
        
    return sparql


# Example usage
if __name__ == "__main__":
    qald_file_path = "data_dir/processed_kgqa_ds/qald9plus/test/aug_gold.json"
    # Read the qald9 preprocessed file
    qald_json = read_json_file(qald_file_path)
    
    answers_dict = dict()
    # For each question
    for question_item in tqdm(qald_json['questions'],desc='Processed Questions'):
        question_id = question_item['id']

         # Extract the English question text
        question_text = next((q['string'] for q in question_item['question'] if q['language'] == 'en'), None)
        # send to process_input_query
        cur_generated_sparql = process_input_query(question_text, DEFAULT_CHAT_LLM_CONFIG)
        
        answers_dict[question_id] = cur_generated_sparql
    
    # Save answers dict as tsv
    save_answers_as_tsv(answers_dict, "data_dir/processed_kgqa_ds/qald9plus/test/prediction/tsv/baseline_pred_sparql.tsv")