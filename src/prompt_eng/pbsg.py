"""
End-to-end DSPy example for pattern-based SPARQL generation.

Assumes available in your codebase:
  - src.sparql_gen.pattern_based_sparql_generator: _collect_root_patterns,
    _score_and_select_top, _build_verbalizations, _update_edge_cache,
    _build_cache_key, extract_patterns_data, find_next_hop_patterns,
    initialize_aux_values, PROPERTY_ID_MAP
  - src.kgqa_tool.entity_retrieval: find_entities_and_relations
  - execute_sparql_query(sparql: str, endpoint: str) -> list | set
      returning the answer set (URIs/literals) produced by running the query.
"""

from typing import Literal, Optional
from src.prompt_eng.pe_common import sparql_f1_metric

import dspy

from src.sparql_gen.pattern_based_sparql_generator import (
    _collect_root_patterns,
    _score_and_select_top,
    _build_verbalizations,
    _update_edge_cache,
    _build_cache_key,
    extract_patterns_data,
    initialize_aux_values,
)
from src.kgqa_tool.graph_traversal import find_next_hop_patterns
from src.const.misc import DEFAULT_WIKIDATA_ENDPOINT_URL, TRIPLE_PATTERN_N_TOP


from src.util.process_flow_logger import ProcessFlowLogger

PROC_LOGGER = ProcessFlowLogger(
    process_name="temp",
    output_dir="data_dir/dspy_logs/"
)

def find_entities_and_relations(text):
    return text, {}, {} 


# --------------------------------------------------------------------------
# 1.  Configure the LM  (custom OpenAI-compatible endpoint + custom model)
# --------------------------------------------------------------------------
# The "openai/" prefix tells LiteLLM (DSPy's backend) to speak the OpenAI
# Chat Completions protocol. The part after the slash is the literal model
# name sent in the `model` field of the request payload.
lm = dspy.LM(
    model="openai/gpt-oss-120b",              # e.g. "openai/gpt-oss-120b"
    api_base="http://dice-merlin.cs.uni-paderborn.de:9292/v1",
    api_key="no-key-needed",
    temperature=0.0,
    max_tokens=2048,
    cache=True,              # DSPy caches identical calls — big savings during dev
    model_type="chat",
)
dspy.configure(lm=lm)


# --------------------------------------------------------------------------
# 2.  Signatures  (one per LM-calling function in your pipeline)
# --------------------------------------------------------------------------
class ExpandOrFinalize(dspy.Signature):
    """Given candidate triple patterns gathered from the KG, either emit the
    final SPARQL query if enough evidence has been gathered, or return the
    indices of patterns that should be expanded one more hop."""
    question: str = dspy.InputField()
    entities: str = dspy.InputField(desc="extracted entity mentions and their QIDs")
    relations: str = dspy.InputField(desc="extracted relation mentions")
    verbalized_patterns: list[str] = dspy.InputField(
        desc="indexed list of candidate triple patterns; list index == selection index"
    )
    action: Literal["finalize", "expand"] = dspy.OutputField()
    sparql: Optional[str] = dspy.OutputField(desc="valid Wikidata SPARQL; only when action='finalize'")
    expand_indices: list[int] = dspy.OutputField(desc="indices into verbalized_patterns; only when action='expand'")


class SparqlFromPatterns(dspy.Signature):
    """Generate a SPARQL query that answers the question, using the given
    triple patterns as the structural basis of the query."""
    question: str = dspy.InputField()
    patterns: list[str] = dspy.InputField(desc="verbalized triple patterns with IDs")
    entities: str = dspy.InputField()
    relations: str = dspy.InputField()
    sparql: str = dspy.OutputField(desc="a valid Wikidata SPARQL query")


class SparqlRefine(dspy.Signature):
    """Refine an existing SPARQL query to better match the user's question —
    fix variable bindings, filters, aggregations, or prefix errors."""
    question: str = dspy.InputField()
    sparql: str = dspy.InputField()
    refined_sparql: str = dspy.OutputField()


