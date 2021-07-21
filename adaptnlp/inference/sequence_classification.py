# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/06_sequence_classification.ipynb (unless otherwise specified).

__all__ = ['logger', 'SequenceResult', 'TransformersSequenceClassifier', 'FlairSequenceClassifier',
           'EasySequenceClassifier']

# Cell
import logging
from typing import List, Dict, Union, Tuple, Callable
from collections import defaultdict, OrderedDict
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import TensorDataset, DataLoader
import datasets
from datasets import ClassLabel
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from flair.data import Sentence, DataPoint
from flair.models import TextClassifier
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    PreTrainedTokenizer,
    PreTrainedModel,
    BertPreTrainedModel,
    DistilBertPreTrainedModel,
    XLMPreTrainedModel,
    XLNetPreTrainedModel,
    ElectraPreTrainedModel,
    BertForSequenceClassification,
    XLNetForSequenceClassification,
    AlbertForSequenceClassification,
    TrainingArguments,
    Trainer,
)

from ..model import AdaptiveModel
from ..model_hub import HFModelResult, FlairModelResult

from fastcore.basics import risinstance
from fastcore.xtras import Path
from ..result import DetailLevel, SentenceResult

from torch import tensor

# Cell
logger = logging.getLogger(__name__)

# Cell
class SequenceResult(SentenceResult):
    """
    A result class designed for Sequence Classification models
    """
    def __init__(self, sentences:List[Sentence], class_names:list = None):
        super().__init__(sentences)
        self.classes = sentences[0].get_label_names()
        self.class_names = class_names

    @property
    def probabilities(self) -> List[List[tensor]]:
        """
        The probabilities returned for each classification
        """
        return torch.stack([tensor(list(map(lambda x: x.score, i.get_labels()))) for i in self._sentences], dim=0)

    @property
    def predictions(self) -> List[str]:
        """
        A list of the best classification for each input
        """
        if self.class_names is not None:
            return [self.class_names[p.argmax()] for p in self.probabilities]
        return [max(s.labels, key=lambda x: x.score).value for s in self._sentences]

    def to_dict(self, detail_level:DetailLevel=DetailLevel.Low):
        """
        Returns details about `self` at various detail levels
        """
        o = {
            'sentences':self.inputs,
            'predictions':self.predictions,
            'probs':self.probabilities
        }
        if detail_level == 'medium' or detail_level == 'high':
            # Add a dictionary of sentence and probabilities, and return the vocab
            o['pairings'] = OrderedDict({
                s:probs for (s,probs) in zip(self.inputs, self.probabilities)
            })
            o['classes'] = self.classes

        if detail_level == 'high':
            # Add original `Sentences`
            o['sentences'] = self._sentences
        return o

