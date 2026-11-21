"""Run every masking system and condition on a data directory.

Usage:
    python model_training/run_all.py DATA_DIR [--systems rule,spacy,llm] [--no-conditions]
                                              [--seeds N] [--out FILE]

Writes DATA_DIR/masked_docs.jsonl (or FILE) with one row per (doc, system or condition),
validates it against the gold docs, and prints dev scores (span recall by group, entity
recall, over-masking). Report the official numbers with data_understanding/recall.py.
A system that cannot run (no spaCy model, no LLM_MODEL) is skipped with a message.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import conditions  # noqa: E402

st = common.st


def run_system(name, gold):
    if name == "rule":
        import rule_masker
        return rule_masker.run(gold)
    if name == "spacy":
        import spacy_masker
        return spacy_masker.run(gold)
    if name == "llm":
        import llm_masker
        return llm_masker.run(gold)
    raise ValueError(f"unknown system {name}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--systems", default="rule,spacy,llm")
    ap.add_argument("--no-conditions", action="store_true")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    gold = st.read_jsonl(args.data_dir / "gold_docs.jsonl")
    rows = [] if args.no_conditions else list(conditions.masked_rows(gold, args.seeds))
    for name in [s for s in args.systems.split(",") if s]:
        try:
            rows += run_system(name, gold)
            print(f"{name}: done")
        except (OSError, ImportError, RuntimeError) as e:
            print(f"{name}: SKIPPED ({e})")

    out = args.out or args.data_dir / "masked_docs.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    errors = st.validate_masked(rows, gold)
    print(f"wrote {len(rows)} rows to {out}; " + ("valid" if not errors else f"{len(errors)} errors"))
    for e in errors[:20]:
        print("  ", e)
    common.print_scores(common.score(gold, rows))
    return not errors


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
