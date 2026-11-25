import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import candidates as cd  # noqa: E402
import prompts as pr  # noqa: E402
import seed_tools as st  # noqa: E402

SAMPLE = ROOT / "data" / "sample"
RANKING = ["C007", "C001", "C002", "C003", "C004"]


@pytest.fixture(scope="module")
def population():
    return st.load_population(SAMPLE / "population.csv")


@pytest.fixture(scope="module")
def lists(population):
    return pr.closed_lists(population)


def reply(**kw):
    return json.dumps({"clues": "село і професія", "ranking": RANKING, **kw}, ensure_ascii=False)


# ---------- messages ----------

def test_reid_prompt_holds_every_profile_and_the_document(population):
    people = population[:10]
    system, user = pr.reid_messages(people, "Текст про ОСОБА_1.")
    assert (system["role"], user["role"]) == ("system", "user")
    for label, p in zip(cd.labels(10), people):
        assert f"{label}. {cd.profile(p)}" in user["content"]
    assert "Текст про ОСОБА_1." in user["content"]


def test_no_document_prompt_differs_only_in_the_tail(population):
    people = population[:10]
    with_doc, without = pr.reid_messages(people, "Текст."), pr.reid_messages(people)
    assert with_doc[0] == without[0]
    head = with_doc[1]["content"].split("\n\nDocument:")[0]
    assert without[1]["content"].startswith(head)
    assert "<<<" not in without[1]["content"]


def test_prompts_of_one_list_share_everything_before_the_document(population):
    a, b = (pr.reid_messages(population[:100], t)[1]["content"] for t in ("Перший.", "Другий."))
    start = a.index("Перший.")
    assert a[:start] == b[:start]


def test_no_placeholder_or_person_id_is_left_in_the_prompts(population, lists):
    texts = [m["content"] for m in pr.reid_messages(population[:100], "Текст.")
             + pr.reid_messages(population[:100]) + pr.attr_messages("Текст.", lists)]
    for text in texts:
        for name in ("{candidates}", "{document}", "{oblasts}", "{occupations}"):
            assert name not in text
        assert not any(p["person_id"] in text for p in population[:100])


def test_attr_prompt_lists_every_allowed_value(lists):
    system, user = pr.attr_messages("Текст.", lists)
    for value in lists["oblast"] + lists["occupation"]:
        assert value in system["content"]
    assert len(lists["oblast"]) == 7 and len(lists["occupation"]) == 22
    assert "Текст." in user["content"]


def test_true_attributes_are_allowed_values(population, lists):
    for p in population:
        t = pr.true_attributes(p)
        assert t["gender"] in ("F", "M") and t["birth_decade"] in pr.DECADES
        assert t["oblast"] in lists["oblast"] and t["occupation"] in lists["occupation"]


# ---------- ranking replies ----------

@pytest.mark.parametrize("text", [
    reply(),
    "```json\n" + reply() + "\n```",
    "Думаю, це вчителька.\n" + reply() + "\nГотово.",
    '{"note": {"a": 1}} ' + reply(),
    reply(ranking=["C000"] * 5) + "\n" + reply(),  # the last object wins
    reply(ranking=["c7", "C1", "С002", "с3", 4]),  # case, zeros, Cyrillic С, numbers
    reply(ranking=["C007. Бережна Марія", "C001.", " C002 ", "C003", "C004"]),
    reply(ranking=RANKING + ["C005", "C006"]),  # longer than asked
])
def test_usable_rankings(text):
    out = pr.parse_ranking(text, 10)
    assert out["ranking"] == RANKING
    assert out["errors"] == []


@pytest.mark.parametrize("text", ["", None, "Не знаю.", "{}", '{"ranking": "C001"}',
                                  '{"ranking": ["C001", "C002"', '["C001", "C002"]',
                                  "Sorry, I cannot identify people."])
def test_unreadable_rankings(text):
    out = pr.parse_ranking(text, 10)
    assert out["ranking"] == [] and out["errors"]


def test_invented_label_keeps_its_place():
    out = pr.parse_ranking(reply(ranking=["C011", "C001", "C002", "C003", "C004"]), 10)
    assert out["ranking"] == [None, "C001", "C002", "C003", "C004"]
    assert len(out["errors"]) == 1


@pytest.mark.parametrize("bad", ["C000", "C1000", "Бережна", "", None, True, {"a": 1}, 0, -1])
def test_labels_that_match_nothing(bad):
    assert pr.parse_label(bad, 10) is None


def test_repeated_and_missing_labels_are_errors():
    out = pr.parse_ranking(reply(ranking=["C001", "C001", "C002"]), 10)
    assert out["ranking"] == ["C001", "C002"]
    assert len(out["errors"]) == 2


def test_every_label_of_a_list_of_100_round_trips():
    for i, label in enumerate(cd.labels(100)):
        assert pr.parse_label(label, 100) == i + 1


# ---------- attribute replies ----------

@pytest.mark.parametrize("attr,value,expected", [
    ("gender", "F", "F"), ("gender", "жінка", "F"), ("gender", "Male", "M"), ("gender", "X", None),
    ("birth_decade", 1970, 1970), ("birth_decade", "1970s", 1970), ("birth_decade", "1974", 1970),
    ("birth_decade", "1950", None), ("birth_decade", "70-ті", None),
    ("oblast", "Полтавська", "Полтавська"), ("oblast", "полтавська область", "Полтавська"),
    ("oblast", "Одеська обл.", "Одеська"), ("oblast", "Київська", None),
    ("occupation", "Вчитель хімії", "вчитель хімії"), ("occupation", "бухгалтерка", "бухгалтер"),
    ("occupation", "медична  сестра", "медична сестра"), ("occupation", "суддя", None),
    ("gender", "unknown", "unknown"), ("oblast", "невідомо", "unknown"),
    ("occupation", None, "unknown"), ("birth_decade", "", "unknown"),
])
def test_attribute_values(lists, attr, value, expected):
    assert pr.parse_value(attr, value, lists) == expected


def test_attribute_reply(lists):
    text = ('Ось відповідь: {"clues": "позивачка", "gender": "F", "birth_decade": 1970, '
            '"oblast": "Харківська", "occupation": "unknown"}')
    out = pr.parse_attributes(text, lists)
    assert out["values"] == {"gender": "F", "birth_decade": 1970, "oblast": "Харківська",
                             "occupation": "unknown"}
    assert out["clues"] == "позивачка" and out["errors"] == []


def test_broken_attribute_replies(lists):
    for text in ("", None, "F, 1970", '{"oblast": "Одеська"}'):
        out = pr.parse_attributes(text, lists)
        assert out["errors"] and set(out["values"].values()) == {None}
    out = pr.parse_attributes('{"gender": "F", "oblast": "Київська", "occupation": "кухар"}', lists)
    assert out["values"] == {"gender": "F", "birth_decade": None, "oblast": None,
                             "occupation": "кухар"}
    assert len(out["errors"]) == 2


def test_every_true_value_parses_back(population, lists):
    for p in population:
        t = pr.true_attributes(p)
        assert {a: pr.parse_value(a, t[a], lists) for a in pr.ATTRIBUTES} == t


def test_preview_prints_the_messages(capsys):
    pr.main([str(SAMPLE), "D102", "--condition", "rule"])
    out = capsys.readouterr().out
    assert "=== system" in out and "C010." in out and "ОСОБА_2" in out
