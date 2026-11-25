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
| `llm` (`llm_masker.py`) | zero-shot prompt `docs/prompts/mask_v1.md`, all 8 categories | same prompt |

All three produce plain spans; `common.to_row()` resolves overlaps (longest wins), groups name mentions of one person (`cluster_persons`) and numbers placeholders.

```
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m spacy download uk_core_news_trf          # ~500 MB
export LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...        # any OpenAI-compatible endpoint
.venv/bin/python model_training/run_all.py data/sample       # conditions + all systems
.venv/bin/python model_training/run_all.py data/seed --systems rule   # quick check
```

`run_all.py` writes `masked_docs.jsonl`, validates it and prints *dev* scores from `common.score()` (span recall by category / DI-QI / case / name part, entity recall, over-masking). LLM answers are cached in `.cache/llm/`.

Rules were written against the 5 seed docs, so seed scores are optimistic; judge them on the pilot. Known natural misses of `rule`: bare adjectival surnames with no name context, diminutives not in the list, occupations, family and other DEM/MISC facts.
