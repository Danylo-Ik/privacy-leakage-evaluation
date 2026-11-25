# Manual check of the generated corpus

The automatic checks catch broken tags, missing planned facts and untagged forms of names we know about. They can't see a nickname the model invented, an address it added, or a case label that is wrong but still valid. This check covers that on a sample, so the Data section can say how good the gold is.

## Setup

```
python data_understanding/review.py pick
```

This picks 20 documents from `data/full/` with a fixed seed: 7 court, 7 news, 6 forum, at least 3 of them ones that needed a retry. It writes:

- `data/full/review/A.md` and `data/full/review/B.md`: 12 documents per reviewer, 4 per genre. Four documents are on both sheets, to measure agreement. Do those without discussing them.
- `data/full/manual_check.csv`: one row per reviewer and document, with the span counts filled in. Fill in your own rows.

Each document on a sheet shows the target's profile, the planned facts and name forms, the side characters, the plain text, the text with every span bracketed and labelled, and a table of the spans. A label reads `[Бережною]⟨E1·PERSON·DI·ins·surname⟩`: entity, category, DI/QI, case, name part, and for attributes `attr→owner`.

Expect about 6–8 minutes per document, so about 1.5 hours per reviewer.

## What to check

Read the plain text first, as an attacker would, then go through the tagged text and the table.

| Column | Check | What to write |
|---|---|---|
| `missed` | Personal information that has no span: any person's name or part of it, initials, nickname, address, phone, code, date tied to a person, organisation that points to a person, place of the target | number of items |
| `missed_items` | the same items | `text CATEGORY` separated by `;`, e.g. `Світланці PERSON; вул. Шевченка LOC` |
| `boundary` | a span too long or too short (`місті Одеса` vs `Одеса` is fine; half a name or a word cut in two is not) | number |
| `category` | wrong category or wrong DI/QI | number |
| `entity` | two people with one entity id, or one person split into two | number |
| `case_wrong` | for every PERSON span: wrong case or wrong name part. `person_spans` is already filled in as the total | number |
| `attr_owner` | wrong `attr` or wrong owner (e.g. a colleague's job marked as the target's) | number |
| `extra_facts` | facts about the target that are not in the plan (a new child, a street, a second job) | the text, empty if none |
| `naturalness` | 1 = clearly machine-made or odd, 2 = fine with some awkward spots, 3 = reads like a real text of the genre | 1, 2 or 3 |
| `grammar` | grammar or agreement errors in the Ukrainian | number |
| `notes` | anything else: third-person self-reference in a forum post, invented courts, odd style | free text |

Leave a count empty only if you did not review the document; write `0` when there is nothing. `summary` treats a row as done once `naturalness` is filled.

Rules of thumb:

- When unsure whether something is personal, count it in `missed` and explain it in `notes`. The attacker sees everything that is not masked, so the gold should rather have too much than too little.
- Count each wrong span once, under the first column that applies.
- Case is judged by the grammar of the sentence, not by the form alone (`Вакарчук` after `від` is genitive).

## Results

```
python data_understanding/review.py summary
```

Prints and saves to `data/full/manual_check_summary.json`:

- share of documents with at least one missed item, and missed items per 100 spans
- case-label accuracy over PERSON spans
- boundary, category, entity and attr/owner errors
- share of documents with extra facts, grammar errors per document, mean naturalness
- agreement on the overlap, per check: both reviewers found something, or both found nothing

For documents seen twice, counts take the larger of the two values.

## Fixes

Corrections go into `data/full/manual_fixes.jsonl`, one per line:

```
{"doc_id": "D104", "op": "add", "text": "Світланці", "occurrence": 1, "category": "PERSON", "id_type": "DI", "entity_id": "E1", "case": "dat", "name_part": "diminutive"}
{"doc_id": "D104", "op": "edit", "start": 87, "end": 96, "set": {"case": "gen"}}
{"doc_id": "D104", "op": "delete", "start": 87, "end": 96}
{"doc_id": "D104", "op": "drop"}
```

- `add` takes `start`, or finds the n-th whole-word occurrence of `text`. Fields that aren't given are empty. The owner defaults as in the tags, and a missing `entity_id` becomes a new one. A `note` field is ignored and is there for the record.
- `edit` and `delete` name a span by its offsets, from the table on the sheet or from `gold_docs.jsonl`. `edit` can also change `start` and `end`.
- `drop` removes the document.

```
python data_understanding/review.py fix
python data_understanding/checks.py data/full
```

The first run keeps the generated gold as `gold_docs.generated.jsonl`, and fixes are always applied to that copy, so running `fix` again is safe. `fix` also rebuilds the `gold_*` rows of `masked_docs.jsonl`, since they depend on the spans. The maskers' rows (rule, spacy, llm) are kept as they are, because they only depend on the text, which fixes never change. Rows of dropped documents are removed.

If a missed item shows a pattern (say, diminutives the plan never asked for), it should become a check in `checks.py`. Then regenerate the documents that fail it, instead of fixing them by hand.
