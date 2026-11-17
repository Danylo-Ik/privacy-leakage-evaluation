"""Tag parser, validators and gold masking.

Usage:
    python seed_tools.py build [DIR]
    python seed_tools.py validate [DIR]
"""
import csv
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SEED_DIR = HERE / "data" / "seed"

CATEGORIES = {"PERSON", "CODE", "LOC", "ORG", "DEM", "DATETIME", "QUANTITY", "MISC"}
ID_TYPES = {"DI", "QI"}
CASES = {"nom", "gen", "dat", "acc", "ins", "loc", "voc", None}
NAME_PARTS = {"first", "patronymic", "surname", "initials", "diminutive", None}
ATTRS = {"gender", "birth_year", "oblast", "settlement", "settlement_type", "occupation",
         "family_status", "children", "event", None}
POP_COLUMNS = ["person_id", "first_name", "patronymic", "surname", "gender", "birth_year",
               "oblast", "settlement", "settlement_type", "occupation", "family_status",
               "children", "event"]
PLACEHOLDER = {"PERSON": "ОСОБА", "CODE": "КОД", "LOC": "МІСЦЕ", "ORG": "ОРГАНІЗАЦІЯ",
               "DEM": "ІНФОРМАЦІЯ", "DATETIME": "ДАТА", "QUANTITY": "ЧИСЛО", "MISC": "ІНФОРМАЦІЯ"}

EDRSR_TYPES = {"ОСОБА", "АДРЕСА", "НОМЕР", "ІНФОРМАЦІЯ", None}
TARGET = "E1"

# [[surface|CAT|TYPE|ENT|case|part|attr|owner]], "-" = null
TAG = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
N_FIELDS = 7
APOSTROPHES = str.maketrans({"'": "’", "ʼ": "’", "`": "’"})


class TagError(ValueError):
    pass


def normalize(text: str) -> str:
    """Normalize apostrophes. Length is unchanged."""
    return text.translate(APOSTROPHES)


CASE_NUMBER = re.compile(r"^(№\s*)?\d+[/-]\d+([/-]\d+)*$")


def edrsr_type(span: dict):
    """ЄДРСР placeholder type for a span, or None."""
    cat, text = span["category"], span["text"].strip()
    if cat == "PERSON":
        return "ОСОБА"
    if cat == "LOC" and span["id_type"] == "DI":
        return "АДРЕСА"
    if cat == "CODE":
        if CASE_NUMBER.match(text):
            return None  # case number
        if "@" in text or text.lower().startswith(("http", "www.")):
            return "ІНФОРМАЦІЯ"
        return "НОМЕР"
    if cat == "DATETIME" and span["attr"] == "birth_year":
        return "ІНФОРМАЦІЯ"
    return None


def parse_tagged(tagged: str, target: str = TARGET):
    """Strip inline tags, return (text, spans)."""
    tagged = normalize(tagged)
    out, spans, pos = [], [], 0
    length = 0
    for m in TAG.finditer(tagged):
        before = tagged[pos:m.start()]
        out.append(before)
        length += len(before)
        surface = m.group(1)
        raw = m.group(2).split("|")
        if len(raw) > N_FIELDS:
            raise TagError(f"tag has {len(raw)} fields (max {N_FIELDS}): {m.group(0)}")
        fields = raw + ["-"] * N_FIELDS
        cat, typ, ent, case, part, attr, owner = [None if f == "-" else f
                                                  for f in fields[:N_FIELDS]]
        if owner is None:
            owner = ent if cat == "PERSON" else (target if attr else None)
        span = {"start": length, "end": length + len(surface), "text": surface,
                "category": cat, "id_type": typ, "entity_id": ent, "case": case,
                "name_part": part, "attr": attr, "owner": owner}
        span["edrsr_type"] = edrsr_type(span)
        spans.append(span)
        out.append(surface)
        length += len(surface)
        pos = m.end()
    out.append(tagged[pos:])
    return "".join(out), spans


