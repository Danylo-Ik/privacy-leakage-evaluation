"""Zero-shot LLM masker.

The model returns entities with their exact surface forms (prompt: docs/prompts/mask_v1.md);
we find every occurrence in the text ourselves, so offsets are always exact.

Configuration (same as data generation): LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, for any
OpenAI-compatible endpoint. Responses are cached in .cache/llm/ keyed by
(model, prompt hash, document text), so reruns are free and reproducible.
"""
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402

PROMPT_PATH = ROOT / "docs" / "prompts" / "mask_v1.md"
CACHE_DIR = ROOT / ".cache" / "llm"
CATEGORIES = set(common.st.PLACEHOLDER)
ALIASES = {"PER": "PERSON", "NAME": "PERSON", "ADDRESS": "LOC", "DATE": "DATETIME",
           "NUMBER": "QUANTITY", "ID": "CODE"}


def prompt_for(text, template=None):
    template = template or PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{text}", text)


def cached_chat(prompt, model, client=None, cache_dir=None, retries=3):
    """One chat completion at temperature 0, cached on disk."""
    key = hashlib.sha256(json.dumps([model, prompt], ensure_ascii=False).encode()).hexdigest()
    path = Path(cache_dir or CACHE_DIR) / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["content"]
    if client is None:
        from openai import OpenAI
        client = OpenAI(base_url=os.environ.get("LLM_BASE_URL"),
                        api_key=os.environ.get("LLM_API_KEY", "none"))
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0,
                messages=[{"role": "user", "content": prompt}])
            content = resp.choices[0].message.content
            break
        except Exception:  # network errors, rate limits
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, "content": content}, ensure_ascii=False),
                    encoding="utf-8")
    return content


def parse_entities(content):
    """Extract the entity list from a model answer (tolerates code fences and chatter)."""
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    ents = data.get("entities", []) if isinstance(data, dict) else []
    out = []
    for e in ents:
        if not isinstance(e, dict):
            continue
        cat = str(e.get("category", "MISC")).upper()
        cat = ALIASES.get(cat, cat if cat in CATEGORIES else "MISC")
        mentions = [m for m in e.get("mentions", []) if isinstance(m, str) and m.strip()]
        out.append({"category": cat, "mentions": mentions})
    return out


def locate(text, mention):
    """All occurrences of a mention at word boundaries (exact, then case-insensitive)."""
    mention = common.st.normalize(mention.strip())
    if len(mention) < 2 and not mention.isdigit():
        return []
    rx = re.compile(rf"(?<![\w’]){re.escape(mention)}(?![\w’])")
    hits = list(rx.finditer(text)) or list(re.compile(rx.pattern, re.I).finditer(text))
    return [(m.start(), m.end()) for m in hits]


def spans_from_entities(text, entities):
    spans, missing = [], []
    for i, e in enumerate(entities):
        for mention in e["mentions"]:
            hits = locate(text, mention)
            if not hits:
                missing.append(mention)
            spans += [{"start": a, "end": b, "category": e["category"], "key": f"llm{i}"}
                      for a, b in hits]
    return spans, missing


def mask_doc(doc, model=None, client=None, template=None):
    """Return (system spans, mentions the model invented)."""
    model = model or os.environ.get("LLM_MODEL")
    if not model:
        raise RuntimeError("set LLM_MODEL (and LLM_BASE_URL, LLM_API_KEY)")
    content = cached_chat(prompt_for(doc["text"], template), model, client)
    return spans_from_entities(doc["text"], parse_entities(content))


def run(gold_docs, name="llm", model=None, client=None, workers=4):
    def one(d):
        spans, missing = mask_doc(d, model, client)
        if missing:
            print(f"  {d['doc_id']}: {len(missing)} mention(s) not found in text: "
                  f"{missing[:3]}", file=sys.stderr)
        return common.to_row(d["doc_id"], name, d["text"], spans)
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, gold_docs))
