# Sample usage: bash pylauncher.sh normal src.util.external_kgqa
import os
import json
import csv
from pathlib import Path
from typing import Iterable, Dict, Any
import re
from typing import Pattern
from src.kgqa_tool.llm_request import sparql_filter
from src.util.process_flow_logger import ProcessFlowLogger
from src.const.llm import ChatModel
from src.util.qald_io import convert_basic_output
from src.util.gerbil import create_export_gerbil_experiment
from src.const.misc import GERBIL_EXPERIMENT_URI_STORE_FILEPATH
from src.util.common import read_json_file, create_directory_if_not_exists, sparql_one_line
from src.sparql_gen.sparql_gen_common import save_answers_as_tsv
from tqdm import tqdm

_LANG_FILTER_RE: Pattern = re.compile(
    r"""
    FILTER\s*\(\s*LANG\s*\(\s*\?\w+\s*\)\s*=\s*['"]\w{2}['"]\s*\)
    """,
    re.IGNORECASE | re.VERBOSE,
)

def has_language_filter(sparql_snippet) -> bool:
    return bool(_LANG_FILTER_RE.search(sparql_snippet))

def qald_to_grasp_jsonl(qald_file, jsonl_out, lang='en', use_translation=False):
    qald_path = Path(qald_file)
    out_path = Path(jsonl_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with qald_path.open(encoding="utf‑8") as f:
        data = json.load(f)

    questions: Iterable[Dict[str, Any]] = data.get("questions", [])
    with out_path.open("w", encoding="utf‑8") as out_f:
        for q in questions:
            q_text = ""
            if not use_translation and isinstance(q.get("question"), list):
                for entry in q["question"]:
                    if entry.get("language") == lang:
                        q_text = entry.get("string", "")
                        break
            if use_translation and isinstance(q.get("translations"), Dict):
                translations = q.get("translations")
                q_text = translations.get(lang)
            
            # ignore question if no text is there
            if not q_text:
                continue
            
            q_id = str(q.get("id"))
            
            entry = {
                "id": q_id,
                "question": q_text,
                "sparql": "", # Keeping this empty on purpose
                "paraphrases": [],
                "info": {}
            }
            out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def grasp_output_to_tsv(grasp_out, tsv_out, refine_sparql, model_config):
    
    # Initialize logger
    log_dir = os.path.dirname(tsv_out)
    log_file = os.path.splitext(os.path.basename(tsv_out))[0]
    proc_logger = ProcessFlowLogger(f"log_{log_file}", log_dir, enable_print=False)
    
    # Log input information
    proc_logger.log_input_info({
        "input_file": grasp_out,
        "output_file": tsv_out,
        "refine_sparql": refine_sparql
    })
    
    proc_logger.start_action("Processing GRASP output to TSV")
    
    try:
        inp_path = Path(grasp_out)
        out_path = Path(tsv_out)
        
        proc_logger.add_step("Creating output directory")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Resume logic
        resume_from = 0                # number of lines already written (excluding header)
        if out_path.is_file():
            # Read existing TSV to find how many rows are already present
            with out_path.open("r", encoding="utf‑8", newline="") as existing_f:
                reader = csv.reader(existing_f, delimiter="\t")
                rows = list(reader)
                if len(rows) > 1:      # header + at least one data row
                    resume_from = len(rows) - 1   # exclude header
                    proc_logger.add_step(
                        f"Resuming from line {resume_from + 1} (already processed {resume_from} entries)"
                    )
        
        # Open output file: write header only if we are starting fresh
        mode = "a" if resume_from > 0 else "w"
        with inp_path.open(encoding="utf‑8") as in_f, \
             out_path.open(mode, encoding="utf‑8", newline="") as out_f:
            
            writer = csv.writer(out_f, delimiter="\t")
            if resume_from == 0:
                # write header for a new file
                writer.writerow(["Question ID", "Answer"])
            
            line_count = resume_from
            for idx, line in enumerate(tqdm(in_f, 'TSV Conversion')):
                # Skip lines that were already processed
                if idx < resume_from:
                    continue
                
                if not line.strip():
                    continue
                obj = json.loads(line)
                qid = obj.get("id")
                output_section = obj.get("output") or {}
                ans = output_section.get("sparql") or ""
                ans = " ".join(ans.split()).strip()
                
                proc_logger.start_action(f"Processing: {ans}")
                if refine_sparql and len(ans) > 0:
                    ans = refine_output_sparql(ans, model_config, proc_logger)
                
                writer.writerow([qid, ans])
                line_count += 1
                proc_logger.complete_action()
        
        proc_logger.add_step(f"Completed processing {line_count} lines")
        
    except Exception as e:
        proc_logger.set_output({"error": str(e)})
        raise
    finally:
        proc_logger.complete_action()
        proc_logger.write_log()
        proc_logger.close()

def generate_qald_output_tsv(ds_qald_file, mst5_qald_file, output_tsv_file):
    ds_qald_obj = read_json_file(ds_qald_file)
    mst5_qald_obj = read_json_file(mst5_qald_file)
    
    mst5_sparql_dict = {}
    # Map question id to pred sparql
    for question_item in mst5_qald_obj['questions']:
        q_id = str(question_item["id"]) # for consistency in matching
        pred_sparql = question_item['query']['sparql']
        # Ensure the SPARQL query is a single‑line string (remove newlines and extra whitespace)
        pred_sparql = sparql_one_line(pred_sparql)
        mst5_sparql_dict[q_id] = pred_sparql
    
    final_pred_sparql_dict = {}
    # Keep all relevant queries
    for question_item in ds_qald_obj['questions']:
        q_id = str(question_item["id"]) # for consistency in matching
        pred_sparql = mst5_sparql_dict.get(q_id, None)
        final_pred_sparql_dict[q_id] = ""
        if pred_sparql:
            final_pred_sparql_dict[q_id] = pred_sparql
    # save output
    create_directory_if_not_exists(output_tsv_file)
    save_answers_as_tsv(final_pred_sparql_dict, output_tsv_file)

def refine_output_sparql(sparql_str, model_config, proc_logger):
    lang_filter = False
    # NOTE: More refinement cases to be added here if needed
    if has_language_filter(sparql_str):
        proc_logger.add_step("found language filter")
        # Refine the input sparql to remove the selected labels if any
        lang_filter = True
    to_filter = lang_filter # or operation
    if to_filter:
        sparql_str = sparql_filter(sparql_str, lang_filter, model_config, proc_logger)
    return sparql_str

def evaluate_external_system(system_name, kgqa_dataset, split, qald_file_path, external_tsv_file, gerbil_output_dir, lang):
    # convert to json file
    wd_ep = kgqa_dataset.value.preferred_wd_endpoint
    # qald_file_path = kgqa_dataset.value.split_dict[split]
    json_output_path = external_tsv_file.replace('/tsv/', '/json/').replace('.tsv', '.json')
    
    convert_basic_output(external_tsv_file, qald_file_path, json_output_path, False, wd_ep)
    # upload gerbil experiment
    gold_dataset_label = f'{kgqa_dataset.value.dataset_id}_{split.name.lower()}'
    
    gerbil_result_path = os.path.join(gerbil_output_dir, f'{system_name}__{gold_dataset_label}.csv')
    
    create_export_gerbil_experiment(gold_dataset_label, qald_file_path, system_name, json_output_path, lang, gerbil_result_path, GERBIL_EXPERIMENT_URI_STORE_FILEPATH)
            
# Example usage
if __name__ == "__main__":
    from src.const.dataset import KgqaDataset, DatasetSplit
    from src.const.llm import ChatModel
    
    llm_config = ChatModel.GPTOSS120B.value # LLM to use
    
    ## Dictionary of input dataset and output path
    grasp_info = {
        'qald10_test': {
            'ds': KgqaDataset.QALD10_UPDATED_TENTRISQ10,
            'split' : DatasetSplit.TEST,
            'input_dir': 'data_dir/external_systems/grasp/input/qald10',
            'orig_out_dir': f'data_dir/external_systems/grasp/output/original/{llm_config.model_id}/qald10',
            'tsv_out_dir': f'data_dir/external_systems/grasp/output/tsv/{llm_config.model_id}/qald10',
            'gerbil_out_dir': f'data_dir/external_systems/grasp/output/gerbil/{llm_config.model_id}/qald10',
            'langs': ['en', 'de', 'ru', 'zh']
        },
        'qald9plus_test': {
            'ds': KgqaDataset.QALD9PLUS_UPDATED_TENTRISQ10,
            'split' : DatasetSplit.TEST,
            'input_dir': 'data_dir/external_systems/grasp/input/qald9plus',
            'orig_out_dir': f'data_dir/external_systems/grasp/output/original/{llm_config.model_id}/qald9plus',
            'tsv_out_dir': f'data_dir/external_systems/grasp/output/tsv/{llm_config.model_id}/qald9plus',
            'gerbil_out_dir': f'data_dir/external_systems/grasp/output/gerbil/{llm_config.model_id}/qald9plus',
            'langs': ['en', 'de', 'fr', 'ba', 'be', 'es', 'hy', 'ru', 'uk']
        },
        'lcquad2_test': {
            'ds': KgqaDataset.LCQUAD2_UPDATED_TENTRISQ10,
            'split' : DatasetSplit.TEST,
            'input_dir': 'data_dir/external_systems/grasp/input/lcquad2',
            'orig_out_dir': f'data_dir/external_systems/grasp/output/original/{llm_config.model_id}/lcquad2',
            'tsv_out_dir': f'data_dir/external_systems/grasp/output/tsv/{llm_config.model_id}/lcquad2',
            'gerbil_out_dir': f'data_dir/external_systems/grasp/output/gerbil/{llm_config.model_id}/lcquad2',
            'langs': ['en']
        },
    }

    for key, ds_info in grasp_info.items():
        print(f'Processing {key}')
        ds_obj = ds_info['ds'].value
        ds_split = ds_info['split']
        ds_langs = ds_info['langs']
        # extract the gold qald file path
        gold_qald_fp = ds_obj.split_dict[ds_split]
        jsonl_dir = ds_info['input_dir']
        orig_out_dir = ds_info['orig_out_dir']
        tsv_out_dir = ds_info['tsv_out_dir']
        
        for lang in tqdm(ds_langs, desc='Processing languages'):
            file_base_name = f'{ds_obj.dataset_id}_{ds_split.name.lower()}_output'
            jsonl_file_name = f'{lang}_native_{file_base_name}.jsonl'
            output_jsonl_file_path = os.path.join(orig_out_dir, jsonl_file_name)
            
            output_tsv = f'{lang}_native_{file_base_name}.tsv'
            output_tsv_file_path = os.path.join(tsv_out_dir, output_tsv)
            
            # process native file
            grasp_output_to_tsv(output_jsonl_file_path, output_tsv_file_path, True, llm_config)
            if lang != "en":
                print(f'Creating jsonl (translated) for: {lang}')
                jsonl_file_name = f'{lang}_translated_{file_base_name}.jsonl'
                output_jsonl_file_path = os.path.join(orig_out_dir, jsonl_file_name)
                
                output_tsv = f'{lang}_translated_{file_base_name}.tsv'
                output_tsv_file_path = os.path.join(tsv_out_dir, output_tsv)
                # process translated file
                grasp_output_to_tsv(output_jsonl_file_path, output_tsv_file_path, True, llm_config)