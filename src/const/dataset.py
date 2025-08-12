from enum import Enum, auto
from const.misc import QALD10_WIKIDATA_EP, CURRENT_WIKIDATA_EP, TENTRIS_WIKIDATA_EP

class DatasetSplit(Enum):
    TRAIN = auto()
    DEV = auto()
    TEST = auto()

class KgqaDatasetInfo:
    def __init__(self, dataset_id, dataset_name, split_dict, preferred_wd_endpoint):
        self.dataset_id = dataset_id
        self.dataset_name = dataset_name
        self.split_dict = split_dict
        self.preferred_wd_endpoint = preferred_wd_endpoint
        
class KgqaDataset(Enum):        
    QALD9PLUS =  KgqaDatasetInfo("qald9plus", "QALD-9-plus", {
        # DatasetSplit.TRAIN: "",
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald9plus/test/aug_gold.json"
    }, None)
    
    QALD9PLUS_UPDATED =  KgqaDatasetInfo("qald9plus_updt", "QALD-9-plus (Updated)", {
        # DatasetSplit.TRAIN: "",
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald9plus/test/updt_aug_gold.json"
    }, TENTRIS_WIKIDATA_EP)
    
    QALD10 =  KgqaDatasetInfo("qald10", "QALD-10", {
        # DatasetSplit.TRAIN: "",
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald10/test/aug_gold.json"
    }, QALD10_WIKIDATA_EP)
    
    QALD10_UPDATED =  KgqaDatasetInfo("qald10_updt", "QALD-10 (Updated)", {
        # DatasetSplit.TRAIN: "",
        DatasetSplit.TEST: "data_dir/processed_kgqa_ds/qald10/test/updt_aug_gold.json"
    }, TENTRIS_WIKIDATA_EP)