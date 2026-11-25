"""Score the attacks and put them next to masking recall and k-anonymity.

Usage: python evaluation/score.py DIR [--attacks DIR/attacks] [--out DIR/results] [--model MODEL]

Reads the attack files written by run_attacks.py, the masked and gold documents and the
population. Writes to OUT:

- by_doc.csv      one row per document and condition: protection, k and target ranks
- summary.csv     one row per condition: recall, k, top-1 and top-5, gender accuracy
- reid.csv        re-identification per design, N and condition, with the no-document baseline
- attributes.csv  attribute inference against always guessing the commonest value
- gender.csv      gender accuracy per condition and genre
- k_buckets.csv   top-1 by k for documents whose target name is fully masked

Intervals are 95% bootstrap intervals over documents. In by_doc.csv a rank of 0 means the
target was not among the five answers and an empty rank means the attack was not run.
Documents without rows are left out, and the coverage is printed.
"""
import argparse
import csv
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "data_understanding"))
sys.path.insert(0, str(HERE.parent / "model_training"))
import candidates as cd  # noqa: E402
import common  # noqa: E402
import prompts as pr  # noqa: E402
import uniqueness as uq  # noqa: E402
from run_attacks import UNMASKED, read_rows  # noqa: E402

st = cd.st
BOOTSTRAP = 2000
SEED = 5
BUCKETS = ((1, 1), (2, 5), (6, 50), (51, None))
EXPOSED_BY = {"birth_decade": "birth_year", "oblast": "oblast", "occupation": "occupation"}


# ---------- statistics ----------

def ratio_ci(pairs, seed=SEED):
    """(sum of hits / sum of counts, low, high), resampling the (hits, count) pairs.

    One pair per document: (1, 1) or (0, 1) for a plain accuracy, larger counts when a
    document contributes several rows, (difference, 1) for a paired comparison.
    """
    pairs = list(pairs)
    total = sum(c for _, c in pairs)
    if not total:
        return None, None, None
    rng, values = random.Random(seed), []
    for _ in range(BOOTSTRAP):
        sample = rng.choices(pairs, k=len(pairs))
        count = sum(c for _, c in sample)
        if count:
            values.append(sum(h for h, _ in sample) / count)
    values.sort()
    return (sum(h for h, _ in pairs) / total,
            values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))])


def mean_ci(values):
    return ratio_ci((v, 1) for v in values)


# ---------- protection per document ----------

def protection(doc, row):
    """Masked mentions, entities and spans of one document (open-mention rule)."""
    text, covered = doc["text"], [False] * len(doc["text"])
    for m in row["masked_spans"]:
        for i in range(m["start"], m["end"]):
            covered[i] = True

    def closed(start, end):
        return not common.span_open(text, {"start": start, "end": end}, covered)

    names = [s for s in doc["spans"] if s["category"] == "PERSON"]
    out = Counter()
    for ent in {s["entity_id"] for s in names}:
        hits = [closed(m[0]["start"], m[-1]["end"]) for m in st.mentions(text, names, ent)]
        out["mentions"] += len(hits)
        out["mentions_closed"] += sum(hits)
        out["persons"] += 1
        out["persons_closed"] += all(hits)
        if ent == doc["target_entity_id"]:
            out["target_closed"] = int(all(hits))
    for s in doc["spans"]:
        kind = s["id_type"].lower()
        out[f"{kind}_spans"] += 1
        out[f"{kind}_closed"] += closed(s["start"], s["end"])
    return {k: out[k] for k in ("mentions", "mentions_closed", "persons", "persons_closed",
                                "target_closed", "di_spans", "di_closed", "qi_spans", "qi_closed")}


# ---------- loading ----------

def load_attacks(attack_dir, model=None):
    """{task: rows of one model and the current prompt version}"""
    out = {}
    for task in pr.TASKS:
        rows = [r for r in read_rows(Path(attack_dir) / f"{task}.jsonl").values()
                if r["prompt_version"] == pr.prompt_version(task)]
        out[task] = [r for r in rows if model is None or r["model"] == model]
    models = {r["model"] for rows in out.values() for r in rows}
    if len(models) > 1:
        raise ValueError(f"several attacker models, pick one with --model: {sorted(models)}")
    return out