# Cell
class TransformersSequenceClassifier(AdaptiveModel):
    """Adaptive model for Transformer's Sequence Classification Model

    Usage:
    ```python
    >>> classifier = TransformersSequenceClassifier.load('transformers-sc-model')
    >>> classifier.predict(text='Example text', mini_batch_size=32)
    ```

    **Parameters:**

    * **tokenizer** - A tokenizer object from Huggingface's transformers (TODO)and tokenizers
    * **model** - A transformers Sequence Classsifciation model
    """

    def __init__(self, tokenizer: PreTrainedTokenizer, model: PreTrainedModel):
        # Load up model and tokenizer
        self.tokenizer = tokenizer
        super().__init__()
        self.set_model(model)

        # Load empty trainer
        self.trainer = None

        # Setup cuda and automatic allocation of model
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)

    @classmethod
    def load(cls, model_name_or_path: Union[HFModelResult, str]) -> AdaptiveModel:
        """Class method for loading and constructing this classifier

        * **model_name_or_path** - A key string of one of Transformer's pre-trained Sequence Classifier Model or a `HFModelResult`
        """
        if isinstance(model_name_or_path, HFModelResult): model_name_or_path = model_name_or_path.name
        tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, use_fast=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_name_or_path)
        classifier = cls(tokenizer, model)
        return classifier

    def predict(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        mini_batch_size: int = 32,
        **kwargs,
    ) -> List[Sentence]:
        """Predict method for running inference using the pre-trained sequence classifier model

        * **text** - String, list of strings, sentences, or list of sentences to run inference on
        * **mini_batch_size** - Mini batch size
        * **&ast;&ast;kwargs**(Optional) - Optional arguments for the Transformers classifier
        """
        id2label = self.model.config.id2label
        sentences = text
        results: List[Sentence] = []

        if not sentences: return sentences

        if risinstance([DataPoint, str], sentences):
            sentences = [sentences]

        # filter empty sentences
        if isinstance(sentences[0], Sentence):
            sentences = [sentence for sentence in sentences if len(sentence) > 0]
        if len(sentences) == 0:
            return sentences

        # reverse sort all sequences by their length
        rev_order_len_index = sorted(
            range(len(sentences)), key=lambda k: len(sentences[k]), reverse=True
        )
        original_order_index = sorted(
            range(len(rev_order_len_index)), key=lambda k: rev_order_len_index[k]
        )

        reordered_sentences: List[Union[DataPoint, str]] = [
            sentences[index] for index in rev_order_len_index
        ]

        # Turn all Sentence objects into strings
        if isinstance(reordered_sentences[0], Sentence):
            str_reordered_sentences = [
                sentence.to_original_text() for sentence in sentences
            ]
        else:
            str_reordered_sentences = reordered_sentences

        dataset = self._tokenize(str_reordered_sentences)
        dl = DataLoader(dataset, batch_size=mini_batch_size)
        predictions: List[Tuple[str, float]] = []

        outputs, _ = super().get_preds(dl=dl)
        logits = torch.cat([o['logits'] for o in outputs])
        predictions = torch.softmax(logits, dim=1).tolist()

        for text, pred in zip(str_reordered_sentences, predictions):
            # Initialize and assign labels to each class in each datapoint prediction
            text_sent = Sentence(text)
            for k, v in id2label.items():
                text_sent.add_label(typename='sc', value=v, score=pred[k])
            results.append(text_sent)

        # Order results back into original order
        results = [results[index] for index in original_order_index]

        return results

    def _tokenize(
        self, sentences: Union[List[Sentence], Sentence, List[str], str]
    ) -> TensorDataset:
        """ Batch tokenizes text and produces a `TensorDataset` with them """

        # TODO: __call__ from tokenizer base class in the transformers library could automate/handle this
        tokenized_text = self.tokenizer.batch_encode_plus(
            sentences,
            return_tensors='pt',
            max_length=None,
            add_special_tokens=True,
        )

        # Bart, XLM, DistilBERT, RoBERTa, and XLM-RoBERTa don't use token_type_ids
        if isinstance(
            self.model,
            (
                BertForSequenceClassification,
                XLNetForSequenceClassification,
                AlbertForSequenceClassification,
            ),
        ):
            dataset = TensorDataset(
                tokenized_text['input_ids'],
                tokenized_text['attention_mask'],
                tokenized_text['token_type_ids'],
            )
        else:
            dataset = TensorDataset(
                tokenized_text['input_ids'], tokenized_text['attention_mask']
            )

        return dataset

# Cell
class FlairSequenceClassifier(AdaptiveModel):
    """Adaptive Model for Flair's Sequence Classifier...very basic

    Usage:
    ```python
    >>> classifier = FlairSequenceClassifier.load('sentiment')
    >>> classifier.predict(text='Example text', mini_batch_size=32)
    ```

    **Parameters:**

    * **model_name_or_path** - A key string of one of Flair's pre-trained Sequence Classifier Model
    """

    def __init__(self, model_name_or_path: str):
        self.classifier = TextClassifier.load(model_name_or_path)

    @classmethod
    def load(cls, model_name_or_path: Union[HFModelResult, FlairModelResult, str]) -> AdaptiveModel:
        """Class method for loading a constructing this classifier

        * **model_name_or_path** - A key string of one of Flair's pre-trained Sequence Classifier Model or a `HFModelResult`
        """
        if risinstance([HFModelResult, FlairModelResult], model_name_or_path):
            model_name_or_path = model_name_or_path.name
        classifier = cls(model_name_or_path)
        return classifier

    def predict(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        mini_batch_size: int = 32,
        **kwargs,
    ) -> List[Sentence]:
        """Predict method for running inference using the pre-trained sequence classifier model

        * **text** - String, list of strings, sentences, or list of sentences to run inference on
        * **mini_batch_size** - Mini batch size
        * **&ast;&ast;kwargs**(Optional) - Optional arguments for the Flair classifier
        """
        if isinstance(text, (Sentence, str)):
            text = [text]
        if isinstance(text[0], str):
            text = [Sentence(s) for s in text]

        self.classifier.predict(
            sentences=text,
            mini_batch_size=mini_batch_size,
            **kwargs,
        )


        return text

