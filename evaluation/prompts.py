"""Attack prompts and reply parsing.

Usage: python evaluation/prompts.py DIR DOC_ID [--task reid|nodoc|attr] [--condition gold_full]
                                    [--design balanced] [--n 10]
Prints the messages the attacker would get. No model is called.

Prompt texts are in docs/prompts/attack_reid_v1.md and attack_attr_v1.md.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "data_understanding"))
import candidates as cd  # noqa: E402
from fact_plan import FEMININE  # noqa: E402
from generate import fill, load_prompt  # noqa: E402

st = cd.st
PROMPT_DIR = HERE.parent / "docs" / "prompts"
REID_VERSION = "attack_reid_v1"
ATTR_VERSION = "attack_attr_v1"
TASKS = ("reid", "nodoc", "attr")
TOP = 5
ATTRIBUTES = ("gender", "birth_decade", "oblast", "occupation")
DECADES = (1960, 1970, 1980, 1990, 2000)
UNKNOWN = "unknown"


# ---------- messages ----------

def prompt_version(task):
    return ATTR_VERSION if task == "attr" else REID_VERSION


def load_task_prompt(task):
    return load_prompt(PROMPT_DIR / f"{prompt_version(task)}.md")


def _messages(system, user):
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def reid_messages(people, document=None, prompt=None):
    """Re-identification, or the no-document baseline when `document` is None.

    `people` are population rows in list order; the labels follow that order.
    """
    prompt = prompt or load_task_prompt("reid")
    lines = [f"{label}. {cd.profile(p)}" for label, p in zip(cd.labels(len(people)), people)]
    head = fill(prompt["candidates"], candidates="\n".join(lines))
    tail = prompt["no_document"] if document is None else fill(prompt["document"], document=document)
    return _messages(prompt["system"], f"{head}\n\n{tail}")


def closed_lists(population):
    """Allowed oblasts and occupations, sorted."""
    return {"oblast": sorted({p["oblast"] for p in population}),
            "occupation": sorted({p["occupation"] for p in population})}


def attr_messages(document, lists, prompt=None):
    prompt = prompt or load_task_prompt("attr")
    system = fill(prompt["system"], oblasts=", ".join(lists["oblast"]),
                  occupations=", ".join(lists["occupation"]))
    return _messages(system, fill(prompt["user"], document=document))


def true_attributes(person):
    return {"gender": person["gender"], "birth_decade": int(person["birth_year"]) // 10 * 10,
            "oblast": person["oblast"], "occupation": person["occupation"]}


# ---------- parsing ----------

def find_json(reply, key):
    """The last JSON object in the reply that has `key`, or None. Text, code fences and
    other objects around it are ignored."""
    decoder, found, pos = json.JSONDecoder(), None, 0
    while (start := reply.find("{", pos)) >= 0:
        try:
            obj, pos = decoder.raw_decode(reply, start)
        except json.JSONDecodeError:
            pos = start + 1
            continue
        if isinstance(obj, dict) and key in obj:
            found = obj
    return found


# the letter may be Latin or Cyrillic, and the profile may follow the label
LABEL = re.compile(r"\s*[CСcс]?\s*0*([1-9]\d{0,3})(?!\d)")


def parse_label(value, n):
    """1-based position in the candidate list, or None."""
    m = LABEL.match(str(value)) if isinstance(value, (str, int)) else None
    return int(m.group(1)) if m and int(m.group(1)) <= n else None


def parse_ranking(reply, n):
    """{"ranking": labels, "clues": text, "errors": [...], "retry": bool}.

    A label that is not in the list becomes None and keeps its place, so an invented
    label never promotes the ones behind it. Repeats are dropped. An unreadable reply has
    an empty ranking. Repeats alone are not worth another try: the ranking is usable, and
    a retry would replace an answer given at temperature 0.
    """
    obj = find_json(reply or "", "ranking")
    if obj is None or not isinstance(obj["ranking"], list):
        return {"ranking": [], "clues": "", "errors": ["no ranking in the reply"], "retry": True}
    errors, out, all_labels, repeats = [], [], cd.labels(n), 0
    for value in obj["ranking"][:TOP]:
        i = parse_label(value, n)
        if i is None:
            errors.append(f"label {value!r} is not in the list")
            out.append(None)
        elif all_labels[i - 1] in out:
            errors.append(f"label {value!r} is repeated")
            repeats += 1
        else:
            out.append(all_labels[i - 1])
    if len(out) < TOP:
        errors.append(f"{len(out)} labels instead of {TOP}")
    return {"ranking": out, "clues": str(obj.get("clues", "")), "errors": errors,
            "retry": None in out or len(out) + repeats < TOP}


def _fold(text):
    return re.sub(r"\s+", " ", st.normalize(str(text))).strip(" .«»\"").casefold()


GENDER_WORDS = {"f": "F", "female": "F", "woman": "F", "ж": "F", "жінка": "F", "жіноча": "F",
                "m": "M", "male": "M", "man": "M", "ч": "M", "чоловік": "M", "чоловіча": "M"}


def parse_value(attr, value, lists):
    """An allowed value, "unknown", or None if the answer fits nothing."""
    word = _fold(value)
    if word in ("", UNKNOWN, "невідомо", "none", "null"):
        return UNKNOWN
    if attr == "gender":
        return GENDER_WORDS.get(word)
    if attr == "birth_decade":
        m = re.match(r"(\d{3})\d", word)
        decade = int(m.group(1)) * 10 if m else None
        return decade if decade in DECADES else None
    if attr == "oblast":
        word = re.sub(r"\s*(область|обл\.?|oblast)$", "", word)
    allowed = {_fold(v): v for v in lists[attr]}
    if attr == "occupation":
        allowed.update({_fold(f): m for m, f in FEMININE.items() if m in lists[attr]})
    return allowed.get(word)


def parse_attributes(reply, lists):
    """{"values": {attr: value}, "clues": text, "errors": [...]}. Missing or unusable
    answers are None."""
    obj = find_json(reply or "", "gender")
    if obj is None:
        return {"values": dict.fromkeys(ATTRIBUTES), "clues": "",
                "errors": ["no attributes in the reply"], "retry": True}
    values, errors = {}, []
    for attr in ATTRIBUTES:
        if attr not in obj:
            values[attr] = None
            errors.append(f"{attr} is missing")
            continue
        values[attr] = parse_value(attr, obj[attr], lists)
        if values[attr] is None:
            errors.append(f"{attr}: {obj[attr]!r} is not an allowed value")
    return {"values": values, "clues": str(obj.get("clues", "")), "errors": errors,
            "retry": bool(errors)}


# ---------- preview ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("doc_id")
    ap.add_argument("--task", choices=TASKS, default="reid")
    ap.add_argument("--condition", default="gold_full")
    ap.add_argument("--design", choices=cd.DESIGNS, default="balanced")
    ap.add_argument("--n", type=int, choices=cd.SIZES, default=10)
    args = ap.parse_args(argv)

    population = st.load_population(args.data_dir / "population.csv")
    by_id = {p["person_id"]: p for p in population}
    text = next(r["masked_text"] for r in st.read_jsonl(args.data_dir / "masked_docs.jsonl")
                if (r["doc_id"], r["system_or_condition"]) == (args.doc_id, args.condition))
    if args.task == "attr":
        messages = attr_messages(text, closed_lists(population))
    else:
        row = next(r for r in st.read_jsonl(args.data_dir / "candidates.jsonl")
                   if (r["doc_id"], r["design"], r["n"]) == (args.doc_id, args.design, args.n))
        messages = reid_messages([by_id[c] for c in row["candidates"]],
                                 text if args.task == "reid" else None)
    for m in messages:
        print(f"=== {m['role']} ({len(m['content'])} characters)\n{m['content']}\n")


if __name__ == "__main__":
    main()
