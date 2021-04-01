import argparse
import logging
import os
import random
import sys

import numpy as np
import torch

# this is a temporal import, we will refactor FedML as a package installation
import wandb
wandb.init(mode="disabled")

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "")))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../")))

from data_manager.text_classification_data_manager import TextClassificationDataManager
from model.transformer.model_args import ClassificationArgs

from transformers import BertTokenizer, BertConfig
from model.fed_transformers.classification.transformer_models.bert_model import BertForSequenceClassification

from data_preprocessing.text_classification_preprocessor import TLMPreprocessor
from training.tc_transformer_trainer import TextClassificationTrainer

def add_args(parser):
    """
    parser : argparse.ArgumentParser
    return a parser added with args required by fit
    """
    # # PipeTransformer related
    parser.add_argument("--run_id", type=int, default=0)

    parser.add_argument("--is_debug_mode", default=0, type=int,
                        help="is_debug_mode")

    # Infrastructure related
    parser.add_argument('--device_id', type=int, default=8, metavar='N',    # TODO: why 8?
                        help='device id')

    # Data related
    # TODO: list all dataset names: 
    parser.add_argument('--dataset', type=str, default='agnews', metavar='N',
                        help='dataset used for training')

    parser.add_argument('--data_file_path', type=str, default='../../fednlp_data/data_files/agnews_data.h5',
                        help='data h5 file path')

    parser.add_argument('--partition_file_path', type=str, default='../../fednlp_data/partition_files/agnews_partition.h5',
                        help='partition h5 file path')
    
    parser.add_argument('--partition_method', type=str, default='uniform',
                        help='partition method')

    # Model related
    parser.add_argument('--model_type', type=str, default='bert', metavar='N',
                        help='transformer model type')
    parser.add_argument('--model_name', type=str, default='bert-base-uncased', metavar='N',
                        help='transformer model name')
    parser.add_argument('--do_lower_case', type=bool, default=True, metavar='N',
                        help='transformer model name')

    # Learning related
    parser.add_argument('--train_batch_size', type=int, default=8, metavar='N',
                        help='input batch size for training (default: 8)')
    parser.add_argument('--eval_batch_size', type=int, default=8, metavar='N',
                        help='input batch size for evaluation (default: 8)')

    parser.add_argument('--max_seq_length', type=int, default=128, metavar='N',
                        help='maximum sequence length (default: 128)')

    parser.add_argument('--learning_rate', type=float, default=1e-5, metavar='LR',
                        help='learning rate (default: 1e-5)')
    parser.add_argument('--weight_decay', type=float, default=0, metavar='N',
                        help='L2 penalty')

    parser.add_argument('--num_train_epochs', type=int, default=3, metavar='EP',
                        help='how many epochs will be trained locally')
    parser.add_argument('--gradient_accumulation_steps', type=int, default=1, metavar='EP',
                        help='how many steps for accumulate the loss.')
    parser.add_argument('--n_gpu', type=int, default=1, metavar='EP',
                        help='how many gpus will be used ')
    parser.add_argument('--fp16', default=False, action="store_true",
                        help='if enable fp16 for training')
    parser.add_argument('--manual_seed', type=int, default=42, metavar='N',
                        help='random seed')

    # IO related
    parser.add_argument('--output_dir', type=str, default="/tmp/", metavar='N',
                        help='path to save the trained results and ckpts')

    args = parser.parse_args()

    return args

def create_model(args, num_labels):
    # create model, tokenizer, and model config (HuggingFace style)
    MODEL_CLASSES = {
        "bert": (BertConfig, BertForSequenceClassification, BertTokenizer),
    }
    config_class, model_class, tokenizer_class = MODEL_CLASSES[model_type]
    config = config_class.from_pretrained(model_name, num_labels=num_labels, **args.config)
    model = model_class.from_pretrained(model_name, config=config)
    tokenizer = tokenizer_class.from_pretrained(model_name, do_lower_case=args.do_lower_case)
    # logging.info(self.model)
    return config, model, tokenizer

def set_seed(seed):
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)


if __name__ == "__main__":
    # parse python script input parameters
    parser = argparse.ArgumentParser()
    args = add_args(parser)

    # customize the log format
    logging.basicConfig(level=logging.INFO,
                        format='%(process)s %(asctime)s.%(msecs)03d - {%(module)s.py (%(lineno)d)} - %(funcName)s(): %(message)s',
                        datefmt='%Y-%m-%d,%H:%M:%S')
    logging.info(args)

    set_seed(0)

    # device
    device = torch.device("cuda:0")

    # attributes
    attributes = TextClassificationDataManager.load_attributes(args.data_file_path)

    # model
    model_type = args.model_type
    model_name = args.model_name
    tc_args = ClassificationArgs()
    tc_args.load(args.model_name)
    tc_args.model_name = model_name
    tc_args.model_type = model_type
    tc_args.num_labels = len(attributes["label_vocab"])
    tc_args.update_from_dict({"num_train_epochs": args.num_train_epochs,
                              "learning_rate": args.learning_rate,
                              "gradient_accumulation_steps": args.gradient_accumulation_steps,
                              "do_lower_case": args.do_lower_case,
                              "manual_seed": args.manual_seed,
                              "reprocess_input_data": False,
                              "overwrite_output_dir": True,
                              "max_seq_length": args.max_seq_length,
                              "train_batch_size": args.train_batch_size,
                              "eval_batch_size": args.eval_batch_size,
                              "fp16": args.fp16,
                              "data_file_path": args.data_file_path,
                              "partition_file_path": args.partition_file_path,
                              "partition_method": args.partition_method,
                              "dataset": args.dataset,
                              "output_dir": args.output_dir,
                              "is_debug_mode": args.is_debug_mode
                              })

    num_labels = len(attributes["label_vocab"])
    model_config, model, tokenizer = create_model(tc_args, num_labels)

    # preprocessor
    preprocessor = TLMPreprocessor(args=tc_args, label_vocab=attributes["label_vocab"], tokenizer=tokenizer)

    # data manager
    process_id = 0
    num_workers = 1
    tc_data_manager = TextClassificationDataManager(tc_args, args, process_id, num_workers, preprocessor)
    tc_data_manager.load_next_round_data()  # The centralized version.
    train_dl, test_dl = tc_data_manager.get_data_loader()
    test_examples = tc_data_manager.test_examples

    # Create a ClassificationModel and start train
    trainer = TextClassificationTrainer(tc_args, device, model, train_dl, test_dl, test_examples)
    trainer.train_model()


''' Example Usage:

export CUDA_VISIBLE_DEVICES=0
DATA_NAME=agnews
python -m experiments.centralized.transformer_exps.main_tc \
    --dataset ${DATA_NAME} \
    --data_file ~/fednlp_data/data_files/${DATA_NAME}_data.h5 \
    --partition_file ~/fednlp_data/partition_files/${DATA_NAME}_partition.h5 \
    --partition_method uniform \
    --model_type bert \
    --model_name bert-base-uncased \
    --do_lower_case True \
    --train_batch_size 32 \
    --eval_batch_size 32 \
    --max_seq_length 256 \
    --learning_rate 1e-5 \
    --num_train_epochs 5 \
    --output_dir /tmp/${DATA_NAME}_fed/ \
    --n_gpu 1 --fp16

'''