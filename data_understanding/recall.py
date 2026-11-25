"""Recall metrics for masked documents (DU-9). Definitions: docs/methods.md.

Usage: python data_understanding/recall.py [DIR] [--with-k] [--boot N] [--out DIR]

Reads DIR/gold_docs.jsonl and DIR/masked_docs.jsonl (default data/full), prints one row per
system or condition and writes recall_report.csv and recall_by_doc.jsonl.

- mention: adjacent name parts of one person are one mention; any other span is its own
- open: a mention is open if any of its words is less than half covered by masked spans
  (the official rule). Labels are ignored: hiding a name as ОРГАНІЗАЦІЯ still counts.
- mention recall: closed mentions / all mentions
- entity recall: share of persons with every mention closed; risk by name = 1 - that
- target protected: every mention of the target's name is closed
- fully protected: every span the target owns (name and attributes) is closed
- over-masking: share of masked characters outside gold spans

Splits by DI/QI, category, case (nom vs oblique) and genre are per mention; the split
by name part is per span (a mention can hold several parts). 95% intervals come from
resampling documents, the same resample for every system.
"""
import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import seed_tools as st  # noqa: E402

DEFAULT_DIR = HERE.parent / "data" / "full"
WORD = re.compile(r"[\w’]+")
BOOT = 1000
CI_METRICS = ["mention_recall", "entity_recall", "target_protected", "fully_protected"]
# metric name -> (numerator key, denominator key) in the per-doc counts
METRICS = {
    "mention_recall": ("m_closed:all", "m:all"),
    "entity_recall": ("p_safe", "p"),
    "target_protected": ("t_safe", "t"),
    "fully_protected": ("f_safe", "t"),
    "entity_recall_all": ("e_safe", "e"),
    "over_masking": ("masked_out", "masked"),
}


def coverage(text, masked_spans):
    covered = [False] * len(text)
    for m in masked_spans:
        for i in range(max(0, m["start"]), min(len(text), m["end"])):
            covered[i] = True
    return covered


def is_open(text, start, end, covered):
    """True if any word in [start, end) is less than half masked."""
    for w in WORD.finditer(text, start, end):
        if 2 * sum(covered[w.start():w.end()]) < w.end() - w.start():
            return True
    return False


def doc_mentions(doc):
    """Mentions as lists of spans: name parts grouped per person, every other span alone."""
    spans, out = doc["spans"], []
    people = {s["entity_id"] for s in spans if s["category"] == "PERSON"}
    for ent in people:
        out += st.mentions(doc["text"], [s for s in spans if s["category"] == "PERSON"], ent)
    out += [[s] for s in spans if s["category"] != "PERSON"]
    return sorted(out, key=lambda m: m[0]["start"])


def mention_case(m):
    cases = [s.get("case") for s in m]
    if all(c is None for c in cases):
        return None
    return "nom" if all(c in (None, "nom") for c in cases) else "oblique"


def groups(m, doc, target):
    s0 = m[0]
    g = ["all", f"type={'DI' if any(s.get('id_type') == 'DI' for s in m) else 'QI'}",
         f"cat={s0['category']}", f"genre={doc.get('genre')}"]
    if s0["category"] == "PERSON":
        g.append(f"case={mention_case(m)}")
        g.append("who=target" if s0["entity_id"] == target else "who=other")
    return g


