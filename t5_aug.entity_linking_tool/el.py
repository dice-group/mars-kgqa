from parameters import ARGSParser
import re
import pickle
from LLM_service import Local_service
from EntityandRelationDetector import EntityAndRelationDetector
from flair_el.predict import EntityLinkingModel
from tqdm import tqdm
import json

class Entity_Linker():
    def __init__(self,llm_model):
        # note: this requires ollama
        self.llmservice = Local_service(llm_model)
        self.wikidata_dict = pickle.load(open("../data/labels_to_id_lower.pkl", "rb"))
        self.wikidata_relations = pickle.load(open("../data/label_to_rel.pkl", "rb"))
        parser = ARGSParser(add_model_args=True, add_training_args=True)
        parser.add_model_args()
        parser.add_inference_args()

        # args = argparse.Namespace(**params)
        args = parser.parse_args()
        print(args)
        self.params = args.__dict__
        self.flair_el = EntityLinkingModel()
        self.mod = EntityAndRelationDetector(self.params)

    def augment_question_ner(self,seq):
        llm_out = self.llmservice.run_ner_request(seq)
        pattern = r'"([^"]+)"[,\]]'
        result = re.search(pattern, llm_out)
        entities = []
        found_ent = {}
        found_rel = {}
        already_ext = set()
        while result is not None:
            # print(result)
            span = result.group(1)
            if span != result and not span in already_ext:
                already_ext.add(span)
                if not re.match(r"P|Q[0-9]+", span):
                    entities.append(span)
            llm_out = llm_out.replace(result.group(0), "", 1)
            result = re.search(pattern, llm_out)
        print(entities)
        for ent in entities:
            if ent.lower() in self.wikidata_dict:
                found_ent[ent] = self.wikidata_dict[ent.lower()]
            if ent.lower() in self.wikidata_relations:
                found_rel[ent] = self.wikidata_relations[ent.lower()].replace('http://www.wikidata.org/entity/', '')
        sequences = []
        seq = seq + " " + " , ".join(entities)
        return found_ent, found_rel, seq

'''
Note: this code expects code in the QALD-format including translated questions into english.
For each question sample it expects translations as follows:

"translations":
    {"<source_language_tag>":"<translation>",
    ...
    }

'''
EL_model = Entity_Linker("gemma3:27b")
#data=json.load(open("../../data/rag-data/qald_9_train_augmented.json","r",encoding="utf-8"))
data=json.load(open(EL_model.params["predict_file"],encoding="utf-8"))

for question in tqdm(data["questions"]):
    question["t5"]={}
    for el in question["translations"]:
        #seq=question["augmented_translations"][el]
        seq = question["translations"][el]
        _,_,seq = EL_model.augment_question_ner(seq)
        question["t5"][el] = seq
        ent, rel = EL_model.mod.predict(seq)
        flair_res = EL_model.flair_el.predic_el(question["translations"][el])
        # flair_res = flair_el.predic_el(question["question"])
        ent.extend(flair_res)
        question["t5"][el]={"entities":ent, "relations":rel}
        #found["entities"]=ent
        #found["relations"]=rel

    #for training data

    #if "entities" in question:
    #    question["entities"].extend(ent)
    '''
        if "relations" in question:
            question["relations"].extend(rel)
    '''
    #for end-to-end-evaluation data
    #question["entities_t5"]=ent
    #question["relations_t5"] = rel


json.dump(data,open(EL_model.params["output_file"],"w",encoding="utf-8"),indent=4,ensure_ascii=False)

