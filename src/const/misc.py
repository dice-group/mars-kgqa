QALD10_WIKIDATA_EP = "https://skynet.coypu.org/wikidata/" # Dump: https://zenodo.org/records/7496690
TENTRIS_WIKIDATA_EP = "https://wikidata.data.dice-research.org/sparql" # Dump: https://files.dice-research.org/datasets/Wikidata/wikidata-20240904-truthy-BETA/
CURRENT_WIKIDATA_EP = "https://query.wikidata.org/sparql"

DEFAULT_WIKIDATA_ENDPOINT_URL = TENTRIS_WIKIDATA_EP

SPARQL_HARD_LIMIT = 10000

ADD_NODES_EXPANSION_LIMIT = 5 # Maximum number of nodes to expand further
MAX_TRIES = 10 # Maximum iterations to keep trying looking for an answer
EXTENDED_ANSWER_SEARCH_LIMIT = 3 # Maximum iterations to keep looking after previous answers were found

TRIPLE_VERBALIZATION_LENGTH_LIMIT = 400 # To keep things under for a tokenization length of 512, just to be on the safe side ;)

ANSWER_NOT_FOUND_STR = 'Answer not found'
LITERAL_VAL_PREFIX = 'literal_val:'

WIKIDATA_PROP_INFO_CACHE_FILEPATH = "data_dir/cache/wikidata_relations.json"