def score_doc(doc, row):
    """Counts for one (doc, masked row) and the list of open mentions."""
    text, target = doc["text"], doc.get("target_entity_id")
    covered = coverage(text, row["masked_spans"])
    c, open_mentions = Counter(), []
    entity_open = {}
    for m in doc_mentions(doc):
        op = any(is_open(text, s["start"], s["end"], covered) for s in m)
        for g in groups(m, doc, target):
            c[f"m:{g}"] += 1
            c[f"m_closed:{g}"] += not op
        ent = m[0]["entity_id"]
        entity_open[ent] = entity_open.get(ent, False) or op
        if op:
            open_mentions.append({"text": text[m[0]["start"]:m[-1]["end"]], "start": m[0]["start"],
                                  "end": m[-1]["end"], "category": m[0]["category"],
                                  "id_type": m[0].get("id_type"), "entity_id": ent,
                                  "case": mention_case(m) if m[0]["category"] == "PERSON" else None,
                                  "name_parts": [s.get("name_part") for s in m if s.get("name_part")],
                                  "target": ent == target or m[0].get("owner") == target})
    for s in doc["spans"]:
        if s["category"] == "PERSON" and s.get("name_part"):
            g = f"part={s['name_part']}"
            c[f"s:{g}"] += 1
            c[f"s_closed:{g}"] += not is_open(text, s["start"], s["end"], covered)
    people = {s["entity_id"] for s in doc["spans"] if s["category"] == "PERSON"}
    c["e"] = len(entity_open)
    c["e_safe"] = sum(not v for v in entity_open.values())
    c["p"] = len(people)
    c["p_safe"] = sum(not entity_open[e] for e in people)
    if target in people:
        c["t"] = 1
        c["t_safe"] = int(not entity_open[target])
        owned = [s for s in doc["spans"] if s.get("owner", s["entity_id"]) == target]
        c["f_safe"] = int(not any(is_open(text, s["start"], s["end"], covered) for s in owned))
    in_gold = [False] * len(text)
    for s in doc["spans"]:
        for i in range(s["start"], s["end"]):
            in_gold[i] = True
    masked = [i for i, x in enumerate(covered) if x and not text[i].isspace()]
    c["masked"] = len(masked)
    c["masked_out"] = sum(not in_gold[i] for i in masked)
    return c, open_mentions


def ratio(c, num, den):
    return c[num] / c[den] if c[den] else None


def metrics_from(c):
    out = {name: ratio(c, n, d) for name, (n, d) in METRICS.items()}
    for key in c:
        if key.startswith("m:") and key != "m:all":
            g = key[2:]
            out[f"mention_recall|{g}"] = ratio(c, f"m_closed:{g}", key)
        elif key.startswith("s:"):
            g = key[2:]
            out[f"span_recall|{g}"] = ratio(c, f"s_closed:{g}", key)
    return out


def bootstrap(per_doc, doc_ids, n=BOOT, seed=0):
    """{system: {metric: (low, high)}} for the headline metrics, resampling documents."""
    rng = random.Random(seed)
    samples = [[rng.choice(doc_ids) for _ in doc_ids] for _ in range(n)]
    keys = sorted({k for m in CI_METRICS for k in METRICS[m]})
    out = {}
    for system, docs in per_doc.items():
        table = {d: [c[k] for k in keys] for d, c in docs.items()}
        vals = {m: [] for m in CI_METRICS}
        for sample in samples:
            sums = [0] * len(keys)
            for d in sample:
                for i, x in enumerate(table.get(d, ())):
                    sums[i] += x
            c = dict(zip(keys, sums))
            for m in CI_METRICS:
                num, den = METRICS[m]
                if c[den]:
                    vals[m].append(c[num] / c[den])
        out[system] = {}
        for m, v in vals.items():
            if v:
                v.sort()
                out[system][m] = (v[int(0.025 * len(v))], v[min(len(v) - 1, int(0.975 * len(v)))])
    return out


def evaluate(gold_docs, rows, boot=BOOT):
    """Returns (results, by_doc, skipped). results: {system: {"n", "metrics", "ci"}}."""
    gold = {d["doc_id"]: d for d in gold_docs}
    per_doc, by_doc, skipped = {}, [], Counter()
    for r in rows:
        system = r["system_or_condition"]
        if r.get("llm_failed"):
            skipped[system] += 1
            continue
        doc = gold[r["doc_id"]]
        c, open_mentions = score_doc(doc, r)
        per_doc.setdefault(system, {})[r["doc_id"]] = c
        by_doc.append({"doc_id": r["doc_id"], "system_or_condition": system,
                       "genre": doc.get("genre"),
                       "mention_recall": ratio(c, "m_closed:all", "m:all"),
                       "target_protected": c["t_safe"] if c["t"] else None,
                       "fully_protected": c["f_safe"] if c["t"] else None,
                       "open": open_mentions})
    ci = bootstrap(per_doc, sorted(gold), boot) if boot else {}
    results = {}
    for system, docs in per_doc.items():
        total = Counter()
        for c in docs.values():
            total.update(c)
        results[system] = {"n": len(docs), "metrics": metrics_from(total), "ci": ci.get(system, {})}
    return results, by_doc, skipped


