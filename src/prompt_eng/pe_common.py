# Common file to store reusable functions for the PE (prompt-engineering) pipeline.
# Runs DSPy's MIPROv2 optimizer (zero-shot, instructions-only) on the MinimalPbsgModule
# which contains only SparqlFromPatterns and ExpandOrFinalize. The optimised
# instruction text is extracted and pasted back into llm_request.py.

from src.util.common import read_json_file, create_directory_if_not_exists, save_json_file
from src.sparql_gen.sparql_gen_common import save_answers_as_tsv
from tqdm import tqdm
import os
import json
from src.util.process_flow_logger import ProcessFlowLogger
from src.sparql_gen.sparql_gen_common import get_question_pf_name
import dspy
from typing import Iterable
from src.util.common import execute_sparql_query


def _normalize(bindings: list) -> set:
    """Extract the answer values from a SPARQL bindings list.
    Each binding is a dict of {var: {type, value}}; we collect all 'value' strings."""
    values = set()
    for binding in (bindings or []):
        for val_dict in binding.values():
            if isinstance(val_dict, dict):
                values.add(val_dict.get('value', '').strip())
            else:
                values.add(str(val_dict).strip())
    return values


def _extract_gold_answerset(answers: list) -> set:
    """Extract a comparable answer set from the dataset's 'answers' field.
    Handles both SELECT (bindings) and ASK (boolean) query results."""
    if not answers:
        return set()
    ans = answers[0]
    if 'boolean' in ans:
        return {str(ans['boolean']).lower()}
    bindings = ans.get('results', {}).get('bindings', [])
    return _normalize(bindings)


def answer_f1(gold: set, pred: set) -> float:
    if not gold and not pred:
        return 1.0
    if not gold or not pred:
        return 0.0
    tp = len(gold & pred)
    if tp == 0:
        return 0.0
    precision = tp / len(pred)
    recall    = tp / len(gold)
    return 2 * precision * recall / (precision + recall)


def sparql_f1_metric(example: dspy.Example, prediction: dspy.Prediction,
                     trace=None) -> float:
    """DSPy metric: (example, prediction, trace) -> float in [0, 1]."""
    gold_answers = set(example.expected_answerset)  # stored as list for JSON serialisability
    pred_sparql  = getattr(prediction, "sparql", None)
    if not pred_sparql:
        return 0.0
    try:
        bindings, _ = execute_sparql_query(pred_sparql, example.wd_endpoint)
        pred_answers = _normalize(bindings)
    except Exception:
        return 0.0
    return answer_f1(gold_answers, pred_answers)


def _extract_optimised_prompts(compiled_generator) -> str:
    """Return a human-readable string of the optimised instruction text per predictor.
    Only extracts SparqlFromPatterns and ExpandOrFinalize (the two prompts targeted
    for optimisation). Paste the relevant sections back into llm_request.py."""
    target_sigs = {"SparqlFromPatterns", "ExpandOrFinalize"}
    lines = ["=" * 72, "OPTIMISED INSTRUCTION TEXT (zero-shot)", "=" * 72]
    for name, predictor in compiled_generator.named_predictors():
        sig_name = predictor.signature.__name__
        if sig_name not in target_sigs:
            continue
        sig = predictor.signature
        lines.append(f"\n--- {sig_name} ---")
        lines.append(f"Instructions:\n{sig.instructions}")
    lines.append("=" * 72)
    return "\n".join(lines)


