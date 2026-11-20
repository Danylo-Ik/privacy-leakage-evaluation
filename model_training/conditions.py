"""Gold masking with deliberate holes (controlled conditions).

Usage:
    python model_training/conditions.py [DATA_DIR] [--seeds N] [--out FILE]

Reads DATA_DIR/gold_docs.jsonl and writes every condition to DATA_DIR/masked_docs.jsonl
(or FILE). Conditions:

- gold_full, gold_di_only, gold_edrsr_policy, gold_miss_one_oblique: see seed_tools.
- gold_drop_p05 ... gold_drop_p40: each mention (adjacent spans of one entity, e.g.
  surname + first name + patronymic) is left unmasked with probability p. A mention
  is dropped as a whole, so no name is half-masked. Every mention gets one random
  number u per (doc, seed) and is dropped when u < p, so the dropped sets are nested:
  p05 ⊂ p10 ⊂ p20 ⊂ p40. With --seeds N > 1, extra runs are named gold_drop_p05_s1...
- gold_keep_patronymic: everything masked except the target's patronymic.

Placeholders are numbered from all gold spans, so the same entity has the same
placeholder in every condition of a document.
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed_tools as st  # noqa: E402

DROP_RATES = (0.05, 0.10, 0.20, 0.40)


def all_mentions(text, spans):
    """Every mention of every entity, in text order."""
    groups = []
    for ent in {s["entity_id"] for s in spans}:
        groups += st.mentions(text, spans, ent)
    return sorted(groups, key=lambda m: m[0]["start"])


def drop_out(doc, rate, seed=0):
    """Gold spans minus the spans of randomly dropped mentions."""
    rng = random.Random(f"{doc['doc_id']}:{seed}")
    dropped = set()
    for m in all_mentions(doc["text"], doc["spans"]):
        if rng.random() < rate:  # draw for every mention, so rates stay nested
            dropped.update(id(s) for s in m)
    return [s for s in doc["spans"] if id(s) not in dropped]


def keep_patronymic(doc):
    target = doc["target_entity_id"]
    return [s for s in doc["spans"]
            if not (s["entity_id"] == target and s["name_part"] == "patronymic")]


def all_conditions(doc, seeds=1):
    """{condition name: spans to mask} for one gold doc."""
    out = st.gold_conditions(doc)
    for seed in range(seeds):
        suffix = f"_s{seed}" if seed else ""
        for rate in DROP_RATES:
            out[f"gold_drop_p{round(rate * 100):02d}{suffix}"] = drop_out(doc, rate, seed)
    out["gold_keep_patronymic"] = keep_patronymic(doc)
    return out


def masked_rows(gold_docs, seeds=1):
    for d in gold_docs:
        for cond, to_mask in all_conditions(d, seeds).items():
            masked_text, masked_spans = st.apply_masking(d["text"], to_mask, d["spans"])
            yield {"doc_id": d["doc_id"], "system_or_condition": cond,
                   "masked_text": masked_text, "masked_spans": masked_spans,
                   "n_unmasked_gold": len(d["spans"]) - len(to_mask)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", nargs="?", type=Path, default=st.SEED_DIR)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    gold = st.read_jsonl(args.data_dir / "gold_docs.jsonl")
    rows = list(masked_rows(gold, args.seeds))
    out = args.out or args.data_dir / "masked_docs.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Conditions that change nothing are not holes; report them so they can be excluded.
    same = [(r["doc_id"], r["system_or_condition"]) for r in rows
            if r["n_unmasked_gold"] == 0 and r["system_or_condition"] != "gold_full"]
    print(f"wrote {len(rows)} rows ({len(gold)} docs) to {out}")
    if same:
        print(f"{len(same)} rows identical to gold_full:")
        for doc_id, cond in same:
            print(f"  {doc_id} {cond}")


if __name__ == "__main__":
    main()
