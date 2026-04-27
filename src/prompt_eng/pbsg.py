"""
DSPy sandbox for pattern-based SPARQL generation (PE pipeline).

Each Signature mirrors one LLM-calling function in src/kgqa_tool/llm_request.py
so that MIPROv2-optimised instruction text can be extracted and pasted back
directly into the production prompts.

Mapping:
  SparqlFromPatterns  →  generate_sparql_from_patterns
  ExpandOrFinalize    →  generate_sparql_or_expansion_indices
  SparqlRefine        →  sparql_refinement
  MhopEstimate        →  estimate_mhop
  VerifyUpdateSparql  →  verify_update_generated_sparql

The Module's forward() mirrors process_input_query_multi_hop() exactly:
  mhop=1              →  final_sparql  (SparqlFromPatterns)
  mhop>1, each hop    →  expand_or_finalize  (ExpandOrFinalize)
  hop limit exceeded  →  final_sparql  (SparqlFromPatterns)
"""

from typing import Optional

import dspy

from src.sparql_gen.pattern_based_sparql_generator import (
    _collect_root_patterns,
    _score_and_select_top,
    _build_verbalizations,
    _update_edge_cache,
    _build_cache_key,
    extract_patterns_data,
    initialize_aux_values,
    PROPERTY_ID_MAP,
)
from src.kgqa_tool.graph_traversal import find_next_hop_patterns
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL, TRIPLE_PATTERN_N_TOP
from src.const.llm import ModelAPIConfig
from src.util.process_flow_logger import ProcessFlowLogger
from src.util.qald_io import get_qald_answer_sparql
from src.sparql_gen.sparql_gen_common import construct_results_literal


# Module-level logger used by the imported KG-traversal helpers (_collect_root_patterns,
# _score_and_select_top). Reconfigured via init_proc_logger() before each run.
PROC_LOGGER: ProcessFlowLogger = None


def init_proc_logger(output_dir: str = "data_dir/pe_logs") -> None:
    """Create (or replace) the module-level process-flow logger."""
    global PROC_LOGGER
    PROC_LOGGER = ProcessFlowLogger(
        process_name="pbsg_pe",
        output_dir=output_dir,
        enable_print=False,
    )


def configure_lm(llm_config: ModelAPIConfig) -> None:
    """Configure DSPy's global LM from a ModelAPIConfig instance.
    Call this from pe_entry.py before running process_dataset."""
    lm = dspy.LM(
        model=f"openai/{llm_config.model_id}",
        api_base=llm_config.endpoint,
        api_key=llm_config.api_key or "no-key",
        temperature=0.0,
        max_tokens=2048,
        cache=True,
        model_type="chat",
    )
    dspy.configure(lm=lm)


# ─────────────────────────────────────────────────────────────────────────────
# Signatures
# Input fields contain only what the corresponding production f-string actually
# interpolates, so the optimised instruction text is a drop-in replacement.
# ─────────────────────────────────────────────────────────────────────────────

class SparqlFromPatterns(dspy.Signature):
    """Given a natural language question, identified entities and a set of Wikidata
    triple patterns (subject, predicate, object) including entity IDs and domain/range
    type restrictions, generate a valid Wikidata SPARQL query utilizing the relevant
    provided IDs that answers the question. Prioritize triple patterns where the entity
    IDs appear relevant to the question and the domain/range types align with the
    expected answer type. Discard any triple patterns that do not contribute to
    answering the question. Do not try to retrieve labels unless explicitly asked."""
    question: str = dspy.InputField()
    entities: str = dspy.InputField(desc="identified question entities with their Wikidata QIDs, one per line as 'label: QID'")
    patterns: str = dspy.InputField(desc="candidate Wikidata triple patterns with entity IDs; one pattern per line, 0-indexed")
    sparql: str = dspy.OutputField(desc="a valid Wikidata SPARQL query, on a single line")