class MhopEstimate(dspy.Signature):
    """Estimate how many hops of KG traversal are needed to answer the question."""
    question: str = dspy.InputField()
    entities: str = dspy.InputField()
    relations: str = dspy.InputField()
    mhop: int = dspy.OutputField(desc="estimated number of hops, >= 1")


# --------------------------------------------------------------------------
# 3.  Module
# --------------------------------------------------------------------------
class PatternBasedSparqlGenerator(dspy.Module):
    def __init__(self, top_n: int = TRIPLE_PATTERN_N_TOP, max_hops: int = 3):
        super().__init__()
        self.top_n = top_n
        self.max_hops = max_hops

        # Looped decision maker — SAME predictor called each hop.
        self.expand_or_finalize = dspy.ChainOfThought(ExpandOrFinalize)
        # Single-shot LM steps.
        self.final_sparql = dspy.Predict(SparqlFromPatterns)
        self.refine       = dspy.Predict(SparqlRefine)
        self.estimate_hop = dspy.Predict(MhopEstimate)

    # ------------------------------------------------------------------
    # Helpers (Python-only; no LM)
    # ------------------------------------------------------------------
    def _expand_indices(self, indices, selected_edges, expanded_edges,
                        cache, wd_ep, use_sleep):
        """Port of your index-expansion block. Returns new candidate patterns."""
        new_patterns = []
        for idx in indices:
            if not (0 <= idx < len(selected_edges)):
                continue
            edge = selected_edges[idx]
            if edge.variable_name in expanded_edges:
                continue

            _update_edge_cache(selected_edges, conc_ex_limit=0,
                               conc_ex_and_constraints_cache=cache,
                               wd_ep=wd_ep, use_sleep=use_sleep)
            constraint_tp = cache[_build_cache_key(edge)][1]
            next_raw = find_next_hop_patterns(constraint_tp, edge.variable_name,
                                              wd_ep, use_sleep=use_sleep)
            extracted, _ = extract_patterns_data(edge.variable_name,
                                                 edge.variable_name,
                                                 next_raw, None)  # pass PROPERTY_ID_MAP in practice
            expanded_edges.add(edge.variable_name)
            new_patterns.extend(extracted)
        return new_patterns

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def forward(self, question: str, wd_ep: str = DEFAULT_WIKIDATA_ENDPOINT_URL,
                mhop_limit: int = -1, refine: bool = True, use_sleep: bool = False):

        # KG/retrieval work (not LM) — call your existing function directly.
        aug_qtxt, entity_dict, relation_dict = find_entities_and_relations(question)
        ent_dict_str = "\n".join(f"{k}: {v}" for k, v in entity_dict.items())
        rel_dict_str = "\n".join(f"{k}: {v}" for k, v in relation_dict.items())

        if mhop_limit < 0:
            mhop_limit = max(1, int(self.estimate_hop(
                question=aug_qtxt, entities=ent_dict_str, relations=rel_dict_str
            ).mhop))

        # Seed root patterns.
        patterns, _, _ = _collect_root_patterns(entity_dict, wd_ep, proc_logger=PROC_LOGGER,
                                                use_sleep=use_sleep)
        top = _score_and_select_top(aug_qtxt, patterns, proc_logger=PROC_LOGGER,
                                    top_n=self.top_n)

        var_id = 1
        selected_edges = []
        for _, edge in top:
            edge.assign_variable_id(var_id); var_id += 1
            selected_edges.append(edge)

        cache, expanded_edges = {}, set()

        # ---------- THE LOOP (same predictor, repeated) ----------
        for hop in range(1, mhop_limit + 1):
            verbs = _build_verbalizations(selected_edges, False, 0, cache, wd_ep,
                                          use_sleep=use_sleep, use_class_info=False)
            pred = self.expand_or_finalize(
                question=question,
                entities=ent_dict_str,
                relations=rel_dict_str,
                verbalized_patterns=verbs,
            )

            if pred.action == "finalize" and pred.sparql:
                sparql = pred.sparql
                if refine:
                    sparql = self.refine(question=question, sparql=sparql).refined_sparql
                return dspy.Prediction(sparql=sparql, hops_used=hop, trajectory=verbs)

            new_patterns = self._expand_indices(pred.expand_indices or [],
                                                selected_edges, expanded_edges,
                                                cache, wd_ep, use_sleep)
            if not new_patterns:
                break

            nxt = _score_and_select_top(aug_qtxt, new_patterns, proc_logger=PROC_LOGGER,
                                        top_n=self.top_n)
            for _, edge in nxt:
                edge.assign_variable_id(var_id); var_id += 1
                selected_edges.append(edge)

        # ---------- Forced finalization ----------
        final_verbs = _build_verbalizations(selected_edges, False, 0, cache, wd_ep,
                                            use_sleep=use_sleep, use_class_info=False)
        sparql = self.final_sparql(
            question=question, patterns=final_verbs,
            entities=ent_dict_str, relations=rel_dict_str,
        ).sparql
        if refine:
            sparql = self.refine(question=question, sparql=sparql).refined_sparql
        return dspy.Prediction(sparql=sparql, hops_used=mhop_limit, trajectory=final_verbs)