def add_k(results, data_dir, gold_docs, rows):
    import uniqueness as uq
    pop = st.load_population(data_dir / "population.csv")
    rows = [r for r in rows if not r.get("llm_failed")]
    for system, s in uq.summarize(uq.score(pop, gold_docs, rows)).items():
        if system in results:
            results[system]["metrics"]["k1_share"] = s["pct_k1"] / 100
            results[system]["metrics"]["median_k"] = s["median_k"]


COLUMNS = [("mention", "mention_recall"), ("DI", "mention_recall|type=DI"),
           ("QI", "mention_recall|type=QI"), ("nom", "mention_recall|case=nom"),
           ("oblique", "mention_recall|case=oblique"), ("persons", "entity_recall"),
           ("target", "target_protected"), ("fully", "fully_protected"),
           ("over", "over_masking")]


def fmt(v):
    return "    -" if v is None else f"{v:5.2f}"


def print_table(results, with_k=False):
    cols = COLUMNS + ([("k=1", "k1_share"), ("med k", "median_k")] if with_k else [])
    print(f"{'system':24}{'n':>4}" + "".join(f"{h:>9}" for h, _ in cols))
    for system, r in results.items():
        cells = []
        for _, key in cols:
            v = r["metrics"].get(key)
            cells.append(f"{v:9.0f}" if key == "median_k" and v is not None else f"{fmt(v):>9}")
        print(f"{system:24}{r['n']:>4}" + "".join(cells))
    if any(r["ci"] for r in results.values()):
        print("\n95% intervals (documents resampled):")
        print(f"{'system':24}" + "".join(f"{m:>22}" for m in CI_METRICS))
        for system, r in results.items():
            cells = [f"{lo:.2f}–{hi:.2f}" if (lo := r['ci'].get(m, (None, None))[0]) is not None
                     and (hi := r['ci'][m][1]) is not None else "-" for m in CI_METRICS]
            print(f"{system:24}" + "".join(f"{c:>22}" for c in cells))


def write_report(results, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["system_or_condition", "metric", "value", "ci_low", "ci_high", "n_docs"])
        for system, r in results.items():
            for metric, v in sorted(r["metrics"].items()):
                lo, hi = r["ci"].get(metric, (None, None))
                w.writerow([system, metric, "" if v is None else round(v, 4),
                            "" if lo is None else round(lo, 4), "" if hi is None else round(hi, 4),
                            r["n"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", nargs="?", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--with-k", action="store_true", help="add k = 1 share and median k")
    ap.add_argument("--boot", type=int, default=BOOT, help="bootstrap resamples, 0 to skip")
    ap.add_argument("--out", type=Path, help="where to write the report (default DIR)")
    args = ap.parse_args(argv)

    gold = list(st.read_jsonl(args.data_dir / "gold_docs.jsonl"))
    rows = list(st.read_jsonl(args.data_dir / "masked_docs.jsonl"))
    results, by_doc, skipped = evaluate(gold, rows, args.boot)
    if args.with_k:
        add_k(results, args.data_dir, gold, rows)
    for system, n in skipped.items():
        print(f"skipped {n} failed {system} rows")
    print_table(results, args.with_k)

    out = args.out or args.data_dir
    out.mkdir(parents=True, exist_ok=True)
    write_report(results, out / "recall_report.csv")
    with open(out / "recall_by_doc.jsonl", "w", encoding="utf-8") as f:
        for r in by_doc:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {out / 'recall_report.csv'} and {out / 'recall_by_doc.jsonl'}")


if __name__ == "__main__":
    main()