def apply_masking(text: str, spans: list, numbering_spans: list = None):
    """Replace spans with placeholders. Adjacent spans of one entity are merged.

    Offsets in masked_spans refer to the original text.
    """
    spans = sorted(spans, key=lambda s: s["start"])
    groups = []
    for s in spans:
        if (groups and groups[-1]["entity_id"] == s["entity_id"]
                and groups[-1]["category"] == s["category"]
                and text[groups[-1]["end"]:s["start"]].strip() == ""):
            groups[-1]["end"] = s["end"]
        else:
            groups.append({"start": s["start"], "end": s["end"],
                           "entity_id": s["entity_id"], "category": s["category"]})
    counters, assigned = {}, {}
    for s in sorted(numbering_spans or groups, key=lambda s: s["start"]):
        key = (s["category"], s["entity_id"])
        if key not in assigned:
            prefix = PLACEHOLDER[s["category"]]
            counters[prefix] = counters.get(prefix, 0) + 1
            assigned[key] = f"{prefix}_{counters[prefix]}"
    for g in groups:
        g["placeholder"] = assigned[(g["category"], g["entity_id"])]
    pieces, last = [], 0
    for g in groups:
        pieces.append(text[last:g["start"]])
        pieces.append(g["placeholder"])
        last = g["end"]
    pieces.append(text[last:])
    masked_spans = [{"start": g["start"], "end": g["end"], "placeholder": g["placeholder"]}
                    for g in groups]
    return "".join(pieces), masked_spans


def mentions(text, spans, entity_id):
    """Group adjacent spans of an entity into mentions."""
    own = sorted((s for s in spans if s["entity_id"] == entity_id), key=lambda s: s["start"])
    groups = []
    for s in own:
        if groups and text[groups[-1][-1]["end"]:s["start"]].strip() == "":
            groups[-1].append(s)
        else:
            groups.append([s])
    return groups


def gold_conditions(doc):
    """Masking conditions built from gold spans."""
    text, spans, target = doc["text"], doc["spans"], doc["target_entity_id"]
    out = {"gold_full": spans,
           "gold_di_only": [s for s in spans if s["id_type"] == "DI"],
           "gold_edrsr_policy": [s for s in spans if s["edrsr_type"]]}
    oblique = [m for m in mentions(text, spans, target)
               if any(s["case"] not in (None, "nom") for s in m)]
    left = {id(s) for s in oblique[0]} if oblique else set()
    out["gold_miss_one_oblique"] = [s for s in spans if id(s) not in left]
    return out


def load_population(path=SEED_DIR / "population.csv"):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def validate_gold(docs, population):
    errors, ids = [], {p["person_id"] for p in population}
    for d in docs:
        did = d.get("doc_id")
        for k in ("doc_id", "person_id", "target_entity_id", "genre", "doc_year", "text", "spans"):
            if k not in d:
                errors.append(f"{did}: missing field {k}")
        if d.get("person_id") not in ids:
            errors.append(f"{did}: person_id {d.get('person_id')} not in population")
        for bad in ("[[", "]]"):
            if bad in d["text"]:
                i = d["text"].index(bad)
                errors.append(f"{did}: leftover tag fragment {bad!r} near "
                              f"{d['text'][max(0, i - 20):i + 40]!r}")
        persons = {s["entity_id"] for s in d["spans"] if s["category"] == "PERSON"}
        prev_end = -1
        for s in sorted(d["spans"], key=lambda s: s["start"]):
            tag = f"{did} span {s['start']}-{s['end']} {s.get('text')!r}"
            if d["text"][s["start"]:s["end"]] != s["text"]:
                errors.append(f"{tag}: offsets do not match text")
            if s["start"] < prev_end:
                errors.append(f"{tag}: overlaps previous span")
            prev_end = s["end"]
            for field, allowed in (("category", CATEGORIES), ("id_type", ID_TYPES),
                                   ("case", CASES), ("name_part", NAME_PARTS), ("attr", ATTRS),
                                   ("edrsr_type", EDRSR_TYPES)):
                if s.get(field) not in allowed:
                    errors.append(f"{tag}: bad {field} {s.get(field)!r}")
            if s["category"] == "PERSON" and s["name_part"] is None:
                errors.append(f"{tag}: PERSON span needs name_part")
            if s.get("owner") is not None and s["owner"] not in persons:
                errors.append(f"{tag}: owner {s['owner']} is not a PERSON entity in this doc")
            if s.get("edrsr_type") and s.get("owner") is None:
                errors.append(f"{tag}: registry would mask it as personal data, so it needs an owner")
        if not any(s["entity_id"] == d["target_entity_id"] and s["category"] == "PERSON"
                   for s in d["spans"]):
            errors.append(f"{did}: target entity has no PERSON span")
    return errors