def process_dataset(proc_name, qald_file_path, output_path, pe_generator, wd_ep,
                    llm_config, use_gold_entrel, log_dir, filter_entities, topn_count,
                    mhop_limit, include_pattern_count, refine_sparql, ent_annot,
                    use_aug_sim, q_lang, use_sleep, conc_ex_limit, use_class_info,
                    verify_update_sparql):
    # Output directory — pass the file path so create_directory_if_not_exists
    # correctly creates the parent directory rather than its own parent.
    output_path = os.path.abspath(output_path)
    create_directory_if_not_exists(output_path)
    create_directory_if_not_exists(log_dir)

    out_dir = os.path.dirname(output_path)
    cache_file = os.path.join(out_dir, f'{proc_name}_cache.json')
    answers_cache = {}
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            answers_cache = json.load(f)

    qald_json = read_json_file(qald_file_path)
    ent_linker = ent_annot.value
    devset = []
    # Cached answers are kept here and merged into the final output later.
    cached_answers = {}

    for question_item in tqdm(qald_json['questions'], desc='Building devset'):
        question_id = question_item['id']
        question_text = next(
            (q['string'] for q in question_item['question'] if q['language'] == q_lang), None
        )
        if not question_text:
            print(f'No "{q_lang}" entry found for question {question_id}')
            continue

        cache_id = f"{question_id}_{question_text}"
        if cache_id in answers_cache:
            cached_answers[question_id] = answers_cache[cache_id]
            continue

        if not use_gold_entrel and not all(
            key in question_item for key in ['augmented_translations', ent_linker]
        ):
            continue

        aug_text = question_item['augmented_translations'][q_lang]

        if use_gold_entrel:
            ent_dict = {e['label']: e['uri'] for e in question_item['gold_ent']}
            rel_dict = {r['label']: r['uri'] for r in question_item['gold_rel']}
        else:
            ent_dict = {e['label']: e['uri'] for e in question_item[ent_linker][q_lang]['entities']}
            rel_dict = {r['label']: r['uri'] for r in question_item[ent_linker][q_lang]['relations']}

        ent_dict_str = "\n".join(f"{k}: {v}" for k, v in ent_dict.items())
        rel_dict_str = "\n".join(f"{k}: {v}" for k, v in rel_dict.items())

        example = dspy.Example(
            question_id=question_id,
            question=aug_text,
            entities=ent_dict_str,
            relations=rel_dict_str,
            expected_answerset=list(_extract_gold_answerset(question_item.get('answers', []))),
            wd_endpoint=wd_ep,
        ).with_inputs("question", "entities", "relations")

        devset.append(example)

    if not devset:
        print("No examples to process. Check dataset and entity-linker fields.")
        save_answers_as_tsv(cached_answers, output_path)
        return None

    # ── Train / eval split (80 / 20) ─────────────────────────────────────────
    split_idx  = max(1, int(len(devset) * 0.8))
    trainset   = devset[:split_idx]
    evalset    = devset[split_idx:]
    print(f"[PE] devset={len(devset)}  trainset={len(trainset)}  evalset={len(evalset)}")

    # ── Initialise generator ──────────────────────────────────────────────────
    generator = pe_generator(top_n=topn_count)

    gen_kwargs = dict(
        wd_ep=wd_ep,
        mhop_limit=mhop_limit,
        refine=refine_sparql,
        verify_update_sparql=verify_update_sparql,
        use_sleep=use_sleep,
    )

    # ── Baseline: generate predictions on evalset ─────────────────────────────
    print("[PE] Generating baseline predictions on evalset...")
    baseline_answers = {}
    for ex in tqdm(evalset, desc='Baseline predictions'):
        pred = generator(question=ex.question, entities=ex.entities,
                         relations=ex.relations, **gen_kwargs)
        baseline_answers[ex.question_id] = getattr(pred, "sparql", "") or ""

    # Merge cached + baseline answers and save baseline TSV
    all_answers = {**cached_answers, **baseline_answers}
    save_answers_as_tsv(all_answers, output_path)

    evaluator = dspy.Evaluate(
        devset=evalset,
        metric=sparql_f1_metric,
        num_threads=4,
        display_progress=True,
        display_table=5,
    )
    baseline_result = evaluator(generator)
    print(f"[PE] Baseline F1 on evalset: {baseline_result.score:.3f}")

    # ── Optimise with MIPROv2 (zero-shot, instructions only) ──────────────────
    # MIPROv2 tunes only the instruction text inside each Signature's docstring.
    # optimize="instructions" ensures no few-shot demonstrations are selected
    # from the training data (zero-shot setting). Only SparqlFromPatterns and
    # ExpandOrFinalize are optimised (the MinimalPbsgModule only contains these
    # two predictors). sparql_f1_metric is used as the reward signal.
    # auto="light" runs the fewest trials; increase to "medium" or "heavy" for
    # better prompt quality at the cost of more LLM calls.
    #
    # verbose=True   → logs the candidate program (all prompts) before each trial
    # log_dir        → writes per-trial JSON snapshots to <log_dir>/mipro_trials/
    #                  each file shows the instructions tried and the trial score;
    #                  tail -f the files to watch evolution live during a long run.
    trials_dir = os.path.join(log_dir, "mipro_trials")
    print("[PE] Running MIPROv2 optimisation on trainset...")
    print(f"[PE] Trial program snapshots → {os.path.join(trials_dir, 'evaluated_programs')}/")
    from dspy.teleprompt import MIPROv2
    optimizer = MIPROv2(metric=sparql_f1_metric, auto="light", num_threads=4,
                        verbose=True, log_dir=trials_dir, optimize="instructions")
    compiled_generator = optimizer.compile(
        generator,
        trainset=trainset,
        requires_permission_to_run=False,
    )

    # ── Optimised: generate predictions on evalset ────────────────────────────
    print("[PE] Generating optimised predictions on evalset...")
    optimised_answers = {}
    for ex in tqdm(evalset, desc='Optimised predictions'):
        pred = compiled_generator(question=ex.question, entities=ex.entities,
                                  relations=ex.relations, **gen_kwargs)
        optimised_answers[ex.question_id] = getattr(pred, "sparql", "") or ""

    optimised_output_path = output_path.replace('.tsv', '_optimised.tsv')
    create_directory_if_not_exists(optimised_output_path)
    save_answers_as_tsv({**cached_answers, **optimised_answers}, optimised_output_path)

    optimised_result = evaluator(compiled_generator)
    print(f"[PE] Optimised F1 on evalset: {optimised_result.score:.3f}")
    print(f"[PE] Delta: {optimised_result.score - baseline_result.score:+.3f}")

    # ── Save compiled generator ───────────────────────────────────────────────
    compiled_path = output_path.replace('.tsv', '_compiled.json')
    compiled_generator.save(compiled_path)
    print(f"[PE] Compiled generator saved to: {compiled_path}")

    # ── Extract and save optimised instruction text ───────────────────────────
    # These are the prompts to paste back into llm_request.py.
    optimised_prompts_str = _extract_optimised_prompts(compiled_generator)
    prompts_path = output_path.replace('.tsv', '_optimised_prompts.txt')
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write(optimised_prompts_str)
    print(f"[PE] Optimised instruction text saved to: {prompts_path}")
    print(optimised_prompts_str)

    # ── Save scores ───────────────────────────────────────────────────────────
    save_json_file({
        "proc_name": proc_name,
        "baseline_score": baseline_result.score,
        "optimised_score": optimised_result.score,
        "delta": optimised_result.score - baseline_result.score,
    }, output_path.replace('.tsv', '_score.json'))

    return compiled_generator
