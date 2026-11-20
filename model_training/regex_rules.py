"""Format-based patterns shared by the rule-based and spaCy systems.

Finds things with a fixed shape: emails, URLs, phones, РНОКПП, case numbers, dates,
years, ages, amounts, street addresses, "село X"/"м. X", oblasts and districts.
It does not try to find names, occupations or family facts.
"""
import re

U = "А-ЯІЇЄҐ"
L = "а-яіїєґ’"
CAP = rf"[{U}][{L}’-]+"
MONTH_GEN = "січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня"
MONTH_LOC = ("січні|лютому|березні|квітні|травні|червні|липні|серпні|вересні|жовтні|"
             "листопаді|грудні")
YEAR_WORD = r"(?:року|році|рік|р\.)"
PREP = r"(?:[уУвВ]\s+)?"
UNITS = (r"грн\.?|гривень|гривні|гривню|гривня|доларів|дол\.|USD|EUR|євро|гектарів|гектарах|"
         r"гектари|гектара|га|тонн|тонни|соток|кв\.\s?м")

PATTERNS = [
    # (category, pattern)
    ("CODE", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    ("CODE", r"(?:https?://|www\.)[^\s,;»)]+"),
    ("CODE", r"(?<![\d\w])(?:\+?38\s?)?\(?0\s?\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"),
    ("CODE", r"(?<![\d\w])[1-9]\d{9}(?!\d)"),                         # РНОКПП
    ("CODE", r"№\s*\d[\d-]*(?:/[\d-]+)+"),                             # case number
    ("CODE", r"(?<![\w])(?:справа|провадження)\s+\d[\d-]*(?:/[\d-]+)+"),
    ("CODE", rf"(?:паспорт\w*|серії)\s+[{U}]{{2}}\s*№?\s*\d{{6}}"),
    ("CODE", r"(?<![\d\w])UA\d{27}(?!\d)"),                             # IBAN
    # dates
    ("DATETIME", rf"{PREP}\d{{1,2}}\s+(?:{MONTH_GEN})\s+\d{{4}}(?:\s+{YEAR_WORD})?"),
    ("DATETIME", rf"\d{{1,2}}\.\d{{1,2}}\.\d{{4}}(?:\s+{YEAR_WORD})?"),
    ("DATETIME", rf"{PREP}(?:{MONTH_GEN}|{MONTH_LOC})\s+\d{{4}}(?:\s+{YEAR_WORD})?"),
    ("DATETIME", r"\d{4}\s+(?:року|р\.)\s*народження|\d{4}\s*р\.\s?н\."),
    ("DATETIME", rf"{PREP}\d{{4}}\s+{YEAR_WORD}"),
    # ages, amounts
    ("DEM", rf"\d{{1,3}}-річн[{L}]+"),
    ("DEM", r"(?<![\d\w])\d{1,3}\s+(?:рік|роки|років)(?![\w])"),
    ("QUANTITY", rf"(?<![\d\w])\d{{1,3}}(?:[  ]\d{{3}})*(?:[.,]\d+)?\s*(?:{UNITS})(?![{L}])"),
    # organisations with a legal form: ТОВ «…», ФГ «…»
    ("ORG", r"(?:ТОВ|ПП|ФГ|ФОП|ПрАТ|ПАТ|АТ|КП|ДП|ГО|ОСББ|СФГ)\s*«[^»]{1,60}»"),
    # places
    ("LOC", rf"(?:(?:м|с|смт)\.\s*{CAP},\s*)?(?:вул\.|вулиця|вулиці|просп\.|проспект|пров\.|"
            rf"провулок|бульв\.|бульвар|пл\.)\s*(?:{CAP}|\d+-?\w*)(?:\s+{CAP})?,?\s*"
            rf"(?:буд\.\s*)?\d+[{L}/-]*\d*(?:,\s*кв\.\s*\d+)?"),
    ("LOC", rf"(?:м\.|с\.|смт\.?|село|селі|села|місто|місті|міста|селище|селищі)\s*{CAP}"),
    ("LOC", rf"{CAP}(?:ськ|цьк|зьк)(?:а|ій|ої|у|ою)\s+(?:област[{L}]*|обл\.)"),
    ("LOC", rf"{CAP}(?:ськ|цьк|зьк)(?:ий|ого|ому|им|ім)\s+район(?:у|і|ом|а)?(?![{L}])"),
    ("LOC", rf"{CAP}(?:щин|ччин)(?:а|и|і|у|ою)?(?![{L}])"),  # Полтавщина, Вінниччині
]
COMPILED = [(cat, re.compile(p)) for cat, p in PATTERNS]


def find(text):
    """All pattern matches as spans (they may overlap; see common.resolve_overlaps)."""
    out = []
    for rank, (cat, rx) in enumerate(COMPILED):
        for m in rx.finditer(text):
            out.append({"start": m.start(), "end": m.end(), "category": cat,
                        "rank": rank, "source": "regex"})
    return out
