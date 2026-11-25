"""Shared pieces for the maskers: spans to placeholders, name clustering, dev scoring.

A system span is a dict {start, end, category} with an optional `key`: spans with the
same (category, key) get the same placeholder. Systems never see gold entity ids.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed_tools as st  # noqa: E402

WORD = re.compile(r"[\w’]+")
UPPER = "А-ЯІЇЄҐA-Z"

# Inflection endings stripped to get a crude stem; longest first.
ENDINGS = sorted("""ого ому ими ій ою ові еві єві ем єм ом ам ах ях ям ий ій их им
                    у ю а я і и е є о""".split(), key=len, reverse=True)


# ---------- spans ----------

def tidy(text, s):
    """Strip whitespace and punctuation (except «») from the ends of a span."""
    start, end = s["start"], s["end"]
    while start < end and (text[start].isspace() or text[start] in ",.;:!?()\"'-—–"):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",;:!?()\"'-—–"):
        end -= 1
    # drop a sentence-final dot, but keep abbreviations ("Н. В.", "р. н.", "обл.")
    if (end > start and text[end - 1] == "."
            and not re.search(r"(?:\b\w|обл|грн|буд|вул|кв|смт)\.$", text[start:end])):
        end -= 1
    return dict(s, start=start, end=end)


def resolve_overlaps(spans):
    """Keep non-overlapping spans; longer spans win, then lower `rank`, then earlier."""
    order = sorted(spans, key=lambda s: (s["start"] - s["end"], s.get("rank", 0), s["start"]))
    kept = []
    for s in order:
        if s["end"] > s["start"] and all(s["end"] <= k["start"] or k["end"] <= s["start"]
                                         for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s["start"])


def stem(word):
    w = word.lower().replace("’", "")
    for e in ENDINGS:
        if w.endswith(e) and len(w) - len(e) >= 3:
            return w[:-len(e)]
    return w


def default_key(text, s):
    return " ".join(stem(w) for w in WORD.findall(text[s["start"]:s["end"]]))


def to_row(doc_id, system, text, spans):
    """Build a masked_docs.jsonl row from system spans."""
    spans = resolve_overlaps([tidy(text, s) for s in spans])
    groups = [{"start": s["start"], "end": s["end"], "category": s["category"],
               "entity_id": s.get("key") or default_key(text, s)} for s in spans]
    masked_text, masked_spans = st.apply_masking(text, groups)
    return {"doc_id": doc_id, "system_or_condition": system,
            "masked_text": masked_text, "masked_spans": masked_spans}


# ---------- person clustering ----------

INITIALS = re.compile(rf"^[{UPPER}]\.\s?(?:[{UPPER}]\.)?$")
PATRONYMIC = re.compile(r"(?:ович|евич|євич|ьович|йович|івн|ївн|овн|евн)\w{0,3}$")


def cluster_persons(text, spans):
    """Give PERSON spans a shared `key` when they look like the same person.

    A mention is a run of adjacent PERSON spans (e.g. "Ковальчинського Тараса Петровича").
    Mentions sharing a non-initial word stem are merged ("Оксану Вигаданчук" + "пані
    Вигаданчук"). A bare first name or bare initials join the first cluster that has a
    matching word or initials.
    """
    persons = sorted((s for s in spans if s["category"] == "PERSON"), key=lambda s: s["start"])
    mentions = []
    for s in persons:
        if mentions and text[mentions[-1][-1]["end"]:s["start"]].strip() == "":
            mentions[-1].append(s)
        else:
            mentions.append([s])

    def words(m):
        return [w for s in m for w in re.findall(rf"[{UPPER}][\w’]*\.?", text[s["start"]:s["end"]])]

    clusters = []  # each: {"stems": set, "initials": set, "spans": list}
    for m in mentions:
        ws = words(m)
        full = [w for w in ws if not w.endswith(".")]
        inits = "".join(w[0] for w in ws if w.endswith("."))
        stems = {stem(w) for w in full}
        letters = set()
        if len(full) >= 2:  # first + patronymic letters, in either name order
            pats = [w for w in full if PATRONYMIC.search(w.lower())]
            others = [w for w in full if w not in pats]
            for p in pats:
                letters |= {o[0] + p[0] for o in others}
        hit = next((c for c in clusters if stems & c["stems"]), None)
        if hit is None and inits:
            hit = next((c for c in clusters if inits in c["initials"]), None)
        if hit is None:
            hit = {"stems": set(), "initials": set(), "spans": []}
            clusters.append(hit)
        hit["stems"] |= stems
        hit["initials"] |= letters | ({inits} if inits and full else set())
        hit["spans"] += m
    out = []
    for i, c in enumerate(clusters):
        out += [dict(s, key=f"person{i}") for s in c["spans"]]
    return out + [s for s in spans if s["category"] != "PERSON"]


# ---------- dev scoring (reported numbers come from data_understanding/recall.py) ----------

def span_open(text, span, covered):
    """Official rule: open if any word of the span is less than half masked."""
    for w in WORD.finditer(text, span["start"], span["end"]):
        n = sum(1 for i in range(w.start(), w.end()) if covered[i])
        if n * 2 < w.end() - w.start():
            return True
    return False


def score(gold_docs, rows):
    """{system: stats} with span recall by group, entity recall and over-masking."""
    gold = {d["doc_id"]: d for d in gold_docs}
    hit, tot, misses = defaultdict(Counter), defaultdict(Counter), defaultdict(list)
    ent_hit, ent_tot, extra, masked_chars = Counter(), Counter(), Counter(), Counter()
    for r in rows:
        d, sysname = gold[r["doc_id"]], r["system_or_condition"]
        covered = [False] * len(d["text"])
        for m in r["masked_spans"]:
            for i in range(m["start"], m["end"]):
                covered[i] = True
        in_gold = [False] * len(d["text"])
        ents = defaultdict(lambda: [True, "QI"])
        for s in d["spans"]:
            for i in range(s["start"], s["end"]):
                in_gold[i] = True
            ok = not span_open(d["text"], s, covered)
            case = None if s["case"] is None else ("nom" if s["case"] == "nom" else "oblique")
            groups = ["all", f"cat={s['category']}", f"type={s['id_type']}"]
            if s["category"] == "PERSON":
                groups += [f"case={case}", f"part={s['name_part']}"]
            for g in groups:
                tot[sysname][g] += 1
                hit[sysname][g] += ok
            if not ok:
                misses[sysname].append((d["doc_id"], s["category"], s["case"], s["text"]))
            e = ents[s["entity_id"]]
            e[0] &= ok
            if s["id_type"] == "DI":
                e[1] = "DI"
        for ok, typ in ents.values():
            for g in ("all", typ):
                ent_tot[(sysname, g)] += 1
                ent_hit[(sysname, g)] += ok
        # whitespace inside a merged "Surname First Patronymic" placeholder is not over-masking
        solid = [not ch.isspace() for ch in d["text"]]
        masked_chars[sysname] += sum(c and s for c, s in zip(covered, solid))
        extra[sysname] += sum(1 for c, g, s in zip(covered, in_gold, solid) if c and s and not g)
    out = {}
    for sysname in tot:
        out[sysname] = {
            "span_recall": {g: hit[sysname][g] / n for g, n in sorted(tot[sysname].items())},
            "span_n": dict(tot[sysname]),
            "entity_recall": {g: ent_hit[(sysname, g)] / ent_tot[(sysname, g)]
                              for g in ("all", "DI", "QI") if ent_tot[(sysname, g)]},
            "overmask_share": extra[sysname] / max(masked_chars[sysname], 1),
            "misses": misses[sysname],
        }
    return out


def print_scores(scores, groups=("all", "type=DI", "type=QI", "cat=PERSON", "case=nom",
                                 "case=oblique", "part=diminutive", "part=initials")):
    head = f"{'system':24}" + "".join(f"{g:>14}" for g in groups) + f"{'ent_DI':>9}{'ent_QI':>9}{'over':>7}"
    print(head)
    for name, s in scores.items():
        cells = "".join(f"{s['span_recall'].get(g, float('nan')):>14.2f}" for g in groups)
        e = s["entity_recall"]
        print(f"{name:24}{cells}{e.get('DI', float('nan')):>9.2f}{e.get('QI', float('nan')):>9.2f}"
              f"{s['overmask_share']:>7.2f}")
