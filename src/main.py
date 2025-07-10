# Sample usage: python -m src.main
import json
import os
from openai import OpenAI
import time
from tqdm import tqdm

OPAI_CLIENT = OpenAI(base_url=os.environ.get("OPENAI_LLM_ENDPOINT"), api_key=os.environ.get("OWUI"))
MODEL_ID="gemma-3-27b-it"

INPUT_DATASET_PATH='data_dir/kgqa_datasets/qald10/qald_9_plus_train_wikidata.json'
ANALYSIS_TEMPLATE_PATH='src/template/qald9plus_analysis_template.md'

ANALYSIS_OUTPUT_DIR='data_dir/qald9plus_analysis/'


def create_directory_if_not_exists(directory_path, logger=None, quiet=True):
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
        message = f"Directory '{directory_path}' created."
    else:
        message = f"Directory '{directory_path}' already exists."
    
    if not quiet:
        if logger:
            logger.debug(message)
        else:
            print(message)

# Function to read dataset files
def read_dataset(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

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


# Function to send batches to OpenAI API
def send_to_openai(batch, markdown_content):
    
    # Create a prompt for the language model
    prompt = f"""You are analyzing a batch of examples for a question answering dataset, use the notes template provided after the examples to fill in the required information
    
    Current batch: 

    {batch}

    ---

    Notes Template:
    {markdown_content}"""
    try:
        # Call the OpenAI API
        completion = OPAI_CLIENT.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        print('Failed for prompt: {prompt}')
        raise e
    # Extract the analysis from theresponse
    analysis = completion.choices[0].message.content
    return analysis


# Function to process the dataset in batches
def process_dataset(file_path, batch_size=10):
    # Read the dataset
    data = read_dataset(file_path)
    
    # Extract the questions
    data = data['questions']
    
    # Replace large lists with a placeholder to avoid context overflow
    data = replace_large_lists(data)
    
    # Check if the analysis file already exists
    if os.path.exists(ANALYSIS_TEMPLATE_PATH):
        with open(ANALYSIS_TEMPLATE_PATH, 'r', encoding='utf-8') as file:
            markdown_content = file.read()
    else:
        raise Exception(f'Cannot find template file at {ANALYSIS_TEMPLATE_PATH}')
    
    batch_count = 0
    # Process the dataset in batches
    for i in tqdm(range(0, len(data), batch_size), desc='Analyzing batches'):
        batch = data[i:i + batch_size]
        
        # Convert batch to string for sending to OpenAI
        batch_str = json.dumps(batch, indent=2)
        
        # Send the batch to OpenAI and get the analysis
        analysis = send_to_openai(batch_str, markdown_content)
        
        # Update the markdown document with the new analysis
        markdown_content = analysis
        
        batch_count+=1
        
        # Save the intermediate analysis to a temporary file
        with open(os.path.join(ANALYSIS_OUTPUT_DIR, f'batch_{batch_count}_analysis.md'), 'w', encoding='utf-8') as batch_file:
            batch_file.write(markdown_content)
        
        # Wait for a short time to avoid too many requests
        time.sleep(2)
    
    return markdown_content


# Main function
if __name__ == "__main__":
    create_directory_if_not_exists(ANALYSIS_OUTPUT_DIR)
    # Process the dataset and get the final markdown document
    final_markdown = process_dataset(INPUT_DATASET_PATH)
    
    print("Analysis complete. Markdown document saved as 'data_dir/analysis.md'.")