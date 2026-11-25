"""Run the attacks on masked documents.

Usage:
    python evaluation/run_attacks.py DIR --task reid|nodoc|attr
        [--conditions gold_full,rule] [--n 10,100] [--design balanced|random]
        [--limit K] [--workers 8] [--model MODEL] [--out OUT] [--dry-run]

Tasks: reid (re-identification), nodoc (the same without the document), attr (attribute
inference). Conditions are all those in DIR/masked_docs.jsonl by default; "unmasked" is the
original text, a check that the attack works at all.

Writes OUT/<task>.jsonl (OUT is DIR/attacks by default), one row per call. Rows are saved as
they finish. A row is kept on a rerun as long as its prompt and model are the same, so a run
can be stopped and continued, and only documents whose masked text changed are attacked again.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "data_understanding"))
import candidates as cd  # noqa: E402
import llm  # noqa: E402
import prompts as pr  # noqa: E402
from generate import pick  # noqa: E402

st = cd.st
UNMASKED = "unmasked"
TEMPERATURES = (0, 0.7, 0.7)  # one per attempt; repeating a call at 0 gives the same reply
MAX_FAILURES = 10
KEY = ("doc_id", "system_or_condition", "design", "n", "model", "prompt_version")


# ---------- jobs ----------

def load(data_dir):
    d = Path(data_dir)
    rows = st.read_jsonl(d / "masked_docs.jsonl")
    gold = st.read_jsonl(d / "gold_docs.jsonl")
    texts = {(r["doc_id"], r["system_or_condition"]): r["masked_text"] for r in rows}
    texts.update({(g["doc_id"], UNMASKED): g["text"] for g in gold})
    return {"gold": gold, "texts": texts,
            "conditions": list(dict.fromkeys(r["system_or_condition"] for r in rows)),
            "population": st.load_population(d / "population.csv"),
            "lists": {(r["doc_id"], r["design"], r["n"]): r["candidates"]
                      for r in st.read_jsonl(d / "candidates.jsonl")}}


def prompt_hash(messages):
    blob = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def make_jobs(data, task, model, conditions=None, sizes=cd.SIZES, design="balanced", limit=None):
    """One dict per call: the key fields of its row, the messages and what the parser needs."""
    by_id = {p["person_id"]: p for p in data["population"]}
    closed = pr.closed_lists(data["population"])
    prompt = pr.load_task_prompt(task)
    conditions = [None] if task == "nodoc" else (conditions or data["conditions"])
    sizes = [None] if task == "attr" else sizes
    design = None if task == "attr" else design
    jobs = []
    for doc in pick(data["gold"], limit):
        for cond in conditions:
            text = None
            if cond is not None:
                if (doc["doc_id"], cond) not in data["texts"]:
                    raise KeyError(f"no masked text for {doc['doc_id']}, condition {cond}")
                text = data["texts"][doc["doc_id"], cond]
            for n in sizes:
                people = None
                if task == "attr":
                    messages = pr.attr_messages(text, closed, prompt)
                else:
                    if (doc["doc_id"], design, n) not in data["lists"]:
                        raise KeyError(f"no {design} list with n={n} for {doc['doc_id']}")
                    people = data["lists"][doc["doc_id"], design, n]
                    messages = pr.reid_messages([by_id[p] for p in people], text, prompt)
                jobs.append({"task": task, "doc_id": doc["doc_id"], "system_or_condition": cond,
                             "design": design, "n": n, "model": model,
                             "prompt_version": pr.prompt_version(task),
                             "prompt_hash": prompt_hash(messages), "messages": messages,
                             "people": people, "target": doc["person_id"], "closed": closed})
    return jobs


def key(row):
    return tuple(row[k] for k in KEY)


# ---------- one call ----------

def parse(job, reply):
    """(parsed reply, number of usable answers in it)"""
    if job["task"] == "attr":
        out = pr.parse_attributes(reply, job["closed"])
        return out, sum(v is not None for v in out["values"].values())
    out = pr.parse_ranking(reply, job["n"])
    return out, sum(label is not None for label in out["ranking"])


def run_job(job):
    """Call the model until a reply has no errors, and keep the best reply seen."""
    best, usage = None, Counter()
    for attempt, temperature in enumerate(TEMPERATURES):
        reply, used, _ = llm.chat(job["messages"], temperature=temperature,
                                  extra={"task": job["task"], "attempt": attempt})
        usage.update(used)
        out, usable = parse(job, reply)
        score = (usable, -len(out["errors"]))
        if best is None or score > best[0]:
            best = (score, out)
        if not out["errors"]:
            break
    (usable, _), out = best
    row = {k: job[k] for k in KEY}
    row["prompt_hash"] = job["prompt_hash"]
    if job["task"] == "attr":
        row["values"] = out["values"]
    else:
        person = dict(zip(cd.labels(job["n"]), job["people"]))
        row["ranking"] = [person.get(label) for label in out["ranking"]]
        row["target_rank"] = (row["ranking"].index(job["target"]) + 1
                              if job["target"] in row["ranking"] else None)
    return dict(row, clues=out["clues"], parse_ok=usable > 0, errors=out["errors"],
                attempts=attempt + 1, usage=dict(usage))


# ---------- files ----------

def read_rows(path):
    """Saved rows by key; the last one wins. A line cut off by an interruption is dropped."""
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows[key(r)] = r
    return rows


def write_rows(path, rows):
    order = sorted(rows, key=lambda r: tuple((v is not None, v) for v in key(r)))
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for r in order:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def validate(rows, jobs):
    """Every job has exactly one up-to-date row and the row fits its candidate list."""
    errors, by_key = [], defaultdict(list)
    for r in rows:
        by_key[key(r)].append(r)
    for j in jobs:
        tag = "/".join(str(v) for v in key(j)[:4])
        found = by_key.get(key(j), [])
        if len(found) != 1:
            errors.append(f"{tag}: {len(found)} rows")
        for r in found:
            if r["prompt_hash"] != j["prompt_hash"]:
                errors.append(f"{tag}: prompt changed since the call")
            if j["people"] and not {p for p in r["ranking"] if p} <= set(j["people"]):
                errors.append(f"{tag}: ranking has people outside the list")
    return errors


# ---------- run ----------

def run(jobs, path, workers=8):
    """Run the missing jobs. Returns (all rows of the file, number of failed calls)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_rows(path)
    todo = [j for j in jobs if rows.get(key(j), {}).get("prompt_hash") != j["prompt_hash"]]
    print(f"{path.name}: {len(jobs)} jobs, {len(jobs) - len(todo)} already done")
    if not todo:
        return list(rows.values()), 0
    write_rows(path, rows.values())  # drops a half-written last line
    done, failed, stop = 0, [], threading.Event()

    def attempt(job):
        if stop.is_set():
            return None
        try:
            return run_job(job)
        except Exception as e:  # keep the finished rows; a rerun picks up the rest
            failed.append(job)
            print(f"  {'/'.join(str(v) for v in key(job)[:4])}: {type(e).__name__}: {e}"[:300],
                  file=sys.stderr)
            if len(failed) >= MAX_FAILURES:
                stop.set()
            return None

    with ThreadPoolExecutor(workers) as pool, \
            open(path, "a", encoding="utf-8", newline="\n") as f:
        for future in as_completed([pool.submit(attempt, j) for j in todo]):
            row = future.result()
            if row is None:
                continue
            rows[key(row)] = row
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(todo)}")
    write_rows(path, rows.values())
    if stop.is_set():
        print("  too many failures, stopped early", file=sys.stderr)
    return list(rows.values()), len(failed)