def load(data_dir, attack_dir=None, model=None):
    d = Path(data_dir)
    gold = {g["doc_id"]: g for g in st.read_jsonl(d / "gold_docs.jsonl")}
    masked = [r for r in st.read_jsonl(d / "masked_docs.jsonl") if not r.get("llm_failed")]
    population = st.load_population(d / "population.csv")
    attacks = load_attacks(attack_dir or d / "attacks", model)
    if any(r["system_or_condition"] == UNMASKED for rows in attacks.values() for r in rows):
        masked += [{"doc_id": i, "system_or_condition": UNMASKED, "masked_spans": []} for i in gold]
    return {"gold": gold, "masked": masked, "population": population, "attacks": attacks,
            "lists": st.read_jsonl(d / "candidates.jsonl"),
            "people": {p["person_id"]: p for p in population}}


def conditions_of(data):
    return list(dict.fromkeys(r["system_or_condition"] for r in data["masked"]))


# ---------- tables ----------

def make_by_doc(data):
    gold, people = data["gold"], data["people"]
    ranks = {}
    for r in data["attacks"]["reid"]:
        ranks[r["doc_id"], r["system_or_condition"], r["design"], r["n"]] = r["target_rank"] or 0
    values = {(r["doc_id"], r["system_or_condition"]): r["values"] for r in data["attacks"]["attr"]}
    out = []
    for r in data["masked"]:
        doc, cond = gold[r["doc_id"]], r["system_or_condition"]
        person = people[doc["person_id"]]
        exposed = uq.exposed_constraints(doc, r)
        row = {"doc_id": doc["doc_id"], "system_or_condition": cond, "genre": doc["genre"],
               "gender": person["gender"], "changed": int(r.get("n_unmasked_gold") != 0),
               "k": uq.k_value(person, data["population"], exposed), **protection(doc, r)}
        for design in cd.DESIGNS:
            for n in cd.SIZES:
                row[f"rank_{design}_{n}"] = ranks.get((doc["doc_id"], cond, design, n))
        truth, said = pr.true_attributes(person), values.get((doc["doc_id"], cond))
        for a in pr.ATTRIBUTES:
            row[f"said_{a}"] = said[a] if said else None
            row[f"right_{a}"] = int(said[a] == truth[a]) if said else None
            row[f"exposed_{a}"] = int(EXPOSED_BY.get(a, "gender") in exposed)
        out.append(row)
    return out


def top(rank, limit):
    return int(0 < rank <= limit)


def group_by(rows, field):
    out = defaultdict(list)
    for r in rows:
        out[r[field]].append(r)
    return out


def reid_table(data, by_doc):
    gold = data["gold"]
    base = {(r["doc_id"], r["design"], r["n"]): r["target_rank"] or 0 for r in data["attacks"]["nodoc"]}
    out = []
    for design in cd.DESIGNS:
        for n in cd.SIZES:
            lists = [r for r in data["lists"] if (r["design"], r["n"]) == (design, n)]
            floor = cd.floor(lists, list(gold.values()), data["population"], cd.guess_both_genre)
            col = f"rank_{design}_{n}"
            full = {r["doc_id"]: r[col] for r in by_doc
                    if r["system_or_condition"] == "gold_full" and r[col] is not None}

            def row(cond, ranks, changed=None):
                """`ranks`: {doc_id: rank}"""
                if not ranks:
                    return
                t1, t5 = mean_ci(top(v, 1) for v in ranks.values()), mean_ci(top(v, 5) for v in ranks.values())
                res = {"design": design, "n": n, "condition": cond, "docs": len(ranks),
                       "top1": t1[0], "top1_low": t1[1], "top1_high": t1[2],
                       "top5": t5[0], "top5_low": t5[1], "top5_high": t5[2],
                       "chance": 1 / n, "rule_without_document": floor}
                for name, other in (("no_document", {d: base[d, design, n] for d in ranks
                                                     if (d, design, n) in base}),
                                    ("gold_full", {d: full[d] for d in ranks if d in full})):
                    diff = mean_ci(top(ranks[d], 1) - top(other[d], 1) for d in other)
                    res.update({f"top1_minus_{name}": diff[0], f"minus_{name}_low": diff[1],
                                f"minus_{name}_high": diff[2]})
                kept = [d for d in ranks if changed is None or changed[d]]
                res["docs_changed"] = len(kept)
                res["top1_changed"] = mean_ci(top(ranks[d], 1) for d in kept)[0]
                out.append(res)

            row("no_document", {d: v for (d, des, m), v in base.items() if (des, m) == (design, n)})
            for cond, rows in group_by(by_doc, "system_or_condition").items():
                rows = [r for r in rows if r[col] is not None]
                row(cond, {r["doc_id"]: r[col] for r in rows},
                    {r["doc_id"]: r["changed"] for r in rows})
    return out


