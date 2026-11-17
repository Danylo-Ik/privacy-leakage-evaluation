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


@pytest.fixture(scope="module")
def population():
    import population as pg
    return pg.make_population()


def test_population_size_and_seed_rows(population):
    people, targets = population
    assert len(people) == 2000 and len(targets) == 150
    for row, seed_row in zip(people, st.TARGETS):
        assert all(str(row[k]) == str(v) for k, v in seed_row.items())
    assert len({(p["first_name"], p["patronymic"], p["surname"]) for p in people}) == 2000


def test_population_is_deterministic(population):
    import population as pg
    assert pg.make_population() == population


def test_lookalikes_match_target(population):
    people, targets = population
    by_id = {p["person_id"]: p for p in people}
    for t in targets:
        ids = t["lookalikes"].split()
        assert 1 <= len(ids) <= 3
        for i in ids:
            for col in ("gender", "birth_year", "oblast", "occupation"):
                assert by_id[i][col] == by_id[t["person_id"]][col]


def test_target_genre_follows_event(population):
    import population as pg
    people, targets = population
    by_id = {p["person_id"]: p for p in people}
    assert {t["genre"] for t in targets} == {"court", "news", "forum"}
    for t in targets:
        assert by_id[t["person_id"]]["event"] == t["event"]
        assert pg.EVENT_GENRE[t["event"].rsplit("_", 1)[0]] == t["genre"]


def test_surname_types():
    import population as pg
    assert pg.surname_type("Ковальчинський") == "skyi"
    assert pg.surname_type("Андрієнко") == "enko"
    assert pg.surname_type("Петришин") == "yshyn"
    assert pg.surname_type("Дубова") == "adj"
    assert pg.surname_type("Щербанюк") == "chuk"
    assert pg.female_surname("Терновський") == "Терновська"
    assert pg.female_surname("Ковальчук") == "Ковальчук"


def test_seed_gold_validates_against_new_population(seed, population):
    _, gold, _ = seed
    assert st.validate_gold(gold, population[0]) == []


def test_validator_allows_extra_population_columns(tmp_path, seed, population):
    import csv
    import population as pg
    st.build(tmp_path)
    with open(tmp_path / "population.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pg.COLUMNS)
        w.writeheader()
        w.writerows(population[0])
    assert st.validate(tmp_path)


def test_name_forms_cover_seed_docs():
    import names
    import seed_docs
    targets = {t["person_id"]: t for t in st.TARGETS}
    for doc in seed_docs.SEED_DOCS:
        t = targets[doc["person_id"]]
        found = names.forms(t["first_name"], t["patronymic"], t["surname"], t["gender"])
        _, spans = st.parse_tagged(doc["tagged"])
        for s in spans:
            if s["entity_id"] == "E1" and s["category"] == "PERSON":
                assert s["text"] in found, (doc["doc_id"], s["text"])


@pytest.mark.parametrize("word,gender,case,expected", [
    ("Олег", "M", "voc", "Олеже"),
    ("Ольга", "F", "dat", "Ользі"),
    ("Наталія", "F", "ins", "Наталією"),
    ("Микола", "M", "acc", "Миколу"),
    ("Сашко", "M", "voc", "Сашку"),
    ("Петро", "M", "voc", "Петре"),
    ("Андрій", "M", "ins", "Андрієм"),
    ("Петрович", "M", "ins", "Петровичем"),
    ("Олегівна", "F", "gen", "Олегівни"),
])
def test_noun_cases(word, gender, case, expected):
    import names
    assert expected in names.noun(word, gender)[case]


def test_surname_cases():
    import names
    assert names.surname_cases("Ковальчинський", "M")["dat"] == ["Ковальчинському"]
    assert names.surname_cases("Терновська", "F")["gen"] == ["Терновської"]
    assert names.surname_cases("Шевченко", "M")["gen"] == ["Шевченка"]
    assert names.surname_cases("Петришин", "M")["ins"] == ["Петришином"]
    assert names.surname_cases("Ковальчук", "F")["dat"] == ["Ковальчук"]


def test_forms_include_orders_and_initials():
    import names
    f = names.forms("Тарас", "Петрович", "Ковальчинський", "M")
    assert {"Ковальчинського Тараса Петровича", "Тараса Петровича Ковальчинського",
            "Т. П.", "Т.П.", "Ковальчинський Т. П.", "Тарасику", "Тарас Петрович"} <= f


def test_side_forms():
    import names
    f = names.side_forms("Остап Романович Вигаданий")
    assert {"Вигаданого", "Остапа", "Романовичем"} <= f


def test_every_person_has_forms(population):
    import names
    for p in population[0]:
        f = names.forms(p["first_name"], p["patronymic"], p["surname"], p["gender"],
                        p["surname_type"])
        assert p["surname"] in f and p["first_name"] in f
