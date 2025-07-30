import json
import os

# Reference: https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe-GGUF
def dot(va, vb):
    return sum(a * b for a, b in zip(va, vb))

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
def read_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data