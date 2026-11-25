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


@pytest.fixture(scope="module")
def plans(population):
    import fact_plan
    people, targets = population
    return fact_plan.make_plans(people, targets)


def test_plans_are_deterministic_and_json(population, plans):
    import json
    import fact_plan
    assert fact_plan.make_plans(*population) == plans
    json.dumps(plans, ensure_ascii=False)


def test_plans_cover_genres_and_qi_spread(plans):
    assert {p["genre"] for p in plans} == {"court", "news", "forum"}
    assert {p["n_qi"] for p in plans} == {2, 3, 4, 5, 6}


def test_plan_sample_per_genre(population):
    import fact_plan
    sample = fact_plan.make_plans(*population, per_genre=10)
    assert len(sample) == 30
    assert all(sum(p["genre"] == g for p in sample) == 10 for g in ("court", "news", "forum"))


def test_plan_facts_match_population(population, plans):
    by_id = {p["person_id"]: p for p in population[0]}
    for plan in plans:
        person = by_id[plan["person_id"]]
        attrs = {f["attr"] for f in plan["facts"]}
        assert "event" in attrs
        for f in plan["facts"]:
            if f["attr"] == "birth_year" and f["category"] == "DEM":
                assert f["value"] == plan["doc_year"] - int(person["birth_year"])
                assert f["text"].startswith(str(f["value"]))
            if f["attr"] == "birth_year" and f["category"] == "DATETIME":
                assert f["text"].startswith(str(person["birth_year"]))
            if f["attr"] == "children":
                assert f["value"] == int(person["children"])


def test_plan_name_requirements(plans):
    import names
    for plan in plans:
        t = plan["target"]
        found = names.forms(t["first_name"], t["patronymic"], t["surname"], t["gender"],
                            t["surname_type"])
        assert any(n["case"] not in ("nom", "voc") for n in plan["names"])
        for n in plan["names"]:
            assert n["text"] in found, (plan["doc_id"], n["text"])
        parts = [n["parts"] for n in plan["names"]]
        if plan["genre"] == "court":
            assert ["surname", "first", "patronymic"] in parts
            assert ["surname", "initials"] in parts
        if plan["genre"] == "news":
            assert ["first", "patronymic"] in parts


def test_side_characters_are_not_in_population(population, plans):
    known = {(p["first_name"], p["patronymic"], p["surname"]) for p in population[0]}
    for plan in plans:
        assert plan["side_characters"]
        for s in plan["side_characters"]:
            assert (s["first_name"], s["patronymic"], s["surname"]) not in known


def _d002_plan():
    def f(attr):
        return {"attr": attr, "category": "DEM", "id_type": "QI", "text": "", "value": None,
                "exact": False}
    return {"doc_id": "D002", "person_id": "P0002", "genre": "court", "doc_year": 2023,
            "target": {"first_name": "Тарас", "patronymic": "Петрович", "surname": "Ковальчинський",
                       "gender": "M", "surname_type": "skyi"},
            "n_qi": 6,
            "facts": [f(a) for a in ("event", "birth_year", "family_status", "children",
                                     "occupation", "settlement")],
            "names": [{"text": "Ковальчинського Тараса Петровича", "case": "gen",
                       "parts": ["surname", "first", "patronymic"]},
                      {"text": "Ковальчинський Т. П.", "case": "nom", "parts": ["surname", "initials"]}],
            "side_characters": [],
            "identifiers": [{"kind": "rnokpp", "category": "CODE", "owner": "E1",
                             "text": "3012345678"}]}


@pytest.fixture
def fake_llm(monkeypatch):
    import generate
    import llm
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://fake")
    calls = []

    def install(replies):
        def chat(messages, **kwargs):
            calls.append(messages)
            return replies[len(calls) - 1], {"completion": 10}, False
        monkeypatch.setattr(llm, "chat", chat)
        return calls
    return generate, install


def test_prompt_contains_plan(plans):
    import generate
    for plan in plans[:20]:
        user = generate.build_messages(plan)[1]["content"]
        for f in plan["facts"]:
            assert f["text"] in user
        for n in plan["names"]:
            assert n["text"] in user
        for s in plan["side_characters"]:
            assert s["mention"] in user
        assert "{" not in user.replace("{{", "")


def test_cache_key_changes_with_model_and_attempt():
    import llm
    msgs = [{"role": "user", "content": "привіт"}]
    params = {"temperature": 0.8}
    a = llm.cache_key("m1", msgs, params, {"attempt": 0})
    assert a == llm.cache_key("m1", msgs, params, {"attempt": 0})
    assert a != llm.cache_key("m2", msgs, params, {"attempt": 0})
    assert a != llm.cache_key("m1", msgs, params, {"attempt": 1})


def test_generate_accepts_good_reply(fake_llm):
    import seed_docs
    generate, install = fake_llm
    d002 = next(d for d in seed_docs.SEED_DOCS if d["doc_id"] == "D002")["tagged"]
    calls = install(["```\n" + d002 + "\n```"])
    doc, log = generate.generate_one(_d002_plan(), st.make_population())
    assert doc is not None and len(calls) == 1
    assert log[0]["ok"] and log[0]["model"] == "fake-model"


def test_generate_retries_with_errors_then_drops(fake_llm):
    generate, install = fake_llm
    broken = "Позов [[Тараса|PERSON|DI|E1|gen|first] задоволено."
    calls = install([broken] * 3)
    doc, log = generate.generate_one(_d002_plan(), st.make_population())
    assert doc is None and len(log) == 3 and not any(e["ok"] for e in log)
    repair = calls[1][-1]["content"]
    assert "leftover tag" in repair and "attr=event" in repair


