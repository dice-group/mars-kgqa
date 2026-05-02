import os
from datetime import datetime
from pathlib import Path
from src.const.dataset import KgqaDataset, DatasetSplit
from src.const import misc as misc_consts
from src.util.external_kgqa import evaluate_external_system
from src.util.qald_io import _get_gerbil_ready_filepath
from src.util.common import create_directory_if_not_exists

now = datetime.now()
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
sparql_log_fp = os.path.join('data_dir/sparql_logs', f"external_systems_{timestamp}.txt")
create_directory_if_not_exists(sparql_log_fp)
misc_consts.sparql_log_filehandle = open(sparql_log_fp, 'a', buffering=1)

def add_header_if_needed(tsv_path):
    with open(tsv_path, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
    if first_line and not first_line.startswith('Question ID'):
        with open(tsv_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(tsv_path, 'w', encoding='utf-8') as f:
            f.write('Question ID\tAnswer\n' + content)
        print(f'  Added header to {tsv_path}')

deeppavlov2_info = {
    'qald10_test': {
        'ds': KgqaDataset.QALD10_UPDATED_TENTRISMAIN,
        'split': DatasetSplit.TEST,
        'tsv_dir': 'data_dir/external_systems/deeppavlov2/output/tsv/qald10',
        'gerbil_out_dir': 'data_dir/external_systems/deeppavlov2/output/gerbil/qald10',
    },
    'qald9plus_test': {
        'ds': KgqaDataset.QALD9PLUS_UPDATED_TENTRISMAIN,
        'split': DatasetSplit.TEST,
        'tsv_dir': 'data_dir/external_systems/deeppavlov2/output/tsv/qald9plus',
        'gerbil_out_dir': 'data_dir/external_systems/deeppavlov2/output/gerbil/qald9plus',
    },
    'lcquad2_test': {
        'ds': KgqaDataset.LCQUAD2_UPDATED_TENTRISMAIN,
        'split': DatasetSplit.TEST,
        'tsv_dir': 'data_dir/external_systems/deeppavlov2/output/tsv/lcquad2',
        'gerbil_out_dir': 'data_dir/external_systems/deeppavlov2/output/gerbil/lcquad2',
    },
}

for key, ds_info in deeppavlov2_info.items():
    print(f'Processing {key}')
    ds_obj = ds_info['ds'].value
    ds_split = ds_info['split']
    gold_qald_fp = ds_obj.split_dict[ds_split]
    gerbilready_gold_json_path = _get_gerbil_ready_filepath(gold_qald_fp)
    tsv_dir = ds_info['tsv_dir']
    gerbil_out_dir = ds_info['gerbil_out_dir']
    create_directory_if_not_exists(gerbil_out_dir)

    for file_path in Path(tsv_dir).rglob('*.tsv'):
        if not file_path.is_file():
            continue
        print(f'  Evaluating {file_path.name}')
        add_header_if_needed(str(file_path))
        lang_id = os.path.splitext(os.path.basename(file_path))[0]
        sysname = f'deeppavlov2-{key}-{lang_id}'
        evaluate_external_system(
            sysname,
            ds_info['ds'],
            ds_split,
            gerbilready_gold_json_path,
            str(file_path),
            gerbil_out_dir,
            'en',
        )
