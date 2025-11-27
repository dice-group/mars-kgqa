from enum import Enum, unique
from typing import Callable

from src.sparql_gen.pattern_based_sparql_generator import (
    process_input_query_multi_hop as pbsg_mhop_fn,
    initialize_aux_values as pbsg_init
)
from src.sparql_gen.simple_sparql_generator import process_input_query as ssg_fn

from src.sparql_gen.subgraph_based_sparql_generator import process_input_query as sbsg_fn

@unique
class Approach(Enum):
    """Enum that maps an approach identifier to its processing callable."""

    # SSG = ("SSG", ssg_fn, None)
    PBSG_MHOP =  ("PBSG_MHOP", pbsg_mhop_fn, pbsg_init)
    SBSG = ("SBSG", sbsg_fn, None)

    def __init__(self, label: str, processor: Callable, aux_init: Callable):
        # expose the callable as a attribute for later use
        self.processor = processor
        self.aux_init = aux_init