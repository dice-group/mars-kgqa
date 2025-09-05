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
from src.util.qald_io import convert_basic_output
from src.analysis.pf_answer_analysis import analyse_mismatches, generate_compiled_analysis
from src.const.misc import GERBIL_EXPERIMENT_URI_STORE_FILEPATH

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
    return parser.parse_args()


def main() -> None:
    
    args = parse_args()

    approach_enum = Approach[args.approach]
    
    approach_id = approach_enum.name
    processor_fn = approach_enum.processor
    aux_init_fn  = approach_enum.aux_init
    llm_config = ChatModel[args.llm].value
    kgqa_ds = KgqaDataset[args.dataset].value
    split_conf = DatasetSplit[args.split]
    
    use_goldentrel = args.use_gold
    
    # Process arguments
    ## Rest of the logic
    approach_name = approach_id # copying id for modification if needed
    if use_goldentrel:
        approach_name+='_gold-entrel'
    
    run_name = f'{approach_name}__{llm_config.model_id}'
    
    wd_ep = kgqa_ds.preferred_wd_endpoint
    
    qald_file_path = kgqa_ds.split_dict[split_conf]
    
    tsv_output_path = generate_output_path(run_name, qald_file_path, 'tsv')
    
    # Generate a log directory path
    log_dir = get_log_dir(run_name, qald_file_path)
    # call the aux init
    aux_init_fn()
    
    # Generates TSV (for readability)
    process_dataset(run_name, qald_file_path, tsv_output_path, processor_fn, wd_ep, llm_config, use_goldentrel, log_dir)
    
    json_output_path = generate_output_path(run_name, qald_file_path, 'json')
    # Converts TSV to JSON (for evaluation)
    convert_basic_output(tsv_output_path, qald_file_path, json_output_path, False, wd_ep)
    
    # Evaluating results on GERBIL
    gold_dataset_label = f'{kgqa_ds.dataset_id}_{split_conf.name.lower()}'
    system_label = f'{run_name}'
    gerbil_result_path = generate_gerbil_export_path(run_name, qald_file_path)
    
    create_export_gerbil_experiment(gold_dataset_label, qald_file_path, system_label, json_output_path, 'en', gerbil_result_path, GERBIL_EXPERIMENT_URI_STORE_FILEPATH)
    
    # Analyse answers
    analysis_dir = get_analysis_dir(run_name, qald_file_path)
    
    analyse_mismatches(qald_file_path, json_output_path, log_dir, analysis_dir, llm_config)
    generate_compiled_analysis(analysis_dir, llm_config)


if __name__ == "__main__":
    main()