# Cell
from ..model_hub import HFModelHub, FlairModelHub

# Cell
class EasySequenceClassifier:
    """Sequence classification models

    Usage:

    ```python
    >>> classifier = EasySequenceClassifier()
    >>> classifier.tag_text(text='text you want to label', model_name_or_path='en-sentiment')
    ```

    """

    def __init__(self):
        self.sequence_classifiers: Dict[AdaptiveModel] = defaultdict(bool)
        self.hf_hub = HFModelHub()
        self.flair_hub = FlairModelHub()

    def tag_text(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        model_name_or_path: Union[str, FlairModelResult, HFModelResult] = 'en-sentiment',
        mini_batch_size: int = 32,
        detail_level:DetailLevel = DetailLevel.Low, # A level of detail to return
        class_names:list = None, # A list of labels
        **kwargs,
    ) -> List[Sentence]:
        """Tags a text sequence with labels the sequence classification models have been trained on

        * **text** - String, list of strings, `Sentence`, or list of `Sentence`s to be classified
        * **model_name_or_path** - The model name key or model path
        * **mini_batch_size** - The mini batch size for running inference
        * **&ast;&ast;kwargs** - (Optional) Keyword Arguments for Flair's `TextClassifier.predict()` method params
        **return** A list of Flair's `Sentence`'s
        """
        # Load Text Classifier Model and Pytorch Module into tagger dict
        name = getattr(model_name_or_path, 'name', model_name_or_path)
        if not self.sequence_classifiers[name]:
            """
            self.sequence_classifiers[name] = TextClassifier.load(
                model_name_or_path
            )
            """
            if risinstance([FlairModelResult, HFModelResult], model_name_or_path):
                try:
                    self.sequence_classifiers[name] = FlairSequenceClassifier.load(name)
                except:
                    self.sequence_classifiers[name] = TransformersSequenceClassifier.load(name)

            elif risinstance([str, Path], model_name_or_path) and (Path(model_name_or_path).exists() and Path(model_name_or_path).is_dir()):
                # Load in previously existing model
                try:
                    self.sequence_classifiers[name] = FlairSequenceClassifier.load(name)
                except:
                    self.sequence_classifiers[name] = TransformersSequenceClassifier.load(name)

            else:
                # Flair
                res = self.flair_hub.search_model_by_name(name, user_uploaded=True)
                if len(res) < 1:
                    # No models found
                    res = self.hf_hub.search_model_by_name(model_name_or_path, user_uploaded=True)
                    if len(res) < 1:
                        logger.info("Not a valid `model_name_or_path` param")
                        return [Sentence('')]
                    else:
                        name = res[0].name.replace('flairNLP', 'flair')
                        self.sequence_classifiers[res[0].name] = TransformersSequenceClassifier.load(name)
                else:
                    name = res[0].name.replace('flairNLP/', '')
                    self.sequence_classifiers[name] = FlairSequenceClassifier.load(name) # Returning the first should always be non-fast

        classifier = self.sequence_classifiers[name]
        out = classifier.predict(
            text=text,
            mini_batch_size=mini_batch_size,
            **kwargs,
        )
        if detail_level is None: return out
        res = SequenceResult(out, class_names)
        return res.to_dict(detail_level)


    def tag_all(
        self,
        text: Union[List[Sentence], Sentence, List[str], str],
        mini_batch_size: int = 32,
        detail_level:DetailLevel = DetailLevel.Low,
        class_names:list = None, # A list of labels
        **kwargs,
    ) -> List[Sentence]:
        """Tags text with all labels from all sequence classification models

        * **text** - Text input, it can be a string or any of Flair's `Sentence` input formats
        * **mini_batch_size** - The mini batch size for running inference
        * **&ast;&ast;kwargs** - (Optional) Keyword Arguments for Flair's `TextClassifier.predict()` method params
        * **return** - A list of Flair's `Sentence`'s
        """
        sentences = text
        for tagger_name in self.sequence_classifiers.keys():
            sentences = self.tag_text(
                sentences,
                model_name_or_path=tagger_name,
                mini_batch_size=mini_batch_size,
                detail_level = None
                **kwargs,
            )
        res = SequenceResult(out, class_names)
        return res.to_dict(detail_level)