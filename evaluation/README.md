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
