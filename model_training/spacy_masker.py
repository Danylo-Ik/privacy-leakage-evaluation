"""spaCy NER masker: uk_core_news_trf entities + the shared regex layer.

The Ukrainian pipelines only tag PER, LOC, ORG and MISC, so codes, dates, ages and
amounts come from regex_rules (the same layer the rule-based system uses). The two
systems therefore differ only in how they find names, places and organisations.

Model: SPACY_MODEL env var, default uk_core_news_trf (fallback: uk_core_news_lg).
"""
import os
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import regex_rules  # noqa: E402

LABELS = {"PER": "PERSON", "PERS": "PERSON", "PERSON": "PERSON", "LOC": "LOC", "GPE": "LOC",
          "ORG": "ORG", "MISC": "MISC"}


@lru_cache(maxsize=2)
def load(model=None):
    import spacy
    return spacy.load(model or os.environ.get("SPACY_MODEL", "uk_core_news_trf"))


def ner_spans(doc):
    return [{"start": e.start_char, "end": e.end_char,
             "category": LABELS.get(e.label_, "MISC"), "source": "ner"} for e in doc.ents]


def mask_spans(text, doc):
    ents = common.cluster_persons(text, ner_spans(doc))
    return regex_rules.find(text) + ents


def run(gold_docs, name="spacy", model=None):
    nlp = load(model)
    texts = [d["text"] for d in gold_docs]
    return [common.to_row(d["doc_id"], name, d["text"], mask_spans(d["text"], doc))
            for d, doc in zip(gold_docs, nlp.pipe(texts, batch_size=8))]
