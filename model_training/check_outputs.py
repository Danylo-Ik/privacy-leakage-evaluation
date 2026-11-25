"""Sanity checks on masked_docs.jsonl before handing it to the metrics and attacks.

Usage: python model_training/check_outputs.py DATA_DIR [DATA_DIR ...]

Checks: the format (seed_tools.validate_masked); every doc has exactly one row per
expected system/condition; LLM status (no "failed"); source texts that already
contain placeholder-like tokens (they would be confused with our masks); system rows
that mask nothing; and, per system, how many docs still show a form of the target's
surname (expected for some gold conditions, suspicious for the systems).
Exit code 1 if a hard problem is found.
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

st = common.st
EXPECTED = ["gold_full", "gold_di_only", "gold_edrsr_policy", "gold_miss_one_oblique",
            "gold_drop_p05", "gold_drop_p10", "gold_drop_p20", "gold_drop_p40",
            "gold_keep_patronymic", "rule", "spacy", "llm"]
SYSTEMS = {"rule", "spacy", "llm"}
PLACEHOLDER = re.compile(r"(ОСОБА|КОД|МІСЦЕ|ОРГАНІЗАЦІЯ|ДАТА|ЧИСЛО|ІНФОРМАЦІЯ|АДРЕСА|НОМЕР)_\d+")


def check(data_dir):
    data_dir = Path(data_dir)
    gold = st.read_jsonl(data_dir / "gold_docs.jsonl")
    rows = st.read_jsonl(data_dir / "masked_docs.jsonl")
    by_doc = {g["doc_id"]: g for g in gold}
    hard = []
    print(f"== {data_dir}: {len(gold)} docs, {len(rows)} rows "
          f"(expected {len(gold) * len(EXPECTED)})")

    errors = st.validate_masked(rows, gold)
    print(f"format: {'ok' if not errors else f'{len(errors)} errors, e.g. {errors[0]}'}")
    hard += errors

    seen = collections.Counter((r["doc_id"], r["system_or_condition"]) for r in rows)
    dups = [k for k, n in seen.items() if n > 1]
    missing = [(g["doc_id"], s) for g in gold for s in EXPECTED if (g["doc_id"], s) not in seen]
    extra = sorted({s for _, s in seen} - set(EXPECTED))
    print(f"completeness: duplicates={len(dups)} missing={len(missing)} "
          f"unexpected systems={extra or 'none'}")
    if missing:
        print(f"  missing, e.g.: {missing[:5]}")
    hard += dups + missing

    status = collections.Counter(r.get("llm_status") for r in rows
                                 if r["system_or_condition"] == "llm")
    print(f"llm status: {dict(status)}")
    failed = [r["doc_id"] for r in rows if r.get("llm_failed")]
    if failed:
        print(f"  llm FAILED docs (unmasked): {' '.join(failed)}")
        hard += failed

    clash = [g["doc_id"] for g in gold if PLACEHOLDER.search(g["text"])]
    print(f"source texts with placeholder-like tokens: {clash or 'none'}")

    empty = [(r["doc_id"], r["system_or_condition"]) for r in rows
             if r["system_or_condition"] in SYSTEMS and not r["masked_spans"]]
    print(f"system rows that mask nothing: {empty or 'none'}")
    hard += empty

    leaks = collections.defaultdict(list)
    for r in rows:
        g = by_doc.get(r["doc_id"])
        if not g:
            continue
        forms = {s["text"] for s in g["spans"]
                 if s["entity_id"] == g["target_entity_id"] and s["name_part"] == "surname"}
        if any(re.search(rf"(?<![\w’]){re.escape(f)}(?![\w’])", r["masked_text"]) for f in forms):
            leaks[r["system_or_condition"]].append(r["doc_id"])
    print("docs where a form of the target's surname is still visible:")
    for s in EXPECTED:
        ids = leaks.get(s, [])
        print(f"  {s:22s} {len(ids):3d}  {' '.join(ids[:10])}{' …' if len(ids) > 10 else ''}")
    return not hard


if __name__ == "__main__":
    dirs = sys.argv[1:] or ["data/full"]
    ok = all([check(d) for d in dirs])
    print("\nALL CHECKS PASSED" if ok else "\nPROBLEMS FOUND (see above)")
    sys.exit(0 if ok else 1)
