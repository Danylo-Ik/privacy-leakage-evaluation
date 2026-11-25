"""Fact plans: what each generated document must say about its target.

Usage: python data_understanding/fact_plan.py [DIR] [PER_GENRE]
Reads DIR/population.csv and DIR/targets.csv, writes DIR/fact_plans.jsonl.
With PER_GENRE, only the first N targets of each genre are planned.

Each plan lists the facts to reveal (with the attr they reveal and how to tag them),
the name forms that must appear, side characters, and other identifiers.
"""
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import names  # noqa: E402
from population import Generator  # noqa: E402

SEED = 7
OBLIQUE = ["gen", "dat", "acc", "ins", "loc"]


POOL = {
    "court": {"birth_year": 3, "address": 3, "family_status": 3, "occupation": 2,
              "children": 2, "oblast": 1},
    "news": {"birth_year": 3, "settlement": 3, "occupation": 3, "children": 2, "oblast": 2,
             "family_status": 1},
    "forum": {"birth_year": 3, "settlement": 3, "occupation": 3, "family_status": 2,
              "children": 1},
}

FEMININE = {
    "вчитель хімії": "вчителька хімії", "вчитель початкових класів": "вчителька початкових класів",
    "водій вантажівки": "водійка вантажівки", "фермер": "фермерка", "агроном": "агрономка",
    "програміст": "програмістка", "бухгалтер": "бухгалтерка", "продавець": "продавчиня",
    "інженер": "інженерка", "лікар": "лікарка", "юрист": "юристка", "кухар": "кухарка",
    "перукар": "перукарка", "економіст": "економістка", "будівельник": "будівельниця",
    "тракторист": "трактористка", "охоронець": "охоронниця", "психолог": "психологиня",
}
FAMILY = {
    "married": ("одружений", "заміжня", "перебуває у шлюбі"),
    "single": ("неодружений", "незаміжня", "не перебуває у шлюбі"),
    "divorced": ("розлучений", "розлучена", "після розірвання шлюбу"),
    "widowed": ("вдівець", "вдова", "після смерті дружини"),
}
CHILDREN = {0: "не має дітей", 1: "одну дитину", 2: "двох дітей", 3: "трьох дітей"}
EVENT_TEXT = {
    "court_wage_claim": "про стягнення заборгованості із заробітної плати",
    "court_loan_claim": "про стягнення боргу за договором позики",
    "award_teacher_of_year": "«Вчитель року»",
    "grant_farm": "грант на розвиток фермерського господарства",
    "dismissal": "звільнення з роботи",
}
STREETS = ["Шевченка", "Лесі Українки", "Садова", "Центральна", "Миру", "Зелена", "Шкільна",
           "Польова", "Франка", "Грушевського", "Незалежності", "Лісова", "Набережна"]
COMPANIES = ["ТОВ «Степова Логістика»", "ТОВ «Агросвіт-Плюс»", "ПП «Будмайстер»",
             "ТОВ «Діджитал Хвиля»", "ТОВ «Колос Трейд»", "ПрАТ «Енергосервіс»",
             "ТОВ «Смарт Код»", "ТОВ «Світанок Фуд»"]
TRANSLIT = dict(zip("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя’",
                    ["a", "b", "v", "h", "g", "d", "e", "ie", "zh", "z", "y", "i", "i", "i", "k",
                     "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh",
                     "shch", "", "iu", "ia", ""]))


def translit(word):
    return "".join(TRANSLIT.get(c, c) for c in word.lower())


def years_word(n):
    if n % 10 == 1 and n % 100 != 11:
        return "рік"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "роки"
    return "років"


def fact(attr, category, text, value, id_type="QI", exact=False):
    return {"attr": attr, "category": category, "id_type": id_type, "text": text,
            "value": value, "exact": exact}


