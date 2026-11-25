import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import candidates as cd  # noqa: E402
import seed_tools as st  # noqa: E402

DIRS = ["sample", "full"]


@pytest.fixture(scope="module", params=DIRS)
def data(request):
    d = ROOT / "data" / request.param
    gold = st.read_jsonl(d / "gold_docs.jsonl")
    population = st.load_population(d / "population.csv")
    targets = cd.load_targets(d / "targets.csv")
    generated = cd.load_generated(d)
    return d, gold, population, targets, cd.make_rows(gold, population, targets, generated=generated)


def pick(rows, design, n):
    return [r for r in rows if (r["design"], r["n"]) == (design, n)]


def test_one_list_per_document_design_and_size(data):
    _, gold, _, _, rows = data
    assert len(rows) == len(gold) * len(cd.DESIGNS) * len(cd.SIZES)
    assert len({(r["doc_id"], r["design"], r["n"]) for r in rows}) == len(rows)


def test_exactly_n_distinct_people(data):
    _, _, population, _, rows = data
    ids = {p["person_id"] for p in population}
    for r in rows:
        assert len(r["candidates"]) == len(set(r["candidates"])) == r["n"]
        assert set(r["candidates"]) <= ids


def test_target_and_every_lookalike_are_in_the_list(data):
    _, gold, _, targets, rows = data
    person = {d["doc_id"]: d["person_id"] for d in gold}
    for r in rows:
        t = targets[person[r["doc_id"]]]
        assert {t["person_id"], *t["lookalikes"].split()} <= set(r["candidates"])


def test_balanced_lists_are_whole_groups_of_one_genre(data):
    _, gold, _, targets, rows = data
    genre = {d["doc_id"]: d["genre"] for d in gold}
    for r in rows:
        if r["design"] != "balanced":
            continue
        people = set(r["candidates"])
        inside = [t for t in targets.values() if t["person_id"] in people]
        assert {t["genre"] for t in inside} == {genre[r["doc_id"]]}
        assert sorted(people) == sorted(p for t in inside for p in cd.group(t))


def test_lists_are_deterministic_and_do_not_share_an_order(data):
    d, gold, population, targets, rows = data
    generated = cd.load_generated(d)
    assert cd.make_rows(gold, population, targets, generated=generated) == rows
    assert cd.make_rows(gold, population, targets, seed=cd.SEED + 1, generated=generated) != rows
    assert len({tuple(r["candidates"]) for r in rows}) == len(rows)


@pytest.mark.parametrize("design", cd.DESIGNS)
@pytest.mark.parametrize("n", cd.SIZES)
def test_target_positions_are_even(data, design, n):
    _, gold, _, _, rows = data
    person = {d["doc_id"]: d["person_id"] for d in gold}
    slots = [r["candidates"].index(person[r["doc_id"]]) for r in pick(rows, design, n)]
    count = Counter(s * 10 // n for s in slots)  # tenths of the list
    assert set(count) == set(range(10))
    assert max(count.values()) - min(count.values()) <= 2  # 1, or 2 after a document is dropped


def test_dropping_a_document_leaves_the_other_lists_alone(data):
    d, gold, population, targets, rows = data
    generated = cd.load_generated(d) or gold
    dropped = gold[3]["doc_id"]
    fewer = cd.make_rows([g for g in gold if g["doc_id"] != dropped], population, targets,
                         generated=generated)
    assert fewer == [r for r in rows if r["doc_id"] != dropped]


def test_target_slots_are_not_tied_to_document_order():
    import random
    slots = cd.target_slots(147, 10, random.Random(1))
    assert slots != sorted(slots)


def test_balanced_floor_is_far_below_random(data):
    _, gold, population, _, rows = data

    def floor(design, n):
        return cd.floor(pick(rows, design, n), gold, population, cd.guess_both_genre)
    assert floor("balanced", 10) < 0.35
    assert floor("balanced", 100) < 0.05
    assert floor("random", 10) > 0.8
    assert floor("random", 100) > 0.6


def test_floor_of_a_blind_guess_is_chance(data):
    _, gold, population, _, rows = data
    assert cd.floor(pick(rows, "balanced", 10), gold, population,
                    lambda people, genre: people) == pytest.approx(0.1)


def test_validate_accepts_the_lists_and_rejects_broken_ones(data):
    _, gold, population, targets, rows = data
    assert cd.validate(rows, gold, population, targets) == []
    r = rows[0]
    target = next(d["person_id"] for d in gold if d["doc_id"] == r["doc_id"])
    no_target = [c for c in r["candidates"] if c != target]
    broken = [dict(r, candidates=r["candidates"][:-1]),
              dict(r, candidates=r["candidates"][:-1] + r["candidates"][:1]),
              dict(r, candidates=no_target + ["P9999"]),
              dict(r, doc_id="D000")]
    for b in broken:
        assert cd.validate([b] + rows[1:], gold, population, targets)
    assert any("2 rows" in e for e in cd.validate(rows + [r], gold, population, targets))
    assert any("no " in e for e in cd.validate(rows[1:], gold, population, targets))


def test_committed_lists_are_up_to_date(data):
    d, _, _, _, rows = data
    assert st.read_jsonl(d / "candidates.jsonl") == rows


def test_fill_exactly_uses_whole_groups_or_fails():
    import random
    pool = [["a", "b"], ["c", "d", "e"], ["f", "g", "h", "i"]]
    out = cd.fill_exactly(pool, 5, random.Random(0))
    assert sorted(out) == ["a", "b", "c", "d", "e"]
    with pytest.raises(ValueError):
        cd.fill_exactly(pool, 8, random.Random(0))


def test_profile_shows_every_attribute_but_no_id():
    p = {"person_id": "P0001", "first_name": "Оксана", "patronymic": "Миколаївна",
         "surname": "Вигаданчук", "gender": "F", "birth_year": "1990", "oblast": "Полтавська",
         "settlement": "Вербівка", "settlement_type": "village", "occupation": "вчитель хімії",
         "family_status": "widowed", "children": "3", "event": "award_teacher_of_year_2019"}
    assert cd.profile(p) == ("Вигаданчук Оксана Миколаївна; жінка; 1990 р. н.; "
                             "Полтавська обл., село Вербівка; вчитель хімії; вдова; дітей: 3; "
                             "подія: нагорода «Вчитель року» (2019)")
    assert cd.profile(dict(p, event="")).endswith("подія: немає")


def test_every_person_has_a_distinct_profile(data):
    _, _, population, _, _ = data
    profiles = [cd.profile(p) for p in population]
    assert len(set(profiles)) == len(population)
    assert not any(p["person_id"] in text for p, text in zip(population, profiles))


def test_labels():
    assert cd.labels(2) == ["C001", "C002"]
    assert cd.labels(100)[-1] == "C100"
