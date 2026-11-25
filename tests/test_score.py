import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import prompts as pr  # noqa: E402
import score as sc  # noqa: E402
import uniqueness as uq  # noqa: E402

SAMPLE = ROOT / "data" / "sample"
MODEL = "fake"


def reid_row(doc_id, cond, rank, n=10, design="balanced", model=MODEL):
    return {"doc_id": doc_id, "system_or_condition": cond, "design": design, "n": n, "model": model,
            "prompt_version": pr.REID_VERSION, "target_rank": rank, "parse_ok": True}


def attr_row(doc_id, cond, values):
    return {"doc_id": doc_id, "system_or_condition": cond, "design": None, "n": None, "model": MODEL,
            "prompt_version": pr.ATTR_VERSION, "values": values, "parse_ok": True}


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture(autouse=True)
def few_draws(monkeypatch):
    monkeypatch.setattr(sc, "BOOTSTRAP", 200)


@pytest.fixture(scope="module")
def empty(tmp_path_factory):
    return sc.load(SAMPLE, tmp_path_factory.mktemp("none"))


@pytest.fixture
def attacked(tmp_path, empty):
    """rule: always first; gold_full: first in every second document, else not found;
    no document: never found. Attributes: gender right, oblast unknown, occupation wrong."""
    docs = list(empty["gold"])
    write(tmp_path / "reid.jsonl",
          [reid_row(d, "rule", 1) for d in docs]
          + [reid_row(d, "gold_full", 1 if i % 2 else None) for i, d in enumerate(docs)])
    write(tmp_path / "nodoc.jsonl", [reid_row(d, None, 3) for d in docs])
    rows = []
    for d in docs:
        truth = pr.true_attributes(empty["people"][empty["gold"][d]["person_id"]])
        wrong = "юрист" if truth["occupation"] != "юрист" else "кухар"
        rows.append(attr_row(d, "gold_full", {**truth, "oblast": "unknown", "occupation": wrong}))
    write(tmp_path / "attr.jsonl", rows)
    return sc.load(SAMPLE, tmp_path)


def find(rows, **want):
    return next(r for r in rows if all(r[k] == v for k, v in want.items()))


# ---------- statistics ----------

def test_ratio_ci_on_known_cases():
    assert sc.mean_ci([1] * 20) == (1, 1, 1)
    assert sc.mean_ci([0] * 20) == (0, 0, 0)
    assert sc.mean_ci([]) == (None, None, None)
    mean, low, high = sc.mean_ci([0, 1] * 50)
    assert mean == 0.5 and 0.33 < low < 0.46 and 0.54 < high < 0.67
    assert sc.mean_ci([0, 1] * 50) == (mean, low, high)  # fixed seed


def test_ratio_ci_counts_documents_not_rows():
    # the same rows from many documents and from two documents: equal mean, wider interval
    many = sc.ratio_ci([(1, 1)] * 50 + [(0, 1)] * 50)
    few = sc.ratio_ci([(50, 50), (0, 50)])
    assert many[0] == few[0] == 0.5
    assert few[2] - few[1] > 2 * (many[2] - many[1])


# ---------- protection ----------

def by_condition(data):
    return sc.group_by(sc.make_by_doc(data), "system_or_condition")


def test_protection_of_the_gold_conditions(empty):
    rows = by_condition(empty)
    for r in rows["gold_full"]:
        assert r["mentions_closed"] == r["mentions"] and r["target_closed"]
        assert r["di_closed"] == r["di_spans"] and r["qi_closed"] == r["qi_spans"]
    for r in rows["gold_di_only"]:
        assert r["target_closed"] and r["di_closed"] == r["di_spans"] and r["qi_closed"] == 0
    for r in rows["gold_miss_one_oblique"]:
        assert not r["target_closed"] and r["mentions_closed"] == r["mentions"] - 1
        assert r["qi_closed"] == r["qi_spans"]


@pytest.mark.parametrize("end,closed", [(6, 0), (9, 0), (10, 1), (13, 1)])
def test_open_mention_boundary(end, closed):
    # "Бережна" is 6-13: three of its seven letters masked leave it open, four close it
    text = "Марія Бережна сказала."
    doc = {"text": text, "target_entity_id": "E1", "spans": [
        {"start": 0, "end": 5, "category": "PERSON", "id_type": "DI", "entity_id": "E1"},
        {"start": 6, "end": 13, "category": "PERSON", "id_type": "DI", "entity_id": "E1"}]}
    out = sc.protection(doc, {"masked_spans": [{"start": 0, "end": 5}, {"start": 6, "end": end}]})
    assert out["mentions"] == 1 and out["persons"] == 1
    assert out["target_closed"] == out["mentions_closed"] == closed


def test_k_matches_uniqueness(empty):
    want = {(r["doc_id"], r["system_or_condition"]): r["k"] for r in
            uq.score(empty["population"], list(empty["gold"].values()), empty["masked"])}
    for r in sc.make_by_doc(empty):
        assert r["k"] == want[r["doc_id"], r["system_or_condition"]]


def test_failed_llm_rows_are_left_out(tmp_path, monkeypatch, empty):
    rows = [dict(r) for r in empty["masked"]]
    bad = next(r for r in rows if r["system_or_condition"] == "llm")
    bad["llm_failed"] = True
    real = sc.st.read_jsonl
    monkeypatch.setattr(sc.st, "read_jsonl",
                        lambda p: rows if Path(p).name == "masked_docs.jsonl" else real(p))
    assert len(sc.load(SAMPLE, tmp_path)["masked"]) == len(rows) - 1


# ---------- attacks ----------

