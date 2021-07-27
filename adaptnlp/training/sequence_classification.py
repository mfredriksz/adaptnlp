# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/15_training.sequence_classification.ipynb (unless otherwise specified).

__all__ = ['SequenceClassificationDatasets', 'SequenceClassificationTuner']

# Cell
import pandas as pd
from fastcore.foundation import L
from fastcore.meta import delegates
from fastcore.xtras import Path, range_of

from fastai.basics import *
from fastai.data.transforms import get_files

from datasets import Dataset
from transformers import AutoModelForSequenceClassification, default_data_collator, AutoTokenizer

from .core import * # Core has everything we need so you should always import * with it

from ..inference.sequence_classification import TransformersSequenceClassifier, SequenceResult, DetailLevel
from typing import List

from .arrow_utils import TextNoNewLineDatasetReader

# Cell
def _tokenize(item, tokenizer, tokenize_kwargs): return tokenizer(item['text'], **tokenize_kwargs)

# Cell
class SequenceClassificationDatasets(TaskDatasets):
    """
    A set of datasets designed for sequence classification
    """
    def __init__(
        self,
        train_dset,
        valid_dset,
        tokenizer_name,
        tokenize,
        tokenize_kwargs,
        auto_kwargs,
        remove_columns,
        categorize
    ):
        "Constructs TaskDatasets, should not be called implicitly"
        super().__init__(
            train_dset,
            valid_dset,
            tokenizer_name,
            tokenize,
            _tokenize,
            tokenize_kwargs,
            auto_kwargs,
            remove_columns
        )
        self.categorize = categorize


    @classmethod
    def from_dfs(
        cls,
        train_df:pd.DataFrame, # A training dataframe
        text_col:str, # The name of the text column
        label_col:str, # The name of the label column
        tokenizer_name:str, # The name of the tokenizer
        tokenize:bool=True, # Whether to tokenize immediatly
        is_multicategory:bool=False, # Whether each item has a single label or multiple labels
        label_delim=' ', # If `is_multicategory`, how to seperate the labels
        valid_df=None, # An optional validation dataframe
        split_func=None, # Optionally a splitting function similar to RandomSplitter
        split_pct=.2, # What % to split the train_df
        tokenize_kwargs:dict={}, # kwargs for the tokenize function
        auto_kwargs:dict={} # kwargs for the AutoTokenizer.from_pretrained constructor
    ):
        "Builds `SequenceClassificationDatasets` from a `DataFrame` or set of `DataFrames`"
        if split_func is None: split_func = RandomSplitter(split_pct)
        if valid_df is None:
            train_idxs, valid_idxs = split_func(range_of(train_df))
            valid_df = train_df.loc[valid_idxs]
            train_df = train_df.loc[train_idxs]

        train_df = train_df[[text_col,label_col]]
        valid_df = valid_df[[text_col,label_col]]
        train_df = train_df.rename(columns={text_col:'text', label_col: 'labels'})
        valid_df = valid_df.rename(columns={text_col:'text', label_col: 'labels'})

        train_dset = Dataset.from_dict(train_df.to_dict('list'))
        valid_dset = Dataset.from_dict(valid_df.to_dict('list'))
        lbls = list(train_df['labels'].unique())
        if is_multicategory:
            classes = set()
            for lbl in lbls:
                sep_l = lbl.split(label_delim)
                for l in sep_l: classes.add(l)
            categorize = MultiCategorize(classes)
        else:
            classes = set()
            for lbl in lbls: classes.add(lbl)
            categorize = Categorize(classes)

        return cls(train_dset, valid_dset, tokenizer_name, tokenize, tokenize_kwargs, auto_kwargs, remove_columns=['text'], categorize)

    @classmethod
    def from_csvs(
        cls,
        train_csv:Path, # A training csv file
        text_col:str, # The name of the text column
        label_col:str, # The name of the label column
        tokenizer_name:str, # The name of the tokenizer
        tokenize:bool=True, # Whether to tokenize immediatly
        is_multicategory:bool=False, # Whether each item has a single label or multiple labels
        label_delim=' ', # If `is_multicategory`, how to seperate the labels
        valid_csv:Path=None, # An optional validation csv
        split_func=None, # Optionally a splitting function similar to RandomSplitter
        split_pct=.2, # What % to split the train_df
        tokenize_kwargs:dict={}, # kwargs for the tokenize function
        auto_kwargs:dict={} # kwargs for the AutoTokenizer.from_pretrained constructor
    ):
        "Builds `SequenceClassificationDatasets` from a single csv or set of csvs. A convience constructor for `from_dfs`"
        train_df = pd.read_csv(train_csv)
        if valid_csv is not None: valid_df = pd.read_csv(valid_csv)
        else: valid_df = None
        return cls.from_dfs(train_df, text_col, label_col, tokenizer_name, tokenize, is_multicategory, label_delim, valid_df, split_func, split_pct, tokenize_kwargs, auto_kwargs)

    @classmethod
    def from_folders(
        cls,
        train_path:Path, # The path to the training data
        get_label:callable, # A function which grabs the label(s) given a text files `Path`
        tokenizer_name:str, # The name of the tokenizer
        tokenize:bool=True, # Whether to tokenize immediatly
        is_multicategory:bool=False, # Whether each item has a single label or multiple labels
        label_delim='_', # if `is_multicategory`, how to seperate the labels
        valid_path:Path=None, # The path to the validation data
        split_func=None, # Optionally a splitting function similar to RandomSplitter
        split_pct=.2, # What % to split the items in the `train_path`
        tokenize_kwargs:dict={}, # kwargs for the tokenize function
        auto_kwargs:dict={}, # kwargs for the AutoTokenizer.from_pretrained constructor
    ):
        "Builds `SequenceClassificationDatasets` from a folder or groups of folders"
        train_txts = get_files(train_path, extensions='.txt')
        if valid_path is not None:
            valid_txts = get_files(valid_path, extensions='.txt')
        else:
            if split_func is None:
                split_func = RandomSplitter(split_pct)
            train_idxs, valid_idxs = split_func(train_txts)
            valid_txts = train_txts[valid_idxs]
            train_txts = train_txts[train_idxs]
        train_txts = [str(x) for x in train_txts]
        valid_txts = [str(x) for x in valid_txts]
        train_dset = TextNoNewLineDatasetReader(train_txts).read()
        valid_dset = TextNoNewLineDatasetReader(valid_txts).read()

        train_lbls = [get_label(o) for o in train_txts]
        valid_lbls = [get_label(o) for o in valid_txts]
        if is_multicategory:
            classes = set()
            for lbl in train_lbls:
                sep_l = lbl.split(label_delim)
                for l in sep_l: classes.add(l)
            categorize = MultiCategorize(classes)
        else:
            classes = set()
            for lbl in train_lbls: classes.add(lbl)
            categorize = Categorize(classes)
        train_dset = train_dset.add_column('label', train_lbls)
        valid_dset = valid_dset.add_column('label', valid_lbls)

        return cls(train_dset, valid_dset, tokenizer_name, tokenize, tokenize_kwargs, auto_kwargs, remove_columns=['text'], categorize)

    @delegates(DataLoaders)
    def dataloaders(
        self,
        batch_size=8, # A batch size
        shuffle_train=True, # Whether to shuffle the training dataset
        collate_fn = None, # A custom collation function
        **kwargs): # Torch DataLoader kwargs
        dls = super().dataloaders(batch_size, shuffle_train, collate_fn, **kwargs)
        dls[0].categorize = self.categorize
        return dls

