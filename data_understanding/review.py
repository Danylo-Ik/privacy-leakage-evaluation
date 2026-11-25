"""Manual check of generated documents (DU-8). Protocol: docs/manual_check.md.

Usage:
    python data_understanding/review.py pick [DIR]      # review sheets + empty manual_check.csv
    python data_understanding/review.py summary [DIR]   # results from the filled csv
    python data_understanding/review.py fix [DIR]       # apply manual_fixes.jsonl to the gold

DIR defaults to data/full. Sheets go to DIR/review/A.md and DIR/review/B.md.
"""
import csv
import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import seed_tools as st  # noqa: E402
import checks  # noqa: E402

DEFAULT_DIR = HERE.parent / "data" / "full"
PER_GENRE = {"court": 7, "news": 7, "forum": 6}
MIN_RETRIED = 3
OVERLAP = 4
SEED = 7

COUNT_FIELDS = ["missed", "boundary", "category", "entity", "case_wrong", "attr_owner", "grammar"]
CSV_FIELDS = (["reviewer", "doc_id", "genre", "spans", "person_spans"] + ["missed", "missed_items"]
              + ["boundary", "category", "entity", "case_wrong", "attr_owner", "extra_facts",
                 "naturalness", "grammar", "notes"])
SPAN_FIELDS = ["category", "id_type", "entity_id", "case", "name_part", "attr", "owner"]


def retried_docs(data_dir):
    log = data_dir / "generation_log.jsonl"
    if not log.exists():
        return set()
    return {r["doc_id"] for r in st.read_jsonl(log) if r["attempt"] > 0}


def pick(docs, retried, per_genre=PER_GENRE, seed=SEED):
    """Doc ids per genre with a fixed seed; the first pick of each genre is a retried doc."""
    rng = random.Random(seed)
    chosen = []
    for genre, n in per_genre.items():
        ids = sorted(d["doc_id"] for d in docs if d["genre"] == genre)
        rng.shuffle(ids)
        again = [i for i in ids if i in retried]
        if again:
            ids.remove(again[0])
            ids.insert(0, again[0])
        chosen += ids[:n]
    left = [d["doc_id"] for d in docs if d["doc_id"] in retried and d["doc_id"] not in chosen]
    rng.shuffle(left)
    while sum(i in retried for i in chosen) < MIN_RETRIED and left:
        swap = next(i for i in reversed(chosen) if i not in retried)
        genre = next(d["genre"] for d in docs if d["doc_id"] == swap)
        same = [i for i in left if next(d["genre"] for d in docs if d["doc_id"] == i) == genre]
        if not same:
            break
        chosen[chosen.index(swap)] = same[0]
        left.remove(same[0])
    return chosen


def assign(doc_ids, genres, overlap=OVERLAP, seed=SEED):
    """{reviewer: doc ids}, balanced by genre. `overlap` docs go to both reviewers."""
    ids = list(doc_ids)
    random.Random(seed).shuffle(ids)
    ids.sort(key=lambda i: genres[i])
    step = len(ids) // overlap if overlap else len(ids) + 1
    sheets, turn = {"A": [], "B": []}, 0
    for n, i in enumerate(ids):
        if overlap and n % step == step // 2 and n // step < overlap:
            sheets["A"].append(i)
            sheets["B"].append(i)
        else:
            sheets["AB"[turn % 2]].append(i)
            turn += 1
    return {k: sorted(v) for k, v in sheets.items()}


def label(s):
    parts = [s["entity_id"], s["category"], s["id_type"]]
    parts += [s[k] for k in ("case", "name_part") if s[k]]
    if s["attr"]:
        parts.append(f"{s['attr']}→{s['owner']}")
    elif s["owner"] != s["entity_id"]:
        parts.append(f"→{s['owner']}")
    return "·".join(parts)


def tagged_text(doc):
    out, pos = [], 0
    for s in sorted(doc["spans"], key=lambda s: s["start"]):
        out.append(doc["text"][pos:s["start"]])
        out.append(f"[{s['text']}]⟨{label(s)}⟩")
        pos = s["end"]
    out.append(doc["text"][pos:])
    return "".join(out)


