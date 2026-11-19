# Privacy leakage evaluation for Ukrainian pseudonymization

Does partial masking of Ukrainian texts still protect people? Three workstreams (data understanding, model training, evaluation) on synthetic data. See `docs/methods.md` for the method and `docs/SCHEMA.md` for file formats.

```
pip install -r requirements.txt
python seed_tools.py build && python -m pytest -q tests
```

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
pip install openai
python data_understanding/llm.py ping
python data_understanding/generate.py data/sample --limit 3
```

Each document is checked after generation. If something is missing (a fact, a name form, a tag), the model gets the list of problems and another try, twice at most. Every call is cached in `data/cache/llm/`, so a rerun costs nothing. The prompt is in `docs/prompts/generate_v1.md`.

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