def make_fact(attr, p, genre, doc_year, rng):
    f = p["gender"] == "F"
    age = doc_year - int(p["birth_year"])
    if attr == "birth_year":
        if genre == "court":
            text = rng.choice([f"{p['birth_year']} року народження", f"{p['birth_year']} р. н."])
            return fact(attr, "DATETIME", text, int(p["birth_year"]), exact=True)
        if genre == "news":
            return fact(attr, "DEM", f"{age}-річн{'а' if f else 'ий'}", age, exact=True)
        return fact(attr, "DEM", f"{age} {years_word(age)}", age, exact=True)
    if attr == "children":
        n = int(p["children"])
        return fact(attr, "DEM", CHILDREN.get(n, f"{n} дітей"), n, exact=True)
    if attr == "family_status":
        m_word, f_word, legal = FAMILY[p["family_status"]]
        if genre == "court" and p["family_status"] == "widowed" and f:
            legal = "після смерті чоловіка"
        text = legal if genre == "court" else (f_word if f else m_word)
        return fact(attr, "DEM", text, p["family_status"])
    if attr == "occupation":
        job = FEMININE.get(p["occupation"], p["occupation"]) if f else p["occupation"]
        return fact(attr, "DEM", job, p["occupation"])
    if attr == "settlement":
        kind = {"city": "місто", "town": "місто", "village": "село"}[p["settlement_type"]]
        return fact(attr, "LOC", f"{kind} {p['settlement']}", p["settlement"])
    if attr == "oblast":
        return fact(attr, "LOC", f"{p['oblast']} область", p["oblast"])
    if attr == "address":
        prefix = "м." if p["settlement_type"] != "village" else "с."
        text = (f"{prefix} {p['settlement']}, вул. {rng.choice(STREETS)}, "
                f"буд. {rng.randint(1, 120)}")
        if p["settlement_type"] == "city":
            text += f", кв. {rng.randint(1, 200)}"
        return fact("settlement", "LOC", text, p["settlement"], id_type="DI", exact=True)
    raise ValueError(attr)


def event_facts(p, event_year):
    kind = p["event"].rsplit("_", 1)[0]
    return [fact("event", "MISC", EVENT_TEXT[kind], kind),
            fact("event", "DATETIME", f"у {event_year} році", event_year)]


def unambiguous_oblique(table):
    """(part, case) pairs whose form belongs to that case only.
    """
    out = []
    for part in ("first", "surname"):
        for case in OBLIQUE:
            form = table[(part, case)][0]
            others = [w for c in names.CASES if c != case for w in table[(part, c)]]
            if form not in others:
                out.append((part, case))
    return out


def required_names(p, genre, rng):
    """Name forms the document must contain. At least one is in an oblique case."""
    table = names.name_forms(p["first_name"], p["patronymic"], p["surname"], p["gender"],
                             p["surname_type"])
    gen_name = " ".join(table[(part, "gen")][0] for part in ("surname", "first", "patronymic"))
    need = []
    if genre == "court":
        need.append({"text": gen_name, "case": "gen", "parts": ["surname", "first", "patronymic"]})
        init = f"{p['first_name'][0]}. {p['patronymic'][0]}."
        need.append({"text": f"{p['surname']} {init}", "case": "nom", "parts": ["surname", "initials"]})
    elif genre == "news":
        need.append({"text": f"{p['first_name']} {p['patronymic']}", "case": "nom",
                     "parts": ["first", "patronymic"]})
    part, case = rng.choice(unambiguous_oblique(table))
    need.append({"text": table[(part, case)][0], "case": case, "parts": [part]})
    dims = names.DIMINUTIVES.get(p["first_name"], [])
    if genre != "court" and dims and rng.random() < 0.3:
        need.append({"text": dims[0], "case": "nom", "parts": ["diminutive"]})
    if genre != "court" and rng.random() < 0.3:
        need.append({"text": table[("first", "voc")][0], "case": "voc", "parts": ["first"]})
    return need


SIDE_ROLES = {
    "court": ["суддя", "представник відповідача"],
    "news": ["голова громади", "колега"],
    "forum": ["керівник", "колега"],
}


