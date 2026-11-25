# Data contract

All files are UTF-8. Offsets are **Python string indices (Unicode code points)**, end-exclusive: `text[start:end] == span text`. Every person here is fictional.

Run `python seed_tools.py validate DIR` on any directory of files you produce before sharing it (default `data/seed`). Apostrophes are normalized to `’` by the parser.

## v2 changes (Nov 17)

- spans: added **`owner`**, the entity id of the person the span tells you something about (needed for person-level "fully protected" and deanonymization risk). Tag field 8. Defaults if omitted: PERSON span → its own entity; span with an `attr` → `E1`; otherwise null. Set it explicitly for other facts about a person (their РНОКПП, phone, employer, loan amount…).
- spans: added **`edrsr_type`** (`ОСОБА` / `АДРЕСА` / `НОМЕР` / `ІНФОРМАЦІЯ` / null), *derived by rule* in `seed_tools.edrsr_type()`, never tagged by hand: what the court registry would mask. Case numbers → null; emails and URLs → ІНФОРМАЦІЯ; birth dates and years → ІНФОРМАЦІЯ; DI addresses → АДРЕСА; other codes → НОМЕР.
- new condition **`gold_edrsr_policy`**: mask exactly the spans with an `edrsr_type`, i.e. registry-style masking.
- validator now also rejects leftover `[[`/`]]`, tags with more than 7 fields, owners that are not PERSON entities in the doc, and registry-masked spans with no owner.
- files live in `data/seed/` (seed) and `data/sample/`, `data/full/` (generated).

## Fields beyond the base format

These fields are needed to generate documents and to compute k-anonymity:

- `population.csv`: added `first_name`, `patronymic`, `surname`, `settlement` (name of the place), `children`.
- `gold_docs.jsonl`: added `target_entity_id` (always `E1`) and `doc_year` (needed to turn "34 роки" into a birth year).
- spans: added `name_part` (to support the "patronymic left unmasked" condition) and `attr` (which population column a QI reveals, used by oracle k-anonymity).
- `masked_spans` entries are `{start, end, placeholder}`, with offsets in the **original** gold text.

## 1. `population.csv` (owner: data understanding)

| column | values |
|---|---|
| person_id | `P0001`… |
| first_name, patronymic, surname | Ukrainian forms, matched to gender (`-енко`/`-чук` invariant, `-ський`→`-ська`) |
| gender | `F` / `M` |
| birth_year | int |
| oblast | e.g. `Полтавська` |
| settlement | e.g. `Вербівка` |
| settlement_type | `city` / `town` / `village` |
| occupation | Ukrainian label, masculine/standard form (`вчитель хімії`) |
| family_status | `married` / `single` / `divorced` / `widowed` |
| children | int |
| event | `<type>_<year>` or empty; types: `award_teacher_of_year`, `court_wage_claim`, `court_loan_claim`, `grant_farm`, `dismissal` |

Extra columns may follow these. The generated population (`data_understanding/population.py`) adds `surname_type`: `chuk` (-чук/-юк/-ук), `enko` (-енко), `skyi` (-ський/-цький), `adj` (-ий/-а), `yshyn` (-ишин) or `other`. It sets how the surname inflects.

Next to it, `targets.csv` lists the people documents are written about: `person_id`, `genre` (court/news/forum), `event`, and `lookalikes` (space-separated ids of people with the same gender, birth year, oblast and occupation).

P0001–P0005 are the seed-document targets. P0006–P0008 are deliberate near-duplicates of P0001–P0003 (same gender, birth year, oblast, settlement type and occupation), so coarse QI tuples give k = 2 and you can check the uniqueness code on them.

## 2. `gold_docs.jsonl` (owner: data understanding)

One JSON object per line:

```json
{"doc_id": "D001", "person_id": "P0001", "target_entity_id": "E1", "genre": "news|court|forum",
 "doc_year": 2024, "text": "...", "spans": [ ... ]}
```

Span:

| field | values |
|---|---|
| start, end, text | offsets into `text`; spans are sorted and never overlap (an outer span wins, e.g. `ФГ «Ліщинчук і син»` is one ORG span) |
| category | `PERSON` `CODE` `LOC` `ORG` `DEM` `DATETIME` `QUANTITY` `MISC` (TAB categories) |
| id_type | `DI` (direct) / `QI` (quasi) |
| entity_id | `E1` = target; same id = same real-world thing, across all its inflected forms |
| case | `nom` `gen` `dat` `acc` `ins` `loc` `voc` or null (invariant tokens, dates, codes) |
| name_part | PERSON only: `first` `patronymic` `surname` `initials` `diminutive` |
| attr | population column the span reveals, or null |
| owner | entity id of the person this span is about, or null (see v2 changes) |
| edrsr_type | derived: `ОСОБА` `АДРЕСА` `НОМЕР` `ІНФОРМАЦІЯ` or null |

A name is split into parts (`Ковальчинського` + `Тараса` + `Петровича` = three spans, same entity). Maskers merge adjacent parts of the same entity into one placeholder.

