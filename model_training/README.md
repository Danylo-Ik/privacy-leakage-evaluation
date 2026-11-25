# Model training: masking

Rule-based, NER and LLM maskers plus degradation conditions. Output `masked_docs.jsonl` per docs/SCHEMA.md (offsets into the original text). Start from `seed_tools.apply_masking()` and `gold_conditions()`.

Note: build the name gazetteer from a generic Ukrainian name list, not from population.csv.

## Controlled conditions

```
python model_training/conditions.py data/seed            # or data/sample, data/full
python model_training/conditions.py data/full --seeds 3  # extra drop-out runs
```

Writes every gold condition to `DATA_DIR/masked_docs.jsonl` and lists the rows that turned out identical to `gold_full`. Run `python seed_tools.py validate DATA_DIR` afterwards. Note that `python seed_tools.py build` rewrites the seed file with only the first four conditions; rerun this script after it.

## Systems

| system | finds names with | finds codes, dates, amounts, addresses with |
|---|---|---|
| `rule` (`rule_masker.py`) | first-name gazetteer (`resources/first_names_uk.txt`) in all cases via pymorphy3, patronymic and surname suffixes, initials, name-order and trigger-word context, surname propagation | `regex_rules.py` |
| `spacy` (`spacy_masker.py`) | `uk_core_news_trf` NER (PER/LOC/ORG/MISC) | `regex_rules.py` |
| `llm` (`llm_masker.py`) | zero-shot Qwen3-32B (self-hosted vLLM), prompt `docs/prompts/mask_v2.md`, all 8 categories | same prompt |

All three produce plain spans; `common.to_row()` resolves overlaps (longest wins), groups name mentions of one person (`cluster_persons`) and numbers placeholders.

The LLM used for the reported outputs is **Qwen3-32B**, deliberately a different model family from the generator (Gemma 4). Its answers are aligned back to the text by the masker itself (exact and inflected forms, name parts), so offsets are always exact. If an answer is empty or not valid JSON (thinking used up the token budget, or the model looped), it is retried once without thinking and with a mild repetition penalty; a cut-off answer keeps the complete mentions it has. Every `llm` row carries `llm_status` (`ok`, `retry`, `salvaged` or `failed`); a `failed` row is unmasked and also has `llm_failed: true`, so exclude it. On `data/full`: ok=140, retry=7, failed=0.

```
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m spacy download uk_core_news_trf          # ~500 MB
# .env (gitignored): MASK_LLM_BASE_URL, MASK_LLM_MODEL, MASK_LLM_API_KEY, MASK_LLM_MAX_TOKENS=8000
#   (falls back to LLM_*; see docs/gpu_setup.md for the vast.ai + vLLM server)
.venv/bin/python model_training/run_all.py data/sample       # conditions + all systems
.venv/bin/python model_training/run_all.py data/seed --systems rule   # quick check
.venv/bin/python model_training/check_outputs.py data/sample data/full  # before handing over
```

`run_all.py` writes `masked_docs.jsonl`, validates it and prints *dev* scores from `common.score()` (span recall by category / DI-QI / case / name part, entity recall, over-masking). If a requested system fails (no model, closed tunnel, no `.env`), it does **not** overwrite the file unless `--allow-missing` is given. LLM answers are cached in `.cache/llm/` (not in git), so a rerun needs no GPU unless the prompt, model or settings change.

Rules were written against the 5 seed docs, so seed scores are optimistic; judge them on the pilot. Known natural misses of `rule`: bare adjectival surnames with no name context, diminutives not in the list, occupations, family and other DEM/MISC facts.
