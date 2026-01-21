import argparse
import os

class ARGSParser(argparse.ArgumentParser):
    """
    Provide an opt-producer and CLI arguement parser.

    More options can be added specific by paassing this object and calling
    ''add_arg()'' or add_argument'' on it.

    :param add_training_args:
        (default False) initializes the default arguments for model training
    :param add_model_args:
        (default False) initializes the default arguments for loading models,
        including initializing arguments from the model.
    :param add_inference_args:
        (default False) initializes the default arguments for inference,
        including prefix tries.
    """

    def __init__(
        self, add_training_args=False, add_model_args=False,add_inference_args=False,
        description=' ',
    ):
        super().__init__(
            description=description,
            allow_abbrev=False,
            conflict_handler='resolve',
            formatter_class=argparse.HelpFormatter,
        )

        self.add_arg = self.add_argument

        self.overridable = {}

        if add_model_args:
            self.add_model_args()
        if add_training_args:
            self.add_training_args()
        if add_inference_args:
            self.add_inference_args()
    def add_model_args(self, args=None):
        """
        Add model args.
        """
        parser = self.add_argument_group("Model Arguments")
        parser.add_argument(
            "--max_input_length",
            default=512,
            type=int,
            help="The maximum total input sequence length after WordPiece tokenization. \n"
            "Sequences longer than this will be truncated, and sequences shorter \n"
            "than this will be padded.",
        )
        parser.add_argument(
            "--max_target_length",
            default=512,
            type=int,
            help="The maximum total input sequence length after WordPiece tokenization. \n"
                 "Sequences longer than this will be truncated, and sequences shorter \n"
                 "than this will be padded.",
        )
        parser.add_argument(
            "--config_name",
            default=None,
            type=str,
            help="Pretrained config name or path if not the same as model_name",
        )
        parser.add_argument(
            "--cache_dir",
            default='hfcache',
            type=str,
            help="Where do you want to store the pretrained models downloaded from s3",
        )
        parser.add_argument(
            "--tokenizer_name",
            default=None,
            type=str,
            help="Pretrained tokenizer name or path if not the same as model_name",
        )

        parser.add_argument(
            "--model_name",
            default="t5-base",
            type=str,
            help="path or name of model",
        )
        parser.add_argument(
            "--eval_beams",
            default=None,
            type=int,
            help="# num_beams to use for evaluation.",
        )


    def add_training_args(self, args=None):
        """
        Add model args.
        """
        parser = self.add_argument_group("Model Arguments")
        parser.add_argument(
            "--warmup_ratio",
            default=0.0,
            type=float,
            help="The warmup ratio",
        )
        parser.add_argument(
            "--label_smoothing",
            default=0.0,
            type=float,
            help="The label smoothing epsilon to apply (if not zero).",
        )
        parser.add_argument(
            "--sortish_sampler",
            default=False,
            type=bool,
            help="Whether to SortishSamler or not.",
        )
        parser.add_argument(
            "--predict_with_generate",
            default='hfcache',
            type=bool,
            help="Whether to use generate to calculate generative metrics (ROUGE, BLEU).",
        )
        parser.add_argument(
            "--train_model",
            default=True,
            type=bool,
            help="Whether to train a model",
        )
        parser.add_argument(
            "--output_dir",
            default="out-augmented-qald",
            type=str,
            help="Whether to train a model",
        )
        parser.add_argument(
            "--training_ds",
            default="../../data/trainq/qald_linked_augmented_gold_ent",
            type=str,
            help="Path to trainig data",
        )
        parser.add_argument(
            "--eval_ds",
            default="../../data/testq/qald_linked_augmented_gold_ent",
            type=str,
            help="Path to training data",
        )
        parser.add_argument(
            "--use_eval_dataset",
            default=False,
            type=bool,
            help="Wheather to use an evaluation dataset or split the training data",
        )
        parser.add_argument(
            "--eval_ratio",
            default=0.05,
            type=float,
            help="Path to evaluation data",
        )
    def add_inference_args(self,args=None):
        parser = self.add_argument_group("Model Arguments")
        parser.add_argument(
            "--entity_trie_file",
            default="../precomputed/EntityLinking/entity_trie.pkl",
            type=str,
            help="Entity Trie File",
        )
        parser.add_argument(
            "--entity_dict_file",
            default="precomputed/label_to_entity_wk.pkl",
            type=str,
            help="Entity Dictionary File",
        )
        parser.add_argument(
            "--relation_dict_file",
            default="precomputed/label_to_relation_wk.pkl",
            type=str,
            help="Relation Dict File",
        )
        parser.add_argument(
            "--pretrained_model_path",
            #default="../precomputed/EntityLinking/span-qald",
            default="out-augmented-qald",
            type=str,
            help="Path to pretrained model"
        )
        parser.add_argument(
            "--cuda_device_id",
            default=1,
            type=int,
            help="id of cuda device to use"
        )
        parser.add_argument(
            "--parameter_path_prefix",
            default="",
            type=str,
            help="optional to add for each path parameter"
        )
        parser.add_argument(
            "--predict_file",
            default="../data/rag-data/qald_9_train_translated.json",
            type=str,
            help="qald_fomated_file_to_predict_resources_for"
        )
        parser.add_argument(
            "--output_file",
            default="output_file.json",
            type=str,
            help="file_to_write"
        )
