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