from enum import Enum, auto
from src.const.misc import QALD10_WIKIDATA_EP, CURRENT_WIKIDATA_EP, TENTRIS_WIKIDATA_EP, QALD10_TENTRIS_WIKIDATA_EP

class DatasetSplit(Enum):
    TRAIN = auto()
    DEV = auto()
    TEST = auto()

class KgqaDatasetInfo:
    def __init__(self, dataset_id, dataset_name, split_dict, preferred_wd_endpoint, use_sleep=False):
        self.dataset_id = dataset_id
        self.dataset_name = dataset_name
        self.split_dict = split_dict
        self.preferred_wd_endpoint = preferred_wd_endpoint
        self.use_sleep = use_sleep
        
class KgqaDataset(Enum):
    ## Obsolete datasets - Start
      
    # QALD9PLUS =  KgqaDatasetInfo("qald9plus", "QALD-9-plus", {
    #     # DatasetSplit.TRAIN: "",
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald9plus/test/aug_gold.json"
    # }, None)

    # QALD9PLUS_UPDATED_TENTRIS =  KgqaDatasetInfo("qald9plus_updt_tentris", "QALD-9-plus (Updated on Tentris)", {
    #     # DatasetSplit.TRAIN: "",
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald9plus/test/tentris_updt_aug_gold.json"
    # }, TENTRIS_WIKIDATA_EP)
    
    # QALD9PLUS_UPDATED_CURWD =  KgqaDatasetInfo("qald9plus_updt_curwd", "QALD-9-plus (Updated on Current Wikidata)", {
    #     DatasetSplit.TRAIN: "data_dir/processed_kgqa_ds/qald9plus/train/curwd_updt_aug_gold.json",
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald9plus/test/curwd_updt_aug_gold.json"
    # }, CURRENT_WIKIDATA_EP)
    
    # QALD10 =  KgqaDatasetInfo("qald10", "QALD-10", {
    #     # DatasetSplit.TRAIN: "",
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald10/test/filtered_gold_ent.json"
    # }, QALD10_WIKIDATA_EP)

    # LCQUAD2_UPDATED_CURWD =  KgqaDatasetInfo("lcquad2_updt", "LC-QuAD2.0 (Updated on Current Wikidata)", {
    #     # DatasetSplit.TRAIN: "",
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/lcquad2/test/updt_curwd_qald_aug_gold.json"
    # }, CURRENT_WIKIDATA_EP)
    
    # SPINACH_TENTRISQ10 =  KgqaDatasetInfo("spinach_tentrisq10", "SPINACH  (Answerset from QALD 10 Wikidata - Tentris)", {
    #     DatasetSplit.TRAIN: "data_dir/processed_kgqa_ds/spinach/train/tentrisq10_aug_gold.json",
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/spinach/test/tentrisq10_aug_gold.json"
    # }, QALD10_TENTRIS_WIKIDATA_EP)
    
    ## Uses federated sparql, cannot host locally
    # SPINACH_TENTRIS_WIKI =  KgqaDatasetInfo("spinach_tentriswd", "SPINACH  (Answerset from Tentris Wikidata)", {
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/spinach/test/tentriswd_qald_test_final.json"
    # }, TENTRIS_WIKIDATA_EP, use_sleep=False)
    
    ## Fails due to frequent timeouts on pattern retrieval on official endpoint, 500 Internal Server Error on QLever
    # SPINACH_CURWD =  KgqaDatasetInfo("spinach_curwd", "SPINACH  (Answerset from Official Wikidata)", {
    #     # DatasetSplit.TRAIN: "data_dir/processed_kgqa_ds/spinach/train/curwd_aug_gold.json", # ignoring train set for now
    #     DatasetSplit.TEST: "data_dir/processed_kgqa_ds/spinach/test/qald_test_final.json"
    # }, CURRENT_WIKIDATA_EP, use_sleep=True)
    
    ## Obsolete datasets - End
    
    ## Working datasets - Start
    
    QALD9PLUS_UPDATED_TENTRISQ10 =  KgqaDatasetInfo("qald9plus_tentrisq10", "QALD-9-plus (Updated on QALD 10 Wikidata - Tentris)", {
        DatasetSplit.TRAIN: "data_dir/processed_kgqa_ds/qald9plus/train/tentrisq10_aug_gold.json", # NOTE: We do not generate annotations for train, since ent-rel linkers have seen this data. This data should only be used for ablation study
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald9plus/test/tentrisq10_aug_gold.json"
    }, QALD10_TENTRIS_WIKIDATA_EP)
    
    QALD10_UPDATED_TENTRISQ10 =  KgqaDatasetInfo("qald10_tentrisq10", "QALD-10  (Updated on QALD 10 Wikidata - Tentris)", {
        DatasetSplit.TRAIN: "data_dir/processed_kgqa_ds/qald9plus/train/tentrisq10_aug_gold.json", # NOTE: We do not generate annotations for train, since ent-rel linkers have seen this data. This data should only be used for ablation study,
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald10/test/tentrisq10_aug_gold.json"
    }, QALD10_TENTRIS_WIKIDATA_EP)
    
    LCQUAD2_UPDATED_TENTRISQ10 =  KgqaDatasetInfo("lcquad2_tentrisq10", "LC-QuAD2.0 (Updated on QALD 10 Wikidata - Tentris)", {
        # DatasetSplit.TRAIN: "", # Too large, no point in using this split
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/lcquad2/test/tentrisq10_aug_gold.json"
    }, QALD10_TENTRIS_WIKIDATA_EP)
    
    ## Working datasets - End