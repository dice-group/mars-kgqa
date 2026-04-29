from enum import Enum, auto
from transformers import AutoTokenizer
import os

# QALD10_WIKIDATA_EP = "https://skynet.coypu.org/wikidata/" # Dump: https://zenodo.org/records/7496690
QALD10_WIKIDATA_EP = "https://wikidata-qald10.data.dice-research.org/sparql" # Dump: https://zenodo.org/records/7496690 # virtuoso @ dice

QALD10_TENTRIS_WIKIDATA_EP = "http://harebell.cs.upb.de:10040/sparql" # Dump: https://zenodo.org/records/7496690 # tentris @ dice

TENTRIS_WIKIDATA_EP = "https://wikidata.data.dice-research.org/sparql" # Dump: https://files.dice-research.org/datasets/Wikidata/wikidata-20240904-truthy-BETA/
TENTRIS_MAIN_WIKIDATA_EP = "http://enexa1.cs.uni-paderborn.de:9080/sparql" # Dump: Main split from all wikidata 22.01.2026
CURRENT_WIKIDATA_EP = "https://query.wikidata.org/sparql"
#CURRENT_WIKIDATA_EP = "https://qlever.cs.uni-freiburg.de/api/wikidata" # Fails on basic pattern retrieval with 500: Internal Server Error

DEFAULT_WIKIDATA_ENDPOINT_URL = TENTRIS_MAIN_WIKIDATA_EP

SPARQL_HARD_LIMIT = 10000

SPARQL_DEFAULT_TIMEOUT = 60
SPARQL_QUICK_TIMEOUT = 10

ADD_NODES_EXPANSION_LIMIT = 5 # Maximum number of nodes to expand further
MAX_TRIES = 10 # Maximum iterations to keep trying looking for an answer
EXTENDED_ANSWER_SEARCH_LIMIT = 3 # Maximum iterations to keep looking after previous answers were found

TRIPLE_PATTERN_N_TOP = 20
MAX_MULTI_HOP = 5
TRIPLE_VERBALIZATION_LENGTH_LIMIT = 400 # To keep things under for a tokenization length of 512, just to be on the safe side ;)

ANSWER_NOT_FOUND_STR = 'Answer not found'
LITERAL_VAL_PREFIX = 'literal_val:'

WIKIDATA_PROP_INFO_CACHE_FILEPATH = "data_dir/cache/wikidata_relations.json"

GERBIL_EXPERIMENT_URI_STORE_FILEPATH = "data_dir/gerbil_results.tsv"

PREFIX_BLOCK = """
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX cc: <http://creativecommons.org/ns#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX hint: <http://www.bigdata.com/queryHints#> 
PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

PREFIX p: <http://www.wikidata.org/prop/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX pqn: <http://www.wikidata.org/prop/qualifier/value-normalized/>
PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX prn: <http://www.wikidata.org/prop/reference/value-normalized/>
PREFIX prv: <http://www.wikidata.org/prop/reference/value/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdata: <http://www.wikidata.org/wiki/Special:EntityData/>
PREFIX wdno: <http://www.wikidata.org/prop/novalue/>
PREFIX wdref: <http://www.wikidata.org/reference/>
PREFIX wds: <http://www.wikidata.org/entity/statement/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wdtn: <http://www.wikidata.org/prop/direct-normalized/>
PREFIX wdv: <http://www.wikidata.org/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
"""

def _build_prefix_map(block: str) -> dict[str, str]:
    """Return {namespace_uri: prefix} from a PREFIX block."""
    mapping = {}
    for line in block.strip().splitlines():
        # line format: PREFIX prefix: <uri>
        parts = line.split()
        if len(parts) != 3:
            continue
        prefix = parts[1].rstrip(":")
        uri = parts[2].strip("<>")
        mapping[uri] = prefix
    return mapping

PREFIX_MAP = _build_prefix_map(PREFIX_BLOCK)

class EntityAnnotator(Enum):
    # AUG_EL_V0D1 = 'aug_linker_v0.1'
    T5AUG_ERL = 't5_aug'   # used by most datasets (qald9plus test, qald10, lcquad2)
    T5_ERL    = 't5'        # used by qald9plus/train/tentrismain_aug_gold.json only
    GRASP = 'grasp' # used by qald10 at the moment

NOMIC_V2_TOKENIZER = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v2-moe")

LLAMA_SERVER_ENDPOINT = os.environ.get("LLAMA_SERVER_ENDPOINT")
LLAMA_MAX_CTX = int(os.environ.get("LLAMA_CTX", 0))
LLAMA_CONTAINER_NAME = os.environ.get("LLAMA_CONTAINER_NAME")
SLURM_ACTIVE = bool(os.environ.get("SLURM_ACTIVE", False))

RUN_STATS = {'failure_count': 0}

sparql_log_filehandle = None # will get a value assigned in run.py
