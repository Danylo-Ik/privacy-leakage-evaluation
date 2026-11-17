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

`data_understanding/uniqueness.py` counts how many people in the population still match what a masked document reveals (k-anonymity).

All people in this repository are fictional.
