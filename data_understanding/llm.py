"""Small OpenAI-compatible client with a disk cache.

Settings come from the environment or from .env in the repo root:
    LLM_BASE_URL   e.g. http://localhost:8000/v1 (vLLM) or https://openrouter.ai/api/v1
    LLM_MODEL      model id
    LLM_API_KEY
    LLM_MIN_INTERVAL  seconds between calls (default 3.5 for OpenRouter, else 0)

Usage: python data_understanding/llm.py ping
"""
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache" / "llm"

_lock = threading.Lock()
_last_call = [0.0]
_client = [None]


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def settings():
    load_env()
    base_url = os.environ.get("LLM_BASE_URL", "")
    default_gap = "3.5" if "openrouter.ai" in base_url else "0"
    return {"base_url": base_url, "model": os.environ.get("LLM_MODEL", ""),
            "api_key": os.environ.get("LLM_API_KEY", "none"),
            "min_interval": float(os.environ.get("LLM_MIN_INTERVAL", default_gap))}


def cache_key(model, messages, params, extra=None):
    blob = json.dumps({"model": model, "messages": messages, "params": params, "extra": extra},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _wait_turn(min_interval):
    with _lock:
        gap = time.monotonic() - _last_call[0]
        if gap < min_interval:
            time.sleep(min_interval - gap)
        _last_call[0] = time.monotonic()


def complete(messages, model, params, cfg):
    """One real API call, with backoff on rate limits and server errors."""
    import openai
    if _client[0] is None:
        _client[0] = openai.OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    for attempt in range(6):
        _wait_turn(cfg["min_interval"])
        try:
            r = _client[0].chat.completions.create(model=model, messages=messages, **params)
            usage = {"prompt": r.usage.prompt_tokens, "completion": r.usage.completion_tokens} \
                if r.usage else {}
            return r.choices[0].message.content or "", usage
        except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError):
            if attempt == 5:
                raise
            time.sleep(min(60, 5 * 2 ** attempt))


def chat(messages, temperature=0.8, max_tokens=2000, extra=None, use_cache=True):
    """Return (text, usage, cached). `extra` goes into the cache key (e.g. the attempt number)."""
    cfg = settings()
    if not cfg["base_url"] or not cfg["model"]:
        raise RuntimeError("Set LLM_BASE_URL and LLM_MODEL (in .env or the environment).")
    params = {"temperature": temperature, "max_tokens": max_tokens}
    key = cache_key(cfg["model"], messages, params, extra)
    path = CACHE_DIR / f"{key}.json"
    if use_cache and path.exists():
        hit = json.loads(path.read_text(encoding="utf-8"))
        return hit["text"], hit["usage"], True
    text, usage = complete(messages, cfg["model"], params, cfg)
    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": cfg["model"], "params": params, "extra": extra,
                                    "messages": messages, "text": text, "usage": usage},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    return text, usage, False


if __name__ == "__main__":
    if sys.argv[1:] != ["ping"]:
        sys.exit(__doc__)
    cfg = settings()
    text, usage, _ = chat([{"role": "user", "content": "Одним реченням українською: яка зараз пора року?"}],
                          max_tokens=60, use_cache=False)
    print(f"{cfg['model']} @ {cfg['base_url']}\n{text.strip()}\n{usage}")