def test_reid_rates_and_differences(attacked):
    table = sc.score(attacked)["reid"]
    rule = find(table, condition="rule", n=10)
    assert (rule["top1"], rule["top1_low"], rule["top1_high"], rule["top5"]) == (1, 1, 1, 1)
    full = find(table, condition="gold_full", n=10)
    assert full["top1"] == full["top5"] == 0.5
    base = find(table, condition="no_document", n=10)
    assert base["top1"] == 0 and base["top5"] == 1
    assert rule["top1_minus_no_document"] == 1 and rule["top1_minus_gold_full"] == 0.5
    assert full["top1_minus_gold_full"] == 0
    assert rule["chance"] == 0.1 and 0.2 < rule["rule_without_document"] < 0.35
    assert not any(r["n"] == 100 for r in table)


def test_paired_difference_uses_the_same_documents(attacked):
    half = list(attacked["gold"])[:10]
    attacked["attacks"]["nodoc"] = [reid_row(d, None, 1) for d in half]
    rule = find(sc.score(attacked)["reid"], condition="rule", n=10)
    assert rule["docs"] == 30 and rule["top1_minus_no_document"] == 0


def test_unchanged_documents_can_be_excluded(attacked):
    same = {r["doc_id"] for r in attacked["masked"]
            if r["system_or_condition"] == "gold_drop_p05" and r["n_unmasked_gold"] == 0}
    assert same
    attacked["attacks"]["reid"] = [reid_row(d, "gold_drop_p05", None if d in same else 1)
                                   for d in attacked["gold"]]
    r = find(sc.score(attacked)["reid"], condition="gold_drop_p05")
    assert r["top1"] < 1 and r["top1_changed"] == 1 and r["docs_changed"] == 30 - len(same)


def test_attributes(attacked):
    table = sc.score(attacked)["attributes"]
    gender = find(table, condition="gold_full", attribute="gender")
    assert gender["accuracy"] == 1 and gender["answered"] == 1 and gender["majority"] < 0.7
    oblast = find(table, condition="gold_full", attribute="oblast")
    assert oblast["accuracy"] == 0 and oblast["answered"] == 0 and oblast["accuracy_answered"] is None
    job = find(table, condition="gold_full", attribute="occupation")
    assert job["accuracy"] == 0 and job["answered"] == 1
    assert job["docs_exposed"] == 0 and job["docs_hidden"] == 30  # gold_full hides every span


def test_gender_by_genre(attacked):
    row = find(sc.score(attacked)["gender"], condition="gold_full")
    assert row["docs_all"] == 30 and row["docs_court"] == row["docs_news"] == 10
    assert row["all"] == row["court"] == 1


def test_buckets_use_fully_masked_names_only(attacked):
    table = sc.score(attacked)["k_buckets"]
    by_doc = sc.make_by_doc(attacked)
    closed = [r for r in by_doc if r["target_closed"] and r["rank_balanced_10"] is not None]
    assert sum(r["rows"] for r in table if r["n"] == 10) == len(closed)
    assert [r["k"] for r in table if r["n"] == 10] == ["1", "2-5", "6-50", "51+"]
    assert find(table, n=10, k="51+")["docs"] == 30


def test_rank_columns_tell_a_miss_from_a_missing_run(attacked):
    rows = by_condition(attacked)
    assert {r["rank_balanced_10"] for r in rows["gold_full"]} == {0, 1}
    assert {r["rank_balanced_10"] for r in rows["spacy"]} == {None}


def test_coverage_reports_missing_rows(attacked):
    text = "\n".join(sc.coverage(attacked))
    assert "reid balanced N=10: 60/360" in text and "reid balanced N=100: 0/360" in text
    assert "nodoc balanced N=10: 30/30" in text and "attr: 30/360" in text


def test_several_models_need_a_choice(tmp_path, empty):
    d = next(iter(empty["gold"]))
    write(tmp_path / "reid.jsonl", [reid_row(d, "rule", 1), reid_row(d, "rule", 2, model="other")])
    with pytest.raises(ValueError):
        sc.load_attacks(tmp_path)
    assert len(sc.load_attacks(tmp_path, "other")["reid"]) == 1


def test_rows_of_an_old_prompt_are_ignored(tmp_path, empty):
    d = next(iter(empty["gold"]))
    write(tmp_path / "reid.jsonl", [dict(reid_row(d, "rule", 1), prompt_version="attack_reid_v0")])
    assert sc.load_attacks(tmp_path)["reid"] == []


def test_unmasked_text_is_scored_as_a_condition(attacked):
    docs = list(attacked["gold"])
    attacked["attacks"]["reid"] += [reid_row(d, "unmasked", 1) for d in docs]
    attacked["masked"] += [{"doc_id": d, "system_or_condition": "unmasked", "masked_spans": []}
                           for d in docs]
    row = find(sc.score(attacked)["summary"], condition="unmasked")
    assert row["mention_recall"] == 0 and row["pct_k1"] == 1 and row["top1_n10"] == 1


def test_main_writes_every_table(attacked, tmp_path, capsys):
    attack_dir = tmp_path  # written by the fixture
    sc.main([str(SAMPLE), "--attacks", str(attack_dir), "--out", str(tmp_path / "res")])
    names = {p.name for p in (tmp_path / "res").iterdir()}
    assert names == {"by_doc.csv", "summary.csv", "reid.csv", "attributes.csv", "gender.csv",
                     "k_buckets.csv"}
    with open(tmp_path / "res" / "by_doc.csv", encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == 360
    assert "no_document" in capsys.readouterr().out


def test_main_works_before_any_attack(tmp_path):
    tables = sc.main([str(SAMPLE), "--attacks", str(tmp_path / "none"), "--out", str(tmp_path / "res")])
    assert len(tables["summary"]) == 12 and tables["reid"] == []
