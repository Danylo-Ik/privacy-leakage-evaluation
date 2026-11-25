import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_understanding"))

import seed_tools as st  # noqa: E402
import review  # noqa: E402


def fake_docs():
    docs = []
    for g in ("court", "news", "forum"):
        for i in range(10):
            docs.append({"doc_id": f"{g}{i}", "genre": g})
    return docs


def test_pick_is_stratified_and_has_retries():
    docs = fake_docs()
    chosen = review.pick(docs, retried={"court3", "news5"})
    genres = [i.rstrip("0123456789") for i in chosen]
    assert len(chosen) == 20
    assert genres.count("court") == 7 and genres.count("news") == 7 and genres.count("forum") == 6
    assert {"court3", "news5"} <= set(chosen)
    assert chosen == review.pick(docs, retried={"court3", "news5"})


def test_assign_overlap_and_balance():
    docs = fake_docs()
    chosen = review.pick(docs, retried=set())
    genres = {d["doc_id"]: d["genre"] for d in docs}
    sheets = review.assign(chosen, genres)
    both = set(sheets["A"]) & set(sheets["B"])
    assert len(sheets["A"]) == len(sheets["B"]) == 12
    assert len(both) == 4
    assert set(sheets["A"]) | set(sheets["B"]) == set(chosen)


def test_tagged_text_brackets_every_span():
    text, spans = st.parse_tagged("Позов [[Ковальчинського|PERSON|DI|E1|gen|surname]] з "
                                  "[[Вербівки|LOC|QI|E2|gen|-|settlement]].")
    out = review.tagged_text({"text": text, "spans": spans})
    assert "[Ковальчинського]⟨E1·PERSON·DI·gen·surname⟩" in out
    assert "[Вербівки]⟨E2·LOC·QI·gen·settlement→E1⟩" in out


def write_sheet(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=review.CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_summary(tmp_path):
    base = {"genre": "news", "spans": 10, "person_spans": 5, "missed_items": "", "boundary": 0,
            "category": 0, "entity": 0, "attr_owner": 0, "grammar": 0, "notes": ""}
    rows = [
        {**base, "reviewer": "A", "doc_id": "D1", "missed": 1, "case_wrong": 1,
         "extra_facts": "", "naturalness": 3},
        {**base, "reviewer": "B", "doc_id": "D1", "missed": 0, "case_wrong": 1,
         "extra_facts": "", "naturalness": 2},
        {**base, "reviewer": "B", "doc_id": "D2", "missed": 0, "case_wrong": 0,
         "extra_facts": "has a dog", "naturalness": 3},
        {**base, "reviewer": "A", "doc_id": "D3"},  # not reviewed yet
    ]
    write_sheet(tmp_path / "manual_check.csv", rows)
    s = review.summary(review.read_sheet(tmp_path / "manual_check.csv"))
    assert s["docs"] == 2
    assert s["docs_with_missed"] == 0.5
    assert s["missed_per_100_spans"] == 5
    assert s["case_label_accuracy"] == 0.9
    assert s["docs_with_extra_facts"] == 0.5
    assert s["overlap_docs"] == 1
    assert s["agreement"]["missed"] == 0 and s["agreement"]["case_wrong"] == 1


def test_fixes_add_edit_delete_drop():
    text, spans = st.parse_tagged("Свідок [[Іваненко|PERSON|DI|E1|nom|surname]] і Мар’янка прийшли. "
                                  "Мар’янка мовчала.")
    docs = [{"doc_id": "D1", "text": text, "spans": spans}, {"doc_id": "D2", "text": text, "spans": []}]
    s = spans[0]
    fixes = [
        {"doc_id": "D1", "op": "add", "text": "Мар’янка", "occurrence": 2, "category": "PERSON",
         "id_type": "DI", "entity_id": "E2", "case": "nom", "name_part": "diminutive"},
        {"doc_id": "D1", "op": "edit", "start": s["start"], "end": s["end"], "set": {"case": "gen"}},
        {"doc_id": "D2", "op": "drop"},
    ]
    out = review.apply_fixes(docs, fixes)
    assert [d["doc_id"] for d in out] == ["D1"]
    new = out[0]["spans"]
    assert new[0]["case"] == "gen"
    added = new[1]
    assert text[added["start"]:added["end"]] == "Мар’янка" and added["start"] > text.index(".")
    assert added["owner"] == "E2" and added["edrsr_type"] == "ОСОБА"
    assert docs[0]["spans"][0]["case"] == "nom"  # input untouched
    out = review.apply_fixes(out, [{"doc_id": "D1", "op": "delete", "start": added["start"],
                                    "end": added["end"]}])
    assert len(out[0]["spans"]) == 1


def test_add_by_offset_gets_a_new_entity():
    text, spans = st.parse_tagged("Мій чоловік [[Олег|PERSON|DI|E1|nom|first]] вдома.")
    doc = {"doc_id": "D1", "text": text, "spans": spans}
    out = review.apply_fixes([doc], [{"doc_id": "D1", "op": "add", "start": 4, "text": "чоловік",
                                      "category": "DEM", "id_type": "QI", "attr": "family_status"}])
    s = out[0]["spans"][0]
    assert (s["text"], s["entity_id"], s["owner"]) == ("чоловік", "E2", "E1")