# --------------------------------------------------------------------------
# 5.  Run it
# --------------------------------------------------------------------------
if __name__ == "__main__":
    initialize_aux_values()        # loads your PROPERTY_INFO_MAP / PROPERTY_ID_MAP
    generator = PatternBasedSparqlGenerator(top_n=TRIPLE_PATTERN_N_TOP, max_hops=3)

    # --- (a) Single-question smoke test ---------------------------------
    question = "Who is the director of Inception?"
    result = generator(question=question, wd_ep=DEFAULT_WIKIDATA_ENDPOINT_URL,
                       mhop_limit=2, refine=True)
    print("Generated SPARQL:\n", result.sparql)
    print("Hops used:", result.hops_used)

    # Peek at the actual prompt/response DSPy sent — useful while debugging.
    dspy.inspect_history(n=2)

    # --- (b) Batch evaluation with the F1 metric ------------------------
    # Build a small dev set. Each Example needs the module's input fields
    # (marked via .with_inputs) and whatever the metric reads as gold.
    devset = [
        dspy.Example(
            question="Who is the director of Inception?",
            wd_endpoint=DEFAULT_WIKIDATA_ENDPOINT_URL,
            expected_answerset={"http://www.wikidata.org/entity/Q25191"},  # Christopher Nolan
        ).with_inputs("question"),
        dspy.Example(
            question="What is the capital of France?",
            wd_endpoint=DEFAULT_WIKIDATA_ENDPOINT_URL,
            expected_answerset={"http://www.wikidata.org/entity/Q90"},     # Paris
        ).with_inputs("question"),
        # ... load the rest from your QALD-9+ file here ...
    ]

    evaluator = dspy.Evaluate(
        devset=devset,
        metric=sparql_f1_metric,
        num_threads=4,               # parallelise LM + SPARQL calls
        display_progress=True,
        display_table=5,
    )
    avg_f1 = evaluator(generator)
    print(f"\nMean answer-set F1 over devset: {avg_f1.score:.3f}")

    # --- (c) (Optional) Prompt optimization with the same metric --------
    # Uncomment once (b) is working. MIPROv2 will jointly tune the
    # instructions + few-shot demos for expand_or_finalize, final_sparql,
    # refine, and estimate_hop — using sparql_f1_metric as the reward.
    #
    # from dspy.teleprompt import MIPROv2
    # optimizer = MIPROv2(metric=sparql_f1_metric, auto="light", num_threads=4)
    # compiled_generator = optimizer.compile(
    #     generator,
    #     trainset=devset,           # replace with a proper trainset
    #     requires_permission_to_run=False,
    # )
    # compiled_generator.save("compiled_pbsg.json")