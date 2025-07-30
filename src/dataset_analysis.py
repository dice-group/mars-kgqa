# Sample usage: python -m src.main
import json
import os
import time
from tqdm import tqdm
from src.util.common import read_json_file, create_directory_if_not_exists
from src.util.llm import prompt_chat_llm
from src.const.llm import ChatModels


# Function to replace large lists with a placeholder
def replace_large_lists(data, threshold=10):
    rep_count = 0
    for item in data:
        answers = item.get('answers')
        if isinstance(answers, list) and answers:
            for ind_answer in answers:
                if isinstance(ind_answer, dict) and 'results' in ind_answer:
                    results = ind_answer['results']
                    bindings = results.get('bindings')
                    if isinstance(bindings, list) and len(bindings) > threshold:
                        results['bindings'] = "this is a placeholder for a really large list of answers"
                        rep_count+=1
    print(f'Total {rep_count} large lists found in the dataset exceeding threshold of {threshold} items.')
    return data

def gen_batch_prompt(batch, markdown_content):
    # Create a prompt for the language model
    prompt = f"""You are analyzing a batch of examples for a question answering dataset, use the notes template provided after the examples to fill in the required information, follow the template structure strictly.
    
    Current batch: 

    {batch}

    ---

    Notes Template:
    {markdown_content}"""
    
    return prompt

# Function to process the dataset in batches
def analyze_dataset_batches(dataset_file_path, template_file_path, output_dir_path, client_instance, model_id, batch_size=10):
    # Read the dataset
    data = read_json_file(dataset_file_path)
    
    # Extract the questions
    data = data['questions']
    
    # Replace large lists with a placeholder to avoid context overflow
    data = replace_large_lists(data)
    
    # Check if the analysis file already exists
    if os.path.exists(template_file_path):
        with open(template_file_path, 'r', encoding='utf-8') as file:
            markdown_content = file.read()
    else:
        raise Exception(f'Cannot find template file at {template_file_path}')
    
    batch_count = 0
    # Process the dataset in batches
    for i in tqdm(range(0, len(data), batch_size), desc='Analyzing batches'):
        batch = data[i:i + batch_size]
        
        # Convert batch to string for sending to OpenAI
        batch_str = json.dumps(batch, indent=2)
        
        # Get batch analysis prompt
        cur_prompt = gen_batch_prompt(batch_str, markdown_content)
        
        # Send the batch to OpenAI and get the analysis
        analysis = prompt_chat_llm(cur_prompt, None, client_instance, model_id)
        
        # Update the markdown document with the new analysis
        markdown_content = analysis
        
        batch_count+=1
        
        # Save the intermediate analysis to a temporary file
        with open(os.path.join(output_dir_path, f'batch_{batch_count}_analysis.md'), 'w', encoding='utf-8') as batch_file:
            batch_file.write(markdown_content)
        
        # Wait for a short time to avoid too many requests
        time.sleep(2)
    print(f"Batch-wise analysis complete. Generated documents can be found at: {output_dir_path}.")
        
def merge_batch_analyses(doc_dir, merge_file_name, client_instance, model_id):
    
    temp_doc_dir = os.path.join(doc_dir, "temp")
    
    create_directory_if_not_exists(temp_doc_dir)
    
    # Find all the documents in this directory
    batch_files = [f for f in os.listdir(doc_dir) if f.endswith('_analysis.md')]

    # Sort the files to ensure they are merged in order
    batch_files.sort()

    # Initialize the merged content with the first batch analysis
    merged_content = ''
    if batch_files:
        with open(os.path.join(doc_dir, batch_files[0]), 'r', encoding='utf-8') as file:
            merged_content = file.read()

    # Merge the batch analysis documents
    for batch_file in tqdm(batch_files[1:], desc='Merging analyses'):
        with open(os.path.join(doc_dir, batch_file), 'r', encoding='utf-8') as file:
            batch_content = file.read()

        # Create a prompt for merging
        merge_prompt = f"""You are merging multiple analysis documents into a single document. You can generalize common statements, but do not omit important information.

        Current merged content:

        {merged_content}

        ---

        New batch content:

        {batch_content}

        """

        # Send the merge prompt to OpenAI and get the merged analysis
        merged_content = prompt_chat_llm(merge_prompt, None, client_instance, model_id)

        # Save the intermediate merge to a temporary file
        with open(os.path.join(temp_doc_dir, f'intermediate_merge_{batch_file}'), 'w', encoding='utf-8') as merge_file:
            merge_file.write(merged_content)

    # Save the final merge
    merged_file_path = os.path.join(doc_dir, merge_file_name)
    with open(merged_file_path, 'w', encoding='utf-8') as final_file:
        final_file.write(merged_content)
        
    print(f"Document merging complete. Final analysis document saved as: {merged_file_path}.")

# Main function
if __name__ == "__main__":
    #model_config = ChatModels.GEMMA3.value
    model_config = ChatModels.QWEN3.value
    # Initializing variables
    opai_client = model_config.get_static_instance()
    model_id=model_config.model_id
    
    input_dataset_path='data_dir/kgqa_datasets/qald10/qald_9_plus_train_wikidata.json'
    analysis_template_path='src/template/qald9plus_analysis_template.md'

    analysis_output_dir='data_dir/qald9plus_analysis/'

    final_mergefile_name='merged_analysis.md' # it will be put in ANALYSIS_OUTPUT_DIR
    
    # Starting analysis
    create_directory_if_not_exists(analysis_output_dir)
    # Process the dataset and generate batch-wise analyses
    analyze_dataset_batches(input_dataset_path, analysis_template_path, analysis_output_dir, opai_client, model_id)
    # Merge the batch analysis documents
    merge_batch_analyses(analysis_output_dir, final_mergefile_name, opai_client, model_id)