**How data understanding produces this:** write tagged text, then run `parse_tagged()`. Tag syntax:
`[[surface|CATEGORY|ID_TYPE|ENTITY|case|name_part|attr|owner]]`. Trailing fields are optional and `-` means null. See `seed_docs.py`, and use the same syntax in the LLM generation prompt.

## 3. `masked_docs.jsonl` (owner: model training; read by data understanding and evaluation)

```json
{"doc_id": "D001", "system_or_condition": "gold_full", "masked_text": "...",
 "masked_spans": [{"start": 7, "end": 15, "placeholder": "МІСЦЕ_1"}]}
```

- Placeholders follow the ЄДРСР style: `ОСОБА_n`, `КОД_n`, `МІСЦЕ_n`, `ОРГАНІЗАЦІЯ_n`, `ДАТА_n`, `ЧИСЛО_n`, `ІНФОРМАЦІЯ_n` (DEM and MISC). The same entity gets the same placeholder throughout a document.
- `system_or_condition` names: `gold_full`, `gold_di_only`, `gold_edrsr_policy`, `gold_miss_one_oblique` `gold_drop_p05`… `gold_drop_p40`, `gold_keep_patronymic` (all in the seed, from `model_training/conditions.py`); then `rule`, `spacy`, `llm`.
- Drop-out leaves whole mentions unmasked, and the dropped sets are nested (p05 ⊂ p10 ⊂ p20 ⊂ p40). Extra random runs are named `gold_drop_p05_s1`…
- Condition rows also carry `n_unmasked_gold`: how many gold spans were deliberately left open. `0` on anything other than `gold_full` means the condition changed nothing for that doc (e.g. no mention was drawn at 5%), so exclude it from per-condition comparisons if needed.
- `llm` rows also carry `llm_status`: `ok`, `retry` (the first answer was empty or not valid JSON; a retry without thinking worked), `salvaged` (only complete mentions from a cut-off answer) or `failed`. A `failed` row masks nothing and also has `llm_failed: true`: exclude it from LLM results. Extra fields like these can be ignored by readers that don't need them.
- Systems don't know entity ids, so they only need start/end/placeholder. Entity-level recall is computed by data understanding against gold.

`apply_masking()` and `gold_conditions()` in `seed_tools.py` show the reference behaviour. Model training can extend them for the drop-out conditions.

## 4. `candidates.jsonl` (owner: evaluation)

```json
{"doc_id": "D101", "design": "balanced", "n": 10, "candidates": ["P0458", "P0013", "..."]}
```

One row per (document, design, n), with n = 10 and 100, in the order shown to the attacker. Every masker and condition of a document is attacked with the same lists. A list always contains the target and all their look-alikes; target positions are spread evenly over the corpus. `evaluation/README.md` explains the two designs, `balanced` and `random`. Not available for `data/seed/`, which has no `targets.csv`.

## 5. `attacks/{reid,nodoc,attr}.jsonl` (owner: evaluation)

```json
{"doc_id": "D101", "system_or_condition": "rule", "design": "balanced", "n": 10,
 "model": "...", "prompt_version": "attack_reid_v1", "prompt_hash": "01b3d04a9d961a07",
 "ranking": ["P1516", "P0458", null, "P0013", "P0027"], "target_rank": 4,
 "clues": "...", "parse_ok": true, "errors": [], "attempts": 1, "usage": {"prompt": 1391, "completion": 40}}
```

- One row per call; `doc_id`, `system_or_condition`, `design`, `n`, `model` and `prompt_version` identify it. `system_or_condition` is null for `nodoc`; `design` and `n` are null for `attr`. The condition `unmasked` is the original text.
- `ranking` holds up to five people, most likely first; null is a label that was not in the list. `target_rank` is 1–5, or null when the target is not among them. `attr` rows have `values` (`gender`, `birth_decade`, `oblast`, `occupation`) instead; a value can be `"unknown"`, or null when the answer was missing or not allowed.
- `parse_ok` is false when no attempt gave a usable answer. Such rows count as misses.
- `prompt_hash` changes with the masked text, the candidate list or the prompt, so a stale row can be recognised.

## What each seed document exercises

| doc | genre | target | Ukrainian-specific cases |
|---|---|---|---|
| D001 | news | P0001 | acc. name, first name + patronymic, `сама`/`вчителька` gender leak, QI combination (village + only chemistry teacher + award) |
| D002 | court | P0002 | surname-first legal order, gen./dat. forms, initials, РНОКПП, address, case number |
| D003 | court | P0003 | invariant `-енко` surname in gen., adjectival surname (`Вигаданий`→`Вигаданого`), `позивачка`/`пояснила` |
| D004 | news | P0004 | diminutive in ins. (`Андрійком`), surname inside an ORG name, age as adjective |
| D005 | forum | P0005 | diminutive `Сашко`, vocative `Олександре`, Russian-form name, transliterated email |
