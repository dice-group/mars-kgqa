from flair.data import Sentence
from flair.nn import Classifier
from flair_el.genre.trie import Trie
from flair_el.genre.hf_model import GENRE

import pickle

class EntityLinkingModel:
    def __init__(self):
        self.ner_tagger=Classifier.load('ner')
        # TODO: remove hardcoded dependencies for GENRE if necessary
        self.el_model = GENRE.from_pretrained("flair/hf_entity_disambiguation_aidayago").eval()
        self.el_model.to("cuda:1")
        #with open("../precomputed/flair/kilt_titles_trie_dict.pkl", "rb") as f:
        #    self.trie = Trie.load_from_dict(pickle.load(f))
        self.wikidata_dict=pickle.load(open("flair/text_to_wikidata_id","rb"))
        self.wikidata_dict = pickle.load(open("flair/text_to_wikidata_id", "rb"))
    def predict_ner(self, input_str:str)->Sentence:
        '''
        runs flair entity tagger on an input string and returns the sentence object
        '''
        sentence = Sentence(input_str)
        self.ner_tagger.predict(sentence)
        return sentence

    def predic_el(self, input_str:str)->list:
        '''
        first runs flair entity linker for tagging named entities, then applies GENRE entity linking to add wikidata links.
        note, that we may have to shoreten sentence, once they don't fit in GERNE or flair anymore

        :param input_str: Text to annotate
        :return: a list that maps entity spans to annotaions
        '''
        annotated_sentence=self.predict_ner(input_str)
        # print the sentence with all annotations
        search_seq=[]
        results = []
        #ner is not existing in the layers, in the case, that no entities are found
        if "ner" in annotated_sentence.annotation_layers:
            spans=annotated_sentence.annotation_layers["ner"]
            curr_ind=0
            # from here the input for GENRE is generated. Note that only one span can be processed within one sample
            #an example sample for Genre is: Paderborn is localted in [START_ENT] North Rine Westfalia  [END_ENT], Germany.
            for i in range(len(spans)):
                cur_sp=spans[i].data_point.text
                start_ind=len(input_str[:curr_ind])+input_str[curr_ind:].index(cur_sp)
                search_seq.append(input_str[:start_ind]+"[START_ENT] "+cur_sp+" [END_ENT]"+input_str[start_ind+len(cur_sp):])
                curr_ind=start_ind+len(cur_sp)
            #run GENRE model on all samples
            el_res=(self.el_model.sample(
                        sentences=search_seq,
                        #prefix_allowed_tokens_fn=lambda batch_id, sent: self.trie.get(sent.tolist()),
            ))

            # extract links from the wikidata dictionary
            if el_res is not None:
                for i in range(len(spans)):
                    if el_res[i][0]["text"] in self.wikidata_dict:
                        results.append({"label":el_res[i][0]["text"],"uri":self.wikidata_dict[el_res[i][0]["text"]]})
        return results


