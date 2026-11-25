"""Zero-shot LLM masker.

The model returns entities with their surface forms (prompt: docs/prompts/mask_v2.md);
we find every occurrence in the text ourselves, so offsets are always exact.

Matching is forgiving in two Ukrainian-specific ways, because models often answer with
a base form or with full names only:
- inflection: a returned word also matches its other case forms ("Ігор" -> "Ігорем",
  "Сосонка" -> "Сосонки"), by stem plus up to 4 letters;
- name parts: every word of a PERSON mention (and its initials) is also masked on its
  own, so "Оксану Вигаданчук" covers a later bare "Вигаданчук".

Settings come from the environment or .env in the repo root. MASK_LLM_* wins over
LLM_*, so the masker can use a different model than data generation:
    MASK_LLM_BASE_URL, MASK_LLM_MODEL, MASK_LLM_API_KEY  (OpenAI-compatible endpoint)
    MASK_LLM_MAX_TOKENS  reply budget, thinking included (default 8000)
    MASK_LLM_NO_THINK=1  ask Qwen3-style models to skip thinking (faster)
Responses are cached in .cache/llm/ keyed by (model, prompt, params).
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

PROMPT_PATH = ROOT / "docs" / "prompts" / "mask_v2.md"
CACHE_DIR = ROOT / ".cache" / "llm"
CATEGORIES = set(common.st.PLACEHOLDER)
ALIASES = {"PER": "PERSON", "NAME": "PERSON", "ADDRESS": "LOC", "DATE": "DATETIME",
           "NUMBER": "QUANTITY", "ID": "CODE"}
GROUPED = {"PERSON", "LOC", "ORG"}
UPPER = "А-ЯІЇЄҐA-Z"
LETTERS = "А-Яа-яІіЇїЄєҐґ’A-Za-z"


# ---------- settings ----------

def load_env(path=ROOT / ".env"):
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def settings():
    """MASK_LLM_* from the environment or .env, falling back to LLM_*."""
    env = {**load_env(), **os.environ}

    def get(name, default=""):
        return env.get(f"MASK_{name}") or env.get(name) or default
    return {"base_url": get("LLM_BASE_URL"), "model": get("LLM_MODEL"),
            "api_key": get("LLM_API_KEY", "none"),
            "max_tokens": int(get("LLM_MAX_TOKENS", "8000")),
            "no_think": env.get("MASK_LLM_NO_THINK", "") not in ("", "0")}


# ---------- model call ----------

def prompt_for(text, template=None):
    template = template or PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{text}", text)


def strip_thoughts(text):
    """Drop <think>/<thought> blocks if the server did not separate them."""
    text = re.sub(r"<(think|thought)>.*?</\1>", "", text or "", flags=re.S)
    return re.split(r"<(?:think|thought)>", text)[0].strip()


def cached_chat(prompt, model, client=None, cache_dir=None, retries=3, cfg=None, fallback=False):
    """One chat completion at temperature 0, cached on disk.

    fallback=True is the second attempt after an empty or unreadable answer: no
    thinking (so the token budget goes to the answer) and a mild repetition penalty
    (against loops like "Ковальського", "Ковальським", … until the limit).
    """
    cfg = cfg or settings()
    params = {"temperature": 0, "max_tokens": cfg["max_tokens"]}
    extra = {}
    if cfg["no_think"] or fallback:
        extra["chat_template_kwargs"] = {"enable_thinking": False}
    if fallback:
        extra["repetition_penalty"] = 1.05
    extra = extra or None
    blob = json.dumps([model, prompt, params, extra], ensure_ascii=False, sort_keys=True)
    path = Path(cache_dir or CACHE_DIR) / f"{hashlib.sha256(blob.encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["content"]
    if client is None:
        from openai import OpenAI
        client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=600)
    for attempt in range(retries):
        try:
            kw = {"extra_body": extra} if extra else {}
            resp = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], **params, **kw)
            content = strip_thoughts(resp.choices[0].message.content)
            break
        except Exception:  # network errors, rate limits
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, "params": params, "extra": extra,
                                "content": content}, ensure_ascii=False), encoding="utf-8")
    return content


STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
ENTITY = re.compile(r'"category"\s*:\s*"([A-Za-z]+)"\s*,\s*"mentions"\s*:\s*\[([^\]]*)', re.S)


def _clean(ents):
    """Normalize categories and drop repeated mentions (models sometimes loop)."""
    out = []
    for e in ents:
        if not isinstance(e, dict):
            continue
        cat = str(e.get("category", "MISC")).upper()
        cat = ALIASES.get(cat, cat if cat in CATEGORIES else "MISC")
        mentions = [m for m in e.get("mentions", []) if isinstance(m, str) and m.strip()]
        out.append({"category": cat, "mentions": list(dict.fromkeys(mentions))})
    return out


def parse_entities(content):
    """Return (entities, how): how is "ok", "salvaged" (cut-off answer, complete
    mentions recovered) or "failed" (empty or unreadable answer)."""
    text = content or ""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        blob = re.sub(r",\s*([\]}])", r"\1", m.group(0))  # trailing commas
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("entities"), list):
            return _clean(data["entities"]), "ok"
    salvaged = []
    for cat, body in ENTITY.findall(text):
        mentions = []
        for s in STRING.findall(body):  # only strings whose closing quote arrived
            try:
                mentions.append(json.loads(f'"{s}"'))
            except json.JSONDecodeError:
                pass
        salvaged.append({"category": cat, "mentions": mentions})
    salvaged = [e for e in _clean(salvaged) if e["mentions"]]
    return (salvaged, "salvaged") if salvaged else ([], "failed")


# ---------- alignment ----------

def word_pattern(word):
    """A word that may appear in another case: stem + up to 4 letters."""
    if len(word) < 4 or not word.isalpha():
        return re.escape(word)
    s = common.stem(word)
    return re.escape(s) + rf"[{LETTERS}]{{0,{4 + len(word) - len(s)}}}" if len(s) >= 3 \
        else re.escape(word)


def locate(text, mention):
    """All occurrences of a mention: exact, then case-insensitive, then inflected forms.

    A mention that starts with a capital letter only matches capitalized text.
    """
    mention = common.st.normalize(mention.strip())
    if len(mention) < 2 and not mention.isdigit():
        return []
    edge_l, edge_r = r"(?<![\w’])", r"(?![\w’])"
    parts = re.findall(r"[\w’]+\.?|[^\w\s]", mention)
    patterns = [re.escape(mention), r"\s*".join(word_pattern(p) for p in parts)]
    found = set()
    for p in patterns:  # the inflected pattern also covers the exact form
        found |= {(h.start(), h.end()) for h in re.finditer(edge_l + p + edge_r, text, re.I)}
    if mention[0].isupper():
        found = {(a, b) for a, b in found if text[a].isupper()}
    return sorted(found)


def person_parts(mention):
    """Single name words and initials of a PERSON mention ("Оксану Вигаданчук" -> both)."""
    words = re.findall(rf"[{UPPER}][\w’-]{{2,}}", mention)
    inits = re.findall(rf"[{UPPER}]\.\s?[{UPPER}]\.", mention)
    return [w for w in words + inits if w != mention.strip()]


def spans_from_entities(text, entities):
    spans, missing = [], []
    for i, e in enumerate(entities):
        mentions = list(e["mentions"])
        if e["category"] == "PERSON":
            mentions += [p for m in e["mentions"] for p in person_parts(m)]
        for j, mention in enumerate(mentions):
            hits = locate(text, mention)
            if not hits and j < len(e["mentions"]):
                missing.append(mention)
            # model-listed mentions outrank name parts when they overlap
            rank = 0 if j < len(e["mentions"]) else 1
            # people, places and organisations keep one placeholder per entity; facts
            # (codes, dates, ages, jobs…) get one per mention, since models tend to
            # lump e.g. an email and a phone into a single entity
            key = f"llm{i}" if e["category"] in GROUPED else f"llm{i}.{j}"
            spans += [{"start": a, "end": b, "category": e["category"], "key": key,
                       "rank": rank} for a, b in hits]
    return spans, missing


# ---------- running ----------

def mask_doc(doc, model=None, client=None, template=None, cfg=None):
    """Return (system spans, mentions not found in the text, status).

    status: "ok"; "retry" (first answer unusable, the no-thinking retry worked);
    "salvaged" (only a cut-off answer, complete mentions recovered from it);
    "failed" (nothing usable: the document is left unmasked and must be flagged).
    """
    cfg = cfg or settings()
    model = model or cfg["model"]
    if not model or (client is None and not cfg["base_url"]):
        raise RuntimeError("set MASK_LLM_BASE_URL and MASK_LLM_MODEL (or LLM_*) in .env")
    prompt = prompt_for(doc["text"], template)
    ents, how = parse_entities(cached_chat(prompt, model, client, cfg=cfg))
    status = how
    if how != "ok":
        ents2, how2 = parse_entities(cached_chat(prompt, model, client, cfg=cfg, fallback=True))
        if how2 == "ok":
            ents, status = ents2, "retry"
        elif how2 == "salvaged" and how == "failed":
            ents, status = ents2, "salvaged"
    spans, missing = spans_from_entities(doc["text"], ents)
    return spans, missing, status


def run(gold_docs, name="llm", model=None, client=None, workers=8):
    """Rows for masked_docs.jsonl. Each row carries llm_status; a row whose status is
    "failed" is unmasked and also gets llm_failed: true, so it can be excluded."""
    cfg = settings()

    def one(d):
        spans, missing, status = mask_doc(d, model, client, cfg=cfg)
        if missing:
            print(f"  {d['doc_id']}: {len(missing)} mention(s) not found in text: "
                  f"{missing[:3]}", file=sys.stderr)
        row = common.to_row(d["doc_id"], name, d["text"], spans)
        row["llm_status"] = status
        if status == "failed":
            row["llm_failed"] = True
        return row
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, gold_docs))
    by_status = {}
    for r in rows:
        by_status.setdefault(r["llm_status"], []).append(r["doc_id"])
    print("  llm status: " + ", ".join(f"{s}={len(v)}" for s, v in sorted(by_status.items())))
    for s in ("retry", "salvaged", "failed"):
        if by_status.get(s):
            print(f"  llm {s}: {' '.join(by_status[s])}")
    return rows
