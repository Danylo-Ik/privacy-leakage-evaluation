"""Compare models after running the same plans through each of them.

    python data_understanding/generate.py data/full --limit 10 --model A --out data/bakeoff/a
    python data_understanding/generate.py data/full --limit 10 --model B --out data/bakeoff/b
    python data_understanding/bakeoff.py [data/bakeoff]
"""
import json
import sys
from pathlib import Path


def summarize(log):
    docs = {}
    for e in log:
        docs.setdefault(e["doc_id"], []).append(e)
    n = len(docs)
    first = sum(entries[0]["ok"] for entries in docs.values())
    final = sum(any(e["ok"] for e in entries) for entries in docs.values())
    attempts = sum(len(entries) for entries in docs.values())
    tokens = sum(e["usage"].get("completion", 0) for e in log)
    return {"model": log[0]["model"] if log else "?", "docs": n, "first_try": first,
            "passed": final, "attempts_per_doc": attempts / n if n else 0,
            "tokens_per_doc": tokens / n if n else 0}


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/bakeoff")
    rows = []
    for path in sorted(root.glob("*/generation_log.jsonl")):
        log = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        rows.append(summarize(log))
    rows.sort(key=lambda r: (-r["passed"], -r["first_try"]))
    print(f"{'model':45s} docs  first try  passed  attempts  tokens")
    for r in rows:
        print(f"{r['model']:45s} {r['docs']:4d}  {r['first_try']:9d}  {r['passed']:6d}"
              f"  {r['attempts_per_doc']:8.1f}  {r['tokens_per_doc']:6.0f}")
