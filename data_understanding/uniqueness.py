"""k-anonymity: number of people matching what a masked doc still exposes.

Usage: python data_understanding/uniqueness.py [DATA_DIR]
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seed_tools import SEED_DIR, load_population, read_jsonl  # noqa: E402

NAME_COL = {"first": "first_name", "diminutive": "first_name",
            "surname": "surname", "patronymic": "patronymic"}
IMPLIES = {"settlement": {"oblast", "settlement_type"}}


def exposed_spans(gold_doc, masked_row):
    cov = [(m["start"], m["end"]) for m in masked_row["masked_spans"]]
    return [s for s in gold_doc["spans"]
            if not any(a < s["end"] and s["start"] < b for a, b in cov)]


def exposed_constraints(gold_doc, masked_row, gender_always=True):
    """Return {column: tolerance} for the target."""
    target = gold_doc["target_entity_id"]
    cons = {"gender": 0} if gender_always else {}
    for s in exposed_spans(gold_doc, masked_row):
        if s["entity_id"] == target and s["category"] == "PERSON":
            if s["name_part"] in NAME_COL:
                cons[NAME_COL[s["name_part"]]] = 0
            elif s["name_part"] == "initials":
                cons["initials"] = 0
            continue
        if s["attr"] and s.get("owner", target) == target:
            col = s["attr"]
            tol = 1 if (col == "birth_year" and s["category"] == "DEM") else 0
            cons[col] = min(cons.get(col, tol), tol)
            for extra in IMPLIES.get(col, ()):
                cons[extra] = 0
    return cons


def _match(p, t, col, tol):
    if col == "initials":
        return (p["first_name"][:1], p["patronymic"][:1]) == (t["first_name"][:1], t["patronymic"][:1])
    if col == "birth_year":
        return abs(int(p["birth_year"]) - int(t["birth_year"])) <= tol
    return p[col] == t[col]


def k_value(target_row, population, cons):
    return sum(all(_match(p, target_row, c, tol) for c, tol in cons.items()) for p in population)


def score(population, gold_docs, masked_rows, gender_always=True):
    """k and exposed columns per (doc, condition)."""
    gold = {d["doc_id"]: d for d in gold_docs}
    by_id = {p["person_id"]: p for p in population}
    out = []
    for r in masked_rows:
        g = gold[r["doc_id"]]
        cons = exposed_constraints(g, r, gender_always)
        out.append({"doc_id": r["doc_id"], "system_or_condition": r["system_or_condition"],
                    "k": k_value(by_id[g["person_id"]], population, cons),
                    "exposed": sorted(cons)})
    return out


def summarize(rows):
    by_cond = {}
    for r in rows:
        by_cond.setdefault(r["system_or_condition"], []).append(r["k"])
    return {c: {"n": len(ks), "pct_k1": 100 * sum(k == 1 for k in ks) / len(ks),
                "median_k": statistics.median(ks)} for c, ks in by_cond.items()}


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else SEED_DIR
    pop = load_population(d / "population.csv")
    rows = score(pop, read_jsonl(d / "gold_docs.jsonl"), read_jsonl(d / "masked_docs.jsonl"))
    for r in rows:
        print(f'{r["doc_id"]} {r["system_or_condition"]:22s} k={r["k"]:3d}  {r["exposed"]}')
    print()
    for c, s in summarize(rows).items():
        print(f'{c:22s} n={s["n"]:3d}  k=1: {s["pct_k1"]:5.1f}%  median k={s["median_k"]}')