class ExpandOrFinalize(dspy.Signature):
    """Given a natural language question, identified entities and a set of Wikidata triple
    patterns (subject, predicate, object) including entity IDs and domain/range type
    restrictions, decide whether enough information is available to generate a final SPARQL
    query, or whether more graph traversal is needed. Prioritize triple patterns where the
    entity IDs appear relevant to the question and the domain/range types align with the
    expected answer type. Discard any triple patterns that do not contribute to answering
    the question. Do not try to retrieve labels unless explicitly asked. If the patterns are
    sufficient, produce a valid Wikidata SPARQL query. If not, return the comma-separated
    0-based indices of the patterns to expand further — pick at least one and do not pick
    too many."""
    question: str = dspy.InputField()
    entities: str = dspy.InputField(desc="identified question entities with their Wikidata QIDs, one per line as 'label: QID'")
    patterns: str = dspy.InputField(desc="candidate Wikidata triple patterns indexed from 0; one pattern per line")
    sparql: Optional[str] = dspy.OutputField(desc="a valid Wikidata SPARQL query on a single line; populated only when patterns are sufficient to answer the question")
    expand_indices: Optional[str] = dspy.OutputField(desc="comma-separated 0-based indices of patterns to expand; populated only when more traversal is needed")


class SparqlRefine(dspy.Signature):
    """For the given question, fix the provided Wikidata SPARQL. Write it as-is if no
    fix is required."""
    question: str = dspy.InputField()
    sparql: str = dspy.InputField()
    refined_sparql: str = dspy.OutputField(desc="the fixed SPARQL query, or the original if no fix was needed")


class MhopEstimate(dspy.Signature):
    """For the given question alongside the recognized entities and relations, estimate
    the number of hops required in the knowledge graph from these entities to generate
    a SPARQL that answers the question."""
    question: str = dspy.InputField()
    entities: str = dspy.InputField(desc="identified question entities")
    relations: str = dspy.InputField(desc="identified question relations")
    mhop: int = dspy.OutputField(desc="estimated number of hops, minimum value is 1")


class VerifyUpdateSparql(dspy.Signature):
    """Given a question, triple patterns, a generated Wikidata SPARQL and its retrieved
    formatted answers, verify whether the SPARQL correctly answers the question. If it
    does, return None. If not, return a corrected Wikidata SPARQL that properly answers
    the question using the relevant provided IDs. Do not try to retrieve labels unless
    explicitly asked."""
    question: str = dspy.InputField()
    entities: str = dspy.InputField(desc="identified question entities with their Wikidata QIDs, one per line as 'label: QID'")
    patterns: str = dspy.InputField(desc="candidate Wikidata triple patterns with entity IDs; one pattern per line")
    generated_sparql: str = dspy.InputField()
    sparql_output: str = dspy.InputField(desc="formatted results returned by executing the generated SPARQL")
    refined_sparql: Optional[str] = dspy.OutputField(desc="corrected SPARQL if changes are needed; None if the current SPARQL is correct")


# ─────────────────────────────────────────────────────────────────────────────
# Module
# Mirrors process_input_query_multi_hop() in pattern_based_sparql_generator.py
# ─────────────────────────────────────────────────────────────────────────────

