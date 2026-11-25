"""Inflected forms of Ukrainian personal names.

    forms("Тарас", "Петрович", "Ковальчинський", "M", "skyi")
returns every surface the checker should look for: each name part in all 7 cases,
diminutives, full names in both orders, initials, and Russian spellings.

Rules are written by hand. pymorphy3 was tried on made-up surnames and picked the
invariant feminine reading for -чук/-енко, so it is not used here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from population import DIMINUTIVES, FEMALE, MALE, surname_type

CASES = ["nom", "gen", "dat", "acc", "ins", "loc", "voc"]
SOFTEN = {"к": "ц", "г": "з", "х": "с"}

# old records and forum posts sometimes use the russian spelling.
RUSSIAN_FIRST = {
    "Андрій": "Андрей", "Олександр": "Александр", "Тарас": "Тарас", "Іван": "Иван",
    "Петро": "Петр", "Микола": "Николай", "Василь": "Василий", "Олег": "Олег",
    "Роман": "Роман", "Ігор": "Игорь", "Дмитро": "Дмитрий", "Сергій": "Сергей",
    "Юрій": "Юрий", "Михайло": "Михаил", "Богдан": "Богдан", "Володимир": "Владимир",
    "Віктор": "Виктор", "Степан": "Степан", "Григорій": "Григорий", "Павло": "Павел",
    "Віталій": "Виталий", "Максим": "Максим", "Євген": "Евгений", "Анатолій": "Анатолий",
    "Ярослав": "Ярослав", "Остап": "Остап", "Назар": "Назар", "Денис": "Денис",
    "Артем": "Артем", "Вадим": "Вадим",
    "Оксана": "Оксана", "Ірина": "Ирина", "Наталія": "Наталья", "Олена": "Елена",
    "Галина": "Галина", "Марія": "Мария", "Тетяна": "Татьяна", "Юлія": "Юлия",
    "Світлана": "Светлана", "Ольга": "Ольга", "Людмила": "Людмила", "Валентина": "Валентина",
    "Надія": "Надежда", "Любов": "Любовь", "Катерина": "Екатерина", "Ганна": "Анна",
    "Христина": "Кристина", "Софія": "София", "Віра": "Вера", "Лариса": "Лариса",
    "Інна": "Инна", "Алла": "Алла", "Вікторія": "Виктория", "Мар’яна": "Марьяна",
    "Уляна": "Ульяна", "Зоряна": "Зоряна", "Дарина": "Дарья", "Ніна": "Нина",
    "Тамара": "Тамара", "Лілія": "Лилия",
}
RUSSIAN_PATRONYMIC = {
    "Андрій": ("Андреевич", "Андреевна"), "Олександр": ("Александрович", "Александровна"),
    "Тарас": ("Тарасович", "Тарасовна"), "Іван": ("Иванович", "Ивановна"),
    "Петро": ("Петрович", "Петровна"), "Микола": ("Николаевич", "Николаевна"),
    "Василь": ("Васильевич", "Васильевна"), "Олег": ("Олегович", "Олеговна"),
    "Роман": ("Романович", "Романовна"), "Ігор": ("Игоревич", "Игоревна"),
    "Дмитро": ("Дмитриевич", "Дмитриевна"), "Сергій": ("Сергеевич", "Сергеевна"),
    "Юрій": ("Юрьевич", "Юрьевна"), "Михайло": ("Михайлович", "Михайловна"),
    "Богдан": ("Богданович", "Богдановна"), "Володимир": ("Владимирович", "Владимировна"),
    "Віктор": ("Викторович", "Викторовна"), "Степан": ("Степанович", "Степановна"),
    "Григорій": ("Григорьевич", "Григорьевна"), "Павло": ("Павлович", "Павловна"),
    "Віталій": ("Витальевич", "Витальевна"), "Максим": ("Максимович", "Максимовна"),
    "Євген": ("Евгеньевич", "Евгеньевна"), "Анатолій": ("Анатольевич", "Анатольевна"),
    "Ярослав": ("Ярославович", "Ярославовна"), "Остап": ("Остапович", "Остаповна"),
    "Назар": ("Назарович", "Назаровна"), "Денис": ("Денисович", "Денисовна"),
    "Артем": ("Артемович", "Артемовна"), "Вадим": ("Вадимович", "Вадимовна"),
}
FATHER = {forms[i]: name for name, forms in MALE.items() for i in (0, 1)}


def noun(word, gender):
    """Case forms of a name that declines like a noun. Returns {case: [forms]}."""
    w = word
    if w == "Любов":
        return {"nom": [w], "gen": ["Любові"], "dat": ["Любові"], "acc": [w],
                "ins": ["Любов’ю"], "loc": ["Любові"], "voc": ["Любове"]}
    if w == "Ігор":
        return {"nom": [w], "gen": ["Ігоря"], "dat": ["Ігореві", "Ігорю"], "acc": ["Ігоря"],
                "ins": ["Ігорем"], "loc": ["Ігореві", "Ігорю"], "voc": ["Ігорю"]}
    if w.endswith("ія"):
        s = w[:-1]
        return {"nom": [w], "gen": [s + "ї"], "dat": [s + "ї"], "acc": [s + "ю"],
                "ins": [s + "єю"], "loc": [s + "ї"], "voc": [s + "є"]}
    if w.endswith("я"):
        s = w[:-1]
        return {"nom": [w], "gen": [s + "і"], "dat": [s + "і"], "acc": [s + "ю"],
                "ins": [s + "ею"], "loc": [s + "і"], "voc": [s + "ю"]}
    if w.endswith("а"):
        s = w[:-1]
        soft = s[:-1] + SOFTEN.get(s[-1], s[-1])
        return {"nom": [w], "gen": [s + "и"], "dat": [soft + "і"], "acc": [s + "у"],
                "ins": [s + "ою"], "loc": [soft + "і"], "voc": [s + "о"]}
    if gender == "F":
        return {c: [w] for c in CASES}
    if w.endswith("о"):
        s = w[:-1]
        voc = s + "у" if s.endswith("к") else s + "е"
        return {"nom": [w], "gen": [s + "а"], "dat": [s + "ові", s + "у"], "acc": [s + "а"],
                "ins": [s + "ом"], "loc": [s + "ові", s + "у"], "voc": [voc]}
    if w.endswith("й"):
        s = w[:-1]
        return {"nom": [w], "gen": [s + "я"], "dat": [s + "єві", s + "ю"], "acc": [s + "я"],
                "ins": [s + "єм"], "loc": [s + "єві", s + "ю"], "voc": [s + "ю"]}
    if w.endswith("ь"):
        s = w[:-1]
        return {"nom": [w], "gen": [s + "я"], "dat": [s + "еві", s + "ю"], "acc": [s + "я"],
                "ins": [s + "ем"], "loc": [s + "еві", s + "ю"], "voc": [s + "ю"]}
    if w[-1] in "жчшщ":
        return {"nom": [w], "gen": [w + "а"], "dat": [w + "еві", w + "у"], "acc": [w + "а"],
                "ins": [w + "ем"], "loc": [w + "еві", w + "у"], "voc": [w + "у"]}
    if w.endswith("к"):
        voc = w + "у"
    elif w.endswith("г"):
        voc = w[:-1] + "же"
    else:
        voc = w + "е"
    return {"nom": [w], "gen": [w + "а"], "dat": [w + "ові", w + "у"], "acc": [w + "а"],
            "ins": [w + "ом"], "loc": [w + "ові", w + "у"], "voc": [voc]}


def adjective(word, gender):
    """Case forms of an adjective-type surname (-ський, -ий and their feminine -а)."""
    if gender == "F":
        s = word[:-1]
        return {"nom": [word], "gen": [s + "ої"], "dat": [s + "ій"], "acc": [s + "у"],
                "ins": [s + "ою"], "loc": [s + "ій"], "voc": [word]}
    s = word[:-2]
    return {"nom": [word], "gen": [s + "ого"], "dat": [s + "ому"], "acc": [s + "ого"],
            "ins": [s + "им"], "loc": [s + "ому", s + "ім"], "voc": [word]}


def surname_cases(surname, gender, stype=None):
    stype = stype or surname_type(surname)
    if stype in ("skyi", "adj"):
        return adjective(surname, gender)
    if gender == "F":
        return {c: [surname] for c in CASES}
    return noun(surname, gender)


def name_forms(first, patronymic, surname, gender, stype=None):
    """{(name_part, case): [forms]} for one person."""
    out = {}
    for part, cases in [("first", noun(first, gender)),
                        ("patronymic", noun(patronymic, gender)),
                        ("surname", surname_cases(surname, gender, stype))]:
        for case, words in cases.items():
            out[(part, case)] = words
    for dim in DIMINUTIVES.get(first, []):
        for case, words in noun(dim, gender).items():
            out.setdefault(("diminutive", case), []).extend(words)
    return out


def initials(first, patronymic):
    a, b = first[0], patronymic[0]
    return {f"{a}. {b}.", f"{a}.{b}."}


def forms(first, patronymic, surname, gender, stype=None):
    """Every surface form worth searching for."""
    table = name_forms(first, patronymic, surname, gender, stype)
    result = {w for words in table.values() for w in words}
    for case in CASES:
        firsts = table[("first", case)]
        patrs = table[("patronymic", case)]
        surs = table[("surname", case)]
        for f in firsts:
            for p in patrs:
                for s in surs:
                    result |= {f"{f} {p} {s}", f"{s} {f} {p}", f"{f} {p}", f"{f} {s}", f"{s} {f}"}
        for s in surs:
            for i in initials(first, patronymic):
                result |= {f"{s} {i}", f"{i} {s}"}
    result |= initials(first, patronymic)

    if first in RUSSIAN_FIRST:
        result.add(RUSSIAN_FIRST[first])
    father = FATHER.get(patronymic)
    if father:
        ru = RUSSIAN_PATRONYMIC[father][0 if gender == "M" else 1]
        result.add(ru)
        if first in RUSSIAN_FIRST:
            result.add(f"{RUSSIAN_FIRST[first]} {ru}")
    return result


def guess_gender(first=None, patronymic=None, surname=None):
    if patronymic:
        return "M" if patronymic.endswith("ич") else "F"
    if first in MALE:
        return "M"
    if first in FEMALE:
        return "F"
    if surname and surname.endswith(("ська", "цька")):
        return "F"
    return "M"


def side_forms(full_name, gender=None):
    """Forms for a side character given as written in nominative, e.g. "Петренко Н. В."
    or "Остап Романович Вигаданий". Initials are kept as they are."""
    words = [w for w in full_name.split() if not w.endswith(".")]
    patronymic = next((w for w in words if w.endswith(("ович", "йович", "івна", "ївна"))), None)
    first = next((w for w in words if w in MALE or w in FEMALE), None)
    rest = [w for w in words if w not in (patronymic, first)]
    gender = gender or guess_gender(first, patronymic, rest[0] if rest else None)
    result = set()
    if first:
        result |= {w for ws in noun(first, gender).values() for w in ws}
    if patronymic:
        result |= {w for ws in noun(patronymic, gender).values() for w in ws}
    for s in rest:
        result |= {w for ws in surname_cases(s, gender).values() for w in ws}
    return result