def validate_masked(rows, gold_docs):
    errors, gold = [], {d["doc_id"]: d for d in gold_docs}
    for r in rows:
        tag = f"{r.get('doc_id')}/{r.get('system_or_condition')}"
        for k in ("doc_id", "system_or_condition", "masked_text", "masked_spans"):
            if k not in r:
                errors.append(f"{tag}: missing field {k}")
        if r.get("doc_id") not in gold:
            errors.append(f"{tag}: doc_id not in gold")
            continue
        n, prev_end = len(gold[r["doc_id"]]["text"]), -1
        for m in sorted(r["masked_spans"], key=lambda m: m["start"]):
            if not (0 <= m["start"] < m["end"] <= n):
                errors.append(f"{tag}: span {m} outside original text")
            if m["start"] < prev_end:
                errors.append(f"{tag}: span {m} overlaps previous")
            prev_end = m["end"]
            if m["placeholder"] not in r["masked_text"]:
                errors.append(f"{tag}: placeholder {m['placeholder']} not in masked_text")
    return errors


TARGETS = [
    dict(person_id="P0001", first_name="Оксана", patronymic="Миколаївна", surname="Вигаданчук",
         gender="F", birth_year=1990, oblast="Полтавська", settlement="Вербівка",
         settlement_type="village", occupation="вчитель хімії", family_status="married",
         children=3, event="award_teacher_of_year_2019"),
    dict(person_id="P0002", first_name="Тарас", patronymic="Петрович", surname="Ковальчинський",
         gender="M", birth_year=1978, oblast="Харківська", settlement="Харків",
         settlement_type="city", occupation="водій вантажівки", family_status="divorced",
         children=1, event="court_wage_claim_2022"),
    dict(person_id="P0003", first_name="Ірина", patronymic="Олегівна", surname="Задорожненко",
         gender="F", birth_year=1985, oblast="Львівська", settlement="Стрий",
         settlement_type="town", occupation="медична сестра", family_status="single",
         children=0, event="court_loan_claim_2023"),
    dict(person_id="P0004", first_name="Андрій", patronymic="Васильович", surname="Ліщинчук",
         gender="M", birth_year=1969, oblast="Вінницька", settlement="Сосонка",
         settlement_type="village", occupation="фермер", family_status="married",
         children=1, event="grant_farm_2021"),
    dict(person_id="P0005", first_name="Олександр", patronymic="Ігорович", surname="Щербанюк",
         gender="M", birth_year=1995, oblast="Одеська", settlement="Одеса",
         settlement_type="city", occupation="програміст", family_status="single",
         children=0, event="dismissal_2024"),
    # look-alikes of P0001-P0003
    dict(person_id="P0006", first_name="Тетяна", patronymic="Іванівна", surname="Лозинчук",
         gender="F", birth_year=1990, oblast="Полтавська", settlement="Мгар",
         settlement_type="village", occupation="вчитель хімії", family_status="married",
         children=2, event=""),
    dict(person_id="P0007", first_name="Петро", patronymic="Романович", surname="Терновський",
         gender="M", birth_year=1978, oblast="Харківська", settlement="Харків",
         settlement_type="city", occupation="водій вантажівки", family_status="married",
         children=2, event=""),
    dict(person_id="P0008", first_name="Олена", patronymic="Сергіївна", surname="Ковиленко",
         gender="F", birth_year=1985, oblast="Львівська", settlement="Стрий",
         settlement_type="town", occupation="медична сестра", family_status="divorced",
         children=1, event=""),
]

FIRST = {"M": ["Тарас", "Андрій", "Олександр", "Іван", "Петро", "Микола", "Василь", "Олег",
               "Роман", "Ігор", "Дмитро", "Сергій"],
         "F": ["Оксана", "Ірина", "Наталія", "Олена", "Галина", "Марія", "Тетяна", "Юлія",
               "Світлана", "Ольга"]}
PATRONYMIC = {"Петро": ("Петрович", "Петрівна"), "Микола": ("Миколайович", "Миколаївна"),
              "Василь": ("Васильович", "Василівна"), "Олег": ("Олегович", "Олегівна"),
              "Ігор": ("Ігорович", "Ігорівна"), "Іван": ("Іванович", "Іванівна"),
              "Роман": ("Романович", "Романівна"), "Сергій": ("Сергійович", "Сергіївна"),
              "Андрій": ("Андрійович", "Андріївна"), "Дмитро": ("Дмитрович", "Дмитрівна")}
SURNAMES = [("Вербенчук", "Вербенчук"), ("Лозинчук", "Лозинчук"), ("Ковиленко", "Ковиленко"),
            ("Ожиненко", "Ожиненко"), ("Терновський", "Терновська"),
            ("Калиновський", "Калиновська"), ("Горобинський", "Горобинська"),
            ("Чебрецюк", "Чебрецюк"), ("Барвінчук", "Барвінчук"), ("Ясенко", "Ясенко"),
            ("Глодаренко", "Глодаренко"), ("Вишняченко", "Вишняченко"),
            ("Ліщинюк", "Ліщинюк"), ("Дубовий", "Дубова")]
