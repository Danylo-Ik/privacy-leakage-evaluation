import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_understanding"))

import seed_tools as st  # noqa: E402
import recall  # noqa: E402


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    d = tmp_path_factory.mktemp("seed")
    st.build(d)
    return st.read_jsonl(d / "gold_docs.jsonl"), st.read_jsonl(d / "masked_docs.jsonl")


def mask(start, end):
    return {"start": start, "end": end}


def test_half_masked_word_is_closed():
    text = "Іван Бойко"  # «Бойко» is 5 letters at 5..10
    assert recall.is_open(text, 5, 10, recall.coverage(text, [mask(5, 7)]))      # 2 of 5
    assert not recall.is_open(text, 5, 10, recall.coverage(text, [mask(5, 8)]))  # 3 of 5
    text = "Олег"
    assert recall.is_open(text, 0, 4, recall.coverage(text, [mask(0, 1)]))       # 1 of 4
    assert not recall.is_open(text, 0, 4, recall.coverage(text, [mask(0, 2)]))   # 2 of 4


def one_doc(tagged, genre="news"):
    text, spans = st.parse_tagged(tagged)
    return {"doc_id": "D1", "genre": genre, "target_entity_id": "E1", "text": text, "spans": spans}


def test_full_name_is_one_mention_and_one_open_part_opens_it():
    doc = one_doc("Свідок [[Ірина|PERSON|DI|E1|nom|first]] [[Петрівна|PERSON|DI|E1|nom|patronymic]] "
                  "[[Бойко|PERSON|DI|E1|nom|surname]] з [[Вербівки|LOC|QI|E2|gen|-|settlement]].")
    first, patr = doc["spans"][0], doc["spans"][1]
    row = {"doc_id": "D1", "system_or_condition": "x",
           "masked_spans": [mask(first["start"], first["end"]), mask(doc["spans"][2]["start"],
                                                                     doc["spans"][3]["end"])]}
    c, open_mentions = recall.score_doc(doc, row)
    assert c["m:all"] == 2 and c["m_closed:all"] == 1
    assert [m["text"] for m in open_mentions] == [doc["text"][first["start"]:doc["spans"][2]["end"]]]
    assert open_mentions[0]["name_parts"] == ["first", "patronymic", "surname"]
    assert c["t_safe"] == 0 and c["f_safe"] == 0
    assert c["s:part=patronymic"] == 1 and c["s_closed:part=patronymic"] == 0


def test_gold_conditions(seed):
    gold, masked = seed
    results, _, _ = recall.evaluate(gold, masked, boot=0)
    full = results["gold_full"]["metrics"]
    for m in ("mention_recall", "entity_recall", "target_protected", "fully_protected"):
        assert full[m] == 1.0
    assert full["over_masking"] == 0.0
    miss = results["gold_miss_one_oblique"]["metrics"]
    assert miss["target_protected"] == 0.0
    assert miss["mention_recall"] > 0.8  # the gap RQ1 is about
    di = results["gold_di_only"]["metrics"]
    assert di["mention_recall|type=QI"] == 0.0 and di["fully_protected"] == 0.0


def test_splits_add_up(seed):
    gold, masked = seed
    docs = {d["doc_id"]: d for d in gold}
    for r in masked:
        c, _ = recall.score_doc(docs[r["doc_id"]], r)
        for prefix in ("type=", "genre="):
            parts = [k for k in c if k.startswith("m:" + prefix)]
            assert sum(c[k] for k in parts) == c["m:all"]
        persons = sum(c[k] for k in ("m:case=nom", "m:case=oblique", "m:case=None"))
        assert persons == c["m:cat=PERSON"]


def test_failed_llm_rows_are_skipped(seed):
    gold, masked = seed
    rows = [dict(r, system_or_condition="llm", llm_failed=True) for r in masked[:2]]
    results, _, skipped = recall.evaluate(gold, masked + rows, boot=0)
    assert skipped["llm"] == 2 and "llm" not in results


def test_names_only_gold_works():
    # official test set style: PERSON spans only, few fields
    text = "Позивач Бойко звернувся до суду."
    doc = {"doc_id": "D1", "text": text,
           "spans": [{"start": 8, "end": 13, "category": "PERSON", "entity_id": "E1"}]}
    row = {"doc_id": "D1", "system_or_condition": "x", "masked_spans": [mask(8, 13)]}
    results, _, _ = recall.evaluate([doc], [row], boot=0)
    m = results["x"]["metrics"]
    assert m["mention_recall"] == 1.0 and m["entity_recall"] == 1.0
    assert m["target_protected"] is None


def test_bootstrap_interval_contains_value(seed):
    gold, masked = seed
    results, _, _ = recall.evaluate(gold, masked, boot=200)
    r = results["gold_miss_one_oblique"]
    lo, hi = r["ci"]["mention_recall"]
    assert lo <= r["metrics"]["mention_recall"] <= hi
