from enum import Enum, unique
from typing import Callable

from src.sparql_gen.pattern_based_sparql_generator import (
    process_input_query_1hop as pbsg_1hop_fn,
    process_input_query_2hop as pbsg_2hop_fn,
    initialize_aux_values as pbsg_init
)
from src.sparql_gen.simple_sparql_generator import process_input_query as ssg_fn


@unique
class Approach(Enum):
    """Enum that maps an approach identifier to its processing callable."""

    SSG = ("SSG", ssg_fn, None)
    PBSG_1HOP = ("PBSG_1HOP", pbsg_1hop_fn, pbsg_init)
    PBSG_2HOP = ("PBSG_2HOP", pbsg_2hop_fn, pbsg_init)

    def __init__(self, label: str, processor: Callable, aux_init: Callable):
        # expose the callable as a attribute for later use
        self.processor = processor
        self.aux_init = aux_init