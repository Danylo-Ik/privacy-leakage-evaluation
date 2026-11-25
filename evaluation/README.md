# Evaluation: attacks

LLM re-identification (N = 10/100 candidates, full names in nominative form, candidate lists include look-alikes), a no-document baseline, attribute inference, caching. k-anonymity: `data_understanding/uniqueness.py`.

## Candidate lists

```
python evaluation/candidates.py data/full
```

Writes `data/full/candidates.jsonl`, checks it, and prints how often the target can be guessed without the document. Adding or removing gold documents changes the lists, so they are regenerated after that.

A list always holds the target and their look-alikes. The rest depends on the design:

- **`balanced`** (main): whole groups (target plus look-alikes) of other targets of the same genre.
- **`random`** (control): random people from the population.

Random lists give the answer away: every target has an event and look-alikes, most other people have neither. Expected top-1 on `data/full` of rules that never read the document:

| design | N | chance | has an event | has look-alikes | both | both, and the event fits the genre |
|---|---|---|---|---|---|---|
| balanced | 10 | 10% | 24.2% | 10.0% | 24.2% | 26.7% |
| balanced | 100 | 1% | 2.4% | 1.0% | 2.4% | 2.7% |
| random | 10 | 10% | 52.9% | 35.5% | 87.3% | 93.8% |
| random | 100 | 1% | 5.9% | 19.6% | 55.5% | 79.1% |

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