def profile(p):
    return (f"{p['first_name']} {p['patronymic']} {p['surname']}, {p['gender']}, born {p['birth_year']}, "
            f"{p['settlement']} ({p['settlement_type']}), {p['oblast']} oblast, {p['occupation']}, "
            f"{p['family_status']}, children: {p['children']}, event: {p['event']}")


def render(doc, person, plan, attempts, n, total):
    lines = [f"## {n}/{total}. {doc['doc_id']} · {doc['genre']} · {doc['doc_year']}"
             f" · attempts: {attempts}", "",
             f"**Target E1:** {profile(person)}", ""]
    if plan:
        lines.append("**Facts in the plan** (anything else said about E1 goes under G):")
        for f in plan["facts"]:
            lines.append(f"- {f['attr']}: {f['text']} ({f['category']}/{f['id_type']})")
        for i in plan.get("identifiers", []):
            lines.append(f"- {i['kind']}: {i['text']} ({i['category']})")
        lines.append("")
        lines.append("**Name forms asked for:** " + ", ".join(
            f"{x['text']} ({x['case']})" for x in plan["names"]))
        sides = [f"{c['mention']} ({c['role']})" for c in plan.get("side_characters", [])]
        if sides:
            lines.append("")
            lines.append("**Side characters:** " + ", ".join(sides))
        lines.append("")
    lines += ["### Plain text (read this first: naturalness, grammar, anything personal)", "",
              doc["text"], "",
              "### Tagged text", "",
              tagged_text(doc), "",
              "### Spans", "",
              "| # | text | " + " | ".join(SPAN_FIELDS) + " |",
              "|---" * (len(SPAN_FIELDS) + 2) + "|"]
    for i, s in enumerate(sorted(doc["spans"], key=lambda s: s["start"]), 1):
        cells = [str(i), s["text"]] + [s[k] or "-" for k in SPAN_FIELDS]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "---", ""]
    return "\n".join(lines)


def person_spans(doc):
    return sum(s["category"] == "PERSON" for s in doc["spans"])