def attribute_table(data, by_doc):
    truths = [pr.true_attributes(data["people"][d["person_id"]]) for d in data["gold"].values()]
    majority = {a: Counter(t[a] for t in truths).most_common(1)[0][1] / len(truths)
                for a in pr.ATTRIBUTES}
    out = []
    for cond, rows in group_by(by_doc, "system_or_condition").items():
        for a in pr.ATTRIBUTES:
            part = [r for r in rows if r[f"right_{a}"] is not None]
            if not part:
                continue
            acc = mean_ci(r[f"right_{a}"] for r in part)
            answered = [r for r in part if r[f"said_{a}"] not in (None, pr.UNKNOWN)]
            res = {"condition": cond, "attribute": a, "docs": len(part), "accuracy": acc[0],
                   "low": acc[1], "high": acc[2], "majority": majority[a],
                   "answered": len(answered) / len(part),
                   "accuracy_answered": mean_ci(r[f"right_{a}"] for r in answered)[0]}
            for name, flag in (("exposed", 1), ("hidden", 0)):
                sub = [r for r in part if r[f"exposed_{a}"] == flag]
                res[f"docs_{name}"] = len(sub)
                res[f"accuracy_{name}"] = mean_ci(r[f"right_{a}"] for r in sub)[0]
            out.append(res)
    return out


def gender_table(by_doc):
    out = []
    for cond, rows in group_by(by_doc, "system_or_condition").items():
        res = {"condition": cond}
        for genre in ("all", "court", "news", "forum"):
            part = [r for r in rows if r["right_gender"] is not None and genre in ("all", r["genre"])]
            res[f"docs_{genre}"] = len(part)
            acc = mean_ci(r["right_gender"] for r in part)
            res.update({genre: acc[0], f"{genre}_low": acc[1], f"{genre}_high": acc[2]})
        if res["docs_all"]:
            out.append(res)
    return out


def bucket_name(low, high):
    return f"{low}" if low == high else f"{low}+" if high is None else f"{low}-{high}"


def bucket_table(by_doc):
    """Top-1 by k, only where the target's name is fully masked; all conditions pooled."""
    out = []
    for n in cd.SIZES:
        col = f"rank_balanced_{n}"
        for low, high in BUCKETS:
            part = [r for r in by_doc if r["target_closed"] and r[col] is not None
                    and r["k"] >= low and (high is None or r["k"] <= high)]
            pairs = [(sum(top(r[col], 1) for r in rows), len(rows))
                     for rows in group_by(part, "doc_id").values()]
            acc = ratio_ci(pairs)
            out.append({"n": n, "k": bucket_name(low, high), "rows": len(part), "docs": len(pairs),
                        "top1": acc[0], "low": acc[1], "high": acc[2]})
    return out


def summary_table(data, by_doc):
    out = []
    for cond, rows in group_by(by_doc, "system_or_condition").items():
        def share(hit, count):
            total = sum(r[count] for r in rows)
            return sum(r[hit] for r in rows) / total if total else None
        res = {"condition": cond, "docs": len(rows),
               "mention_recall": share("mentions_closed", "mentions"),
               "entity_recall": share("persons_closed", "persons"),
               "target_closed": mean_ci(r["target_closed"] for r in rows)[0],
               "di_recall": share("di_closed", "di_spans"), "qi_recall": share("qi_closed", "qi_spans"),
               "pct_k1": mean_ci(r["k"] == 1 for r in rows)[0],
               "median_k": statistics.median(r["k"] for r in rows)}
        for n in sorted(cd.SIZES, reverse=True):
            ranks = [r[f"rank_balanced_{n}"] for r in rows if r[f"rank_balanced_{n}"] is not None]
            for limit in (1, 5):
                res[f"top{limit}_n{n}"] = mean_ci(top(v, limit) for v in ranks)[0]
        res["gender_accuracy"] = mean_ci(r["right_gender"] for r in rows
                                         if r["right_gender"] is not None)[0]
        out.append(res)
    return out


