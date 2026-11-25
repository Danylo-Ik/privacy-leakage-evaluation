# Privacy leakage evaluation for Ukrainian pseudonymization

Does partial masking of Ukrainian texts still protect people? Three workstreams (data understanding, model training, evaluation) on synthetic data. See `docs/methods.md` for the method and `docs/SCHEMA.md` for file formats.

Dependencies are managed with [uv](https://docs.astral.sh/uv/getting-started/installation/) (`pyproject.toml` and `uv.lock`):

```
uv sync                        # base + pytest
uv sync --group evaluation     # + matplotlib for the plots
uv sync --group masking        # + spaCy, torch and uk_core_news_trf (about 1.5 GB)
uv sync --all-groups           # everything

uv run python seed_tools.py build && uv run pytest -q tests
```

`uv sync` removes packages of groups that are not listed, so every needed group has to be named. Run the commands below with `uv run` in front (`uv run python ...`), or activate `.venv` first. Add a dependency with `uv add <package>` (`--group <name>` for a group) and commit `uv.lock`.

## Data

```
python data_understanding/population.py data/full
```

This writes `population.csv` (2,000 people) and `targets.csv` (150 people the documents are about, with 1–3 look-alikes each). Documents come in three genres: court decisions, news and forum posts. About 30% of surnames are made up from invented stems, the rest are common real ones.

`data_understanding/names.py` lists every form of a person's name: all seven cases, diminutives, initials, both name orders and Russian spellings. The gold checks use it to find name mentions that were left untagged.

```
python data_understanding/fact_plan.py data/full
```

This writes `fact_plans.jsonl`: for each target, the facts the document has to mention, the name forms it has to use, and a few invented side characters (a judge, a colleague, a boss). Documents are generated from these plans.

## Generating documents

Generation works with any OpenAI-compatible endpoint: a vLLM server on a rented GPU, OpenRouter, or a hosted API. Put the connection in `.env` (it is gitignored):

```
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=google/gemma-3-27b-it
LLM_API_KEY=...
```

For vLLM on a rented GPU, follow `docs/gpu_setup.md`: one shared server, each person connects through their own SSH tunnel. For OpenRouter, use `https://openrouter.ai/api/v1` and a model id ending in `:free`. Free models allow 20 requests a minute and 50 a day, or 1,000 a day once the account has $10 of credits. The client waits between calls on its own.

```
python data_understanding/llm.py ping
python data_understanding/generate.py data/sample --limit 3
```

The corpus in `data/full/` (147 documents) and the sample in `data/sample/` (30) were generated with Gemma 4 31B on one A100. Each document is checked after generation. If something is missing (a fact, a name form, a tag), the model gets the list of problems and another try, twice at most. Every call is cached in `data/cache/llm/`, so a rerun costs nothing. The prompt is in `docs/prompts/generate_v2.md`.

## Checking documents

```
python data_understanding/checks.py data/sample
```

This prints PASS or FAIL for every document and writes `check_report.jsonl`. A document fails if:

- a tag is broken or the offsets are wrong
- something from its plan is missing (a fact, an identifier, a required name form)
- any form of the target's name, or a side character's name, appears without a tag
- the age, birth year or number of children doesn't match the population
- it is far too short or too long, or names the target fewer than three times

An untagged name is the one mistake we can't afford: no metric sees it, but an attacker does. `generate.py` runs the same checks and sends the errors back to the model.

To compare models, run the same 10 plans through each one and print a summary:

```
python data_understanding/generate.py data/full --limit 10 --model <model> --out data/bakeoff/<name>
python data_understanding/bakeoff.py
```

## Metrics

`data_understanding/uniqueness.py` counts how many people in the population still match what a masked document reveals (k-anonymity).

All people in this repository are fictional.
