import json
import os
import requests
from src.const.misc import PREFIX_MAP, SPARQL_DEFAULT_TIMEOUT, SPARQL_QUICK_TIMEOUT
import src.const.misc as misc_consts
import csv
import time
import re
import subprocess
from collections import deque, defaultdict
from typing import Dict, List, Tuple, Any

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
        stderr = result.stderr.strip()
        # If the instance/container is already gone, that's the desired outcome
        no_instance_patterns = ["no instance found", "no such container", "not found"]
        if any(pat in stderr.lower() for pat in no_instance_patterns):
            runtime = "Apptainer instance" if use_apptainer else "Docker container"
            print(f"{runtime} '{container_name}' already stopped.")
            return 0
        raise RuntimeError(f"Failed to kill container '{container_name}': {stderr}")

    runtime = "Apptainer instance" if use_apptainer else "Docker container"
    print(f"{runtime} '{container_name}' killed with {signal}.")
    return result.returncode


def count_sparql_hops(
    sparql: str,
    patterns: List[Dict[str, Any]],
    default_var: str = "?uri"
) -> Tuple[int, Dict[str, int]]:
    """
    Compute the reasoning depth (number of hops) a SPARQL query requires.
    Builds an undirected graph from the triple patterns, infers the anchor
    variable (starting point), then runs BFS to find the maximum depth to
    any terminal node. Returns (max_hops, hops_per_entity).
    Parameters
    ----------
    sparql : str
        The raw SPARQL query string.
    patterns : list of dict
        Extracted triple patterns, each with at least "s" and "o" keys.
        Path-type patterns may also have "type" == "path" and
        "path.predicates" listing the predicate chain.
    default_var : str
        Fallback anchor variable if nothing else can be inferred.
    Returns
    -------
    (max_hops, hops_per_entity)
        max_hops : int — maximum BFS depth from anchor to a terminal.
        hops_per_entity : dict mapping grounded entity URIs (wd:Q…) to
                          their hop distance.
    """
    # --- helper: check if an edge is a path-type pattern ---
    def is_path_edge(s, o):
        for pat in patterns:
            if pat.get("type") == "path" and (
                (pat.get("s") == s and pat.get("o") == o) or
                (pat.get("s") == o and pat.get("o") == s)
            ):
                return True
        return False
    # --- helper: infer the anchor variable to start BFS from ---
    def infer_anchor():
        # 1) prefer ?uri if present
        for pat in patterns:
            if pat.get("s") == "?uri" or pat.get("o") == "?uri":
                return "?uri"
        # 2) infer answer variable from SELECT clause
        answer_var = infer_answer_var()
        for pat in patterns:
            if pat.get("s") == answer_var or pat.get("o") == answer_var:
                return answer_var
        # 3) first grounded entity subject (wd:Q…)
        for pat in patterns:
            s = pat.get("s")
            if isinstance(s, str) and s.startswith("wd:Q"):
                return s
        # 4) any grounded entity
        for pat in patterns:
            for node in (pat.get("s"), pat.get("o")):
                if isinstance(node, str) and node.startswith("wd:Q"):
                    return node
        return default_var
    # --- helper: extract the answer variable from SELECT ---
    def infer_answer_var():
        s = sparql.strip()
        # aggregate queries fall back to default
        if re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", s, re.IGNORECASE):
            return default_var
        m = re.search(
            r"SELECT\s+(DISTINCT\s+|REDUCED\s+)?(.+?)\s+WHERE",
            s,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return default_var
        for tok in m.group(2).strip().split():
            if tok.startswith("?"):
                return tok
        return default_var
    # --- helper: build adjacency list from patterns ---
    def build_adj():
        adj = defaultdict(set)
        for pat in patterns:
            s, o = pat.get("s"), pat.get("o")
            # Skip wikibase:quantity* predicates — they access scalar parts of a
            # quantity value node (amount, unit, bounds) and inflate hop depth
            # without representing real knowledge-graph traversal steps.
            p_uri = str(pat.get("p", ""))
            if s and o and not p_uri.startswith("http://wikiba.se/ontology#quantity"):
                adj[s].add(o)
                adj[o].add(s)
        return adj
    # --- BFS from anchor ---
    anchor = infer_anchor()
    adj = build_adj()
    visited = {anchor}
    queue = deque([(anchor, 0)])
    max_depth = 0
    entity_depths: Dict[str, int] = {}
    while queue:
        node, depth = queue.popleft()
        max_depth = max(max_depth, depth)
        for nbr in adj.get(node, []):
            if nbr in visited:
                continue
            # path-type edges: expand by number of predicates
            if is_path_edge(node, nbr):
                for pat in patterns:
                    if pat.get("type") == "path" and (
                        (pat.get("s") == node and pat.get("o") == nbr) or
                        (pat.get("s") == nbr and pat.get("o") == node)
                    ):
                        preds = pat.get("path", {}).get("predicates", [])
                        # type paths (P31 / P279) count as 1 hop
                        if set(preds).issubset({"wdt:P31", "wdt:P279"}):
                            hop_inc = 1
                        else:
                            hop_inc = len(preds)
                        new_depth = depth + hop_inc
                        max_depth = max(max_depth, new_depth)
                        visited.add(nbr)
                        # grounded entities are terminals; otherwise continue BFS
                        if isinstance(nbr, str) and nbr.startswith("wd:Q"):
                            entity_depths[nbr] = new_depth
                        else:
                            queue.append((nbr, new_depth))
                        break
                continue
            # grounded entities (wd:Q…) are terminals
            if isinstance(nbr, str) and nbr.startswith("wd:Q"):
                new_depth = depth + 1
                max_depth = max(max_depth, new_depth)
                entity_depths[nbr] = new_depth
                visited.add(nbr)
                continue
            visited.add(nbr)
            queue.append((nbr, depth + 1))
    return max_depth, entity_depths