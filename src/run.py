"""
Command‑line interface for running different processing approaches
on a chosen dataset/split with a specified LLM.
"""

import argparse
from src.const.dataset import DatasetSplit, KgqaDataset
from src.const.llm import ChatModel
from src.const.approach import Approach
from src.sparql_gen.sparql_gen_common import process_dataset, generate_output_path, generate_gerbil_export_path, get_log_dir, get_analysis_dir
from src.util.qald_io import convert_basic_output
from src.util.gerbil import create_export_gerbil_experiment
from src.util.qald_io import convert_basic_output, clean_qald_gerbil_json, _get_gerbil_ready_filepath
from src.analysis.pf_answer_analysis import analyse_mismatches, generate_compiled_analysis
from src.const.misc import GERBIL_EXPERIMENT_URI_STORE_FILEPATH, EntityAnnotator

from src.const.misc import MAX_MULTI_HOP, TRIPLE_PATTERN_N_TOP, RUN_STATS
import src.const.misc as misc_consts
from src.util.common import create_directory_if_not_exists
import time
import os

def parse_args() -> argparse.Namespace:
    """Define and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run a specific processing approach on a dataset split."
    )
    parser.add_argument(
        "--approach",
        type=str,
        required=True,
        choices=[a.name for a in Approach],
        help="Identifier of the processing approach to run."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=[a.name for a in KgqaDataset],
        help="Name or ID of the dataset."
    )
    parser.add_argument(
        "--split",
        type=str,
        required=True,
        choices=[a.name for a in DatasetSplit],
        help="Which split of the dataset to process."
    )
    parser.add_argument(
        "--llm",
        type=str,
        required=True,
        choices=[a.name for a in ChatModel],
        help="Identifier of the LLM to use."
    )
    parser.add_argument(
        "--use-gold",
        action="store_true",
        help="Use gold entity and relation annotations if provided."
    )
    
    parser.add_argument(
        "--filter-entities",
        action="store_true",
        help="Filter out entities that do not meet certain criteria."
    )
    parser.add_argument(
        "--topn-count",
        type=int,
        default=TRIPLE_PATTERN_N_TOP,
        help="Maximum number of top‑N candidates to keep per step."
    )
    parser.add_argument(
        "--mhop-limit",
        type=int,
        default=MAX_MULTI_HOP,
        help="Maximum number of hops allowed in multi‑hop reasoning."
    )
    parser.add_argument(
        "--include-pattern-count",
        action="store_true",
        help="Include the count of matched patterns in the output."
    )
    parser.add_argument(
        "--refine-sparql",
        action="store_true",
        help="Run a post‑processing step to refine generated SPARQL queries."
    )
    parser.add_argument(
        "--entity-annotator",
        type=str,
        choices=[a.name for a in EntityAnnotator],
        default=EntityAnnotator.T5AUG_ERL.name,
        help="Select which entity annotator to apply."
    )
    parser.add_argument(
        "--use-aug-similarity",
        action="store_true",
        help="Use augmented sequence for similarity computations."
    )
    parser.add_argument(
        "--language",
        type=str,
        default='en',
        help="Language code for the questions to use."
    )
    parser.add_argument(
        "--conc-ex-limit",
        type=int,
        default=0,
        help="Number of concrete examples to use for each pattern."
    )
    parser.add_argument(
        "--use-class-info",
        action="store_true",
        help="Use class (domain/range) information in the verbalizations."
    )
    parser.add_argument(
        "--verify-update-sparql",
        action="store_true",
        help="Use the results from the generated SPARQL to verify if it returns seemingly expected answer. Update the SPARQL one last time if it does not."
    )
    # NOTE: If new arguments are added, update execute_experiment.sh and slurm/schedule_experiment.sh with new arguments as well.
    return parser.parse_args()


def main() -> None:
    
    args = parse_args()

    approach_enum = Approach[args.approach]
    
    approach_id = approach_enum.name
    processor_fn = approach_enum.processor
    aux_init_fn  = approach_enum.aux_init
    llm_config = ChatModel[args.llm].value
    llm_name = ChatModel[args.llm].name
    kgqa_ds = KgqaDataset[args.dataset].value
    split_conf = DatasetSplit[args.split]
    # entity_annotator
    ent_annot = EntityAnnotator[args.entity_annotator]
    q_lang = args.language
    
    use_goldentrel = args.use_gold
    
    approach_config = []

    if args.filter_entities:
        approach_config.append("enfil")
    if args.topn_count: # this can be set to 0 to remove this suffix in special cases
        approach_config.append(f"t{args.topn_count}")
    if args.mhop_limit: # this can be set to 0 to remove this suffix in cases like SSG
        approach_config.append(f"h{args.mhop_limit}")
    if args.include_pattern_count:
        approach_config.append("pc")
    if args.refine_sparql:
        approach_config.append("sref")
    if args.use_aug_similarity:
        approach_config.append("ausm")
    # always include the chosen entity annotator (even if default)
    if use_goldentrel:
        approach_config.append(f"gld-enrl")
    else:
        approach_config.append(f"{ent_annot.name.lower()}")
    if args.conc_ex_limit:
        approach_config.append(f"exlim{args.conc_ex_limit}")
    if args.use_class_info:
        approach_config.append("clsinf")
    if args.verify_update_sparql:
        approach_config.append("verupdt")
    # join the parts with dashes; if no extra flags, keep it empty
    approach_suffix = ""
    if approach_config:
        approach_suffix = "__" + "-".join(approach_config)
    
    # Process arguments
    ## Rest of the logic
    approach_name = approach_id # copying id for modification if needed
    
    # adding config info to approach name
    approach_name += approach_suffix
    
    # read system name from env: RUN_SYS_NAME
    run_sys_name = os.environ.get("RUN_SYS_NAME")
    
    run_name = f'{q_lang}__{run_sys_name}__{approach_name}__{llm_name.lower()}' # Keep this under 120 characters or GERBIL will show blank result page
    
    if len(run_name) > 100:
        raise ValueError(
            f'Assigned name is too long, this will lead to GERBIL issues, please fix.\nName: {run_name}'
        )
    
    wd_ep = kgqa_ds.preferred_wd_endpoint
    
    gold_qald_path = kgqa_ds.split_dict[split_conf]
    
    tsv_output_path = generate_output_path(run_name, gold_qald_path, 'tsv')
    
    # SPARQL common logs
    sparql_log_fp = os.path.join('./data_dir/sparql_logs', f"{run_name}.txt")
    create_directory_if_not_exists(sparql_log_fp)
    misc_consts.sparql_log_filehandle = open(sparql_log_fp, 'a', buffering=1) # buffering=1 for line-buffering
    
    # Generate a log directory path
    log_dir = get_log_dir(run_name, gold_qald_path)
    # call the aux init
    if aux_init_fn:
        aux_init_fn()
        
    start = time.time()
    
    # Generates TSV (for readability)
    process_dataset(run_name, gold_qald_path, tsv_output_path, processor_fn, wd_ep, llm_config, use_goldentrel, log_dir,
    args.filter_entities, args.topn_count, args.mhop_limit, args.include_pattern_count, args.refine_sparql, ent_annot, args.use_aug_similarity, q_lang, kgqa_ds.use_sleep, args.conc_ex_limit, args.use_class_info, args.verify_update_sparql)
    
    print(f"[TIME] Prediction on dataset took {time.time() - start:.2f}s")
    
    print(f"[STATS] Run statistics: {RUN_STATS}")
    
    cur_start = time.time()
    
    json_output_path = generate_output_path(run_name, gold_qald_path, 'json')
    # Converts TSV to JSON (for evaluation)
    convert_basic_output(tsv_output_path, gold_qald_path, json_output_path, False, wd_ep)
    
    print(f"[TIME] Extraction of results took {time.time() - cur_start:.2f}s")
    
    cur_start = time.time()
    
    # Evaluating results on GERBIL
    gold_dataset_label = f'{kgqa_ds.dataset_id}_{split_conf.name.lower()}'
    system_label = f'{run_name}'
    gerbil_result_path = generate_gerbil_export_path(run_name, gold_qald_path)
    
    # Use gerbil-ready gold and pred json
    gerbilready_pred_json_path = clean_qald_gerbil_json(json_output_path)
    
    gerbilready_gold_json_path = _get_gerbil_ready_filepath(gold_qald_path)
    if not os.path.isfile(gerbilready_gold_json_path):
        gerbilready_gold_json_path = clean_qald_gerbil_json(gold_qald_path)
    
    create_export_gerbil_experiment(gold_dataset_label, gerbilready_gold_json_path, system_label, gerbilready_pred_json_path, q_lang, gerbil_result_path, GERBIL_EXPERIMENT_URI_STORE_FILEPATH)
    
    print(f"[TIME] Gerbil evaluation took {time.time() - cur_start:.2f}s")
    
    # closing sparql log file handle
    misc_consts.sparql_log_filehandle.close()
    
    cur_start = time.time()
    
    # Analyse answers
    analysis_dir = get_analysis_dir(run_name, gold_qald_path)
    
    analyse_mismatches(gold_qald_path, json_output_path, log_dir, analysis_dir, llm_config)
    
    print(f"[TIME] Analyzing mismatched entries took {time.time() - cur_start:.2f}s")
    
    cur_start = time.time()
    
    generate_compiled_analysis(analysis_dir, llm_config)
    
    print(f"[TIME] Compilation of analyses took {time.time() - cur_start:.2f}s")
    
    print(f"[TIME] Total processing took {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()