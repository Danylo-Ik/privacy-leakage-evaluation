import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_understanding"))

import seed_tools as st  # noqa: E402
import uniqueness as uq  # noqa: E402


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    d = tmp_path_factory.mktemp("seed")
    st.build(d)
    return (st.load_population(d / "population.csv"), st.read_jsonl(d / "gold_docs.jsonl"),
            st.read_jsonl(d / "masked_docs.jsonl"))


def test_seed_validates(seed):
    pop, gold, masked = seed
    assert st.validate_gold(gold, pop) == []
    assert st.validate_masked(masked, gold) == []


def test_offsets_roundtrip():
    text, spans = st.parse_tagged("Позов [[Ковальчинського|PERSON|DI|E1|gen|surname]] задоволено.")
    s = spans[0]
    assert text[s["start"]:s["end"]] == "Ковальчинського"
    assert s["owner"] == "E1" and s["edrsr_type"] == "ОСОБА"


def test_apostrophes_normalized():
    text, spans = st.parse_tagged("[[Мар'яна|PERSON|DI|E1|nom|first]] і Мар`яна")
    assert text == "Мар’яна і Мар’яна"
    assert spans[0]["text"] == "Мар’яна"


def test_too_many_fields_raises():
    with pytest.raises(st.TagError):
        st.parse_tagged("[[Оксана|PERSON|DI|E1|nom|first|-|E1|extra]]")


def test_broken_tag_is_caught(seed):
    pop, _, _ = seed
    text, spans = st.parse_tagged("Привітали [[Оксану|PERSON|DI|E1|acc|first] сьогодні.")
    doc = {"doc_id": "X", "person_id": "P0001", "target_entity_id": "E1", "genre": "news",
           "doc_year": 2024, "text": text, "spans": spans}
    errs = st.validate_gold([doc], pop)
    assert any("leftover tag" in e for e in errs)


def test_owner_defaults():
    _, spans = st.parse_tagged(
        "[[Ігорем|PERSON|DI|E9|ins|first]] [[Вербівка|LOC|QI|E2|nom|-|settlement]] "
        "[[12 травня|DATETIME|QI|E3]] [[3012345678|CODE|DI|E6|-|-|-|E1]]")
    assert [s["owner"] for s in spans] == ["E9", "E1", None, "E1"]


@pytest.mark.parametrize("tag,expected", [
    ("[[№ 640/9071/22|CODE|DI|E2]]", None),
    ("[[3012345678|CODE|DI|E2|-|-|-|E1]]", "НОМЕР"),
    ("[[a.b@example.com|CODE|DI|E2|-|-|-|E1]]", "ІНФОРМАЦІЯ"),
    ("[[м. Харків, вул. Вигадана, 7|LOC|DI|E2|-|-|settlement]]", "АДРЕСА"),
    ("[[Вербівка|LOC|QI|E2|nom|-|settlement]]", None),
    ("[[1978 року народження|DATETIME|QI|E2|-|-|birth_year]]", "ІНФОРМАЦІЯ"),
    ("[[34-річна|DEM|QI|E2|nom|-|birth_year]]", None),
])
def test_edrsr_type(tag, expected):
    _, spans = st.parse_tagged(tag)
    assert spans[0]["edrsr_type"] == expected


def test_k_counts_leaked_names(seed):
    pop, gold, masked = seed
    rows = {(r["doc_id"], r["system_or_condition"]): r["k"] for r in uq.score(pop, gold, masked)}
    assert rows[("D001", "gold_miss_one_oblique")] == 1
    assert rows[("D001", "gold_full")] > 1
    assert rows[("D001", "gold_edrsr_policy")] == 1
