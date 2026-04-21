"""
Command‑line interface for running different processing approaches
on a chosen dataset/split with a specified LLM.
"""

from src.run import parse_args, get_approach_name
from src.const.dataset import DatasetSplit, KgqaDataset
from src.const.llm import ChatModel
from src.const.approach import PeApproach
from src.prompt_eng.pe_common import process_dataset
from src.sparql_gen.sparql_gen_common import generate_output_path, get_log_dir
from src.const.misc import EntityAnnotator

import src.const.misc as misc_consts
from src.util.common import create_directory_if_not_exists
import time
import os


def main() -> None:
    
    args = parse_args(PeApproach)
    approach_enum = PeApproach[args.approach]
    
    generator = approach_enum.generator
    aux_init_fn  = approach_enum.aux_init
    llm_config = ChatModel[args.llm].value
    llm_name = ChatModel[args.llm].name
    kgqa_ds = KgqaDataset[args.dataset].value
    split_conf = DatasetSplit[args.split]
    # entity_annotator
    ent_annot = EntityAnnotator[args.entity_annotator]
    q_lang = args.language
    use_goldentrel = args.use_gold
    
    # adding config info to approach name
    approach_name= get_approach_name(args)
    
    # read system name from env: RUN_SYS_NAME
    run_sys_name = os.environ.get("RUN_SYS_NAME")
    
    run_name = f'pe_{q_lang}__{run_sys_name}__{approach_name}__{llm_name.lower()}' # Keep this under 120 characters or GERBIL will show blank result page
    
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
    
    process_dataset(run_name, gold_qald_path, tsv_output_path, generator, wd_ep, llm_config, use_goldentrel, log_dir,
    args.filter_entities, args.topn_count, args.mhop_limit, args.include_pattern_count, args.refine_sparql, ent_annot, args.use_aug_similarity, q_lang, kgqa_ds.use_sleep, args.conc_ex_limit, args.use_class_info, args.verify_update_sparql)
    
    print(f"[TIME] Total processing took {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()