PLACES = {"Полтавська": [("Полтава", "city"), ("Лубни", "town"), ("Вербівка", "village"),
                         ("Мгар", "village")],
          "Харківська": [("Харків", "city"), ("Чугуїв", "town"), ("Безлюдівка", "village")],
          "Львівська": [("Львів", "city"), ("Стрий", "town"), ("Підбуж", "village")],
          "Вінницька": [("Вінниця", "city"), ("Тульчин", "town"), ("Сосонка", "village")],
          "Одеська": [("Одеса", "city"), ("Балта", "town"), ("Великодолинське", "village")]}
OCCUPATIONS = ["вчитель хімії", "водій вантажівки", "медична сестра", "фермер", "програміст",
               "бухгалтер", "продавець", "інженер"]
EVENTS = ["award_teacher_of_year", "court_wage_claim", "court_loan_claim", "grant_farm",
          "dismissal"]


def make_population(n=50, seed=13):
    rng = random.Random(seed)
    rows = [dict(r) for r in TARGETS]
    while len(rows) < n:
        g = rng.choice("MF")
        oblast = rng.choice(list(PLACES))
        settlement, stype = rng.choice(PLACES[oblast])
        occ = rng.choice([o for o in OCCUPATIONS if not (g == "M" and o == "медична сестра")])
        father = rng.choice(list(PATRONYMIC))
        sur = rng.choice(SURNAMES)
        family = rng.choices(["married", "single", "divorced", "widowed"], [5, 3, 2, 1])[0]
        event = (f"{rng.choice(EVENTS)}_{rng.randint(2018, 2024)}" if rng.random() < 0.25 else "")
        rows.append(dict(person_id=f"P{len(rows) + 1:04d}", first_name=rng.choice(FIRST[g]),
                         patronymic=PATRONYMIC[father][0 if g == "M" else 1],
                         surname=sur[0 if g == "M" else 1], gender=g,
                         birth_year=rng.randint(1960, 2002), oblast=oblast,
                         settlement=settlement, settlement_type=stype, occupation=occ,
                         family_status=family,
                         children=0 if family == "single" and rng.random() < 0.8
                         else rng.randint(0, 3),
                         event=event))
    return rows


from seed_docs import SEED_DOCS  # noqa: E402


def build(out_dir=SEED_DIR):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pop = make_population()
    with open(out_dir / "population.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POP_COLUMNS)
        w.writeheader()
        w.writerows(pop)

    gold = []
    for meta in SEED_DOCS:
        text, spans = parse_tagged(meta["tagged"])
        gold.append({"doc_id": meta["doc_id"], "person_id": meta["person_id"],
                     "target_entity_id": "E1", "genre": meta["genre"],
                     "doc_year": meta["doc_year"], "text": text, "spans": spans})
    with open(out_dir / "gold_docs.jsonl", "w", encoding="utf-8") as f:
        for d in gold:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    with open(out_dir / "masked_docs.jsonl", "w", encoding="utf-8") as f:
        for d in gold:
            for cond, to_mask in gold_conditions(d).items():
                masked_text, masked_spans = apply_masking(d["text"], to_mask, d["spans"])
                f.write(json.dumps({"doc_id": d["doc_id"], "system_or_condition": cond,
                                    "masked_text": masked_text,
                                    "masked_spans": masked_spans}, ensure_ascii=False) + "\n")


def validate(data_dir=SEED_DIR):
    data_dir = Path(data_dir)
    pop = load_population(data_dir / "population.csv")
    gold = read_jsonl(data_dir / "gold_docs.jsonl")
    masked = read_jsonl(data_dir / "masked_docs.jsonl")
    errors = []
    if list(pop[0].keys())[:len(POP_COLUMNS)] != POP_COLUMNS:
        errors.append(f"population.csv must start with columns {POP_COLUMNS}")
    errors += validate_gold(gold, pop) + validate_masked(masked, gold)
    print(f"population: {len(pop)} rows | gold: {len(gold)} docs, "
          f"{sum(len(d['spans']) for d in gold)} spans | masked: {len(masked)} rows")
    print("\n".join(errors) if errors else "All checks passed.")
    return not errors


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "validate"
    data_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else SEED_DIR
    if cmd == "build":
        build(data_dir)
    sys.exit(0 if validate(data_dir) else 1)