def cmd_pick(data_dir):
    docs = list(st.read_jsonl(data_dir / "gold_docs.jsonl"))
    by_id = {d["doc_id"]: d for d in docs}
    people = {p["person_id"]: p for p in st.load_population(data_dir / "population.csv")}
    plans = {}
    if (data_dir / "fact_plans.jsonl").exists():
        plans = {p["doc_id"]: p for p in st.read_jsonl(data_dir / "fact_plans.jsonl")}
    attempts = {}
    if (data_dir / "generation_log.jsonl").exists():
        for r in st.read_jsonl(data_dir / "generation_log.jsonl"):
            attempts[r["doc_id"]] = max(attempts.get(r["doc_id"], 0), r["attempt"] + 1)
    retried = retried_docs(data_dir)
    chosen = pick(docs, retried)
    sheets = assign(chosen, {d["doc_id"]: d["genre"] for d in docs})

    out = data_dir / "review"
    out.mkdir(exist_ok=True)
    both = set(sheets["A"]) & set(sheets["B"])
    for reviewer, ids in sheets.items():
        head = [f"# Manual check, reviewer {reviewer}", "",
                f"{len(ids)} documents. Protocol and what to record: docs/manual_check.md.",
                f"Reviewed by both reviewers: {', '.join(sorted(both))}. Do these without talking.",
                "", "---", ""]
        body = [render(by_id[i], people[by_id[i]["person_id"]], plans.get(i), attempts.get(i, 1),
                       n, len(ids)) for n, i in enumerate(ids, 1)]
        (out / f"{reviewer}.md").write_text("\n".join(head + body), encoding="utf-8")

    sheet = data_dir / "manual_check.csv"
    if sheet.exists():
        print(f"{sheet} already exists, left as it is")
    else:
        with open(sheet, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            for reviewer, ids in sheets.items():
                for i in ids:
                    d = by_id[i]
                    w.writerow({"reviewer": reviewer, "doc_id": i, "genre": d["genre"],
                                "spans": len(d["spans"]), "person_spans": person_spans(d)})
        print(f"wrote {sheet}")
    print(f"picked {len(chosen)} docs ({sum(i in retried for i in chosen)} needed a retry)")
    for reviewer, ids in sheets.items():
        print(f"  {reviewer}: {len(ids)} docs -> {out / (reviewer + '.md')}")
    print(f"  both: {', '.join(sorted(both))}")


def number(value):
    value = (value or "").strip()
    return float(value) if value else None


def read_sheet(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k in COUNT_FIELDS + ["spans", "person_spans", "naturalness"]:
                r[k] = number(r.get(k))
            rows.append(r)
    return rows


def filled(r):
    return r["naturalness"] is not None


def merge(rows):
    """One row per doc. For docs seen twice, counts take the larger value and naturalness the mean."""
    docs = {}
    for r in rows:
        if not filled(r):
            continue
        d = docs.setdefault(r["doc_id"], {"genre": r["genre"], "spans": r["spans"],
                                          "person_spans": r["person_spans"], "nat": [],
                                          "extra": False, **{k: 0 for k in COUNT_FIELDS}})
        for k in COUNT_FIELDS:
            d[k] = max(d[k], r[k] or 0)
        d["nat"].append(r["naturalness"])
        d["extra"] = d["extra"] or bool(r["extra_facts"].strip())
    return docs


def agreement(rows):
    """Share of overlap docs where both reviewers agree, per check (zero vs some)."""
    seen = {}
    for r in rows:
        if filled(r):
            seen.setdefault(r["doc_id"], []).append(r)
    pairs = [v for v in seen.values() if len(v) == 2]
    if not pairs:
        return 0, {}
    out = {}
    for k in COUNT_FIELDS:
        out[k] = sum(((a[k] or 0) > 0) == ((b[k] or 0) > 0) for a, b in pairs) / len(pairs)
    out["extra_facts"] = sum(bool(a["extra_facts"].strip()) == bool(b["extra_facts"].strip())
                             for a, b in pairs) / len(pairs)
    out["naturalness"] = sum(a["naturalness"] == b["naturalness"] for a, b in pairs) / len(pairs)
    return len(pairs), out


def summary(rows):
    docs = merge(rows)
    n = len(docs)
    if not n:
        return {"docs": 0}
    spans = sum(d["spans"] for d in docs.values())
    person = sum(d["person_spans"] for d in docs.values())
    nat = [x for d in docs.values() for x in d["nat"]]
    pairs, agree = agreement(rows)
    return {
        "docs": n,
        "docs_with_missed": sum(d["missed"] > 0 for d in docs.values()) / n,
        "missed_per_100_spans": 100 * sum(d["missed"] for d in docs.values()) / spans,
        "case_label_accuracy": 1 - sum(d["case_wrong"] for d in docs.values()) / person if person else None,
        "boundary_errors": sum(d["boundary"] for d in docs.values()),
        "category_errors": sum(d["category"] for d in docs.values()),
        "entity_errors": sum(d["entity"] for d in docs.values()),
        "attr_owner_errors": sum(d["attr_owner"] for d in docs.values()),
        "docs_with_extra_facts": sum(d["extra"] for d in docs.values()) / n,
        "grammar_per_doc": sum(d["grammar"] for d in docs.values()) / n,
        "naturalness": sum(nat) / len(nat),
        "overlap_docs": pairs,
        "agreement": agree,
    }


def cmd_summary(data_dir):
    rows = read_sheet(data_dir / "manual_check.csv")
    done = sum(filled(r) for r in rows)
    print(f"{done}/{len(rows)} rows filled")
    s = summary(rows)
    if not s["docs"]:
        return s
    pct = {"docs_with_missed", "case_label_accuracy", "docs_with_extra_facts"}
    for k, v in s.items():
        if k == "agreement":
            continue
        if v is None:
            print(f"{k:24} -")
        elif k in pct:
            print(f"{k:24} {v:.0%}")
        elif isinstance(v, float):
            print(f"{k:24} {v:.2f}")
        else:
            print(f"{k:24} {v}")
    if s["agreement"]:
        print("agreement on the overlap (both found something, or both found nothing):")
        for k, v in s["agreement"].items():
            print(f"  {k:22} {v:.0%}")
    with open(data_dir / "manual_check_summary.json", "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    return s


def find_span(doc, fix):
    for s in doc["spans"]:
        if s["start"] == fix["start"] and s["end"] == fix["end"]:
            return s
    raise ValueError(f"{doc['doc_id']}: no span at {fix['start']}-{fix['end']}")


def apply_fix(doc, fix):
    """Apply one fix to a gold doc in place. Returns False if the doc should be dropped."""
    op = fix["op"]
    if op == "drop":
        return False
    if op == "add":
        if "start" in fix:
            start = fix["start"]
            if doc["text"][start:start + len(fix["text"])] != fix["text"]:
                raise ValueError(f"{doc['doc_id']}: «{fix['text']}» is not at {start}")
        else:
            starts = checks.find_word(doc["text"], fix["text"])
            k = fix.get("occurrence", 1)
            if len(starts) < k:
                raise ValueError(f"{doc['doc_id']}: «{fix['text']}» occurrence {k} not found")
            start = starts[k - 1]
        span = {"start": start, "end": start + len(fix["text"]), "text": fix["text"]}
        for key in SPAN_FIELDS:
            span[key] = fix.get(key)
        if span["entity_id"] is None:
            used = [int(x["entity_id"][1:]) for x in doc["spans"]]
            span["entity_id"] = f"E{max(used, default=0) + 1}"
        if span["owner"] is None:
            span["owner"] = st.TARGET if span["attr"] else span["entity_id"]
        doc["spans"].append(span)
    elif op == "edit":
        span = find_span(doc, fix)
        span.update(fix["set"])
        span["text"] = doc["text"][span["start"]:span["end"]]
    elif op == "delete":
        doc["spans"].remove(find_span(doc, fix))
    else:
        raise ValueError(f"unknown op {op!r}")
    for s in doc["spans"]:
        s["edrsr_type"] = st.edrsr_type(s)
    doc["spans"].sort(key=lambda s: s["start"])
    return True


def apply_fixes(docs, fixes):
    by_doc = {}
    for f in fixes:
        by_doc.setdefault(f["doc_id"], []).append(f)
    out = []
    for d in docs:
        d = json.loads(json.dumps(d))
        if all(apply_fix(d, f) for f in by_doc.get(d["doc_id"], [])):
            out.append(d)
    return out


def rebuild_conditions(data_dir, docs):
    """Replace the gold_* rows of masked_docs.jsonl and keep the maskers' rows.
    Maskers only see the text, which fixes don't change; conditions depend on the spans."""
    sys.path.insert(0, str(HERE.parent / "model_training"))
    import conditions
    path = data_dir / "masked_docs.jsonl"
    keep = set(d["doc_id"] for d in docs)
    old = list(st.read_jsonl(path)) if path.exists() else []
    systems = [r for r in old if not r["system_or_condition"].startswith("gold_")
               and r["doc_id"] in keep]
    rows = list(conditions.masked_rows(docs)) + systems
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def cmd_fix(data_dir):
    gold, original = data_dir / "gold_docs.jsonl", data_dir / "gold_docs.generated.jsonl"
    if not original.exists():
        shutil.copy(gold, original)
    fixes = list(st.read_jsonl(data_dir / "manual_fixes.jsonl"))
    docs = apply_fixes(st.read_jsonl(original), fixes)
    with open(gold, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    population = st.load_population(data_dir / "population.csv")
    errors = st.validate_gold(docs, population)
    print(f"applied {len(fixes)} fixes -> {gold} ({len(docs)} docs)")
    rows = rebuild_conditions(data_dir, docs)
    errors += st.validate_masked(rows, docs)
    print(f"rebuilt the gold conditions in masked_docs.jsonl ({len(rows)} rows, masker rows kept)")
    for e in errors:
        print(f"    {e}")
    return not errors


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("pick", "summary", "fix"):
        print(__doc__)
        sys.exit(2)
    d = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DIR
    if sys.argv[1] == "pick":
        cmd_pick(d)
    elif sys.argv[1] == "summary":
        cmd_summary(d)
    else:
        sys.exit(0 if cmd_fix(d) else 1)
