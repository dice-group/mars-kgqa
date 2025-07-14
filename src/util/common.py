import json
import os

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

# Function to send batches to OpenAI API
def send_to_llm(prompt, client_instance, model_id):
    try:
        # Call the OpenAI API
        completion = client_instance.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        print('Failed for prompt: {prompt}')
        raise e
    # Extract the analysis from theresponse
    model_res_text = completion.choices[0].message.content
    return model_res_text