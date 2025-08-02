#WIKIDATA_ENDPOINT_URL = "https://skynet.coypu.org/wikidata/" # QALD10
WIKIDATA_ENDPOINT_URL = "https://wikidata.data.dice-research.org/sparql"
# WIKIDATA_ENDPOINT_URL = "https://query.wikidata.org/sparql"

SPARQL_HARD_LIMIT = 10000

ADD_NODES_EXPANSION_LIMIT = 5 # Maximum number of nodes to expand further
MAX_TRIES = 10 # Maximum iterations to keep trying looking for an answer
EXTENDED_ANSWER_SEARCH_LIMIT = 3 # Maximum iterations to keep looking after previous answers were found

TRIPLE_VERBALIZATION_LENGTH_LIMIT = 400 # To keep things under for a tokenization length of 512, just to be on the safe side ;)

ANSWER_NOT_FOUND_STR = 'Answer not found'
LITERAL_VAL_PREFIX = 'literal_val:'