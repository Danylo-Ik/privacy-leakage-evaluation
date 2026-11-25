"""Candidate lists for the re-identification attack.

Usage: python evaluation/candidates.py DIR [--out FILE]
Reads DIR/gold_docs.jsonl, population.csv and targets.csv, writes DIR/candidates.jsonl:
one row per (document, design, N), so every masker is attacked with the same lists.

A group is a target plus their look-alikes. The document's own group is always in the list.
Two designs fill the rest:

- balanced: whole groups of other targets of the same genre.
- random: random people from the population.

Random lists can be solved without the document. Every target has an event and look-alikes,
while most other people have neither, so "the one with an event and look-alikes" is nearly
always the target. Balanced lists are made of groups that all look like that. The script
prints how often such rules find the target without reading the text.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed_tools as st  # noqa: E402

SIZES = (10, 100)
DESIGNS = ("balanced", "random")
SEED = 11
MAX_TRIES = 200

GENDER = {"F": "жінка", "M": "чоловік"}
PLACE = {"city": "місто", "town": "містечко", "village": "село"}
FAMILY = {"married": "у шлюбі", "single": "не у шлюбі", "divorced": "у розлученні",
          "widowed": {"F": "вдова", "M": "вдівець"}}
EVENT = {"court_wage_claim": "позов про стягнення заробітної плати",
         "court_loan_claim": "позов про стягнення боргу за договором позики",
         "award_teacher_of_year": "нагорода «Вчитель року»",
         "grant_farm": "грант на розвиток фермерського господарства",
         "dismissal": "звільнення з роботи"}
EVENT_GENRE = {"court_wage_claim": "court", "court_loan_claim": "court",
               "award_teacher_of_year": "news", "grant_farm": "news", "dismissal": "forum"}


# ---------- profiles ----------

def event_text(event):
    if not event:
        return "немає"
    kind, year = event.rsplit("_", 1)
    return f"{EVENT[kind]} ({year})"


def profile(p):
    """One-line profile with the full name in the nominative. Never shows person_id."""
    family = FAMILY[p["family_status"]]
    if isinstance(family, dict):
        family = family[p["gender"]]
    return "; ".join([f"{p['surname']} {p['first_name']} {p['patronymic']}", GENDER[p["gender"]],
                      f"{p['birth_year']} р. н.",
                      f"{p['oblast']} обл., {PLACE[p['settlement_type']]} {p['settlement']}",
                      p["occupation"], family, f"дітей: {p['children']}",
                      f"подія: {event_text(p['event'])}"])


def labels(n):
    """C001, C002, ... for a list of n candidates."""
    return [f"C{i + 1:03d}" for i in range(n)]


# ---------- lists ----------

def group(target):
    """The target and their look-alikes."""
    return [target["person_id"]] + target["lookalikes"].split()


def fill_exactly(pool, room, rng):
    """Whole groups from the pool with exactly `room` people in total. No group is cut,
    because a target without look-alikes would give itself away as a filler."""
    for _ in range(MAX_TRIES):
        left, out = room, []
        for g in rng.sample(pool, len(pool)):
            if len(g) <= left and left - len(g) != 1:
                out += g
                left -= len(g)
            if left == 0:
                return out
    raise ValueError(f"no combination of groups has exactly {room} people")


def target_slots(n_docs, n, rng):
    """Target positions for all documents, spread evenly over the list and shuffled.
    Models tend to favour some positions, so the target must not cluster in any of them."""
    slots = [i * n // n_docs for i in range(n_docs)]
    rng.shuffle(slots)
    return slots


def candidate_list(doc, design, n, slot, population, targets, seed=SEED):
    """Person ids: the document's own group plus fillers, n in total, shuffled, with the
    target at index `slot`."""
    rng = random.Random(f"{seed}:{design}:{n}:{doc['doc_id']}:{doc['person_id']}")
    own = group(targets[doc["person_id"]])
    if design == "balanced":
        pool = [group(t) for t in targets.values()
                if t["genre"] == doc["genre"] and t["person_id"] != doc["person_id"]]
        rest = fill_exactly(pool, n - len(own), rng)
    elif design == "random":
        rest = rng.sample([p["person_id"] for p in population if p["person_id"] not in own],
                          n - len(own))
    else:
        raise ValueError(f"unknown design {design}")
    others = own[1:] + rest
    rng.shuffle(others)
    return others[:slot] + own[:1] + others[slot:]


def make_rows(gold_docs, population, targets, designs=DESIGNS, sizes=SIZES, seed=SEED, generated=None):
    """`generated`: all documents as first generated, so that dropping one later does not
    move the target in the lists of the others."""
    rows, kept = [], {d["doc_id"] for d in gold_docs}
    generated = generated or gold_docs
    for design in designs:
        for n in sizes:
            slots = target_slots(len(generated), n, random.Random(f"{seed}:{design}:{n}"))
            rows += [{"doc_id": d["doc_id"], "design": design, "n": n,
                      "candidates": candidate_list(d, design, n, slot, population, targets, seed)}
                     for d, slot in zip(generated, slots) if d["doc_id"] in kept]
    return rows


def validate(rows, gold_docs, population, targets):
    errors, gold = [], {d["doc_id"]: d for d in gold_docs}
    ids = {p["person_id"] for p in population}
    seen = Counter((r["doc_id"], r["design"], r["n"]) for r in rows)
    errors += [f"{key}: {count} rows" for key, count in seen.items() if count > 1]
    for design, n in sorted({(r["design"], r["n"]) for r in rows}):
        errors += [f"{doc_id}: no {design} list with n={n}" for doc_id in gold
                   if (doc_id, design, n) not in seen]
    for r in rows:
        tag, cands = f"{r['doc_id']}/{r['design']}/{r['n']}", r["candidates"]
        if r["doc_id"] not in gold:
            errors.append(f"{tag}: doc_id not in gold")
            continue
        if len(cands) != r["n"] or len(set(cands)) != r["n"]:
            errors.append(f"{tag}: {len(set(cands))} distinct of {len(cands)} candidates, "
                          f"expected {r['n']}")
        if not set(cands) <= ids:
            errors.append(f"{tag}: candidates not in population")
        missing = set(group(targets[gold[r["doc_id"]]["person_id"]])) - set(cands)
        if missing:
            errors.append(f"{tag}: target or look-alikes missing: {sorted(missing)}")
    return errors


# ---------- how far a guesser gets without the document ----------

def _lookalike_key(p):
    return p["gender"], p["birth_year"], p["oblast"], p["occupation"]


def _event_genre(p):
    return EVENT_GENRE[p["event"].rsplit("_", 1)[0]] if p["event"] else None


def keep(people, test):
    """The people that pass the test, or everyone if nobody does."""
    return [p for p in people if test(p)] or people


def guess_event(people, genre):
    return keep(people, lambda p: p["event"])


def guess_lookalikes(people, genre):
    count = Counter(_lookalike_key(p) for p in people)
    return keep(people, lambda p: count[_lookalike_key(p)] > 1)


def guess_both(people, genre):
    return guess_event(guess_lookalikes(people, genre), genre)


def guess_both_genre(people, genre):
    return keep(guess_both(people, genre), lambda p: _event_genre(p) == genre)


GUESSES = {"event": guess_event, "look-alikes": guess_lookalikes, "both": guess_both,
           "both + genre": guess_both_genre}


def floor(rows, gold_docs, population, guess):
    """Expected top-1 accuracy of a guess that picks at random among the people it keeps."""
    by_id = {p["person_id"]: p for p in population}
    gold = {d["doc_id"]: d for d in gold_docs}
    total = 0
    for r in rows:
        d = gold[r["doc_id"]]
        left = [p["person_id"] for p in guess([by_id[c] for c in r["candidates"]], d["genre"])]
        total += (d["person_id"] in left) / len(left)
    return total / len(rows)


def print_floors(rows, gold_docs, population):
    print(f"{'design':10}{'N':>5}{'chance':>9}" + "".join(f"{name:>14}" for name in GUESSES))
    for design, n in sorted({(r["design"], r["n"]) for r in rows}):
        part = [r for r in rows if (r["design"], r["n"]) == (design, n)]
        cells = "".join(f"{floor(part, gold_docs, population, g):>14.1%}" for g in GUESSES.values())
        print(f"{design:10}{n:>5}{1 / n:>9.1%}{cells}")


# ---------- files ----------

def load_targets(path):
    """{person_id: row of targets.csv}"""
    return {t["person_id"]: t for t in st.load_population(path)}


def load_generated(data_dir):
    """Documents before the manual fixes, or None."""
    path = Path(data_dir) / "gold_docs.generated.jsonl"
    return st.read_jsonl(path) if path.exists() else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    gold = st.read_jsonl(args.data_dir / "gold_docs.jsonl")
    population = st.load_population(args.data_dir / "population.csv")
    targets = load_targets(args.data_dir / "targets.csv")
    rows = make_rows(gold, population, targets, generated=load_generated(args.data_dir))
    out = args.out or args.data_dir / "candidates.jsonl"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    errors = validate(rows, gold, population, targets)
    print(f"wrote {len(rows)} lists for {len(gold)} documents to {out}; "
          + ("valid" if not errors else f"{len(errors)} errors"))
    for e in errors[:20]:
        print("  ", e)
    print("\nTop-1 of a guess that never reads the document:")
    print_floors(rows, gold, population)
    return not errors


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