def test_generate_fixes_on_second_try(fake_llm):
    import seed_docs
    generate, install = fake_llm
    d002 = next(d for d in seed_docs.SEED_DOCS if d["doc_id"] == "D002")["tagged"]
    install(["нічого", d002])
    doc, log = generate.generate_one(_d002_plan(), st.make_population())
    assert doc is not None and [e["ok"] for e in log] == [False, True]


def test_pick_balances_genres(plans):
    import generate
    picked = generate.pick(plans, limit=10)
    assert [p["genre"] for p in picked].count("court") == 4
    assert len(picked) == 10


def test_case_number_year_matches_event(plans):
    for plan in plans:
        year = next(f["value"] for f in plan["facts"]
                    if f["attr"] == "event" and f["category"] == "DATETIME")
        for i in plan["identifiers"]:
            if i["kind"] == "case_number":
                assert i["text"].endswith(f"/{year % 100:02d}")


def _seed_doc(doc_id, edit=None):
    import seed_docs
    meta = next(d for d in seed_docs.SEED_DOCS if d["doc_id"] == doc_id)
    tagged = meta["tagged"]
    if edit:
        old, new = edit
        assert old in tagged
        tagged = tagged.replace(old, new, 1)
    text, spans = st.parse_tagged(tagged)
    return {"doc_id": doc_id, "person_id": meta["person_id"], "target_entity_id": "E1",
            "genre": meta["genre"], "doc_year": meta["doc_year"], "text": text, "spans": spans}


def test_checks_pass_on_seed_docs():
    import checks
    pop = st.make_population()
    for doc_id in ("D001", "D002", "D003", "D004", "D005"):
        assert checks.check_doc(_seed_doc(doc_id), pop) == [], doc_id


@pytest.mark.parametrize("doc_id,edit,expected", [
    ("D001", ("називає [[Оксану|PERSON|DI|E1|acc|first]]", "називає Оксану"), "untagged name of E1"),
    ("D002", ("[[Т. П.|PERSON|DI|E1|-|initials]]", "Т. П."), "untagged name of E1"),
    ("D002", ("позов не визнала.", "позов не визнала. Сидорчук пішла."), "untagged name of side"),
    ("D001", ("[[34-річна|", "[[40-річна|"), "age «40-річна»"),
    ("D002", ("[[1978 року", "[[1980 року"), "birth year"),
    ("D001", ("[[виховує трьох дітей|", "[[виховує двох дітей|"), "says 2 children"),
    ("D003", ("Заслухавши пояснення [[Задорожненко|PERSON|DI|E1|gen|surname]] "
              "[[І. О.|PERSON|DI|E1|-|initials]], суд", "Суд"), "mentioned 2 times"),
])
def test_checks_catch_broken_docs(doc_id, edit, expected):
    import checks
    errors = checks.check_doc(_seed_doc(doc_id, edit), st.make_population())
    assert any(expected in e for e in errors), errors


def test_checks_use_the_plan():
    import checks
    plan = _d002_plan()
    pop = st.make_population()
    assert checks.check_doc(_seed_doc("D002"), pop, plan) == []
    plan["facts"].append(dict(plan["facts"][0], attr="oblast"))
    plan["names"].append({"text": "Тарасом", "case": "ins", "parts": ["first"]})
    plan["side_characters"].append({"role": "колега", "gender": "F", "first_name": "Олена",
                                    "patronymic": "Іванівна", "surname": "Мельник",
                                    "mention": "Олена Мельник"})
    errors = checks.check_doc(_seed_doc("D002"), pop, plan)
    assert any("attr=oblast" in e for e in errors)
    assert any("«Тарасом»" in e for e in errors)


def test_check_dir_writes_report(tmp_path):
    import checks
    st.build(tmp_path)
    report = checks.check_dir(tmp_path)
    assert len(report) == 5 and all(r["ok"] for r in report)
    assert (tmp_path / "check_report.jsonl").exists()


def test_fold_system_moves_system_into_user():
    import llm
    msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "task"},
            {"role": "assistant", "content": "draft"}, {"role": "user", "content": "fix"}]
    out = llm.fold_system(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[0]["content"] == "rules\n\ntask" and msgs[1]["content"] == "task"


def test_strip_thoughts():
    import llm
    assert llm.strip_thoughts("<thought>міркую\nдалі</thought>Зараз весна.") == "Зараз весна."
    assert llm.strip_thoughts("<thought>не закінчив") == ""
    assert llm.strip_thoughts("Просто текст") == "Просто текст"


def test_required_oblique_form_is_unambiguous(plans):
    import names
    for plan in plans:
        t = plan["target"]
        table = names.name_forms(t["first_name"], t["patronymic"], t["surname"], t["gender"],
                                 t["surname_type"])
        for n in plan["names"]:
            if n["parts"] in (["first"], ["surname"]) and n["case"] not in ("nom", "voc"):
                part = n["parts"][0]
                others = [w for c in names.CASES if c != n["case"] for w in table[(part, c)]]
                assert n["text"] not in others, (plan["doc_id"], n["text"])


def test_place_attr_must_name_the_place():
    import checks
    doc = _seed_doc("D002", ("[[Київський районний суд м. Харкова|", "[[Шепкиївський районний суд|"))
    errors = checks.check_doc(doc, st.make_population())
    assert any("does not name Харків" in e for e in errors)


def test_merged_name_parts_fail():
    import checks
    doc = _seed_doc("D001", ("[[Оксана|PERSON|DI|E1|nom|first]] [[Миколаївна|PERSON|DI|E1|nom|patronymic]]",
                             "[[Оксана Миколаївна|PERSON|DI|E1|nom|first]]"))
    errors = checks.check_doc(doc, st.make_population())
    assert any("several name parts" in e for e in errors)