# Cell
class SequenceClassificationTuner(AdaptiveTuner):
    """
    An `AdaptiveTuner` with good defaults for Sequence Classification tasks

    **Valid kwargs and defaults:**
      - `lr`:float = 0.001
      - `splitter`:function = `trainable_params`
      - `cbs`:list = None
      - `path`:Path = None
      - `model_dir`:Path = 'models'
      - `wd`:float = None
      - `wd_bn_bias`:bool = False
      - `train_bn`:bool = True
      - `moms`: tuple(float) = (0.95, 0.85, 0.95)

    """
    def __init__(
        self,
        dls:DataLoaders, # A set of DataLoaders
        model_name:str, # A HuggingFace model
        tokenizer = None, # A HuggingFace tokenizer
        loss_func = CrossEntropyLossFlat(), # A loss function
        metrics = [accuracy, F1Score()], # Metrics to monitor the training with
        opt_func = Adam, # A fastai or torch Optimizer
        additional_cbs = None, # Additional Callbacks to have always tied to the Tuner,
        expose_fastai_api = False, # Whether to expose the fastai API
        num_classes:int=None, # The number of classes
        **kwargs, # kwargs for `Learner.__init__`
    ):
        additional_cbs = listify(additional_cbs)
        for arg in 'dls,model,loss_func,metrics,opt_func,cbs,expose_fastai'.split(','):
            if arg in kwargs.keys(): kwargs.pop(arg) # Pop all existing kwargs
        if hasattr(dls[0], 'categorize'): num_classes = getattr(dls[0].categorize, 'classes', None)
        if num_classes is None: raise ValueError("Could not extrapolate number of classes, please pass it in as a param")
        if not isinstance(num_classes, int): num_classes = len(num_classes)
        model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=num_classes)
        if tokenizer is None: tokenizer = AutoTokenizer.from_pretrained(model_name)

        super().__init__(
            expose_fastai_api,
            dls = dls,
            model = model,
            tokenizer = tokenizer,
            loss_func = loss_func,
            metrics = metrics,
            opt_func = opt_func,
            cbs=additional_cbs,
            **kwargs
        )

    @delegates(Learner.__init__)
    @classmethod
    def from_df(
        cls,
        df:pd.DataFrame, # A Pandas Dataframe or Path to a DataFrame
        text_col:str = 'text', # Name of the column the text is stored
        label_col:str = 'labels', # Name of the column the label(s) are stored
        remove_columns:Union[str,List[str]] = None, # Name of columns to be removed after tokenizing
        model_name:str = None, # The string name of a huggingFace model
        split_func:callable = RandomSplitter(), # A function which splits the data
        loss_func = CrossEntropyLossFlat(), # A loss function
        metrics = [accuracy, F1Score()], # Metrics to monitor the training with
        batch_size=8, # A batch size
        collate_fn=default_data_collator, # An optional custom collate function
        opt_func = Adam, # A fastai or torch Optimizer
        additional_cbs = None, # Additional Callbacks to have always tied to the Tuner,
        expose_fastai_api = False, # Whether to expose the fastai API
        tokenize_func:callable = None, # Optional custom tokenize function for a single item, such as `def _inner(item): return self.tokenizer(item['text'])`
        tokenize_kwargs:dict = {'padding':True}, # Some kwargs for when we call the tokenizer
        auto_kwargs:dict = {}, # Some kwargs when calling `AutoTokenizer.from_pretrained`
        **kwargs # Learner kwargs
    ):
        "Convience method to build a `SequenceClassificationTuner` from a Pandas Dataframe"
        try:
            splits = split_func(df)
        except:
            splits = split_func(range_of(df))
        dset = SequenceClassificationDatasets.from_df(
            df,
            text_col,
            label_col,
            splits,
            tokenizer_name=model_name,
            tokenize_kwargs=tokenize_kwargs,
            auto_kwargs=auto_kwargs,
            tokenize_func=tokenize_func,
            remove_columns=remove_columns
        )

        tokenizer = dset.tokenizer

        dls = dset.dataloaders(batch_size, collate_fn)

        return cls(dls, model_name, tokenizer, loss_func, metrics, opt_func, additional_cbs, expose_fastai_api)

    def predict(
        self,
        text:Union[List[str], str], # Some text or list of texts to do inference with
        bs:int=64, # A batch size to use for multiple texts
        detail_level:DetailLevel = DetailLevel.Low, # A detail level to return on the predictions
    ):
        "Predict some `text` for sequence classification with the currently loaded model"
        if getattr(self, '_inferencer', None) is None: self._inferencer = TransformersSequenceClassifier(self.tokenizer, self.model)
        preds = self._inferencer.predict(text,bs)
        cat = getattr(self.dls, 'categorize', None)
        vocab = cat.classes if cat is not None else None
        return SequenceResult(preds, vocab).to_dict(detail_level)