def side_characters(p, genre, gen, rng):
    people = []
    roles = list(SIDE_ROLES[genre])
    if genre == "court" and p["event"].startswith("court_loan_claim"):
        roles.append("відповідач")
    if p["family_status"] == "married" and genre != "court":
        roles.append("чоловік" if p["gender"] == "F" else "дружина")
    for role in roles:
        if role in ("чоловік", "дружина"):
            g = "M" if role == "чоловік" else "F"
        else:
            g = rng.choice("MF")
        first, patronymic, surname = gen.name(g)
        if role == "суддя":
            mention = f"{surname} {first[0]}. {patronymic[0]}."
        elif role in ("чоловік", "дружина"):
            mention = first
        else:
            mention = f"{first} {surname}"
        people.append({"role": role, "gender": g, "first_name": first, "patronymic": patronymic,
                       "surname": surname, "mention": mention})
    return people


def other_identifiers(p, genre, rng, case_year):
    ids = []
    if genre == "court":
        ids.append({"kind": "case_number", "category": "CODE", "owner": None,
                    "text": f"№ {rng.randint(100, 760)}/{rng.randint(1000, 99999)}/{case_year % 100:02d}"})
        ids.append({"kind": "rnokpp", "category": "CODE", "owner": "E1",
                    "text": str(rng.randint(2000000000, 3999999999))})
        if p["event"].startswith("court_wage_claim"):
            ids.append({"kind": "employer", "category": "ORG", "owner": "E1",
                        "text": rng.choice(COMPANIES)})
    if genre == "forum":
        if rng.random() < 0.5:
            email = f"{translit(p['first_name'])}.{translit(p['surname'])}{rng.randint(1, 99)}@example.com"
            ids.append({"kind": "email", "category": "CODE", "owner": "E1", "text": email})
        if rng.random() < 0.3:
            phone = f"+380 {rng.choice([50, 63, 67, 68, 73, 93, 97])} {rng.randint(100, 999)} {rng.randint(10, 99)} {rng.randint(10, 99)}"
            ids.append({"kind": "phone", "category": "CODE", "owner": "E1", "text": phone})
        if rng.random() < 0.5:
            ids.append({"kind": "employer", "category": "ORG", "owner": "E1",
                        "text": rng.choice(COMPANIES)})
    return ids


def make_plan(doc_id, p, target, gen, rng):
    genre = target["genre"]
    event_year = int(target["event"].rsplit("_", 1)[1])
    doc_year = event_year + (0 if genre == "forum" else rng.randint(0, 1))

    pool = dict(POOL[genre])
    n_other = rng.randint(1, 5)
    chosen = []
    while pool and len(chosen) < n_other:
        attr = rng.choices(list(pool), list(pool.values()))[0]
        chosen.append(attr)
        del pool[attr]
    facts = event_facts(p, event_year) + [make_fact(a, p, genre, doc_year, rng) for a in chosen]

    return {
        "doc_id": doc_id, "person_id": p["person_id"], "genre": genre, "doc_year": doc_year,
        "target": {k: p[k] for k in ("first_name", "patronymic", "surname", "gender",
                                     "surname_type")},
        "n_qi": 1 + len(chosen),
        "facts": facts,
        "names": required_names(p, genre, rng),
        "side_characters": side_characters(p, genre, gen, rng),
        "identifiers": other_identifiers(p, genre, rng, event_year),
    }


def make_plans(population, targets, per_genre=None, seed=SEED):
    rng = random.Random(seed)
    gen = Generator(seed)
    gen.used_names |= {(p["first_name"], p["patronymic"], p["surname"]) for p in population}
    by_id = {p["person_id"]: p for p in population}
    picked, counts = [], {}
    for t in targets:
        if per_genre is None or counts.get(t["genre"], 0) < per_genre:
            counts[t["genre"]] = counts.get(t["genre"], 0) + 1
            picked.append(t)
    return [make_plan(f"D{i + 101}", by_id[t["person_id"]], t, gen, rng)
            for i, t in enumerate(picked)]


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/full")
    per_genre = int(sys.argv[2]) if len(sys.argv) > 2 else None
    plans = make_plans(read_csv(d / "population.csv"), read_csv(d / "targets.csv"), per_genre)
    with open(d / "fact_plans.jsonl", "w", encoding="utf-8") as f:
        for plan in plans:
            f.write(json.dumps(plan, ensure_ascii=False) + "\n")
    print(f"{len(plans)} plans -> {d / 'fact_plans.jsonl'}")
