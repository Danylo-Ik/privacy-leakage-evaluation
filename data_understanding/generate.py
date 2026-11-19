"""Generate tagged gold documents from fact plans with an LLM.

Usage:
    python data_understanding/generate.py DIR [--limit N] [--doc D101] [--workers 8]
                                          [--out OUT] [--model MODEL]

Reads DIR/fact_plans.jsonl and DIR/population.csv. Writes gold_docs.jsonl,
masked_docs.jsonl and generation_log.jsonl to OUT (default DIR).
A document that fails the checks is sent back with the list of errors, up to two times;
after that it is dropped and the failure stays in the log.
"""
import argparse
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import seed_tools as st  # noqa: E402
from seed_docs import SEED_DOCS  # noqa: E402
import checks  # noqa: E402
import llm  # noqa: E402
from fact_plan import read_csv  # noqa: E402

PROMPT_VERSION = "generate_v1"
PROMPT_FILE = HERE.parent / "docs" / "prompts" / f"{PROMPT_VERSION}.md"
MAX_ATTEMPTS = 3

GENRES = {
    "court": ("Ukrainian court decision", "A decision of a local court in a civil case, in the official style of the "
              "Unified State Register of Court Decisions: case number, «РІШЕННЯ ІМЕНЕМ УКРАЇНИ», date, court, "
              "«ВСТАНОВИВ:», «УХВАЛИВ:». Parties are named surname first. 250–450 words."),
    "news": ("Ukrainian local news article", "A short piece from a regional news site about the main person, with one "
             "or two quotes. 180–350 words."),
    "forum": ("Ukrainian forum post", "A first-person post on a forum, written by the main person and asking for "
              "advice. Informal, with a few typos allowed. Other people can be quoted. 150–300 words."),
}
EXAMPLES = {"court": ["D002", "D003"], "news": ["D001", "D004"], "forum": ["D005", "D001"]}


def load_prompt(path=PROMPT_FILE):
    sections, name = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            sections[name] = []
        elif name:
            sections[name].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def fill(template, **values):
    for k, v in values.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def describe_plan(plan):
    t = plan["target"]
    gender = "woman" if t["gender"] == "F" else "man"
    target = f"{t['first_name']} {t['patronymic']} {t['surname']}, {gender}"

    facts = []
    for f in plan["facts"]:
        how = "exact" if f["exact"] else "suggested wording, adapt to the sentence"
        facts.append(f"- «{f['text']}» — {f['category']}, {f['id_type']}, attr={f['attr']} ({how})")

    names = [f"- «{n['text']}» ({n['case']}; {' + '.join(n['parts'])})" for n in plan["names"]]

    side = []
    for s in plan["side_characters"]:
        full = f"{s['first_name']} {s['patronymic']} {s['surname']}"
        side.append(f"- {s['role']}: {full} ({'woman' if s['gender'] == 'F' else 'man'}), "
                    f"mention as «{s['mention']}»")

    ids = []
    for i in plan["identifiers"]:
        owner = f", owner={i['owner']}" if i["owner"] else ""
        ids.append(f"- {i['kind']}: «{i['text']}» — {i['category']}, DI{owner}" if i["category"] == "CODE"
                   else f"- {i['kind']}: «{i['text']}» — {i['category']}, QI{owner}")

    return {"target": target, "facts": "\n".join(facts), "names": "\n".join(names),
            "side_characters": "\n".join(side) or "- none",
            "identifiers": "\n".join(ids) or "- none"}


def build_messages(plan, prompt=None):
    prompt = prompt or load_prompt()
    seeds = {d["doc_id"]: d["tagged"] for d in SEED_DOCS}
    examples = "\n\n---\n\n".join(seeds[i] for i in EXAMPLES[plan["genre"]])
    name, notes = GENRES[plan["genre"]]
    user = fill(prompt["user"], genre_name=name, genre_notes=notes, examples=examples,
                doc_year=plan["doc_year"], **describe_plan(plan))
    return [{"role": "system", "content": prompt["system"]}, {"role": "user", "content": user}]


