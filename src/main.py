import json
import os
from openai import OpenAI
import time
from tqdm import tqdm

OPAI_CLIENT = OpenAI(base_url=os.environ.get("OPENAI_LLM_ENDPOINT"), api_key=os.environ.get("OWUI"))
MODEL_ID="gemma-3-27b-it"

INPUT_DATASET_PATH='data_dir/kgqa_datasets/qald10/qald_9_plus_train_wikidata.json'
ANALYSIS_FILE_PATH='data_dir/qald9plus_analysis.md'

# Construct the temporary file path
TEMP_FILE_PATH = 'temp.' + os.path.basename(ANALYSIS_FILE_PATH)
TEMP_FILE_PATH = os.path.join(os.path.dirname(ANALYSIS_FILE_PATH), TEMP_FILE_PATH)

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
    prompt = f"""Analyze the following batch of questions from a question-answering dataset, and replace the current notes with your updated analysis that should include different types of questions you have seen so far with some examples, do not write anything other than the content for the notes:

    {batch}

    ---

    Current Notes in Markdown:
    {markdown_content}"""
    try:
        # Call the OpenAI API
        completion = OPAI_CLIENT.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        with open(TEMP_FILE_PATH, 'w', encoding='utf-8') as temp_file:
            temp_file.write(prompt)
        raise e
    # Extract the analysis from theresponse
    analysis = completion.choices[0].message.content
    return analysis


# Function to process the dataset in batches
def process_dataset(file_path, batch_size=20):
    # Read the dataset
    data = read_dataset(file_path)
    
    # Extract the questions
    data = data['questions']
    
    # Replace large lists with a placeholder to avoid context overflow
    data = replace_large_lists(data)
    
    # Check if the analysis file already exists
    if os.path.exists(ANALYSIS_FILE_PATH):
        with open(ANALYSIS_FILE_PATH, 'r', encoding='utf-8') as file:
            markdown_content = file.read()
    else:
        # Initialize an empty markdown document
        markdown_content = "# Analysis of Dataset\n\n"
    
    # Process the dataset in batches
    for i in tqdm(range(0, len(data), batch_size), desc='Analyzing batches'):
        batch = data[i:i + batch_size]
        
        # Convert batch to string for sending to OpenAI
        batch_str = json.dumps(batch, indent=2)
        
        # Send the batch to OpenAI and get the analysis
        analysis = send_to_openai(batch_str, markdown_content)
        
        # Update the markdown document with the new analysis
        markdown_content = analysis
        
        # Save the intermediate analysis to a temporary file
        with open(TEMP_FILE_PATH, 'w', encoding='utf-8') as temp_file:
            temp_file.write(markdown_content)
        
        # Wait for a short time to avoid too many requests
        time.sleep(2)
    
    return markdown_content


# Main function
if __name__ == "__main__":
    
    # Process the dataset and get the final markdown document
    final_markdown = process_dataset(INPUT_DATASET_PATH)
    
    # Save the final markdown document to a file
    with open(ANALYSIS_FILE_PATH, 'w', encoding='utf-8') as file:
        file.write(final_markdown)
    
    print("Analysis complete. Markdown document saved as 'data_dir/analysis.md'.")