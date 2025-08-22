# Sample usage: python -m src.misc.lcquad2_conversion
from src.util.qald_io import convert_lcquad2_to_qald
# from src.const.misc import TENTRIS_WIKIDATA_EP
from src.const.misc import CURRENT_WIKIDATA_EP

lcquad2_file_path = "data_dir/processed_kgqa_ds/lcquad2/test/lcquad_filtered.json"
output_file_path = "data_dir/processed_kgqa_ds/lcquad2/test/updt_curwd_qald_aug_gold.json"
# TODO: Update to remove failed queries
convert_lcquad2_to_qald(lcquad2_file_path, output_file_path, CURRENT_WIKIDATA_EP)
