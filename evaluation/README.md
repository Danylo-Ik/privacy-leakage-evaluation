# Evaluation: attacks

Method and limitations: `docs/attacks.md`. Findings: `docs/results.md`.

LLM re-identification (N = 10/100 candidates, full names in nominative form, candidate lists include look-alikes), a no-document baseline, attribute inference, caching. k-anonymity: `data_understanding/uniqueness.py`.

## Candidate lists

```
python evaluation/candidates.py data/full
```

Writes `data/full/candidates.jsonl`, checks it, and prints how often the target can be guessed without the document. Dropping a document (as in the manual check) removes its lists and leaves the others unchanged, because target positions are assigned over `gold_docs.generated.jsonl`.

A list always holds the target and their look-alikes. The rest depends on the design:

- **`balanced`** (main): whole groups (target plus look-alikes) of other targets of the same genre.
- **`random`** (control): random people from the population.

Random lists give the answer away: every target has an event and look-alikes, most other people have neither. Expected top-1 on `data/full` of rules that never read the document:

| design | N | chance | has an event | has look-alikes | both | both, and the event fits the genre |
|---|---|---|---|---|---|---|
| balanced | 10 | 10% | 24.2% | 10.0% | 24.2% | 26.7% |
| balanced | 100 | 1% | 2.4% | 1.0% | 2.4% | 2.7% |
| random | 10 | 10% | 52.9% | 35.6% | 87.2% | 93.7% |
| random | 100 | 1% | 5.9% | 19.6% | 55.2% | 78.9% |

Balanced lists are not at chance either, since a list of 10 holds only 3–5 groups. Attack results are therefore compared with the no-document baseline on the same lists, and N = 100 is the main setting.

Profiles are one line each: full name in the nominative, gender, birth year, oblast and settlement, occupation, family status, children and event. The attacker sees labels (`C001`…), never `person_id`.

## Prompts and parsing

```
python evaluation/prompts.py data/sample D102 --condition rule          # re-identification
python evaluation/prompts.py data/sample D102 --task nodoc --n 100      # no-document baseline
python evaluation/prompts.py data/sample D102 --task attr               # attribute inference
```

Prints the exact messages without calling a model. Prompt texts: `docs/prompts/attack_reid_v1.md` and `attack_attr_v1.md`.

- **Re-identification:** candidate profiles, then the masked document. The reply is JSON with the five most likely labels and a short note on the clues.
- **No-document baseline:** the same message with the document left out. It does not depend on the masker.
- **Attribute inference:** gender, decade of birth, oblast and occupation, without candidates. Oblasts and occupations are closed lists. "unknown" is allowed and scored as wrong.

All three prompts say who the main person is: the claimant, the subject of the article, or the author of the post. This holds for every document in `data/full`. They do not give the genre, the document year or the masker. `uniqueness.py` does use the document year, so its k is slightly more favourable to the attacker when only an age is left.

The parser accepts text around the JSON, Cyrillic letters in labels and feminine job titles. An invented label keeps its place in the ranking as a miss, so it never promotes the labels behind it. Any irregularity is returned in `errors`, so that the call can be repeated.

## Running the attacks

The endpoint and model come from `.env` (see the main README). The attacker should be neither the generator (Gemma 4 31B) nor the LLM masker (Qwen3-32B).

```
python evaluation/run_attacks.py data/sample --task reid --conditions unmasked,gold_full,rule --n 10   # pilot
python evaluation/run_attacks.py data/full --task nodoc
python evaluation/run_attacks.py data/full --task reid --n 100
python evaluation/run_attacks.py data/full --task reid --n 10
python evaluation/run_attacks.py data/full --task attr
python evaluation/run_attacks.py data/full --task reid --design random \
    --conditions gold_full,gold_edrsr_policy,gold_miss_one_oblique,rule    # control
python evaluation/run_attacks.py data/full --task nodoc --design random
```

Results go to `data/full/attacks/` (format in `docs/SCHEMA.md`). `--dry-run` counts the calls without making them, `--limit 80` takes a subset spread over the genres. Calls per task on `data/full` with the balanced design: 3,528 for `reid` (12 conditions, two list sizes), 294 for `nodoc`, 1,764 for `attr`. The longest prompt has about 18,000 characters.

- A run can be stopped and continued: finished rows are saved at once and reused as long as their prompt and model are the same. After a change in `masked_docs.jsonl` only the affected documents are attacked again.
- The first attempt uses temperature 0. A reply that is unreadable, too short or holds an invented label is repeated up to twice at 0.7, and the best reply is kept. A repeated label in an otherwise complete ranking is dropped without a retry. Without a usable reply the row counts as a miss.
- Failed calls leave no row. After ten of them the run stops; the same command continues it.
- `unmasked` attacks the original text. It should be close to 100% for N = 10; if not, the attack itself does not work.

## Scoring

```
python evaluation/score.py data/full
```

Reads the attack files, the masked and gold documents and the population, prints the main tables and writes them to `data/full/results/`:

| file | content |
|---|---|
| `summary.csv` | one row per condition: mention, entity and QI recall, k = 1, median k, top-1 and top-5, gender accuracy |
| `reid.csv` | top-1 and top-5 per design, N and condition; difference to the no-document baseline and to `gold_full` on the same documents |
| `attributes.csv` | accuracy per attribute, the share of always guessing the commonest value, accuracy where the attribute is still visible and where it is masked |
| `gender.csv` | gender accuracy per condition and genre |
| `k_buckets.csv` | top-1 by k (1, 2–5, 6–50, 51+) where the target's name is fully masked, all conditions pooled |
| `by_doc.csv` | one row per document and condition, the source of everything above; a rank of 0 is a miss, an empty rank means the attack was not run |

- Intervals are 95% bootstrap intervals over documents (2,000 draws, fixed seed). When a document contributes several rows, it is resampled as a whole.
- `top1_changed` leaves out the documents in which a drop-out condition changed nothing.
- `rule_without_document` is the expected top-1 of a rule that never reads the document (see "Candidate lists"); `chance` is 1/N.
- "unknown" and unusable answers count as wrong. `accuracy_answered` covers the answered ones only.
- Rows with `llm_failed` and rows of an older prompt version are ignored. Missing rows are reported, not filled in.
- Recall follows the open-mention rule through `model_training/common.py`, until `data_understanding/recall.py` exists. k comes from `data_understanding/uniqueness.py`.

## Figures

```
uv sync --group evaluation
python evaluation/plots.py data/full
```

Reads `data/full/results/` and writes PNG and PDF figures and `main_table.md` to `data/full/results/figures/`. A figure whose data is missing is skipped.

| figure | question |
|---|---|
| `headline_n100`, `headline_n10` | RQ1: masking recall (by mention and by person) against re-identification |
| `reid` | top-1 per condition with the no-document baseline |
| `dropout` | RQ2: attack and k = 1 against the share of mentions left open; single leaks |
| `k_buckets` | RQ5: does k predict the attack when the name is masked |
| `gender` | gender accuracy per condition, and per genre when everything is masked |
| `lists` | why lists of random people are not used |
