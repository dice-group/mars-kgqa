import json
import os
import requests
from src.const.misc import PREFIX_MAP
import csv

# Reference: https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe-GGUF
def dot(va, vb):
    return sum(a * b for a, b in zip(va, vb))

def get_last_uri_fragment(uri):
    # Split on '/' first, then on '#', and take the final non‑empty part.
    fragment = uri.rsplit('/', 1)[-1]
    fragment = fragment.rsplit('#', 1)[-1]
    return fragment

def create_directory_if_not_exists(directory_path, logger=None, quiet=True):
    # Convert the path to an absolute path
    directory_path = os.path.abspath(directory_path)
    
    # Check if the path is a file path and extract the parent directory
    if not os.path.isdir(directory_path):
        directory_path = os.path.dirname(directory_path)
    
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

def save_json_file(json_obj, output_file_path):
    create_directory_if_not_exists(output_file_path)
    # Write qald_obj to output_file_path
    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        json.dump(json_obj, outfile, ensure_ascii=False, indent=4)

def execute_sparql_query(query, endpoint_url, get_only_bindings=True):
    headers = {
        "Accept": "application/sparql-results+json",
        # Identify the client as Firefox (optional version string)
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0"
    }
    
    req_failed = False

    try:
        response = requests.get(endpoint_url, params={'query': query, 'format': 'json'}, headers=headers, timeout=600)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()
    except requests.exceptions.RequestException as e:
        # TODO: Try again for Service Unavailable Errors: "HTTP Request failed: 503 Server Error: Service Unavailable for url:"
        print(f"Failed SPARQL: {query}")
        print(f"HTTP Request failed: {e}")
        req_failed = True
        return [] if get_only_bindings else {}, req_failed

    ret_val = data
    if get_only_bindings:
        ret_val = data['results']['bindings']
    return ret_val, req_failed

def get_prefixed_id(resource_uri):
    longest_ns: str | None = None
    longest_pfx: str | None = None

    for ns, pfx in PREFIX_MAP.items():
        if resource_uri.startswith(ns):
            # Keep the longest namespace seen so far
            if longest_ns is None or len(ns) > len(longest_ns):
                longest_ns = ns
                longest_pfx = pfx

    if longest_ns is not None and longest_pfx is not None:
        local = resource_uri[len(longest_ns):]   # strip the matched namespace
        return f"{longest_pfx}:{local}"

    return f'<{resource_uri}>' # for URIs that cannot be prefixed

def export_csv(output_file, dataset):
    create_directory_if_not_exists(output_file)
    with open(output_file, "w") as f:
        writer = csv.writer(f)
        writer.writerows(dataset)
    f.close()
    print("csv file is exported to ", output_file)