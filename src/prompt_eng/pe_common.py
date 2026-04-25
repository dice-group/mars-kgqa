# Common file to store reusable functions for SPARQL generators
from src.util.common import read_json_file, create_directory_if_not_exists, save_json_file
from tqdm import tqdm
import os
import json
from src.util.process_flow_logger import ProcessFlowLogger
from src.sparql_gen.sparql_gen_common import get_question_pf_name
import dspy
from typing import Iterable
from src.util.common import execute_sparql_query

def _normalize(items: Iterable) -> set:
    """Coerce whatever execute_sparql_query returns into a comparable set."""
    return {str(x).strip() for x in (items or [])}


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
    return 2 * precision * recall / (precision + recall) # harmonic mean


def sparql_f1_metric(example: dspy.Example, prediction: dspy.Prediction,
                     trace=None) -> float:
    """DSPy metric signature: (example, prediction, trace) -> float in [0, 1]."""
    gold_answers = _normalize(example.expected_answerset)
    pred_sparql  = getattr(prediction, "sparql", None)
    if not pred_sparql:
        return 0.0
    try:
        pred_answers = _normalize(
            execute_sparql_query(pred_sparql, example.wd_endpoint)
        )
    except Exception:
        # Malformed SPARQL, endpoint timeout, etc. — score as 0.
        return 0.0
    return answer_f1(gold_answers, pred_answers)
            
def process_dataset(proc_name, qald_file_path, output_path, pe_generator, wd_ep,
                    llm_config, use_gold_entrel, log_dir, filter_entities, topn_count,
                    mhop_limit, include_pattern_count, refine_sparql, ent_annot, use_aug_sim, q_lang, use_sleep, conc_ex_limit, use_class_info, verify_update_sparql):
    # Output directory
    output_path = os.path.abspath(output_path)
    out_dir = os.path.dirname(output_path)
    create_directory_if_not_exists(out_dir)

    # Log directory
    create_directory_if_not_exists(log_dir)
    # Handle cache file
    cache_file = os.path.join(out_dir, f'{proc_name}_cache.json')

    # Read cache if it exists
    answers_cache = {}
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            answers_cache = json.load(f)

    cur_answers_dict = {}

    # Read the qald preprocessed file
    qald_json = read_json_file(qald_file_path)
    
    ent_linker = ent_annot.value
    devset = []

    # For each question
    for question_item in tqdm(qald_json['questions'], desc='Processing Questions'):
        question_id = question_item['id']

        # Extract the language-specific question text
        question_text = next(
            (q['string'] for q in question_item['question'] if q['language'] == q_lang), None
        )
        
        if not question_text:
            print(f'No "{q_lang}" entry found for Question: {question_id}')
            continue
        
        # Initialise a logger for this question
        proc_logger = ProcessFlowLogger(
            process_name=get_question_pf_name(question_id),
            output_dir=log_dir
        ).start_action(
            "process_question",
            {"question_id": question_id, "question_text": question_text, "language": q_lang}
        )
        
        proc_logger.add_step(f"Wikidata Endpoint: {wd_ep}")
        if use_gold_entrel:
            proc_logger.add_step(f"NOTE: The model will have access to the provided gold entities.")
        else:
            proc_logger.add_step(f"NOTE: The model will not have access to the provided gold entities. It must use the predicted/extracted entities.")
        
        cache_id = f"{question_id}_{question_text}"

        
        # Cache lookup
        if cache_id in answers_cache:
            proc_logger.add_step(f"Using cached answer for cache ID: {cache_id}")
            cur_answers_dict[question_id] = answers_cache[cache_id]
            proc_logger.set_output({"cached_answer": answers_cache[cache_id]}).complete_action()
            continue

        
        # Verify required pre‑processed fields are present
        if not use_gold_entrel and not all(
            key in question_item for key in ['augmented_translations', ent_linker]
        ):
            proc_logger.add_step("Missing augmented data; skipping question").complete_action()
            continue  # skip if augmented data is missing

        
        # Load augmented text / entities / relations
        aug_text = question_item['augmented_translations'][q_lang]
        
        # Log the gold entities, relations and SPARQL
        proc_logger.add_step(f"Gold Entities: {question_item['gold_ent']}")
        proc_logger.add_step(f"Gold Relations: {question_item['gold_rel']}")
        proc_logger.add_step(f"Gold SPARQL: {question_item['query']['sparql']}")

        if use_gold_entrel:
            ent_dict = {e['label']: e['uri'] for e in question_item['gold_ent']}
            rel_dict = {r['label']: r['uri'] for r in question_item['gold_rel']}
        else:
            proc_logger.add_step(f'Entity/Relation Linker: {ent_linker}')
            ent_dict = {e['label']: e['uri'] for e in question_item[ent_linker][q_lang]['entities']}
            rel_dict = {r['label']: r['uri'] for r in question_item[ent_linker][q_lang]['relations']}

        proc_logger.add_step(
            f"Prepared input – aug_text length: {len(aug_text)}, "
            f"entities: {len(ent_dict)}, relations: {len(rel_dict)}"
        )
        ent_dict_str = "\n".join(f"{k}: {v}" for k, v in ent_dict.items())
        rel_dict_str = "\n".join(f"{k}: {v}" for k, v in rel_dict.items())

        # Create a DSPy Example
        # We include everything the metric and the generator need
        example = dspy.Example(
            question_id=question_id,
            question=aug_text,
            entities=ent_dict_str,
            relations=rel_dict_str,
            expected_answerset=set(question_item['answer']['answerset']), # Assuming this structure in QALD
            wd_endpoint=wd_ep
        ).with_inputs("question", "entities", "relations")

        
        devset.append(example)
        
    # --- Initialize generator ---
    generator = pe_generator(top_n=topn_count)

    # --- Generate and save individual predictions ---
    cur_answers_dict = {}
    for ex in tqdm(devset, desc='Generating SPARQL'):
        # The generator.forward takes (question, entities, relations, ...)
        prediction = generator(
            question=ex.question, 
            entities=ex.entities, 
            relations=ex.relations
        )
        sparql = getattr(prediction, "sparql", "Empty Result")
        cur_answers_dict[ex.question_id] = sparql
    
    save_answers_as_tsv(cur_answers_dict, output_path)

    # --- Initialize evaluator ---
    evaluator = dspy.Evaluate(
        devset=devset,
        metric=sparql_f1_metric,
        num_threads=4,
        display_progress=True,
        display_table=5,
    )

    # --- Call evaluator on generator ---
    result = evaluator(generator)
    
    # Save overall score
    final_results = {
        "proc_name": proc_name,
        "score": result.score,
        "metrics": result.metrics if hasattr(result, 'metrics') else {}
    }
    save_json_file(final_results, output_path.replace('.tsv', '_score.json'))
    
    return result

