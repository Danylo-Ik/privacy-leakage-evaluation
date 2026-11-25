import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_understanding"))
sys.path.insert(0, str(ROOT / "model_training"))

import conditions as cd  # noqa: E402
import seed_tools as st  # noqa: E402
import uniqueness as uq  # noqa: E402


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    d = tmp_path_factory.mktemp("seed")
    st.build(d)
    cd.main([str(d), "--seeds", "2"])
    return (st.load_population(d / "population.csv"), st.read_jsonl(d / "gold_docs.jsonl"),
            st.read_jsonl(d / "masked_docs.jsonl"))


def unmasked(doc, to_mask):
    keep = {id(s) for s in to_mask}
    return {(s["start"], s["end"]) for s in doc["spans"] if id(s) not in keep}


def test_all_conditions_validate(seed):
    pop, gold, masked = seed
    assert st.validate_masked(masked, gold) == []
    names = {r["system_or_condition"] for r in masked}
    for n in ("gold_full", "gold_di_only", "gold_edrsr_policy", "gold_miss_one_oblique",
              "gold_drop_p05", "gold_drop_p10", "gold_drop_p20", "gold_drop_p40",
              "gold_drop_p05_s1", "gold_keep_patronymic"):
        assert n in names


def test_drop_out_is_nested_and_deterministic(seed):
    _, gold, _ = seed
    for d in gold:
        holes = [unmasked(d, cd.drop_out(d, r)) for r in cd.DROP_RATES]
        assert all(a <= b for a, b in zip(holes, holes[1:]))
        assert unmasked(d, cd.drop_out(d, 0.2)) == holes[2]
        assert unmasked(d, cd.drop_out(d, 0.0)) == set()
        assert unmasked(d, cd.drop_out(d, 1.0)) == {(s["start"], s["end"]) for s in d["spans"]}


def test_drop_out_drops_whole_mentions(seed):
    _, gold, _ = seed
    for d in gold:
        holes = unmasked(d, cd.drop_out(d, 0.4))
        for m in cd.all_mentions(d["text"], d["spans"]):
            parts = {(s["start"], s["end"]) for s in m}
            assert parts <= holes or not (parts & holes)


def test_drop_rate_is_roughly_right(seed):
    _, gold, _ = seed
    n = sum(len(cd.all_mentions(d["text"], d["spans"])) for d in gold)
    dropped = 0
    for d in gold:
        holes = unmasked(d, cd.drop_out(d, 0.4))
        dropped += sum(1 for m in cd.all_mentions(d["text"], d["spans"])
                       if (m[0]["start"], m[0]["end"]) in holes)
    assert 0.25 < dropped / n < 0.55


def test_seeds_differ(seed):
    _, gold, _ = seed
    assert any(unmasked(d, cd.drop_out(d, 0.4, 0)) != unmasked(d, cd.drop_out(d, 0.4, 1))
               for d in gold)


def test_keep_patronymic(seed):
    pop, gold, masked = seed
    rows = {(r["doc_id"], r["system_or_condition"]): r for r in masked}
    r = rows[("D001", "gold_keep_patronymic")]
    assert "ОСОБА_1 Миколаївна" in r["masked_text"]
    d2 = rows[("D002", "gold_keep_patronymic")]["masked_text"]
    assert "Петровича" in d2 and "Ковальчинськ" not in d2 and "Тараса" not in d2
    k = {(x["doc_id"], x["system_or_condition"]): x["k"] for x in uq.score(pop, gold, masked)}
    for d in gold:
        assert k[(d["doc_id"], "gold_keep_patronymic")] <= k[(d["doc_id"], "gold_full")]


def test_placeholders_stable_across_conditions(seed):
    _, _, masked = seed
    rows = {(r["doc_id"], r["system_or_condition"]): r for r in masked}
    full = {(m["start"], m["end"]): m["placeholder"]
            for m in rows[("D002", "gold_full")]["masked_spans"]}
    for m in rows[("D002", "gold_drop_p40")]["masked_spans"]:
        assert full[(m["start"], m["end"])] == m["placeholder"]
