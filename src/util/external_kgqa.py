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

def qald_to_grasp_jsonl(qald_file, jsonl_out):
    qald_path = Path(qald_file)
    out_path = Path(jsonl_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with qald_path.open(encoding="utf‑8") as f:
        data = json.load(f)

    questions: Iterable[Dict[str, Any]] = data.get("questions", [])
    with out_path.open("w", encoding="utf‑8") as out_f:
        for q in questions:
            q_text = ""
            if isinstance(q.get("question"), list):
                for entry in q["question"]:
                    if entry.get("language") == "en":
                        q_text = entry.get("string", "")
                        break
            q_text = q_text or q.get("string", "") or q.get("question", "")
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
        
        proc_logger.add_step("Reading input file and writing TSV output")
        with inp_path.open(encoding="utf‑8") as in_f, \
             out_path.open("w", encoding="utf‑8", newline="") as out_f:
            writer = csv.writer(out_f, delimiter="\t")
            # header
            header = ["Question ID", "Answer"]
            writer.writerow(header)
            
            line_count = 0
            for line in tqdm(in_f, 'TSV Conversion'):
                if not line.strip():
                    continue
                obj = json.loads(line)
                qid = obj.get("id")
                output_section = obj.get("output") or {} # setting default get value does not work if the data has "null" mapped to the key
                ans = output_section.get("sparql") or ""
                # Ensure the SPARQL query is a single‑line string (remove newlines and extra whitespace)
                ans = " ".join(ans.split())
                ans = ans.strip()
                proc_logger.start_action(f"Processing: {ans}")
                if refine_sparql and len(ans) > 0: 
                    ans = refine_output_sparql(ans, model_config, proc_logger)
                row = [qid, ans]
                writer.writerow(row)
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

def generate_mst5_output_tsv(ds_qald_file, mst5_qald_file, output_tsv_file):
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
    
    ds_obj = KgqaDataset.QALD9PLUS_UPDATED_CURWD
    ds_split = DatasetSplit.TEST
    
    llm_config = ChatModel.GPTOSS120B.value # LLM to use
    
    output_dir = 'data_dir/external_systems/grasp/output'
    
    ## Convert input QALD to jsonl for GRASP
    # ds_path = ds_obj.value.split_dict[ds_split]
    # qald_to_grasp_jsonl(ds_path, f'data_dir/external_systems/grasp/input/{ds_obj.value.dataset_id}_{ds_split.name.lower()}.jsonl')
    
    ## Convert output of GRASP to TSV to be processed
    tsv_file_path = f'{output_dir}/tsv/gpt-oss-120b/qald9plus_updt_curwd_test_output.tsv'
    # grasp_output_to_tsv(f'{output_dir}/original/gpt-oss-120b/qald10_test_output.jsonl', tsv_file_path, True, llm_config)
    
    ## Generate QALD json and execute gerbil experiment
    sysname = f'grasp_{llm_config.model_id.lower()}'
    gerbil_output_dir = f'{output_dir}/gerbil/'
    
    evaluate_external_system(sysname, ds_obj, ds_split, tsv_file_path, gerbil_output_dir, 'en')
    
    