def summary(rows, jobs):
    """Quick look at the rows of these jobs; the reported numbers come from scoring."""
    wanted = {key(j) for j in jobs}
    rows = [r for r in rows if key(r) in wanted]
    if not rows:
        return
    tokens = Counter()
    for r in rows:
        tokens.update(r["usage"])
    print(f"{len(rows)} rows, unreadable: {sum(not r['parse_ok'] for r in rows)}, "
          f"with errors: {sum(bool(r['errors']) for r in rows)}, "
          f"repeated: {sum(r['attempts'] > 1 for r in rows)}, "
          f"tokens: {tokens['prompt']} in, {tokens['completion']} out")
    if "ranking" not in rows[0]:
        return
    groups = defaultdict(list)
    for r in rows:
        groups[r["system_or_condition"] or "no document", r["design"], r["n"]].append(r["target_rank"])
    print(f"{'condition':24}{'design':10}{'N':>5}{'docs':>6}{'top-1':>8}{'top-5':>8}")
    for (cond, design, n), ranks in groups.items():
        print(f"{cond:24}{design:10}{n:>5}{len(ranks):>6}"
              f"{sum(r == 1 for r in ranks) / len(ranks):>8.1%}"
              f"{sum(r is not None for r in ranks) / len(ranks):>8.1%}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--task", choices=pr.TASKS, required=True)
    ap.add_argument("--conditions")
    ap.add_argument("--n", default=",".join(str(n) for n in cd.SIZES))
    ap.add_argument("--design", choices=cd.DESIGNS, default="balanced")
    ap.add_argument("--limit", type=int, help="number of documents, spread over the genres")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    model = llm.settings()["model"]
    if not model and not args.dry_run:
        sys.exit("Set LLM_BASE_URL and LLM_MODEL (in .env or the environment).")
    jobs = make_jobs(load(args.data_dir), args.task, model,
                     args.conditions.split(",") if args.conditions else None,
                     [int(n) for n in args.n.split(",")], args.design, args.limit)
    if args.dry_run:
        size = [sum(len(m["content"]) for m in j["messages"]) for j in jobs]
        print(f"{len(jobs)} jobs, {sum(size)} characters, longest prompt {max(size)}")
        return True
    path = (args.out or args.data_dir / "attacks") / f"{args.task}.jsonl"
    rows, n_failed = run(jobs, path, args.workers)
    errors = validate(rows, jobs)
    summary(rows, jobs)
    print(f"{path}: " + ("complete" if not errors else
                         f"{len(errors)} problems, {n_failed} failed calls; rerun to continue"))
    for e in errors[:10]:
        print("  ", e)
    return not errors


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