class PatternBasedSparqlGenerator(dspy.Module):
    def __init__(self, top_n: int = TRIPLE_PATTERN_N_TOP):
        super().__init__()
        initialize_aux_values()
        self.top_n = top_n

        self.expand_or_finalize = dspy.ChainOfThought(ExpandOrFinalize)
        self.final_sparql       = dspy.Predict(SparqlFromPatterns)
        self.refine             = dspy.Predict(SparqlRefine)
        self.estimate_hop       = dspy.Predict(MhopEstimate)
        self.verify_update      = dspy.Predict(VerifyUpdateSparql)

    def _finalize(self, sparql, patterns_str, question, ent_dict_str,
                  refine, verify_update_sparql, wd_ep, use_sleep):
        """Apply optional refine then optional verify/update and return the final SPARQL.
        Mirrors the refine + apply_sparql_verupdt block that follows every finalization
        point in process_input_query_multi_hop."""
        if refine:
            sparql = self.refine(question=question, sparql=sparql).refined_sparql or sparql

        if verify_update_sparql:
            try:
                _, sparql_response = get_qald_answer_sparql(sparql, wd_ep, use_sleep)
                output_literal = construct_results_literal(sparql_response, wd_ep, use_sleep)
            except Exception:
                output_literal = "Error retrieving results"
            refined = self.verify_update(
                question=question,
                entities=ent_dict_str,
                patterns=patterns_str,
                generated_sparql=sparql,
                sparql_output=output_literal,
            ).refined_sparql
            if refined:
                sparql = refined

        return sparql

    def _expand_edge(self, idx, selected_edges, expanded_edges, cache, wd_ep, use_sleep):
        """Expand one edge by list index. Returns new NodeEdge patterns, or []."""
        if not (0 <= idx < len(selected_edges)):
            return []
        edge = selected_edges[idx]
        if edge.variable_name in expanded_edges:
            return []
        _update_edge_cache(selected_edges, conc_ex_limit=0,
                           conc_ex_and_constraints_cache=cache,
                           wd_ep=wd_ep, use_sleep=use_sleep)
        constraint_tp = cache[_build_cache_key(edge)][1]
        next_raw = find_next_hop_patterns(constraint_tp, edge.variable_name,
                                          wd_ep, use_sleep=use_sleep)
        extracted, _ = extract_patterns_data(edge.variable_name, edge.variable_name,
                                              next_raw, PROPERTY_ID_MAP)
        expanded_edges.add(edge.variable_name)
        return extracted

    def forward(self, question: str, entities: str, relations: str,
                wd_ep: str = DEFAULT_WIKIDATA_ENDPOINT_URL,
                mhop_limit: int = -1, refine: bool = True,
                verify_update_sparql: bool = False, use_sleep: bool = False):

        if PROC_LOGGER is None:
            init_proc_logger()

        ent_dict_str = entities
        rel_dict_str = relations
        entity_dict = {
            line.split(': ')[0]: line.split(': ')[1]
            for line in entities.split('\n') if ': ' in line
        }

        if mhop_limit < 0:
            mhop_limit = max(1, int(self.estimate_hop(
                question=question, entities=ent_dict_str, relations=rel_dict_str
            ).mhop))

        # Collect 1-hop root patterns for each entity
        patterns, _, _ = _collect_root_patterns(entity_dict, wd_ep,
                                                 proc_logger=PROC_LOGGER,
                                                 use_sleep=use_sleep)
        top = _score_and_select_top(question, patterns, proc_logger=PROC_LOGGER,
                                    top_n=self.top_n)

        var_id = 1
        selected_edges = []
        for _, edge in top:
            edge.assign_variable_id(var_id)
            var_id += 1
            selected_edges.append(edge)

        cache, expanded_edges = {}, set()

        fin_kwargs = dict(question=question, ent_dict_str=ent_dict_str, refine=refine,
                          verify_update_sparql=verify_update_sparql, wd_ep=wd_ep,
                          use_sleep=use_sleep)

        # ── mhop=1: direct finalization (mirrors production mhop==1 branch) ──
        if mhop_limit == 1:
            verbs = _build_verbalizations(selected_edges, False, 0, cache, wd_ep,
                                          use_sleep=use_sleep)
            patterns_str = '\n'.join(verbs)
            sparql = self.final_sparql(
                question=question, entities=ent_dict_str, patterns=patterns_str
            ).sparql
            sparql = self._finalize(sparql, patterns_str, **fin_kwargs)
            return dspy.Prediction(sparql=sparql, hops_used=1)

        # ── mhop>1: expand-or-finalize loop ──────────────────────────────────
        for hop in range(1, mhop_limit + 1):
            verbs = _build_verbalizations(selected_edges, False, 0, cache, wd_ep,
                                          use_sleep=use_sleep)
            patterns_str = '\n'.join(verbs)
            pred = self.expand_or_finalize(
                question=question, entities=ent_dict_str, patterns=patterns_str
            )

            if pred.sparql:
                sparql = self._finalize(pred.sparql, patterns_str, **fin_kwargs)
                return dspy.Prediction(sparql=sparql, hops_used=hop)

            # Expand requested indices
            new_patterns = []
            for idx_str in [s.strip() for s in (pred.expand_indices or "").split(',') if s.strip()]:
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                new_patterns.extend(
                    self._expand_edge(idx, selected_edges, expanded_edges, cache, wd_ep, use_sleep)
                )

            if not new_patterns:
                break

            next_top = _score_and_select_top(question, new_patterns, proc_logger=PROC_LOGGER,
                                             top_n=self.top_n)
            for _, edge in next_top:
                edge.assign_variable_id(var_id)
                var_id += 1
                selected_edges.append(edge)

        # ── Forced finalization after hop limit (mirrors production) ──────────
        final_verbs = _build_verbalizations(selected_edges, False, 0, cache, wd_ep,
                                            use_sleep=use_sleep)
        patterns_str = '\n'.join(final_verbs)
        sparql = self.final_sparql(
            question=question, entities=ent_dict_str, patterns=patterns_str
        ).sparql
        sparql = self._finalize(sparql, patterns_str, **fin_kwargs)
        return dspy.Prediction(sparql=sparql, hops_used=mhop_limit)