def extract_tagged(reply):
    text = reply.strip()
    fence = re.match(r"^```[a-zA-Z]*\n(.*?)\n?```$", text, re.S)
    return fence.group(1).strip() if fence else text


def to_gold(plan, tagged):
    text, spans = st.parse_tagged(tagged)
    return {"doc_id": plan["doc_id"], "person_id": plan["person_id"], "target_entity_id": "E1",
            "genre": plan["genre"], "doc_year": plan["doc_year"], "text": text, "spans": spans}


def check(doc, plan, population):
    return checks.check_doc(doc, population, plan)


def generate_one(plan, population, checker=check, prompt=None):
    """Return (gold_doc or None, log entries)."""
    prompt = prompt or load_prompt()
    messages = build_messages(plan, prompt)
    log = []
    for attempt in range(MAX_ATTEMPTS):
        reply, usage, cached = llm.chat(messages, extra={"doc_id": plan["doc_id"], "attempt": attempt,
                                                         "prompt": PROMPT_VERSION})
        tagged = extract_tagged(reply)
        if not tagged:
            log.append({"doc_id": plan["doc_id"], "genre": plan["genre"], "attempt": attempt,
                        "ok": False, "errors": ["empty reply (ran out of tokens while thinking?)"],
                        "model": llm.settings()["model"], "prompt": PROMPT_VERSION,
                        "usage": usage, "cached": cached})
            continue
        try:
            doc = to_gold(plan, tagged)
            errors = checker(doc, plan, population)
        except st.TagError as e:
            doc, errors = None, [str(e)]
        log.append({"doc_id": plan["doc_id"], "genre": plan["genre"], "attempt": attempt,
                    "ok": not errors, "errors": errors, "model": llm.settings()["model"],
                    "prompt": PROMPT_VERSION, "usage": usage, "cached": cached})
        if not errors:
            return doc, log
        messages = messages + [{"role": "assistant", "content": reply},
                               {"role": "user", "content": fill(prompt["repair"],
                                                                errors="\n".join(f"- {e}" for e in errors))}]
    return None, log


def pick(plans, limit=None, doc=None):
    if doc:
        return [p for p in plans if p["doc_id"] == doc]
    if limit is None:
        return plans
    by_genre = {g: [p for p in plans if p["genre"] == g] for g in ("court", "news", "forum")}
    out = []
    while len(out) < limit and any(by_genre.values()):
        for g in ("court", "news", "forum"):
            if by_genre[g] and len(out) < limit:
                out.append(by_genre[g].pop(0))
    return out


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run(data_dir, out_dir=None, limit=None, doc=None, workers=None):
    data_dir = Path(data_dir)
    out_dir = Path(out_dir or data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plans = pick(st.read_jsonl(data_dir / "fact_plans.jsonl"), limit, doc)
    population = read_csv(data_dir / "population.csv")
    if workers is None:
        workers = 1 if "openrouter.ai" in llm.settings()["base_url"] else 8
    prompt = load_prompt()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: generate_one(p, population, prompt=prompt), plans))

    gold = [d for d, _ in results if d]
    log = [entry for _, entries in results for entry in entries]
    masked = []
    for d in gold:
        for cond, to_mask in st.gold_conditions(d).items():
            text, spans = st.apply_masking(d["text"], to_mask, d["spans"])
            masked.append({"doc_id": d["doc_id"], "system_or_condition": cond,
                           "masked_text": text, "masked_spans": spans})
    if out_dir != data_dir:
        shutil.copy(data_dir / "population.csv", out_dir / "population.csv")
    write_jsonl(out_dir / "gold_docs.jsonl", gold)
    write_jsonl(out_dir / "masked_docs.jsonl", masked)
    write_jsonl(out_dir / "generation_log.jsonl", log)
    print(f"{len(gold)}/{len(plans)} documents passed -> {out_dir}")
    if gold:
        st.validate(out_dir)
    return gold, log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--doc")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--out")
    ap.add_argument("--model")
    a = ap.parse_args()
    if a.model:
        os.environ["LLM_MODEL"] = a.model
    run(a.dir, a.out, a.limit, a.doc, a.workers)
