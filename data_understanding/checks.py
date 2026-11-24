"""Automatic checks on gold documents.

Usage: python data_understanding/checks.py [DIR]   (default data/seed)
Reads gold_docs.jsonl and population.csv (and fact_plans.jsonl if it exists), prints
PASS/FAIL per document and writes check_report.jsonl. Exits with 1 if any document fails.

1. validator: offsets, fields, leftover tags, owners
2. plan coverage: every planned fact, identifier and name form is in the document
3. untagged names: a form of the target's name, or a side character's name, outside a span
4. consistency: age or birth year, number of children, and settlement/oblast spans match the population
5. sanity: length for the genre, at least 3 mentions of the target
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import seed_tools as st  # noqa: E402
import names  # noqa: E402

WORDS = {"court": (80, 800), "news": (50, 600), "forum": (50, 600)}
MIN_MENTIONS = 3
NUMBER_WORDS = {"двох": 2, "двоє": 2, "двома": 2, "трьох": 3, "троє": 3, "трьома": 3,
                "чотирьох": 4, "четверо": 4, "п’ятьох": 5, "п’ятеро": 5}
ONE_CHILD = ("син", "доньк", "дочк", "дочер", "дитин")


def find_word(text, form):
    """Start offsets of `form` as a whole word or phrase."""
    pattern = r"(?<![\w’])" + re.escape(form) + r"(?![\w’])"
    return [m.start() for m in re.finditer(pattern, text)]


def covered(text, spans, start, end):
    """True if every non-space character in [start, end) is inside some span."""
    return all(any(s["start"] <= i < s["end"] for s in spans)
               for i in range(start, end) if not text[i].isspace())


def untagged_names(doc, person, plan=None):
    text, spans = doc["text"], doc["spans"]
    target = {w for w in names.forms(person["first_name"], person["patronymic"], person["surname"],
                                     person["gender"], person.get("surname_type"))
              if " " not in w or "." in w}
    others = {s["text"] for s in spans if s["category"] == "PERSON" and s["entity_id"] != "E1"
              and s["name_part"] != "initials"}
    if plan:
        for c in plan.get("side_characters", []):
            full = f"{c['first_name']} {c['patronymic']} {c['surname']}"
            others |= names.side_forms(full, c["gender"])
    errors = []
    for label, forms in (("E1", target), ("side character", others)):
        for form in sorted(forms, key=len, reverse=True):
            for start in find_word(text, form):
                if not covered(text, spans, start, start + len(form)):
                    errors.append(f"untagged name of {label}: «{form}» at {start}")
    return errors


def age_or_year(span):
    """Return ('year', 1978), ('age', 34) or None."""
    year = re.search(r"\b(19|20)\d{2}\b", span["text"])
    if year:
        return "year", int(year.group(0))
    age = re.search(r"\d{1,3}", span["text"])
    return ("age", int(age.group(0))) if age else None


def children_count(text):
    t = text.lower()
    if "не має дітей" in t or "бездітн" in t or "без дітей" in t:
        return 0
    digits = re.search(r"\d+", t)
    if digits:
        return int(digits.group(0))
    for word, n in NUMBER_WORDS.items():
        if word in t:
            return n
    if any(stem in t for stem in ONE_CHILD):
        return 1
    return None


def consistency(doc, person):
    errors = []
    born = int(person["birth_year"])
    for s in doc["spans"]:
        if s.get("owner") != "E1":
            continue
        if s["attr"] == "birth_year":
            got = age_or_year(s)
            if got is None:
                errors.append(f"cannot read an age or year from «{s['text']}»")
            elif got[0] == "year" and got[1] != born:
                errors.append(f"birth year «{s['text']}» but the person was born in {born}")
            elif got[0] == "age" and abs(doc["doc_year"] - born - got[1]) > 1:
                errors.append(f"age «{s['text']}» but the person is {doc['doc_year'] - born} "
                              f"in {doc['doc_year']}")
        if s["attr"] in ("settlement", "oblast"):
            stem = st.normalize(person[s["attr"]]).lower()[:4]
            if stem not in s["text"].lower():
                errors.append(f"«{s['text']}» is tagged attr={s['attr']} but does not name "
                              f"{person[s['attr']]}")
        if s["attr"] == "children":
            n = children_count(s["text"])
            if n is None:
                errors.append(f"cannot read the number of children from «{s['text']}»")
            elif n != int(person["children"]):
                errors.append(f"«{s['text']}» says {n} children, the person has {person['children']}")
    return errors


def plan_coverage(doc, plan):
    errors = []
    mine = [s for s in doc["spans"] if s.get("owner") == "E1"]
    for attr in sorted({f["attr"] for f in plan["facts"]}):
        if not any(s["attr"] == attr for s in mine):
            errors.append(f"no tagged span with attr={attr} about E1")
    for f in plan["facts"]:
        if f["exact"] and f["category"] == "LOC":
            place = st.normalize(f["value"])
            if not any(s["category"] == "LOC" and place in s["text"] for s in mine):
                errors.append(f"address with «{f['value']}» is missing")
    tagged = {s["text"] for s in doc["spans"]}
    for i in plan["identifiers"]:
        if st.normalize(i["text"]) not in tagged:
            errors.append(f"identifier «{i['text']}» is missing or not tagged as one span")
    for n in plan["names"]:
        if not find_word(doc["text"], st.normalize(n["text"])):
            errors.append(f"required name form «{n['text']}» does not appear")
    return errors


def sanity(doc):
    errors = []
    for s in doc["spans"]:
        if s["category"] == "PERSON" and s["name_part"] != "initials" and " " in s["text"].strip():
            errors.append(f"«{s['text']}» holds several name parts in one tag; tag the first name, "
                          f"patronymic and surname separately")
    lo, hi = WORDS.get(doc["genre"], (50, 800))
    n = len(doc["text"].split())
    if not lo <= n <= hi:
        errors.append(f"{n} words, expected {lo}–{hi} for {doc['genre']}")
    k = len(st.mentions(doc["text"], doc["spans"], doc["target_entity_id"]))
    if k < MIN_MENTIONS:
        errors.append(f"the target is mentioned {k} times, expected at least {MIN_MENTIONS}")
    return errors


def check_doc(doc, population, plan=None):
    by_id = population if isinstance(population, dict) else {p["person_id"]: p for p in population}
    errors = st.validate_gold([doc], list(by_id.values()))
    person = by_id.get(doc["person_id"])
    if person is None:
        return errors
    if plan:
        errors += plan_coverage(doc, plan)
    errors += untagged_names(doc, person, plan)
    errors += consistency(doc, person)
    errors += sanity(doc)
    return errors


def check_dir(data_dir):
    data_dir = Path(data_dir)
    population = {p["person_id"]: p for p in st.load_population(data_dir / "population.csv")}
    plans = {}
    if (data_dir / "fact_plans.jsonl").exists():
        plans = {p["doc_id"]: p for p in st.read_jsonl(data_dir / "fact_plans.jsonl")}
    report = []
    for doc in st.read_jsonl(data_dir / "gold_docs.jsonl"):
        errors = check_doc(doc, population, plans.get(doc["doc_id"]))
        report.append({"doc_id": doc["doc_id"], "genre": doc["genre"], "ok": not errors,
                       "errors": errors})
    with open(data_dir / "check_report.jsonl", "w", encoding="utf-8") as f:
        for r in report:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return report


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else st.SEED_DIR
    report = check_dir(d)
    for r in report:
        print(f"{r['doc_id']} {'PASS' if r['ok'] else 'FAIL'}")
        for e in r["errors"]:
            print(f"    {e}")
    passed = sum(r["ok"] for r in report)
    print(f"{passed}/{len(report)} passed")
    sys.exit(0 if passed == len(report) else 1)
