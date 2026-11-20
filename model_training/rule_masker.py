"""Rule-based masker: regex layer + Ukrainian name rules.

Names are found by:
1. a first-name gazetteer (resources/first_names_uk.txt) expanded to all cases with pymorphy3;
2. patronymic suffixes (-ович/-івна and their case forms) and initials ("Т. П.");
3. distinctive surname suffixes (-енко/-ієнко, -чук/-юк/-ук, -ник, -ишин) on capitalized words;
4. context: an unknown capitalized word next to a first name, patronymic or initials
   (both name orders), or after a trigger word ("пані", "позивача"), is a surname;
   adjectival surnames (-ський, -ий) are accepted only in such a context;
5. propagation: once a surname is found, every other form with the same stem is masked.
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import regex_rules  # noqa: E402

U, L = "А-ЯІЇЄҐ", "а-яіїєґ’'"
TOKEN = re.compile(rf"[{U}]\.|[{U}{L}][{L}-]*")
PATR = re.compile(r"(?:ович|евич|євич|йович)(?:а|у|ем|еві|ові|і|е)?$|(?:івн|ївн|овн|евн)(?:а|и|і|у|ою|о)$")
SURNAME = re.compile(r"(?:[еє]нк(?:о|а|у|ові|ом)|(?:чук|юк|ук|чак|ник)(?:а|у|ові|ом|е|еві)?|"
                     r"ишин(?:а|у|ові|им|ою|ій|ої)?)$")
ADJ_SURNAME = re.compile(r"(?:ськ|цьк|зьк|ов|ин|н)(?:ий|ого|ому|им|ім|а|ої|ій|у|ою)$")
TRIGGERS = re.compile(r"^(?:пан|пані|панові|пана|гр\.|громадян\w*|позивач\w*|відповідач\w*|"
                      r"судд\w+|адвокат\w*|представни\w+|свід\w+|заявни\w+|потерпіл\w+|"
                      r"обвинувачен\w+|директор\w*|керівни\w+|лікар\w*|вчител\w+|колег\w+)$",
                      re.I)
# capitalized words that are never names
STOP = {"суд", "україни", "україна", "іменем", "рішення", "справа", "позивач", "позивачка",
        "відповідач", "відповідачка", "встановив", "вирішив", "ухвалив", "суддя"}


@lru_cache(maxsize=1)
def first_name_forms():
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer(lang="uk")
    names = []
    for line in (HERE / "resources" / "first_names_uk.txt").read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            names += line.split()
    forms = set()
    for n in names:
        low = n.lower()
        forms.add(low)
        for p in morph.parse(n):
            if "Name" in p.tag:
                forms |= {f.word for f in p.lexeme}
    return frozenset(forms)


def label_tokens(text):
    toks = [{"start": m.start(), "end": m.end(), "w": m.group(0)} for m in TOKEN.finditer(text)]
    first = first_name_forms()
    for t in toks:
        w = t["w"]
        cap = w[0].isupper()
        t["lab"] = None
        if not cap or w.lower() in STOP:
            continue
        if len(w) == 2 and w.endswith("."):
            t["lab"] = "init"
        elif w.lower() in first:
            t["lab"] = "first"
        elif PATR.search(w):
            t["lab"] = "patr"
        elif SURNAME.search(w) and len(w) > 4:
            t["lab"] = "surn"
        elif ADJ_SURNAME.search(w):
            t["lab"] = "adj"  # candidate only
        else:
            t["lab"] = "cap"  # unknown capitalized word
    return toks


def adjacent(text, a, b):
    return text[a["end"]:b["start"]].strip() == ""


def resolve_context(text, toks):
    names = {"first", "patr", "init", "surn"}
    for _ in range(2):  # second pass lets new labels support neighbours
        for i, t in enumerate(toks):
            if t["lab"] not in ("cap", "adj"):
                continue
            prev = toks[i - 1] if i and adjacent(text, toks[i - 1], t) else None
            nxt = toks[i + 1] if i + 1 < len(toks) and adjacent(text, t, toks[i + 1]) else None
            nxt2 = (toks[i + 2] if nxt and i + 2 < len(toks) and adjacent(text, nxt, toks[i + 2])
                    else None)
            p, n, n2 = (x["lab"] if x else None for x in (prev, nxt, nxt2))
            if n == "patr" and t["lab"] == "cap":
                t["lab"] = "first"                      # Александр Игоревич
            elif "init" in (p, n):
                t["lab"] = "surn"                       # Петренко Н. В. / Т. П. Петренко
            elif p in ("first", "patr"):
                t["lab"] = "surn"                       # Андрій Ліщинчук, Оксана Миколаївна Ч.
            elif n == "first" and n2 == "patr":
                t["lab"] = "surn"                       # Ковальчинського Тараса Петровича
            elif prev is None and i and TRIGGERS.match(toks[i - 1]["w"]):
                t["lab"] = "surn"                       # пані Вигаданчук
            elif t["lab"] == "adj" and (p in names or n in names):
                t["lab"] = "surn"
    # propagation: other forms of a confirmed surname
    stems = {common.stem(t["w"]) for t in toks if t["lab"] == "surn"}
    for t in toks:
        if t["lab"] in ("cap", "adj") and common.stem(t["w"]) in stems:
            t["lab"] = "surn"
    return toks


def name_spans(text):
    toks = resolve_context(text, label_tokens(text))
    spans = []
    for t in toks:
        if t["lab"] in ("first", "patr", "init", "surn"):
            spans.append({"start": t["start"], "end": t["end"], "category": "PERSON",
                          "rank": -1, "source": "names"})
    # glue "Т. П." into one span so initials cluster together
    merged = []
    for s in spans:
        if merged and text[merged[-1]["end"]:s["start"]].strip() == "":
            merged[-1] = dict(merged[-1], end=s["end"])
        else:
            merged.append(s)
    return merged


QUOTED = re.compile(rf"«[{U}][^»]{{0,40}}»")


def quoted_orgs(text):
    """«Вигаданий Софт»: short quoted names whose words are all capitalized."""
    out = []
    for m in QUOTED.finditer(text):
        words = re.findall(rf"[{U}{L}]+", m.group(0))
        if 1 <= len(words) <= 4 and all(w[0].isupper() for w in words):
            out.append({"start": m.start(), "end": m.end(), "category": "ORG", "source": "quoted"})
    return out


PLACE_AFTER = re.compile(rf"(?<![\w’])(?:[вуВУ]|із|з|зі|до|від|біля|поблизу|під)\s+([{U}][{L}-]+)")


@lru_cache(maxsize=1)
def morph():
    import pymorphy3
    return pymorphy3.MorphAnalyzer(lang="uk")


def place_spans(text):
    """"в Одесі", "із Сосонки": a capitalized inanimate noun after a place preposition."""
    out = []
    for m in PLACE_AFTER.finditer(text):
        w = m.group(1)
        tag = morph().parse(w)[0].tag
        if w.lower() in first_name_forms() or "anim" in tag or "Name" in tag or "Surn" in tag:
            continue
        if tag.POS in ("NOUN", None):
            out.append({"start": m.start(1), "end": m.end(1), "category": "LOC",
                        "source": "place"})
    return out


def mask_spans(text):
    names = common.cluster_persons(text, name_spans(text))
    return regex_rules.find(text) + quoted_orgs(text) + place_spans(text) + names


def run(gold_docs, name="rule"):
    return [common.to_row(d["doc_id"], name, d["text"], mask_spans(d["text"])) for d in gold_docs]
