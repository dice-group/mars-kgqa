import json
import os
import requests
from src.const.misc import PREFIX_MAP, SPARQL_DEFAULT_TIMEOUT, SPARQL_QUICK_TIMEOUT
import src.const.misc as misc_consts
import csv
import time
import re
import subprocess

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

    # If a file path was given, use its parent directory
    if not os.path.isdir(directory_path):
        directory_path = os.path.dirname(directory_path)

    try:
        # exist_ok=True tells makedirs to ignore the error if the dir already exists
        os.makedirs(directory_path, exist_ok=True)
        message = f"Directory '{directory_path}' created."
    except FileExistsError:
        # This can happen on a tiny race window; treat it as “already exists”
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
        
def log_sparql_query(sparql_query):
    ol_query = sparql_one_line(sparql_query)
    misc_consts.sparql_log_filehandle.write(ol_query + '\n')

def execute_sparql_query(query, endpoint_url, get_only_bindings=True, timeout=600, use_sleep=False):
    headers = {
        "Accept": "application/sparql-results+json",
        # Identify the client as Firefox (optional version string)
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0"
    }
    
    # Log the query
    log_sparql_query(query)
    
    req_failed = False

    try:
        response = requests.post(endpoint_url, data={'query': query, 'format': 'json'}, headers=headers, timeout=timeout)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()
    except requests.exceptions.RequestException as e:
        # TODO: Try again for Service Unavailable Errors: "HTTP Request failed: 503 Server Error: Service Unavailable for url:"
        # When a query is malformed, its usually this error: "HTTP Request failed: 400 Client Error: Bad Request for url:"
        # Or "HTTP Request failed: 500 Server Error: Server Error for url:"
        print(f"Failed SPARQL: {query}")
        print(f"HTTP Request failed: {e}")
        req_failed = True
        return [] if get_only_bindings else {}, req_failed
    
    
    # to avoid overwhelming the endpoint with frequent requests
    if use_sleep:
        time.sleep(3) # not need if using local endpoints

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
    
def get_sparql_timeout(use_sleep=False):
    timeout = SPARQL_DEFAULT_TIMEOUT if use_sleep else SPARQL_QUICK_TIMEOUT
    return timeout

def sparql_one_line(query):
    """
    Convert a multiline SPARQL string to a single-line representation.
    """
    no_comments = re.sub(
        r'(?s:"""(?:[^\\]|\\.)*?""")|'     # triple-double-quoted string (DOTALL)
        r"(?s:'''(?:[^\\]|\\.)*?''')|"      # triple-single-quoted string (DOTALL)
        r'"(?:[^"\\]|\\.)*"|'              # double-quoted string
        r"'(?:[^'\\]|\\.)*'|"             # single-quoted string
        r'(<[^>]*>)'                       # URI ref
        r'|(#.*)',                          # stops at newline
        lambda m: m.group(0) if not m.group(2) else '',
        query,
    )

    return re.sub(r'\s+', ' ', no_comments).strip()

def kill_container(container_name: str, signal: str = "SIGKILL", use_apptainer: bool = False) -> int:
    print(f"Apptainer config dir: {os.getenv('APPTAINER_CONFIGDIR', 'No Apptainer config dir set!')}")
    if use_apptainer:
        cmd = ["apptainer", "instance", "stop", "--signal", signal, container_name]
    else:
        cmd = ["docker", "kill", "--signal", signal, container_name]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to kill container '{container_name}': {result.stderr.strip()}")

    runtime = "Apptainer instance" if use_apptainer else "Docker container"
    print(f"{runtime} '{container_name}' killed with {signal}.")
    return result.returncode