def coverage(data):
    """Lines on what is missing from the attack files."""
    docs, conds = len(data["gold"]), [c for c in conditions_of(data) if c != UNMASKED]
    per = Counter((r["system_or_condition"], r["design"], r["n"]) for r in data["attacks"]["reid"])
    out = []
    for n in cd.SIZES:
        have = sum(per[c, "balanced", n] for c in conds)
        out.append(f"reid balanced N={n}: {have}/{docs * len(conds)}")
    base = Counter((r["design"], r["n"]) for r in data["attacks"]["nodoc"])
    out += [f"nodoc {design} N={n}: {base[design, n]}/{docs}" for design in cd.DESIGNS for n in cd.SIZES]
    out.append(f"attr: {sum(r['system_or_condition'] != UNMASKED for r in data['attacks']['attr'])}"
               f"/{docs * len(conds)}")
    bad = sum(not r["parse_ok"] for rows in data["attacks"].values() for r in rows)
    out.append(f"unreadable replies: {bad} of {sum(len(v) for v in data['attacks'].values())}")
    return out


# ---------- output ----------

def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: f"{v:.4f}" if isinstance(v, float) else v for k, v in r.items()})


def pct(value):
    return "-" if value is None else f"{100 * value:.1f}"


def print_table(rows, columns, width=10):
    """`columns`: (key, heading) pairs; fractions are printed as percentages."""
    if not rows:
        return
    first = max(len(str(r[columns[0][0]])) for r in rows) + 2
    print(f"{columns[0][1]:{first}}" + "".join(f"{h:>{width}}" for _, h in columns[1:]))
    for r in rows:
        cells = [r[k] if k in ("median_k", "rows", "docs") else pct(r[k]) for k, _ in columns[1:]]
        print(f"{r[columns[0][0]]!s:{first}}" + "".join(f"{c!s:>{width}}" for c in cells))


def score(data):
    by_doc = make_by_doc(data)
    return {"by_doc": by_doc, "summary": summary_table(data, by_doc),
            "reid": reid_table(data, by_doc), "attributes": attribute_table(data, by_doc),
            "gender": gender_table(by_doc), "k_buckets": bucket_table(by_doc)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--attacks", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--model")
    args = ap.parse_args(argv)
    data = load(args.data_dir, args.attacks, args.model)
    tables = score(data)
    out = args.out or args.data_dir / "results"
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        write_csv(out / f"{name}.csv", rows)
    print("\n".join(coverage(data)))
    print("\nPer condition (percent):")
    print_table(tables["summary"], [("condition", "condition"), ("mention_recall", "mentions"),
                                    ("entity_recall", "entities"), ("target_closed", "target"),
                                    ("qi_recall", "QI"), ("pct_k1", "k=1"), ("median_k", "median k"),
                                    ("top1_n100", "top1 100"), ("top5_n100", "top5 100"),
                                    ("top1_n10", "top1 10"), ("gender_accuracy", "gender")])
    for design in cd.DESIGNS:
        for n in sorted(cd.SIZES, reverse=True):
            rows = [r for r in tables["reid"] if (r["design"], r["n"]) == (design, n)]
            if rows:
                print(f"\nRe-identification, {design}, N = {n}; rule without the document: "
                      f"{pct(rows[0]['rule_without_document'])}")
                print_table(rows, [("condition", "condition"), ("docs", "docs"), ("top1", "top1"),
                                   ("top1_low", "low"), ("top1_high", "high"), ("top5", "top5"),
                                   ("top1_minus_no_document", "-no doc"),
                                   ("top1_minus_gold_full", "-full")])
    print("\nTop-1 by k, target name fully masked:")
    for n in cd.SIZES:
        print(f"N = {n}")
        print_table([r for r in tables["k_buckets"] if r["n"] == n],
                    [("k", "k"), ("rows", "rows"), ("docs", "docs"), ("top1", "top1"),
                     ("low", "low"), ("high", "high")])
    print(f"\nwrote {', '.join(f'{n}.csv' for n in tables)} to {out}")
    return tables


if __name__ == "__main__":
    main()
